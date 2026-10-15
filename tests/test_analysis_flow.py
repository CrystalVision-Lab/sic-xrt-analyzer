"""TD-04 single-screen preparation, real ROI gestures and Run lifecycle."""
from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import LifecycleAdapter, choose
from test_desktop_research import create_jpeg_source as create_source
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import AnalysisScope

pytest_plugins = ('test_toolbar',)


class CountingAdapter(LifecycleAdapter):
    def __init__(self, mode='success'):
        super().__init__(mode)
        self.requests = []

    def analyze_source(self, request, token):
        self.requests.append(request)
        return super().analyze_source(request, token)


def prepare(w, mode='success'):
    adapter = CountingAdapter(mode)
    w.bridge.pipeline.adapter = adapter
    w.open(create_source(w.path.parent).path)
    assert w.panel.property('requestedContext') == 'image'
    w.click('imagePrepareAnalysis')
    assert w.item('analysisDialog').property('visible')
    assert not adapter.entered.is_set()  # Navigation never starts inference.
    return adapter


def set_scope(w, scope):
    # Explicit state injection also covers unavailable/unsupported internal scopes.
    w.state.setProperty('analysisScope',scope)
    QTest.qWait(35)
    assert w.state.property('analysisScope')==scope


def drag_area(w, start=(128, 128), end=(384, 384)):
    mouse, frame, viewer = w.item('viewerMouseArea'), w.item('imageFrame'), w.item('imageViewer')

    def point(xy):
        scale = viewer.property('displayScale')
        return mouse.mapToScene(QPointF(frame.property('x') + xy[0] * scale,
                                      frame.property('y') + xy[1] * scale)).toPoint()

    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, point(start))
    QTest.mouseMove(w.window, point(end), 20)
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, point(end))
    QTest.qWait(35)


@pytest.mark.parametrize('case,reason', [
    ('no-image', '원본 TIFF 또는 JPG'), ('no-model', '연구 모델을 연결'),
    ('no-source', '원본이 준비되지'), ('loading', '이미지 준비'),
    ('page', '현재 페이지'), ('scope', '범위를 선택'), ('roi', '영역을 지정'),
])
def test_not_ready_reasons_follow_existing_run_gates(workbench, case, reason):
    w = workbench
    w.open(create_source(w.path.parent).path)
    choose(w, 'analysis')
    if case == 'no-image':
        invoke(w.window, 'closeImage')
        choose(w, 'analysis')
        w.bridge.pipeline.adapter = None
        w.bridge.pipeline.invalidate()
    elif case == 'no-model':
        w.bridge.pipeline.adapter = None
        w.bridge.pipeline.invalidate()
        assert not w.item('confirmAnalysis').property('enabled')
        assert not w.panel.property('visible')
    elif case == 'no-source':
        w.bridge.pipeline.set_source(None)
    elif case == 'loading':
        w.state.setProperty('opening', True)
    elif case == 'page':
        stack = dict(w.bridge.stackState)
        stack['busy'] = True
        w.state.setProperty('stack', stack)  # Test-only busy snapshot, no backend gate change.
    elif case == 'scope':
        set_scope(w, '')
    else:
        set_scope(w, 'ROI')
    assert not w.item('confirmAnalysis').property('enabled')
    assert not w.state.property('canAnalyze')
    assert w.state.property('analysisReason')
    assert not w.item('confirmAnalysis').property('enabled')
    if case == 'no-image':
        assert not w.state.property('modelAvailable')


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_primary_settings_and_one_click_full_image_run(workbench, size):
    w = workbench
    w.window.resize(*size)
    adapter = prepare(w)
    try:
        assert w.state.property('analysisScope') == 'FULL_IMAGE'
        assert not w.state.property('hasRoi')
        assert w.state.property('canAnalyze')
        assert not w.panel.property('visible')
        for name in ('analysisInputInfo', 'confirmAnalysis'):
            obj = w.item(name)
            point = obj.mapToScene(QPointF())
            assert obj.property('visible') and 0 <= point.y()
            assert point.y() + obj.property('height') <= size[1] - 28, name
        invoke(w.item('modelInfoAction'), 'trigger')
        assert not w.panel.property('visible')
        assert w.item('infoDialog').property('visible')
        assert adapter.model_version in w.item('infoDialog').property('bodyText')
        invoke(w.item('infoDialog'), 'close')
        w.click('confirmAnalysis')  # Only Run; no scope/confirmation step.
        spin(w.app, adapter.entered.is_set)
        assert len(adapter.requests) == 1
        assert adapter.requests[0].scope == AnalysisScope.FULL_IMAGE
        assert adapter.requests[0].roi is None
        adapter.release.set()
        spin(w.app, lambda: w.bridge.analysis['hasResult'])
        assert w.panel.property('requestedContext') == 'result', {k: w.state.property(k) for k in ('hasResult','filePath','analysis','workspaceIndex','loading')}
        assert not w.item('infoDialog').property('visible')
    finally:
        adapter.release.set()


