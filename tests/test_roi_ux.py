"""TD-06 ROI lifecycle, real Viewer input and unchanged record semantics."""
import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from roifile import ImagejRoi
from test_analysis_flow import prepare, set_scope
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_result_ux import analyzed
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.imaging.imagej_roi import load_rois

pytest_plugins = ('test_toolbar',)


def flow(w, key):
    return w.item('roiFlowState').property(key)


def scene(w, x, y):
    viewer, frame = w.item('imageViewer'), w.item('imageFrame')
    scale = viewer.property('displayScale')
    return w.item('viewerMouseArea').mapToScene(QPointF(frame.property('x') + x*scale,
                                                     frame.property('y') + y*scale)).toPoint()


def draw(w, start=(128, 128), end=(384, 384), check=None):
    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, *start))
    QTest.mouseMove(w.window, scene(w, *end), 20)
    if check:
        check()
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, *end))
    QTest.qWait(40)


def imported(w, name='generated'):
    path = w.path.parent / (name + '.roi')
    ImagejRoi.frompoints(np.array([[40, 50], [100, 120], [160, 80]], dtype=np.float32)).tofile(path)
    assert w.bridge.importRois([w.bridge.localUrl(str(path))])
    spin(w.app, lambda: not w.bridge.roiState['busy'])
    QTest.qWait(40)
    return path


def test_no_image_and_empty_area_are_normal_states(workbench):
    w = workbench
    choose(w, 'roi')
    assert flow(w, 'areaPhase') == 'NONE' and flow(w, 'imagejPhase') == 'EMPTY'
    assert '전체 이미지 분석' in w.item('analysisAreaHint').property('text')
    assert w.item('roiSpecifyArea').property('enabled')
    assert not w.item('roiEditButton').property('enabled')
    w.same_action('roiSpecifyArea', 'toolAnalysisRoi')
    invoke(w.window, 'closeImage')
    choose(w, 'roi')
    assert flow(w, 'areaPhase') == 'DISABLED'
    assert w.item('roiToolHint').property('text') == '이미지를 먼저 여세요.'
    assert not w.item('roiSpecifyArea').property('enabled')
    assert not w.item('importRoisButton').property('enabled')


@pytest.mark.parametrize('context', ['analysis', 'roi'])
def test_analysis_area_drawing_ready_replace_remove_and_shared_action(workbench, context):
    w = workbench
    adapter = prepare(w)
    try:
        set_scope(w, 'ROI')
        choose(w, context)
        w.same_action('roiSpecifyArea', 'analysisSpecifyArea')
        w.click('roiSpecifyArea' if context == 'roi' else 'analysisSpecifyArea')
        assert w.item('viewerMouseArea').property('activeFocus')
        draw(w, check=lambda: (assert_drawing(w, context)))
        assert flow(w, 'areaPhase') == 'READY'
        assert w.panel.property('requestedContext') == context
        assert w.state.property('roiX') == pytest.approx(128, abs=1)
        assert w.state.property('roiY') == pytest.approx(128, abs=1)
        assert w.state.property('roiWidth') == pytest.approx(256, abs=1)
        assert w.state.property('roiHeight') == pytest.approx(256, abs=1)
        assert w.state.property('canAnalyze')
        roi = w.bridge.pipeline.current_roi
        assert (roi.x, roi.y, roi.width, roi.height) == tuple(w.state.property(k) for k in ('roiX', 'roiY', 'roiWidth', 'roiHeight'))
        choose(w, 'roi')
        w.click('roiSpecifyArea')
        assert w.state.property('hasRoi')  # R alone keeps previous area.
        QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 40, 40))
        assert not w.state.property('hasRoi')  # Replacement begins on press.
        QTest.mouseMove(w.window, scene(w, 100, 100), 20)
        QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 100, 100))
        QTest.qWait(40)
        assert flow(w, 'areaPhase') == 'READY'
        w.click('roiRemoveArea')
        assert flow(w, 'areaPhase') == 'NONE' and not w.state.property('canAnalyze')
        assert not w.bridge.roiState['items']
        choose(w, 'analysis'); set_scope(w, 'FULL_IMAGE')
        assert w.state.property('canAnalyze')
    finally:
        adapter.release.set()


