"""TD-03 milestone transitions and real Context popup interactions."""
from threading import Event

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from roifile import ImagejRoi
from test_analysis_pipeline import spin
from test_desktop_research import create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import AdapterOutput

KEYS = ('image', 'analysis', 'result', 'viewer', 'roi')
pytest_plugins = ('test_toolbar',)


def choose(w, key):
    w.select('contextSwitcher', 'contextChoice' + str(KEYS.index(key)))
    assert w.panel.property('requestedContext') == key
    assert w.panel.property('lastReason') == 'MANUAL'
    assert w.item('viewerMouseArea').property('activeFocus')


class LifecycleAdapter(ManyCandidates):
    def __init__(self, mode='success'):
        super().__init__()
        self.mode = mode
        self.entered, self.release, self.returned = Event(), Event(), Event()

    def analyze_source(self, request, token):
        self.entered.set()
        try:
            assert self.release.wait(10), 'Test gate was not released'
            if self.mode == 'error':
                raise RuntimeError('test-only inference failure')
            if self.mode == 'empty':
                return AdapterOutput((), {'counts': {'BPD': 0, 'TED': 0, 'TSD': 0}}, {})
            # Deliberately noncooperative: the existing pipeline must reject
            # late results after cancel/new file/close without moving Context.
            return super().analyze_source(request, token)
        finally:
            self.returned.set()


def begin(w, mode='success'):
    adapter = LifecycleAdapter(mode)
    w.bridge.pipeline.adapter = adapter
    w.open(create_source(w.path.parent).path)
    w.state.setProperty('analysisScope', 'FULL_IMAGE')
    choose(w, 'analysis')
    w.click('contextRunAnalysis')
    spin(w.app, adapter.entered.is_set)
    assert w.bridge.analysis['state'] == 'RUNNING'
    assert w.panel.property('requestedContext') == 'analysis'
    assert not w.item('contextRunAnalysis').property('enabled')
    assert w.item('contextCancelAnalysis').property('visible')
    return adapter


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_manual_navigation_keyboard_focus_and_panel_bounds(workbench, size):
    w = workbench
    w.window.resize(*size)
    QTest.qWait(35)
    assert w.panel.property('requestedContext') == 'image'
    for key in KEYS:
        choose(w, key)
        QTest.qWait(35)
        assert w.panel.property('width') == (380 if key == 'result' else 282)
        assert w.item('centralWorkspace').property('width') >= 536
        if key == 'analysis':
            execute = w.item('contextRunAnalysis')
            point = execute.mapToScene(QPointF())
            assert 0 <= point.y() and point.y() + execute.property('height') <= size[1] - 28
        for name in ('contextHeader', 'contextSwitcher', 'contextSubtitle'):
            item = w.item(name)
            point = item.mapToScene(QPointF())
            assert 0 <= point.x() < size[0] and 0 <= point.y() < size[1]
            assert point.x() + item.property('width') <= size[0]
        w.click('contextSwitcher')
        current = w.item('contextChoice' + str(KEYS.index(key)))
        assert current.property('checked')
        w.click(current.objectName())  # Reselecting never clears active state.
        assert current.property('checked')
        assert w.item('viewerMouseArea').property('activeFocus')
    w.click('contextSwitcher')
    assert w.item('contextMenu').property('currentIndex') == -1
    QTest.keyClick(w.window, Qt.Key_Down)
    QTest.keyClick(w.window, Qt.Key_Down)
    QTest.keyClick(w.window, Qt.Key_Return)
    QTest.qWait(35)
    assert w.panel.property('requestedContext') == 'analysis'
    assert w.item('viewerMouseArea').property('activeFocus')
    w.click('contextSwitcher')
    QTest.keyClick(w.window, Qt.Key_Escape)
    QTest.qWait(35)
    assert w.panel.property('requestedContext') == 'analysis'
    assert w.item('viewerMouseArea').property('activeFocus')


