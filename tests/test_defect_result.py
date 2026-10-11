"""Source-bound import, unified selection and original-coordinate geometry rendering."""
import hashlib
import json
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_bpd_structure import settings, source_for
from test_context_panel import choose
from test_result_ux import analyzed
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.bpd_structure import detect_structures
from sic_xrt_analyzer.results import AnalysisProject
from sic_xrt_analyzer.results.bpd_experiment import (
    attach_experiment,
    comparison_image,
    save_experiment_bundle,
)
from sic_xrt_analyzer.ui.geometry_overlay import GeometryOverlay, intersects, mask_image

pytest_plugins = ('test_toolbar',)


def bundle(tmp_path, kind='y', dtype='uint16', offset=(41, 73)):
    source, roi = source_for(tmp_path, kind, dtype=dtype, offset=offset)
    experiment = detect_structures(source, roi, settings())
    project = AnalysisProject('Synthetic GUI QA')
    attached = attach_experiment(project, experiment)
    output = tmp_path / ('bundle-' + kind)
    save_experiment_bundle(output, attached, comparison_image(experiment, project, attached))
    return source, output


def load(app, controller, folder):
    controller.load(str(folder))
    spin(app, lambda: not controller.loading)


def test_normal_bundle_graph_selection_preview_and_no_inference(qt_app, tmp_path, bridge_factory):
    source, folder = bundle(tmp_path)
    before = hashlib.sha256(Path(source.path).read_bytes()).hexdigest()
    bridge = bridge_factory()
    assert bridge.openImage(QUrl.fromLocalFile(source.path).toString())['ok']
    c = bridge.experiments
    load(qt_app, c, folder)
    assert not c.error and c.state['total'] == 1
    row = c.rows[0]
    assert row['kind'] == 'BRANCHED_GRAPH' and len(row['paths']) == 3
    assert sorted(n['degree'] for n in row['nodes']) == [1, 1, 1, 3]
    assert row['bounds'][0] >= 41 and row['bounds'][1] >= 73
    c.select(row['id'])
    assert bridge.research.state['selection']['kind'] == 'DEFECT_INSTANCE'
    assert bridge.research.state['selected'] == {}
    spin(qt_app, lambda: bool(c.preview) or bool(c.preview_error))
    assert c.preview and not c.preview_error
    assert bridge.pipeline.result is None
    assert hashlib.sha256(Path(source.path).read_bytes()).hexdigest() == before
    c.unload()
    assert c.state['selected'] == {} and c.state['rows'] == []
    assert bridge.research.state['selection']['id'] == ''


@pytest.mark.parametrize('fault', ['json', 'schema', 'hash', 'missing', 'png', 'reference', 'page', 'source', 'roi_hash', 'path'])
def test_bundle_rejections_preserve_valid_snapshot(qt_app, tmp_path, bridge_factory, fault):
    source, folder = bundle(tmp_path)
    bridge = bridge_factory()
    bridge.openImage(QUrl.fromLocalFile(source.path).toString())
    c = bridge.experiments
    load(qt_app, c, folder)
    c.select(c.rows[0]['id'])
    original_rows, original_selection = c.rows, c.selected_id
    manifest_path = folder/'experiment.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    mask_path = Path(c.rows[0]['mask']['path'])
    reference = next(k for k in manifest['assets'] if (folder/k).resolve() == mask_path)
    if fault == 'json':
        manifest_path.write_text('{broken', encoding='utf-8')
    else:
        if fault == 'schema':
            manifest['schema_version'] = '100.0.0'
        elif fault == 'hash':
            manifest['assets'][reference] = '0'*64
        elif fault == 'missing':
            mask_path.unlink()
        elif fault == 'png':
            mask_path.write_bytes(b'not a PNG')
            manifest['assets'][reference] = hashlib.sha256(mask_path.read_bytes()).hexdigest()
        elif fault == 'reference':
            manifest['proposals'][0]['geometry_id'] = 'absent'
        elif fault == 'page':
            manifest['source_identity']['page_index'] = 1
        elif fault == 'source':
            manifest['source_identity']['canonical_path'] += '.other'
        elif fault == 'roi_hash':
            manifest['roi_sha256'] = '0'*64
        elif fault == 'path':
            manifest['assets']['../outside.png'] = '0'*64
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    load(qt_app, c, folder)
    assert c.error and c.rows is original_rows and c.selected_id == original_selection
    assert bridge.original_source.identity == source.identity