def assert_drawing(w, context):
    assert flow(w, 'areaPhase') == 'DRAWING'
    assert w.item('analysisRoiState').property('text') == '분석 영역 지정 중'
    assert 'Esc' not in w.item('analysisAreaHint').property('text')
    assert w.panel.property('requestedContext') == context


def test_running_locks_area_actions_without_locking_pan_zoom(workbench):
    w = workbench
    adapter = prepare(w)
    try:
        set_scope(w, 'ROI'); w.click('analysisSpecifyArea'); draw(w)
        w.click('contextRunAnalysis'); spin(w.app, adapter.entered.is_set)
        choose(w, 'roi')
        before = w.bridge.pipeline.current_roi
        assert flow(w, 'areaPhase') == 'LOCKED'
        assert not w.item('roiSpecifyArea').property('enabled')
        assert not w.item('roiRemoveArea').property('enabled')
        draw(w, (40, 40), (100, 100))
        assert w.bridge.pipeline.current_roi == before
        w.click('toolbarPan'); w.click('toolbarZoom'); w.click('toolbarFit')
        assert w.panel.property('requestedContext') == 'roi'
    finally:
        w.bridge.pipeline.cancel(); adapter.release.set()
        spin(w.app, lambda: not w.bridge.pipeline._tasks)


@pytest.mark.parametrize('tool,menu,style,points', [
    ('Rectangle', 'toolRectangle', 'drag', 4), ('Oval', 'toolOval', 'drag', 128),
    ('Freehand', 'toolFreehand', 'drag', 3), ('Polygon', 'toolPolygon', 'vertices', 3),
    ('Line', 'measurementLine', 'drag', 2), ('Polyline', 'measurementPolyline', 'vertices', 3),
    ('Angle', 'measurementAngle', 'angle', 3), ('Point', 'toolPoint', 'point', 1),
])
def test_shape_lifecycle_count_selection_geometry_and_context(workbench, tool, menu, style, points):
    w = workbench
    choose(w, 'roi')
    button = 'roiToolDropdown' if menu.startswith('tool') else 'measurementToolDropdown'
    w.select(button, menu)
    assert flow(w, 'imagejPhase') == 'EMPTY'  # Selecting a tool is not drawing.
    assert w.panel.property('requestedContext') == 'roi'
    assert tool in w.item('viewerToolMode').property('text')
    if style == 'drag':
        QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 40, 40))
        QTest.mouseMove(w.window, scene(w, 70, 45), 10)
        assert flow(w, 'imagejPhase') == 'DRAWING'
        QTest.mouseMove(w.window, scene(w, 100, 100), 10)
        QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 100, 100))
    elif style in ('vertices', 'angle'):
        QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 40, 40))
        assert flow(w, 'imagejPhase') == 'DRAWING'
        for xy in ((100, 40), (100, 100)):
            QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, *xy))
        if style == 'vertices':
            QTest.keyClick(w.window, Qt.Key_Return)
    else:
        QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 40, 40))
    QTest.qWait(40)
    assert flow(w, 'count') == 1 and flow(w, 'imagejPhase') == 'SELECTED'
    record = w.bridge.roi_manager.records[0]
    assert record.tool == tool and record.page_index == 0
    assert len(record.paths[0]) == points
    assert record.paths[0][0][0] == pytest.approx(40 if tool != 'Oval' else 100, abs=1)
    assert not w.state.property('hasRoi')  # No implicit analysis-area conversion.
    assert w.panel.property('requestedContext') == 'roi'
    if tool == 'Point':
        QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 100, 100))
        assert flow(w, 'count') == 1 and len(w.bridge.roi_manager.records[0].paths[0]) == 2