def test_open_close_jpeg_and_explicit_stack_settings(workbench, tmp_path):
    w = workbench
    assert w.panel.property('lastReason') == 'OPEN_IMAGE'
    w.select('advancedToolGroup', 'toolbarViewerSettings')
    assert w.panel.property('requestedContext') == 'viewer'
    assert w.panel.property('lastReason') == 'VIEWER_SETTINGS'
    assert w.item('pageSlider').property('visible')
    choose(w, 'result')
    w.bridge.requestPage(1)
    spin(w.app, lambda: w.state.property('pageIndex') == 1 and not w.state.property('pageLoading'))
    assert w.panel.property('requestedContext') == 'result'
    choose(w, 'analysis')
    w.bridge.requestPage(2)
    spin(w.app, lambda: w.state.property('pageIndex') == 2 and not w.state.property('pageLoading'))
    assert w.panel.property('requestedContext') == 'analysis'
    choose(w, 'result')
    jpg = tmp_path / 'new.jpg'
    Image.fromarray(np.zeros((512, 512, 3), np.uint8)).save(jpg)
    invoke(w.window, 'selectImagePath', str(jpg))
    assert w.state.property('loading')
    assert w.panel.property('requestedContext') == 'result'  # Loading/progress is not OPEN_IMAGE.
    spin(w.app, lambda: w.state.property('imageFormat') == 'JPEG' and not w.state.property('loading'))
    assert w.panel.property('requestedContext') == 'image'
    assert w.state.property('imageFormat') == 'JPEG'
    assert not w.state.property('stackFeaturesVisible')
    assert not w.item('measurementToolDropdown').property('enabled')
    assert w.item('analysisSettings') is not None
    choose(w, 'result')
    assert w.item('resultLifecycleMessage').property('text') == '아직 분석 결과가 없습니다.'
    invoke(w.window, 'closeImage')
    assert w.panel.property('activeContext') == 'idle'
    assert w.panel.property('lastReason') == 'CLOSE_IMAGE'
    assert not w.bridge.research.state['selected']
    assert not w.bridge.analysis['hasResult']


@pytest.mark.parametrize('mode', ['success', 'empty', 'error', 'cancel'])
def test_analysis_terminal_milestones_and_empty_states(workbench, mode):
    w = workbench
    adapter = begin(w, mode)
    try:
        # A user may inspect another Context while a job runs. Merely
        # refreshing a RUNNING snapshot must not steal it back.
        choose(w, 'image')
        w.bridge.analysisChanged.emit()
        w.app.processEvents()
        assert w.panel.property('requestedContext') == 'image'
        if mode == 'cancel':
            choose(w, 'analysis')
            w.click('contextCancelAnalysis')
            assert w.panel.property('requestedContext') == 'analysis'
            assert w.panel.property('lastReason') == 'ANALYSIS_CANCELED'
        adapter.release.set()
        spin(w.app, lambda: w.bridge.analysis['state'] != 'RUNNING')
        spin(w.app, adapter.returned.is_set)
        if mode in ('success', 'empty'):
            assert w.panel.property('requestedContext') == 'result'
            assert w.panel.property('lastReason') == 'ANALYSIS_COMPLETE'
            w.click('contextSwitcher')
            assert w.item('contextChoice2').property('checked')
            QTest.keyClick(w.window, Qt.Key_Escape)
            QTest.qWait(35)
            assert w.panel.property('resultPhase') == ('list' if mode == 'success' else 'zero')
            assert w.item('resultLifecycleMessage').property('text') == (
                '후보 231개 · 검토할 후보를 선택하세요.' if mode == 'success'
                else '분석이 완료되었지만 후보가 없습니다.')
            choose(w, 'roi')
            w.click('contextSwitcher')
            assert w.item('contextChoice4').property('checked')
            assert not w.item('contextChoice2').property('checked')
            QTest.keyClick(w.window, Qt.Key_Escape)
            QTest.qWait(35)
            w.bridge.analysisChanged.emit()  # Same completed ID/ROI snapshot.
            w.bridge.setCurrentRoi(True, 10, 10, 50, 50)
            w.app.processEvents()
            assert w.panel.property('requestedContext') == 'roi'
        else:
            assert w.panel.property('requestedContext') == 'analysis'
            assert not w.bridge.analysis['hasResult']
            assert not w.bridge.research.state['selected']
            assert w.panel.property('lastReason') == ('ANALYSIS_FAILED' if mode == 'error' else 'ANALYSIS_CANCELED')
            assert not w.item('contextCancelAnalysis').property('visible')
    finally:
        adapter.release.set()


