"""Opt-in Qt UI QA/capture and overlay benchmark; physical mouse acceptance is separate.

Synthetic mode creates clearly labelled generated pixels/bundles. Actual mode
requires an explicit original, approved model and TD02 bundle. All outputs stay
under the caller-specified folder; original data and inference values are read-only.
"""
import argparse
import json
import os
import platform
import time
from collections import Counter
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import numpy as np
import psutil
import tifffile
from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session, stats
from PySide6.QtCore import Q_ARG, QMetaObject, QPoint, QPointF, Qt, qVersion
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sic_xrt_analyzer.analysis.bpd_samples import synthetic_sample
from sic_xrt_analyzer.analysis.bpd_structure import StructureSettings, detect_structures
from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
    Region,
)
from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject
from sic_xrt_analyzer.results.bpd_experiment import (
    attach_experiment,
    comparison_image,
    save_experiment_bundle,
)
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def invoke(obj, name, *args):
    assert QMetaObject.invokeMethod(obj, name, *(Q_ARG('QVariant', value) for value in args))


class SyntheticClassifier:
    manifest: ClassVar = {'bundle_id': 'SYNTHETIC_UI_QA', 'model_sha256': 'a'*64}


class SyntheticAdapter(DesktopResearchAdapter):
    def __init__(self):
        super().__init__(None, SyntheticClassifier())

    def analyze_source(self, request, token):
        rows = []
        for kind, count in [('BPD', 245), ('TED', 1398), ('TSD', 1303)]:
            index = ('BPD', 'TED', 'TSD').index(kind)
            for _ in range(count):
                i = len(rows)
                score = [0.1, 0.1, 0.1]
                score[index] = 0.8
                rows.append(Detection(f'candidate_{i:06d}', index, kind, 0.8,
                    Geometry(GeometryKind.POINT, ((70+i%15*24, 70+i//15%15*24),), coordinate_space=CoordinateSpace.ORIGINAL),
                    {'scores': score, 'point_id': str(i), 'low_score': i%5 == 0}))
        return AdapterOutput(tuple(rows), {'counts': {'BPD':245,'TED':1398,'TSD':1303}}, {})


def generated(output):
    image = np.full((512,512,3), 120, np.uint8)
    image[60:220,60:220] = synthetic_sample('straight', rgb=True)
    image[280:440,280:440] = synthetic_sample('y', rgb=True)
    path = output/'SYNTHETIC_UI_QA_RGB.tif'
    tifffile.imwrite(path, image, photometric='rgb')
    source = OriginalImageSource(path)
    e = detect_structures(source, Region(32,32,448,448), StructureSettings(scales=(1,2), background_sigma=8, link_distance_px=4, method='sato', polarity='bright', low_threshold=.10, high_threshold=.25, min_area=12, min_length_px=20, max_width_px=12, min_aspect=3, contrast_floor=.005))
    p = AnalysisProject('SYNTHETIC UI QA; not scientific accuracy evidence')
    attached = attach_experiment(p, e)
    folder = output/'synthetic-bundle'
    save_experiment_bundle(folder, attached, comparison_image(e,p,attached))
    return path, folder


def export_bytes(s, output):
    assert s.bridge.research.exportResult(str(output))
    folder = Path(s.bridge.research.export_path)
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--experiment', type=Path)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--repeats', type=int, default=8)
    args = parser.parse_args()
    if args.synthetic == bool(args.image) or not 2 <= args.repeats <= 100:
        parser.error('Choose --synthetic or explicit --image/--model/--experiment; repeats 2..100')
    if not args.synthetic and not (args.model and args.experiment):
        parser.error('Actual mode requires --model and --experiment')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    # Windows offscreen has no system font database; QA-only font registration.
    # Native app/runtime styling is untouched.
    if platform.system() == "Windows" and app.platformName() == "offscreen":
        for name in ("segoeui.ttf", "malgun.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"])/"Fonts"/name))
        app.setFont(QFont("Malgun Gothic"))
    QQuickStyle.setStyle('Basic')
    s = Session.__new__(Session)
    original_paint = PreparedView.paint
    report = {'synthetic': args.synthetic, 'manual_mouse_acceptance': 'PENDING', 'cases': [], 'screenshots': [],
        'environment': {'os':platform.platform(), 'qt':qVersion(), 'platform':app.platformName(), 'scale':os.getenv('QT_SCALE_FACTOR'), 'render_loop':os.getenv('QSG_RENDER_LOOP')},
        'timing_scope': 'QTest dispatch -> Qt frameSwapped submission; not monitor FPS/input-to-photon'}
    try:
        with patch.object(PreparedView, 'paint', lambda item,painter: s.paint(original_paint,item,painter)):
            Session.__init__(s, app, args.output)
            if app.platformName() == 'windows':
                s.window.raise_()
                s.window.requestActivate()
            s.window.setTitle('XRT-RESULT-TD-03 automated QA' + (' — SYNTHETIC' if args.synthetic else ''))
            image, folder = generated(args.output) if args.synthetic else (args.image.resolve(), args.experiment.resolve())
            before = digest(image)
            report['open_s'] = s.open(image)
            report['environment'].update(dpr=s.window.devicePixelRatio(), graphics_api=str(s.window.rendererInterface().graphicsApi()))
            if args.synthetic:
                s.bridge.pipeline.adapter = SyntheticAdapter()
            else:
                s.bridge.research.loadModel(str(args.model))
                spin(app, lambda: not s.bridge.research.loading, 120)
                assert not s.bridge.research.error, s.bridge.research.error
            assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{'point_mode':'contrast_proposals'})
            spin(app, lambda: s.bridge.analysis['hasResult'], 600)
            r, c = s.bridge.research, s.bridge.experiments
            result = s.bridge.pipeline.result
            report['counts'] = dict(Counter(p['type'] for p in r.rows))
            assert report['counts'] == {'BPD':245,'TED':1398,'TSD':1303}
            baseline_export = export_bytes(s, args.output/'exports-before')
            def capture(name):
                QTest.qWait(70)
                path = args.output/(name+'.png')
                assert s.window.grabWindow().save(str(path))
                report['screenshots'].append(path.name)
            for size in [(1100,700),(1440,900),(1920,1080)]:
                s.window.resize(*size)
                invoke(s.window, 'requestContext', 'result', 'MANUAL')
                s.set_zoom(None)
                for kind in ('ALL','BPD','TED','TSD'):
                    r.setFilter(kind,False,'')
                    capture(f'{size[0]}-{kind}')
                r.stepCandidate(1)
                spin(app, lambda: bool(r.thumbnail_source), 30)
                QTest.qWait(480)
                capture(f'{size[0]}-candidate')
            c.load(str(folder))
            spin(app, lambda: not c.loading, 120)
            assert not c.error, c.error
            report['structures'] = dict(Counter(row['kind'] for row in c.rows))
            overlay = s.item('geometryOverlay')
            for size in [(1100,700),(1440,900)]:
                s.window.resize(*size)
                for kind in ('POLYLINE','BRANCHED_GRAPH'):
                    row = next((v for v in c.rows if v['kind']==kind), None)
                    if row:
                        c.select(row['id'])
                        spin(app, lambda: bool(c.preview) or bool(c.preview_error), 30)
                        QTest.qWait(520)
                        capture(f'{size[0]}-{kind}')
                s.ui.setProperty('maskMode','fill')
                spin(app, lambda: overlay.stats['maskCount']>0, 30)
                capture(f'{size[0]}-mask')
                invoke(s.item('structureDetailDialog'),'open')
                capture(f'{size[0]}-structure-detail')
                invoke(s.item('structureDetailDialog'),'close')
                s.ui.setProperty('maskMode','off')
            report['result_object_preserved'] = s.bridge.pipeline.result is result
            report['legacy_export_bytes_equal'] = export_bytes(s,args.output/'exports-after') == baseline_export
            assert report['legacy_export_bytes_equal'] and report['result_object_preserved']
            s.window.resize(1440,900)
            cx = c.manifest['roi']['x']+c.manifest['roi']['width']/2
            cy = c.manifest['roi']['y']+c.manifest['roi']['height']/2
            for zoom in (None,1.,4.):
                for mode in ('ALL','BPD','SELECTED','GEOMETRY'):
                    s.ui.setProperty('analysisLayerVisible',mode in ('ALL','BPD'))
                    for name,value in [('bpdLayerVisible',True),('tedLayerVisible',mode=='ALL'),('tsdLayerVisible',mode=='ALL'),('structureLayerVisible',mode=='GEOMETRY')]:
                        s.ui.setProperty(name,value)
                    r._clear_selection()
                    c.clear_selection()
                    r.changed.emit()
                    if mode=='SELECTED':
                        nearest=min(r.rows,key=lambda p:(p['x']-cx)**2+(p['y']-cy)**2)
                        r.selectCandidate(nearest['id'])
                    if mode=='GEOMETRY':
                        c.select(c.rows[0]['id'])
                        s.ui.setProperty('maskMode','boundary')
                    else:
                        s.ui.setProperty('maskMode','off')
                    QTest.qWait(500)
                    s.set_zoom(zoom)
                    scale=s.viewer.property('displayScale')
                    s.viewer.setProperty('panX',(s.bridge.original_source.metadata.width/2-cx)*scale)
                    s.viewer.setProperty('panY',(s.bridge.original_source.metadata.height/2-cy)*scale)
                    s.settle()
                    if mode=='GEOMETRY':
                        spin(app,lambda: not overlay.pending,30)
                    pans,zooms,point_paint,geometry_paint=[],[],[],[]
                    cpu,begin=time.process_time(),time.perf_counter()
                    for i in range(args.repeats):
                        origin=s.viewport.mapToScene(QPointF(s.viewport.width()/2,s.viewport.height()/2))
                        at=QPoint(round(origin.x()),round(origin.y()))
                        def pan(at=at, i=i):
                            QTest.mousePress(s.window,Qt.LeftButton,Qt.NoModifier,at)
                            QTest.mouseMove(s.window,at+QPoint(12 if i%2==0 else -12,6))
                            QTest.mouseRelease(s.window,Qt.LeftButton,Qt.NoModifier,at+QPoint(12 if i%2==0 else -12,6))
                        pans.append(s.command(pan))
                        point_paint.append(s.overlay.property('paintMs'))
                        geometry_paint.append(overlay.stats['paintMs'])
                        value=(zoom or s.ui.property('fitZoom'))*(1.05 if i%2==0 else 1)
                        zooms.append(s.command(lambda value=value:invoke(s.viewer,'zoomAt',value,s.viewport.width()/2,s.viewport.height()/2)))
                    row={'zoom':'FIT' if zoom is None else zoom,'mode':mode,'pan_submission_ms':stats([p['swap_ms'] for p in pans]),
                        'zoom_submission_ms':stats([p['swap_ms'] for p in zooms]),'pan_state_ms':stats([p['state_ms'] for p in pans if p['state_ms'] is not None]),
                        'point_canvas_js_ms_quantized':stats(point_paint),'geometry_paint_ms':stats(geometry_paint) if mode=='GEOMETRY' else None,
                        'rss':psutil.Process().memory_info().rss,'mask':overlay.stats,'cpu_one_core_percent':(time.process_time()-cpu)/(time.perf_counter()-begin)*100}
                    report['cases'].append(row)
                    print(json.dumps({'zoom':row['zoom'],'mode':mode,'pan_median':row['pan_submission_ms']['median'],'zoom_median':row['zoom_submission_ms']['median']},ensure_ascii=False),flush=True)
            report['sha_preserved'] = digest(image)==before
            assert report['sha_preserved']
            if args.synthetic:
                class EmptyAdapter(SyntheticAdapter):
                    def analyze_source(self, request, token):
                        return AdapterOutput((), {'counts':{'BPD':0,'TED':0,'TSD':0}}, {})
                s.bridge.pipeline.adapter = EmptyAdapter()
                assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{})
                spin(app,lambda:s.bridge.analysis['hasResult'],30)
                c.unload()
                invoke(s.viewer,'fitView')
                capture('zero-results')
            # Close clears geometry, mask cache and canonical selection; no-results screenshot.
            invoke(s.window,'closeImage')
            assert not c.rows and not r.rows
            invoke(s.window,'requestContext','result','MANUAL')
            capture('empty')
            report['qml_warnings']=s.warnings
            assert not s.warnings
            report['status']='PASS'
    finally:
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if hasattr(s,'window'):
            s.close()


if __name__=='__main__':
    main()