@pytest.mark.parametrize('end', ['escape', 'pan', 'zoom', 'roi', 'page'])
def test_unfinished_polygon_does_not_leak_across_mode_or_page(workbench, end):
    w = workbench
    choose(w, 'image'); w.select('roiToolDropdown', 'toolPolygon')
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 40, 40))
    assert flow(w, 'isDrawing')
    if end == 'escape':
        QTest.keyClick(w.window, Qt.Key_Escape)
    elif end == 'pan':
        QTest.keyClick(w.window, Qt.Key_H)
    elif end == 'zoom':
        w.click('toolbarZoom')
    elif end == 'roi':
        w.select('roiToolDropdown', 'toolRectangle')
    else:
        w.bridge.requestPage(1); spin(w.app, lambda: w.state.property('pageIndex') == 1)
    assert not flow(w, 'isDrawing')
    assert w.item('imageViewer').property('toolPoints').toVariant() == []
    assert not w.bridge.roiState['items']
    assert w.panel.property('requestedContext') == 'image'


def test_import_cancel_error_selection_edit_and_copy_serialization(workbench):
    w = workbench
    choose(w, 'roi'); w.click('importRoisButton')
    assert w.item('roiFileDialog').property('visible')
    invoke(w.item('roiFileDialog'), 'reject'); QTest.qWait(40)
    assert not w.bridge.roiState['errors'] and flow(w, 'imagejPhase') == 'EMPTY'
    path = imported(w)
    original_bytes = path.read_bytes()
    imported(w, 'second')
    assert flow(w, 'count') == 2
    w.click('roiRecord0')
    selected_id = w.bridge.roiState['items'][0]['id']
    assert w.bridge.roi_manager.selected == selected_id
    assert w.item('importedRoiOverlay').property('rois')[0]['selected']
    w.click('roiManagerButton')
    assert w.panel.property('lastReason') == 'ROI_MANAGER_OPEN'
    assert w.bridge.roi_manager.selected == selected_id
    w.click('roiEditButton')
    assert flow(w, 'imagejPhase') == 'EDITING'
    QTest.qWait(60)
    assert w.item('viewerMouseArea').property('activeFocus')
    assert not w.item('toolbarPan').property('checked')
    assert not w.item('toolPolygon').property('checked')
    w.same_action('roiEditButton', 'roiEditModeCheck')
    w.click('roiEditButton')
    assert flow(w, 'imagejPhase') == 'SELECTED'
    w.click('roiEditorDetails')
    assert w.item('roiEditorDialog').property('visible')
    w.item('roiPointXField').setProperty('text', '150.5')
    w.item('roiPointYField').setProperty('text', '160.25')
    invoke(w.item('applyRoiPointButton'), 'clicked')
    assert w.bridge.roi_manager.records[0].paths[0][0] == (150.5, 160.25)
    invoke(w.item('roiEditorDialog'), 'reject'); QTest.qWait(40)
    saved = []
    w.bridge.roiSaved.connect(saved.append)
    target = w.path.parent / 'EditedRoiSet.zip'
    w.bridge.saveRoiCopy(w.bridge.localUrl(str(target)))
    spin(w.app, lambda: bool(saved))
    records, errors = load_rois([target], w.bridge.original_source.metadata)
    assert not errors and len(records) == 2
    assert records[0].paths == w.bridge.roi_manager.records[0].paths
    assert path.read_bytes() == original_bytes
    w.click('roiRemoveRecord0')
    assert flow(w, 'imagejPhase') == 'AVAILABLE' and flow(w, 'count') == 1
    bad = w.path.parent / 'bad.roi'; bad.write_bytes(b'invalid')
    w.bridge.importRois([w.bridge.localUrl(str(bad))])
    assert flow(w, 'imagejPhase') == 'IMPORTING'
    spin(w.app, lambda: not w.bridge.roiState['busy'])
    assert flow(w, 'imagejPhase') == 'ERROR'
    assert 'traceback' not in w.item('roiErrorSummary').property('text').lower()
    assert w.bridge.roiState['errors'][0] not in w.item('roiErrorSummary').property('text')
    w.click('roiErrorDetails'); assert w.item('roiErrorDialog').property('visible')
    invoke(w.item('roiErrorDialog'), 'reject')


