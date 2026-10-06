"""TD-04 single-screen preparation, real ROI gestures and Run lifecycle."""
from dataclasses import replace

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QPointF, Qt
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import LifecycleAdapter, choose
from test_desktop_research import create_source
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
    assert w.panel.property('requestedContext') == 'analysis'
    assert not adapter.entered.is_set()  # Navigation never starts inference.
    return adapter


def set_scope(w, scope):
    combo = w.item('analysisScopeCombo')
    index = {'': 0, 'FULL_IMAGE': 1, 'ROI': 2}[scope]
    combo.setProperty('currentIndex', index)
    assert QMetaObject.invokeMethod(combo, 'activated', Q_ARG('int', index))
    QTest.qWait(35)
    assert w.state.property('analysisScope') == scope


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
    choose(w, 'analysis')
    if case == 'no-image':
        invoke(w.window, 'closeImage')
        choose(w, 'analysis')
        w.bridge.pipeline.adapter = None
        w.bridge.pipeline.invalidate()
    elif case == 'no-model':
        w.bridge.pipeline.adapter = None
        w.bridge.pipeline.invalidate()
        assert w.item('researchModelButton').property('enabled')
        w.click('researchModelButton')
        assert w.item('researchModelDialog').property('visible')
        invoke(w.item('researchModelDialog'), 'reject')
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
    assert not w.item('contextRunAnalysis').property('enabled')
    assert not w.state.property('canAnalyze')
    assert reason in w.item('analysisReadinessReasons').property('text')
    assert w.item('analysisLifecycleState').property('text') == '분석 준비 필요'
    if case == 'no-image':
        assert '연구 모델을 연결' in w.item('analysisReadinessReasons').property('text')


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_primary_settings_and_one_click_full_image_run(workbench, size):
    w = workbench
    w.window.resize(*size)
    adapter = prepare(w)
    try:
        assert w.state.property('analysisScope') == 'FULL_IMAGE'
        assert not w.state.property('hasRoi')
        assert w.item('analysisLifecycleState').property('text') == '분석 준비 완료'
        assert not w.item('analysisSettingsScroll').property('visible')
        for name in ('researchModelStatus', 'analysisScopeCombo', 'analysisAreaSummary',
                     'analysisLifecycleState', 'contextRunAnalysis'):
            obj = w.item(name)
            point = obj.mapToScene(QPointF())
            assert obj.property('visible') and 0 <= point.y()
            assert point.y() + obj.property('height') <= size[1] - 28, name
        w.click('contextModelInfo')
        assert w.panel.property('requestedContext') == 'analysis'
        assert w.item('infoDialog').property('visible')
        assert adapter.model_version in w.item('infoDialog').property('bodyText')
        invoke(w.item('infoDialog'), 'close')
        w.click('contextRunAnalysis')  # Only Run; no scope/confirmation step.
        spin(w.app, adapter.entered.is_set)
        assert len(adapter.requests) == 1
        assert adapter.requests[0].scope == AnalysisScope.FULL_IMAGE
        assert adapter.requests[0].roi is None
        adapter.release.set()
        spin(w.app, lambda: w.bridge.analysis['hasResult'])
        assert w.panel.property('requestedContext') == 'result'
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
        assert not w.state.property('hasRoi') and not w.item('contextRunAnalysis').property('enabled')
        w.same_action('analysisSpecifyArea', 'toolAnalysisRoi')
        w.click('analysisSpecifyArea')
        assert w.item('viewerMouseArea').property('activeFocus')
        assert w.panel.property('requestedContext') == 'analysis'
        drag_area(w)
        assert w.state.property('hasRoi')
        selected = tuple(w.state.property(key) for key in ('roiX', 'roiY', 'roiWidth', 'roiHeight'))
        assert all(abs(actual - expected) <= 1 for actual, expected in zip(selected, (128, 128, 256, 256)))
        assert f'{selected[2]} × {selected[3]}' in w.item('analysisAreaSummary').property('text')
        assert w.item('contextRunAnalysis').property('enabled')
        assert w.panel.property('requestedContext') == 'analysis'
        w.click('contextRunAnalysis')
        spin(w.app, adapter.entered.is_set)
        request = adapter.requests[0]
        assert (request.roi.x, request.roi.y, request.roi.width, request.roi.height) == selected
        assert not w.item('analysisSpecifyArea').property('enabled')
        assert not w.item('clearRoiAction').property('enabled')
        drag_area(w, (40, 40), (120, 120))  # Already-active R cannot mutate the running range.
        assert tuple(w.state.property(key) for key in ('roiX', 'roiY', 'roiWidth', 'roiHeight')) == selected
        w.click('contextCancelAnalysis')
        adapter.release.set()
        spin(w.app, lambda: not w.bridge.pipeline._tasks)
        assert w.state.property('analysisScope') == 'ROI' and w.state.property('roiWidth') == selected[2]
        assert w.item('analysisSpecifyArea').property('enabled')
    finally:
        adapter.release.set()