@pytest.mark.parametrize('change', ['cancel', 'file', 'page', 'unload'])
def test_late_load_is_invalidated(qt_app, tmp_path, bridge_factory, monkeypatch, change):
    source, folder = bundle(tmp_path)
    bridge = bridge_factory()
    bridge.openImage(QUrl.fromLocalFile(source.path).toString())
    c = bridge.experiments
    from sic_xrt_analyzer.results import bpd_experiment
    actual = bpd_experiment.load_experiment_bundle
    entered, release = Event(), Event()
    def delayed(path):
        entered.set()
        assert release.wait(10)
        return actual(path)
    monkeypatch.setattr(bpd_experiment, 'load_experiment_bundle', delayed)
    c.load(str(folder))
    spin(qt_app, entered.is_set)
    try:
        if change == 'cancel':
            c.cancel()
        elif change == 'unload':
            c.unload()
        elif change == 'file':
            other, _ = source_for(tmp_path, 'straight')
            c.bind_source(other)
        else:
            from dataclasses import replace
            from types import SimpleNamespace
            c.bind_source(SimpleNamespace(identity=replace(source.identity, page_index=1)))
        assert not c.loading
    finally:
        release.set()
    spin(qt_app, lambda: c.reader.task is None)
    assert not c.rows and not c.folder


def test_crossing_line_hit_culling_and_mask_coordinates(qt_app, tmp_path):
    _source, folder = bundle(tmp_path)
    from sic_xrt_analyzer.results.bpd_experiment import load_experiment_bundle
    from sic_xrt_analyzer.ui.experiment_controller import present_bundle
    project, manifest = load_experiment_bundle(folder)
    row = present_bundle(folder, project, manifest)[0]
    overlay = GeometryOverlay()
    overlay.setWidth(100)
    overlay.setHeight(100)
    overlay.rows = [{**row, 'paths': [[(-100, 50), (200, 50)]], 'bounds': [-100, 50, 300, 0], 'nodes': []}]
    overlay.viewTransform = [0, 0, 1]
    assert intersects([-100, 50, 300, 0], [0, 0, 100, 100])
    assert overlay.hit(50, 53, 8) == row['id']
    assert overlay.hit(50, 60, 8) == ''
    image = QImage(100, 100, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    overlay.paint(painter)
    painter.end()
    assert overlay.stats['visiblePaths'] == 1
    assert any(image.pixelColor(x, 50).alpha() for x in range(100))
    overlay.viewTransform = [0, -200, 1]
    painter = QPainter(image)
    overlay.paint(painter)
    painter.end()
    assert overlay.stats['visiblePaths'] == 0
    mask = row['mask']
    x, y, w, h = map(int, mask['bounds'])
    colored, bounds, _ = mask_image(mask, (x, y, w, h), 'fill')
    assert bounds == [x, y, w, h]
    assert (colored.width(), colored.height()) == (w, h)
    import numpy as np
    from PIL import Image
    samples = np.asarray(Image.open(mask['path']))
    for yy, xx in np.argwhere(samples != 0)[::max(1, int(np.count_nonzero(samples)/20))]:
        assert colored.pixelColor(int(xx), int(yy)).alpha() == 55
    boundary, _, _ = mask_image(mask, (x, y, w, h), 'boundary')
    assert boundary != colored
    overlay.rows = [row]
    overlay.lines = False
    overlay.highlight = False
    overlay.maskMode = 'fill'
    key = (mask['path'], mask['sha256'], (x,y,w,h), 'fill')
    overlay.keys = (key,)
    overlay.cache = {key: (colored, bounds, 0.)}
    yy, xx = np.argwhere(samples != 0)[0]
    assert overlay.hit(x+int(xx), y+int(yy), .1) == row['id']
    overlay.maskMode = 'off'
    assert overlay.hit(x+int(xx), y+int(yy), .1) == ''
    overlay.reader.shutdown()


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900), (1920, 1080)])
def test_gui_import_graph_mask_focus_and_cleanup(workbench, tmp_path, size):
    w = workbench
    source, folder = bundle(tmp_path)
    w.window.resize(*size)
    w.open(source.path)
    choose(w, 'result')
    # Exercise the real dialog's accepted signal; no native-mouse claim.
    dialog = w.item('experimentFolderDialog')
    dialog.setProperty('selectedFolder', QUrl.fromLocalFile(str(folder)))
    dialog.accepted.emit()
    spin(w.app, lambda: not w.bridge.experiments.loading)
    c = w.bridge.experiments
    assert not c.error
    w.click('browseStructures')
    w.click('structureRow1')
    spin(w.app, lambda: bool(c.preview))
    QTest.qWait(520)
    assert c.selected_id and w.state.property('hasRoi') is False
    assert w.item('geometryOverlay').property('visible')
    assert w.item('structureThumbnail').property('source').toString()
    b = c.rows[0]['bounds']
    viewer, frame = w.item('imageViewer'), w.item('imageFrame')
    scale = viewer.property('displayScale')
    # All graph bounds, not its first node, fit inside viewport after focus.
    assert frame.property('x') + b[0]*scale >= -1
    assert frame.property('y') + b[1]*scale >= -1
    for name in ('resultTotal', 'experimentStatus', 'selectedStructureHeader', 'analysisExportButton'):
        item = w.item(name)
        pos = item.mapToScene(QPointF())
        assert item.property('visible') and 0 <= pos.y() < size[1]-28, name
    w.state.setProperty('maskMode', 'fill')
    overlay = w.item('geometryOverlay')
    spin(w.app, lambda: overlay.stats['maskCount'] > 0)
    assert overlay.stats['maskBytes'] <= 32*1024**2
    w.state.setProperty('structureLayerVisible', False)
    QTest.qWait(40)
    assert overlay.stats['maskBytes'] == 0
    w.state.setProperty('structureLayerVisible', True)
    w.click('structureDetails')
    assert w.item('structureDetailDialog').property('visible')
    invoke(w.item('structureDetailDialog'), 'close')
    # uint16 retains RGB model preflight, but experiment navigation works.
    assert not w.state.property('inputCompatible')
    invoke(w.window, 'closeImage')
    assert not c.rows and not c.selected_id
    assert not overlay.property('visible')