def test_area_action_real_drawing_and_imagej_roi_separation(workbench):
    w = workbench
    adapter = prepare(w)
    try:
        set_scope(w, 'ROI')
        w.bridge.newPointRoi()
        assert len(w.bridge.roiState['items']) == 1
        assert not w.state.property('hasRoi') and not w.item('confirmAnalysis').property('enabled')
        invoke(w.item('analysisDialog'),'close')
        w.same_action('roiSpecifyArea', 'toolAnalysisRoi')
        invoke(w.item('roiAction'),'trigger')
        QTest.qWait(35)
        assert w.item('viewerMouseArea').property('activeFocus')
        assert not w.panel.property('visible')
        drag_area(w)
        assert w.state.property('hasRoi')
        selected = tuple(w.state.property(key) for key in ('roiX', 'roiY', 'roiWidth', 'roiHeight'))
        assert all(abs(actual - expected) <= 1 for actual, expected in zip(selected, (128, 128, 256, 256)))
        assert selected[2] > 0 and selected[3] > 0
        w.click('imagePrepareAnalysis')
        assert w.item('confirmAnalysis').property('enabled')
        assert not w.panel.property('visible')
        w.click('confirmAnalysis')
        spin(w.app, adapter.entered.is_set)
        request = adapter.requests[0]
        assert (request.roi.x, request.roi.y, request.roi.width, request.roi.height) == selected
        assert not w.item('roiAction').property('enabled')
        assert not w.item('clearRoiAction').property('enabled')
        drag_area(w, (40, 40), (120, 120))  # Already-active R cannot mutate the running range.
        assert tuple(w.state.property(key) for key in ('roiX', 'roiY', 'roiWidth', 'roiHeight')) == selected
        invoke(w.item('cancelAnalysisAction'),'trigger')
        adapter.release.set()
        spin(w.app, lambda: not w.bridge.pipeline._tasks)
        assert w.state.property('analysisScope') == 'ROI' and w.state.property('roiWidth') == selected[2]
        assert w.item('roiAction').property('enabled')
    finally:
        adapter.release.set()