def test_page_scope_visibility_and_new_image_reset(workbench):
    w = workbench
    choose(w, 'roi'); w.select('roiToolDropdown', 'toolRectangle'); draw(w)
    page_roi_id = w.bridge.roi_manager.selected
    imported(w)  # Imported polygon without a page tag is image-wide.
    w.click('roiSpecifyArea'); draw(w)
    w.bridge.requestPage(1); spin(w.app, lambda: w.state.property('pageIndex') == 1)
    assert flow(w, 'areaPhase') == 'NONE'
    assert len(w.bridge.roiState['items']) == 2
    assert not w.bridge.roiState['items'][0]['active'] and w.bridge.roiState['items'][1]['active']
    w.bridge.selectImportedRoi(page_roi_id); QTest.qWait(40)
    assert not w.item('roiEditButton').property('enabled')
    w.bridge.requestPage(0); spin(w.app, lambda: w.state.property('pageIndex') == 0)
    assert w.item('roiEditButton').property('enabled')
    w.click('roiVisible0'); assert not w.item('roiEditButton').property('enabled')
    w.click('roiVisible0'); w.click('roiEditButton')
    # Existing discard confirmation is retained on opening a new source.
    invoke(w.window, 'selectImagePath', str(w.path))
    invoke(w.item('roiDiscardDialog'), 'discarded')
    invoke(w.item('roiDiscardDialog'), 'close')
    spin(w.app, lambda: not w.state.property('loading') and not w.bridge.roiState['items'])
    assert not w.bridge.roiState['items'] and not w.bridge.roi_manager.selected
    assert not w.state.property('roiEditMode') and not w.state.property('hasRoi')
    assert w.panel.property('requestedContext') == 'image'


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_fixed_roi_status_selection_and_actions_in_bounds(workbench, size):
    w = workbench
    w.window.resize(*size); QTest.qWait(40); choose(w, 'roi')
    imported(w)
    for name in ('analysisRoiState', 'roiSpecifyArea', 'imagejRoiState', 'selectedRoiSummary',
                 'importRoisButton', 'roiManagerButton', 'roiEditButton', 'roiRecordList', 'roiSaveEntry'):
        item = w.item(name); p = item.mapToScene(QPointF())
        assert item.property('visible'), name
        assert 0 <= p.y() and p.y() + item.property('height') <= size[1] - 28, (name, p)
        assert p.x() + item.property('width') <= size[0], (name, p)
    assert w.panel.property('width') == 282
    assert w.item('roiRecordList').property('height') >= 60


def test_result_selection_filter_and_analysis_area_survive_imagej_management(workbench):
    w = workbench
    r = analyzed(w)
    w.click('resultFilterBPD'); w.click('nextCandidate')
    before = w.bridge.pipeline.result
    candidate = r.state['selected']['id']
    area = w.bridge.pipeline.current_roi
    imported(w)
    w.click('roiEditButton'); w.click('roiEditButton')
    assert r.state['filterKind'] == 'BPD' and r.state['selected']['id'] == candidate
    assert w.bridge.pipeline.result is before and w.bridge.pipeline.current_roi == area
    assert w.state.property('candidateRoiId') == candidate
    w.click('roiRemoveRecord0'); assert not w.bridge.roiState['items']
    assert r.state['selected']['id'] == candidate and w.bridge.pipeline.result is before


def test_wand_uses_existing_async_imagej_bridge(workbench):
    w = workbench
    choose(w, 'roi'); w.select('roiToolDropdown', 'toolWand')
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, scene(w, 80, 80))
    spin(w.app, lambda: not w.bridge.imagej.state['busy'])
    assert not w.bridge.imagej.state['error']
    assert flow(w, 'count') == 1 and flow(w, 'imagejPhase') == 'SELECTED'
    assert w.bridge.roi_manager.records[0].tool == 'Polygon'  # Existing wand result record representation.
    assert w.panel.property('requestedContext') == 'roi'
    assert not w.state.property('hasRoi')
