import copy
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.feedback import (
    apply_event,
    new_session,
    validate_session,
)
from sic_xrt_analyzer.ui.bridge import FileBridge


def session():
    data = new_session({'file_path': 'fixture.tif', 'sha256': 'a'*64, 'width': 512, 'height': 512,
                        'page_index': 0, 'coordinate_space': 'raw_pixel_xy', 'orientation': 'encoded_no_exif_rotation'})
    data['wafer_id'] = '1'
    return data


ORIGINAL = {'candidate_id': 'c1', 'x': 100., 'y': 100., 'predicted_type': 'TSD',
            'analysis_id': 'run1', 'model_sha256': 'b'*64, 'model_id': 'fixture'}


def test_independent_masks_original_history_unknown_and_undo():
    data = apply_event(session(), 'r1', ORIGINAL, 'confirm', 'test reviewer')
    assert data['events'][-1]['target']['label'] is None
    assert not data['events'][-1]['target']['location_confirmed']
    data = apply_event(data, 'r1', ORIGINAL, 'type', 'test reviewer', label='TED')
    data = apply_event(data, 'r1', ORIGINAL, 'location', 'test reviewer', x=105., y=99.)
    data = apply_event(data, 'r1', ORIGINAL, 'background', 'test reviewer')
    data = apply_event(data, 'r1', ORIGINAL, 'undo', 'test reviewer')
    assert data['events'][-1]['target'] == {'x': 105., 'y': 99., 'objectness': True, 'label': 'TED', 'location_confirmed': True, 'duplicate_of': None}
    data = apply_event(data, 'r1', ORIGINAL, 'type_unknown', 'test reviewer')
    assert data['events'][-1]['target']['objectness'] is True
    assert data['events'][-1]['target']['label'] is None
    assert data['events'][-1]['original'] == ORIGINAL
    validate_session(data)
    altered = copy.deepcopy(data)
    altered['events'][0]['target']['label'] = 'TSD'
    with pytest.raises(ValueError, match='이력'):
        validate_session(altered)


def test_missing_metadata_defer_duplicates_and_invalid_coordinate():
    with pytest.raises(ValueError, match='먼저'):
        apply_event(new_session(session()['source']), 'r', ORIGINAL, 'confirm', 'test reviewer')
    data = apply_event(session(), 'r1', ORIGINAL, 'type', 'test reviewer', label='BPD')
    data = apply_event(data, 'r1', ORIGINAL, 'defer', 'test reviewer')
    assert data['events'][-1]['target']['objectness'] is None
    data = apply_event(data, 'r1', ORIGINAL, 'duplicate', 'test reviewer', duplicate_of='r2')
    assert data['events'][-1]['target']['duplicate_of'] == 'r2'
    for x in (float('nan'), -1, 512):
        with pytest.raises(ValueError, match='위치'):
            apply_event(data, 'r1', ORIGINAL, 'location', 'test reviewer', x=x, y=100)


def test_controller_persistence_failure_import_and_source_change(qt_app, tmp_path, bridge_factory, monkeypatch):
    settings = QSettings(str(tmp_path/'review.ini'), QSettings.IniFormat)
    bridge = bridge_factory(settings=settings)
    bridge.pipeline.adapter = ManyCandidates()
    source = create_source(tmp_path)
    bridge.pipeline.set_source(source)
    assert bridge.requestAnalysis('FULL_IMAGE', 0, 0, 0, 0, {})
    spin(qt_app, lambda: bridge.analysis['hasResult'] and bridge.feedback.state['ready'])
    f = bridge.feedback
    f.configure('test reviewer', '1')
    bridge.research.selectCandidate('candidate_000000')
    ident = f.state['selected']['id']
    assert f.state['eventsCount'] == 0
    assert f.record('confirm')
    f.setMode('location')
    assert f.place(83.5, 77.)
    assert f.state['selected']['original']['x'] == 80
    assert f.state['selected']['x'] == 83.5
    f.setMode('add')
    assert f.place(250., 250.)
    assert f.record('type', 'BPD')
    assert f.exportFeedback(str(tmp_path/'exports'))
    exported = Path(f.state['exportPath'])
    assert json.loads(exported.read_text(encoding='utf-8'))['expert_ground_truth'] is False
    assert f.importFeedback(str(exported))
    # Disk failure must leave both current labels and event count unchanged.
    f.selectRecord(ident)
    before = copy.deepcopy(f.data)
    def fail(*args):
        raise OSError('simulated disk full')
    with monkeypatch.context() as patch:
        patch.setattr('sic_xrt_analyzer.ui.feedback_controller.atomic_json', fail)
        assert not f.record('background')
    assert f.data == before
    bridge.pipeline.set_source(None)
    assert f.state['selected'] == {}
    bridge.pipeline.set_source(source)
    spin(qt_app, lambda: f.state['ready'])
    f.selectRecord(ident)
    assert f.state['selected']['x'] == 83.5
    corrupted = json.loads(exported.read_text(encoding='utf-8'))
    corrupted['source']['sha256'] = 'c'*64
    wrong = tmp_path/'wrong.json'
    wrong.write_text(json.dumps(corrupted), encoding='utf-8')
    assert not f.importFeedback(str(wrong))
    assert f.data['source']['sha256'] == before['source']['sha256']