def test_list_filter_layers_selection_and_legacy_export_are_independent(workbench, tmp_path):
    w = workbench
    r = analyzed(w)
    before = w.bridge.pipeline.result
    r.exportResult(str(tmp_path/'before'))
    original = (Path(r.export_path)/'predictions.csv').read_bytes()
    w.click('resultFilterBPD')
    w.click('resultLayers')
    w.click('bpdLayer')
    assert not w.state.property('bpdLayerVisible') and w.state.property('tedLayerVisible')
    assert r.state['filterKind'] == 'BPD' and r.state['filteredTotal'] == 245
    QTest.keyClick(w.window, Qt.Key_Escape)
    # Clicking a visible TED point is allowed even when the list shows BPD only.
    r.selectCandidate('candidate_000245')
    assert r.state['selected']['type'] == 'TED' and r.state['selectedIndex'] == -1
    assert r.state['selection']['kind'] == 'OBSERVATION'
    r.exportResult(str(tmp_path/'after'))
    assert (Path(r.export_path)/'predictions.csv').read_bytes() == original
    assert w.bridge.pipeline.result is before


def test_repeated_import_and_manual_roi_remain_separate(workbench, tmp_path):
    w = workbench
    source, folder = bundle(tmp_path)
    w.open(source.path)
    choose(w, 'result')
    c = w.bridge.experiments
    w.state.setProperty('autoCandidateRoi',False)
    for name,value in [('roiStartX',.1),('roiStartY',.2),('roiEndX',.4),('roiEndY',.5),('hasRoi',True)]:
        w.state.setProperty(name,value)
    roi = tuple(w.state.property(k) for k in ('roiStartX','roiStartY','roiEndX','roiEndY'))
    for _ in range(3):
        load(w.app,c,folder)
        assert not c.error
        c.select(c.rows[0]['id'])
        assert w.bridge.research.state['selection']['kind']=='DEFECT_INSTANCE'
        assert w.state.property('hasRoi')
        assert tuple(w.state.property(k) for k in ('roiStartX','roiStartY','roiEndX','roiEndY'))==roi
        c.unload()
        assert w.bridge.research.state['selection']['id']==''
        assert not c.rows


def test_linked_observation_requires_same_coords_score_and_model(qt_app, tmp_path, bridge_factory):
    from types import SimpleNamespace

    from test_bpd_structure import legacy_project

    from sic_xrt_analyzer.ui.experiment_controller import present_bundle
    source, roi = source_for(tmp_path,'straight')
    project = legacy_project(source,[(40,80,'BPD'),(80,80,'BPD')])
    e = detect_structures(source,roi,settings())
    attached = attach_experiment(project,e,run_id=project.analysis_runs[0].run_id)
    folder = tmp_path/'linked'
    save_experiment_bundle(folder,attached,comparison_image(e,project,attached))
    rows = present_bundle(folder,attached.project,json.loads((folder/"experiment.json").read_text(encoding="utf-8")))
    bridge = bridge_factory()
    c = bridge.experiments
    c.rows = rows
    observation = project.observations[0]
    bridge.pipeline.result = SimpleNamespace(model_version=project.analysis_runs[0].model_version)
    candidate = {'id':observation.source_candidate_id,'x':observation.x,'y':observation.y,'type':'BPD','scores':list(observation.raw_scores)}
    assert len(c.related(candidate))==1
    assert c.related({**candidate,'x':candidate['x']+1})==[]
    assert c.related({**candidate,'scores':[.1,.2,.7]})==[]
    bridge.pipeline.result = SimpleNamespace(model_version='another-model')
    assert c.related(candidate)==[]
    bridge.pipeline.result = None
