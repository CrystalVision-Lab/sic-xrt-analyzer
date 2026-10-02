import json
import time
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.dataset_review import (
    ReviewBridge,
    ReviewImageProvider,
    ReviewStore,
    sha,
)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def manifest(root):
    write(root/'output_hashes.json', {p.name: sha(p) for p in root.iterdir() if p.is_file() and p.name != 'output_hashes.json'})


@pytest.fixture
def inputs(tmp_path):
    raw, registry, workspace, candidates = [tmp_path/n for n in ('raw', 'registry', 'workspace', 'candidates')]
    for p in (raw, registry, workspace, candidates):
        p.mkdir()
    tifffile.imwrite(raw/'source.tif', np.full((64,64), 128, np.uint8))
    file = {'asset_id':'img', 'area_id':'1', 'sha256':sha(raw/'source.tif'), 'suffix':'.tif',
            'source_kind':'file', 'kind':'image', 'locator':'source.tif'}
    (registry/'assets.jsonl').write_text(json.dumps(file)+'\n')
    manifest(registry)
    write(workspace/'workspace.json', {'schema':'annotation_workspace', 'schema_version':2,
        'registry_root':str(registry), 'registry_manifest_sha256':sha(registry/'output_hashes.json'),
        'source_root':str(raw), 'summary':{'requested_reviewer_name':'양희승'}})
    (workspace/'images.jsonl').write_text(json.dumps(file)+'\n')
    point = {'point_id':'pt', 'image_asset_id':'img', 'area_id':'1', 'phase':'before', 'x':20.25, 'y':30.5, 'fine_label':'TED_a'}
    (workspace/'provider_points.jsonl').write_text(json.dumps(point)+'\n')
    manifest(workspace)
    write(candidates/'candidate_summary.json', {'schema':'candidate_workbench', 'schema_version':1,
                                               'workspace_manifest_sha256':sha(workspace/'output_hashes.json')})
    cand = {'candidate_id':'cand', 'image_asset_id':'img', 'area_id':'1', 'phase':'after', 'x':40.0, 'y':40.0}
    (candidates/'candidates_2d.jsonl').write_text(json.dumps(cand)+'\n')
    (candidates/'candidates_3d.jsonl').write_text('')
    manifest(candidates)
    return raw, workspace, candidates, tmp_path/'session'


def test_point_review_records_are_append_only_and_restart_restores_latest(inputs):
    raw, a, b, session = inputs
    before = sha(raw/'source.tif')
    store = ReviewStore(a,b,session)
    assert store.rows()['total'] == 2
    with pytest.raises(ValueError, match='직접 확인'):
        store.save('pt','confirm','TED_a','합성 검수자',False)
    with pytest.raises(ValueError, match='실제로 확인'):
        store.save('pt','confirm','TED_a','Codex_AI',True)
    with pytest.raises(ValueError, match='다른 종류'):
        store.save('pt','confirm','TSD_b','합성 검수자',True)
    first = store.save('pt','confirm','TED_a','합성 검수자',True)
    second = store.save('pt','hold','TED_a','합성 검수자',False,'다시 확인')
    assert second['previous_event_sha256'] == first['event_sha256']
    restored = ReviewStore(a,b,session)
    assert len(restored.events) == 2 and restored.latest['pt']['decision'] == 'hold'
    assert restored.rows(state='unreviewed')['total'] == 1
    assert sha(raw/'source.tif') == before


def test_native_crop_and_marker_use_original_grid_and_changed_source_is_rejected(inputs):
    raw,a,b,session = inputs
    store = ReviewStore(a,b,session)
    image = store.crop('pt')
    assert image.width() == image.height() == 64
    assert image.pixelColor(20,30).red() == 128
    marker = store.crop('pt', marked=True)
    assert marker.pixelColor(20,30).red() == 244
    (raw/'source.tif').write_bytes(b'changed')
    with pytest.raises(ValueError, match='바뀌었습니다'):
        store.crop('pt')


def test_changed_input_or_review_log_is_rejected(inputs):
    _,a,b,session = inputs
    store = ReviewStore(a,b,session)
    (session/'decisions.jsonl').write_text('{}\n')
    with pytest.raises(ValueError, match='다른 창'):
        store.save('pt','hold','TED_a','합성 검수자',False)
    (a/'provider_points.jsonl').write_text('changed')
    with pytest.raises(ValueError, match='해시'):
        ReviewStore(a,b,session)


def test_two_windows_cannot_append_conflicting_history(inputs):
    _,a,b,session = inputs
    first, second = ReviewStore(a,b,session), ReviewStore(a,b,session)
    (session/'.write.lock').write_bytes(b'')
    with pytest.raises(ValueError, match='저장 중'):
        first.save('pt','hold','TED_a','합성 검수자',False)
    (session/'.write.lock').unlink()
    first.save('pt','hold','TED_a','합성 검수자',False)
    with pytest.raises(ValueError, match='다른 창'):
        second.save('cand','correct','BPD','합성 검수자',True)
    assert len(ReviewStore(a,b,session).events) == 1
    assert not (session/'.write.lock').exists()


def test_review_window_loads_native_patches_and_has_no_automatic_approval(inputs, qt_app):
    _,a,b,session = inputs
    store = ReviewStore(a,b,session)
    bridge = ReviewBridge(store)
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('reviewBridge', bridge)
    engine.rootContext().setContextProperty('reviewSessionPath', str(session))
    engine.addImageProvider('review', ReviewImageProvider(store,bridge))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/DatasetReview.qml')))
    assert engine.rootObjects()
    window = engine.rootObjects()[0]
    deadline = time.monotonic()+10
    while time.monotonic()<deadline and not (window.property('rawReady') and window.property('markedReady')):
        qt_app.processEvents()
        QTest.qWait(20)
    assert window.property('rawReady') and window.property('markedReady')
    assert not window.property('cropFailed')
    assert not store.events
    window.close()
    engine.deleteLater()