def test_actual_qml_click_moves_adds_and_does_not_reselect_old_candidate(qt_app, tmp_path):
    QQuickStyle.setStyle('Basic')
    engine=QQmlApplicationEngine()
    bridge=FileBridge(parent=engine,settings=QSettings(str(tmp_path/'ui.ini'),QSettings.IniFormat))
    bridge.pipeline.adapter=ManyCandidates()
    engine.addImageProvider('tiff',bridge.provider)
    engine.rootContext().setContextProperty('fileBridge',bridge)
    warnings=[]
    engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window=engine.rootObjects()[0];state=window.findChild(QObject,'uiState')
    try:
        source=create_source(tmp_path)
        invoke(window,'selectImagePath',source.path)
        spin(qt_app,lambda:state.property('hasLoadedImage') and not state.property('loading') and bridge.feedback.state['ready'])
        state.setProperty('analysisScope','FULL_IMAGE')
        invoke(window.findChild(QObject,'runAction'),'trigger')
        spin(qt_app,lambda:bridge.analysis['hasResult'])
        bridge.feedback.configure('synthetic test reviewer','1')
        bridge.research.selectCandidate('candidate_000000')
        spin(qt_app,lambda:not window.findChild(QObject,'candidateFocusAnimation').property('running'))
        invoke(window,'openInspectorTab',5)
        ident=bridge.feedback.state['selected']['id']
        invoke(window.findChild(QObject,'feedbackMove'),'clicked')
        assert bridge.feedback.state['mode']=='location'
        viewer=window.findChild(QObject,'imageViewer');viewport=window.findChild(QObject,'viewerViewport');frame=window.findChild(QObject,'imageFrame')
        def click(x,y):
            scale=viewer.property('displayScale')
            point=viewport.mapToScene(QPointF(frame.property('x')+x*scale,frame.property('y')+y*scale))
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(round(point.x()),round(point.y())))
        click(86,78)
        assert bridge.feedback.state['eventsCount']==1 and bridge.feedback.state['selected']['id']==ident
        assert bridge.feedback.state['selected']['x']==pytest.approx(86,abs=1)
        spin(qt_app,lambda:not window.findChild(QObject,'candidateFocusAnimation').property('running'))
        invoke(window.findChild(QObject,'feedbackAdd'),'clicked')
        click(130,100)
        added=bridge.feedback.state['selected']['id']
        assert added != ident and bridge.feedback.state['selected']['original']['candidate_id'] is None
        assert bridge.feedback.state['eventsCount']==2
        invoke(window.findChild(QObject,'feedbackBackground'),'clicked')
        assert bridge.feedback.state['selected']['target']['objectness'] is False
        invoke(window.findChild(QObject,'feedbackUndo'),'clicked')
        assert bridge.feedback.state['selected']['target']['objectness'] is True
        assert not warnings, '\n'.join(warnings)
    finally:
        bridge.waitForLoads();window.close();engine.deleteLater();qt_app.processEvents()