@pytest.mark.parametrize('action', ['new-file', 'close'])
def test_late_analysis_does_not_restore_old_result_context(workbench, tmp_path, action):
    w = workbench
    adapter = begin(w)
    try:
        if action == 'new-file':
            jpg = tmp_path / 'replacement.jpg'
            Image.fromarray(np.zeros((64, 64, 3), np.uint8)).save(jpg)
            w.open(jpg)
            assert w.panel.property('requestedContext') == 'image'
        else:
            invoke(w.window, 'closeImage')
            assert w.panel.property('activeContext') == 'idle'
        adapter.release.set()
        spin(w.app, adapter.returned.is_set)
        spin(w.app, lambda: not w.bridge.pipeline._tasks)
        assert w.panel.property('requestedContext') == 'image'
        assert not w.bridge.analysis['hasResult']
        assert w.bridge.research.state['total'] == 0
        assert not w.bridge.research.state['selected']
    finally:
        adapter.release.set()


def test_candidate_selection_hover_pan_zoom_and_status_preserve_context(workbench):
    w = workbench
    adapter = begin(w)
    adapter.release.set()
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    choose(w, 'image')
    viewer, mouse, frame = w.item('imageViewer'), w.item('viewerMouseArea'), w.item('imageFrame')
    point = mouse.mapToScene(QPointF(frame.property('x') + 80 * viewer.property('displayScale'),
                                    frame.property('y') + 80 * viewer.property('displayScale'))).toPoint()
    QTest.mouseMove(w.window, point)
    w.app.processEvents()
    assert w.panel.property('requestedContext') == 'image'
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, point)
    spin(w.app, lambda: bool(w.bridge.research.state['selected']))
    assert w.panel.property('requestedContext') == 'result'
    assert w.panel.property('detailContext') == 'candidate'
    assert w.panel.property('lastReason') == 'CANDIDATE_SELECTED'
    selected = w.bridge.research.state['selected']['id']
    for tool in ('toolbarPan', 'toolbarZoom', 'toolbarFit'):
        w.click(tool)
        assert w.panel.property('requestedContext') == 'result'
    w.state.setProperty('statusText', 'test pixel/status update')
    w.bridge.analysisChanged.emit()
    QTest.mouseMove(w.window, QPoint(200, 180))
    w.app.processEvents()
    assert w.panel.property('requestedContext') == 'result'
    assert w.bridge.research.state['selected']['id'] == selected
    choose(w, 'image')
    w.bridge.research.selectCandidate(selected)
    assert w.panel.property('requestedContext') == 'result'


def test_roi_tools_manager_import_edit_and_whitelist(workbench, tmp_path):
    w = workbench
    choose(w, 'result')
    w.click('roiToolDropdown')
    assert w.panel.property('requestedContext') == 'result'
    QTest.mouseMove(w.window, w.item('toolRectangle').mapToScene(QPointF(40, 12)).toPoint())
    assert w.panel.property('requestedContext') == 'result'
    w.click('toolRectangle')
    assert w.panel.property('requestedContext') == 'result'
    QTest.keyClick(w.window, Qt.Key_R)
    assert w.panel.property('requestedContext') == 'result'
    w.state.setProperty('hasRoi', True)
    w.state.setProperty('roiEndX', .25)
    w.state.setProperty('roiEndY', .25)
    invoke(w.item('advancedRoiManagerAction'), 'trigger')
    assert w.panel.property('lastReason') == 'ROI_MANAGER_OPEN'
    assert '128 × 128' in w.item('analysisRoiState').property('text')
    path = tmp_path / 'generated.roi'
    ImagejRoi.frompoints([[40, 50], [100, 120], [160, 80]]).tofile(path)
    choose(w, 'image')
    assert w.bridge.importRois([w.bridge.localUrl(str(path))])
    spin(w.app, lambda: not w.bridge.roiState['busy'])
    assert w.panel.property('lastReason') == 'ROI_IMPORT'
    assert w.panel.property('requestedContext') == 'roi'
    assert 'ImageJ ROI 1개' in w.item('imagejRoiState').property('text')
    assert w.state.property('hasRoi')  # Import did not replace the analysis range.
    invoke(w.item('advancedEditRoiAction'), 'trigger')
    assert w.panel.property('lastReason') == 'ROI_EDIT'
    assert w.state.property('roiEditMode')
    assert '편집 모드' in w.item('imagejRoiState').property('text')
    for reason in ('PAN', 'ZOOM', 'HOVER', 'PAGE_CHANGED', 'STATUS', 'REDRAW', 'PIXEL_READ', 'LOADING_PROGRESS'):
        invoke(w.item('contextState'), 'requestContext', 'viewer', reason)
        assert w.panel.property('requestedContext') == 'roi'
        assert w.panel.property('lastReason') == 'ROI_EDIT'