@pytest.mark.parametrize('mode', ['success', 'empty', 'error', 'cancel'])
def test_running_settings_lock_cancel_error_and_retry(workbench, mode):
    w = workbench
    adapter = prepare(w, mode)
    try:
        w.click('analysisAdvancedToggle')
        assert w.item('analysisSettingsScroll').property('visible')
        w.click('contextRunAnalysis')
        spin(w.app, adapter.entered.is_set)
        for name in ('researchModelButton', 'analysisScopeCombo', 'analysisPointModeCombo', 'roiAction'):
            assert not w.item(name).property('enabled'), name
        assert not w.item('contextRunAnalysis').property('enabled')
        QTest.qWait(35)
        for name in ('contextRunAnalysis', 'contextCancelAnalysis'):
            button = w.item(name)
            point = button.mapToScene(QPointF())
            assert point.y() + button.property('height') <= w.window.height() - 28
        invoke(w.item('runAction'), 'trigger')  # Disabled shared Action cannot enqueue a duplicate.
        assert len(adapter.requests) == 1
        for name in ('toolbarPan', 'toolbarZoom', 'toolbarFit'):
            w.click(name)
            assert w.panel.property('requestedContext') == 'analysis'
        if mode == 'cancel':
            w.click('contextCancelAnalysis')
        adapter.release.set()
        spin(w.app, lambda: not w.bridge.pipeline._tasks)
        if mode in ('success', 'empty'):
            assert w.panel.property('requestedContext') == 'result'
            assert w.panel.property('resultPhase') == ('list' if mode == 'success' else 'zero')
        else:
            assert w.panel.property('requestedContext') == 'analysis'
            assert not w.bridge.analysis['hasResult']
            assert w.item('contextRunAnalysis').property('text') == '다시 분석'
            assert w.item('contextRunAnalysis').property('enabled')
            assert w.state.property('analysisScope') == 'FULL_IMAGE'
            assert w.state.property('analysisPointMode') == 'contrast_proposals'
            if mode == 'error':
                assert w.bridge.analysis['errorMessage'] in w.item('analysisReadinessReasons').property('text')
                assert 'test-only inference failure' not in w.item('analysisReadinessReasons').property('text')
            w.click('contextRunAnalysis')
            spin(w.app, lambda: len(adapter.requests) == 2 and not w.bridge.pipeline._tasks)
    finally:
        adapter.release.set()


def test_advanced_input_and_model_details_preserve_parameters(workbench, tmp_path):
    w = workbench
    adapter = prepare(w)
    try:
        w.click('analysisInputInfo')
        assert w.item('infoDialog').property('visible')
        invoke(w.item('infoDialog'), 'close')
        w.click('analysisAdvancedToggle')
        combo = w.item('analysisPointModeCombo')
        combo.setProperty('currentIndex', 1)
        assert QMetaObject.invokeMethod(combo, 'activated', Q_ARG('int', 1))
        csv = tmp_path / 'points.csv'
        csv.write_text('point_id,x,y\np1,256,256\n', encoding='utf-8')
        w.bridge.research.setCoordinates(str(csv))
        w.click('analysisAdvancedToggle')
        assert not w.item('analysisSettingsScroll').property('visible')
        w.click('contextRunAnalysis')
        spin(w.app, adapter.entered.is_set)
        assert adapter.requests[0].parameters['point_mode'] == 'provided_coordinates'
        assert len(adapter.requests[0].parameters['points']) == 1
    finally:
        adapter.release.set()


def test_only_supported_scopes_and_invalid_scope_explanation(workbench):
    w = workbench
    w.bridge.pipeline.adapter.input_contract = replace(w.bridge.pipeline.adapter.input_contract,
                                                      supported_scopes=(AnalysisScope.ROI,))
    w.bridge.pipeline.invalidate()
    choose(w, 'analysis')
    assert w.item('analysisScopeCombo').property('count') == 2  # Placeholder and the one actual scope.
    assert not w.item('contextRunAnalysis').property('enabled')
    assert '지원하지' in w.item('analysisReadinessReasons').property('text')
    w.state.setProperty('analysisScope', 'ROI')
    assert '영역을 지정' in w.item('analysisReadinessReasons').property('text')


def test_new_image_keeps_settings_and_requires_a_new_area(workbench, tmp_path):
    w = workbench
    adapter = prepare(w)
    try:
        w.click('contextRunAnalysis')
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
        assert not w.item('contextRunAnalysis').property('enabled')
        assert '영역을 지정' in w.item('analysisReadinessReasons').property('text')
        set_scope(w, 'FULL_IMAGE')
        assert w.item('contextRunAnalysis').property('enabled')
    finally:
        adapter.release.set()