@pytest.mark.parametrize('mode', ['success', 'empty', 'error', 'cancel'])
def test_running_settings_lock_cancel_error_and_retry(workbench, mode):
    w = workbench
    adapter = prepare(w, mode)
    try:
        assert w.item('analysisDialog').property('visible')
        w.click('confirmAnalysis')
        spin(w.app, adapter.entered.is_set)
        for name in ('runAction', 'roiAction'):
            assert not w.item(name).property('enabled'), name
        assert not w.item('confirmAnalysis').property('enabled')
        assert not w.item('analysisDialog').property('visible')
        assert w.item('cancelAnalysisAction').property('enabled')
        invoke(w.item('runAction'), 'trigger')  # Disabled shared Action cannot enqueue a duplicate.
        assert len(adapter.requests) == 1
        for name in ('toolbarPan', 'toolbarZoom', 'toolbarFit'):
            w.click(name)
            assert not w.panel.property('visible')
        if mode == 'cancel':
            invoke(w.item('cancelAnalysisAction'),'trigger')
        adapter.release.set()
        spin(w.app, lambda: not w.bridge.pipeline._tasks)
        if mode in ('success', 'empty'):
            assert w.panel.property('requestedContext') == 'result', {k: w.state.property(k) for k in ('hasResult','filePath','analysis','workspaceIndex','loading')}
            assert w.panel.property('resultPhase') == ('list' if mode == 'success' else 'zero')
        else:
            assert not w.panel.property('visible')
            assert not w.bridge.analysis['hasResult']
            if w.item('infoDialog').property('visible'): invoke(w.item('infoDialog'),'close')
            w.click('imagePrepareAnalysis')
            assert w.item('analysisDialog').property('visible')
            assert w.item('confirmAnalysis').property('enabled')
            assert w.state.property('analysisScope') == 'FULL_IMAGE'
            assert w.state.property('analysisPointMode') == 'contrast_proposals'
            if mode == 'error':
                assert w.bridge.analysis['errorMessage'] in w.state.property('analysisReason')
                assert 'test-only inference failure' not in w.state.property('analysisReason')
            w.click('confirmAnalysis')
            spin(w.app, lambda: len(adapter.requests) == 2 and not w.bridge.pipeline._tasks)
    finally:
        adapter.release.set()


def test_advanced_input_and_model_details_preserve_parameters(workbench, tmp_path):
    w = workbench
    adapter = prepare(w)
    try:
        w.click('analysisInputInfo')
        assert w.item('analysisDialog').property('detailsExpanded')
        assert not w.item('infoDialog').property('visible')
        assert not w.panel.property('visible')
        csv = tmp_path / 'points.csv'
        csv.write_text('point_id,x,y\np1,256,256\n', encoding='utf-8')
        w.bridge.research.setCoordinates(str(csv))
        invoke(w.item('analysisDialog'),'close')
        assert w.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{'point_mode':'provided_coordinates'})
        spin(w.app, adapter.entered.is_set)
        assert adapter.requests[0].parameters['point_mode'] == 'provided_coordinates'
        assert len(adapter.requests[0].parameters['points']) == 1
    finally:
        adapter.release.set()


def test_only_supported_scopes_and_invalid_scope_explanation(workbench):
    w = workbench
    w.open(create_source(w.path.parent).path)
    w.bridge.pipeline.adapter.input_contract = replace(w.bridge.pipeline.adapter.input_contract,
                                                      supported_scopes=(AnalysisScope.ROI,))
    w.bridge.pipeline.invalidate()
    choose(w, 'analysis')
    assert w.bridge.analysis['supportedScopes'] == ['ROI']
    assert not w.item('confirmAnalysis').property('enabled')
    assert '지원하지' in w.state.property('analysisReason')
    w.state.setProperty('analysisScope', 'ROI')
    assert 'ROI' in w.state.property('analysisReason')


def test_new_image_keeps_settings_and_requires_a_new_area(workbench, tmp_path):
    w = workbench
    adapter = prepare(w)
    try:
        w.click('confirmAnalysis')
        spin(w.app, adapter.entered.is_set)
        adapter.release.set()
        spin(w.app, lambda: w.bridge.analysis['hasResult'])
        w.bridge.research.selectCandidate('candidate_000000')
        set_scope(w, 'ROI')
        replacement = tmp_path / 'replacement'
        replacement.mkdir()
        w.open(create_source(replacement).path)
        assert w.panel.property('requestedContext') == 'image'
        assert not w.bridge.analysis['hasResult'] and not w.bridge.research.state['selected']
        w.click('imagePrepareAnalysis')
        assert w.state.property('analysisScope') == 'ROI'
        assert not w.state.property('hasRoi')
        assert not w.item('confirmAnalysis').property('enabled')
        assert 'ROI' in w.state.property('analysisReason')
        set_scope(w, 'FULL_IMAGE')
        assert w.item('confirmAnalysis').property('enabled')
    finally:
        adapter.release.set()
