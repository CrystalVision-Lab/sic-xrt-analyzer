"""Feedback branch integration with current Context and viewer contracts."""
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_result_explorer import ManyCandidates
from test_result_ux import analyzed
from test_ui_analysis_contract import invoke

pytest_plugins = ('test_toolbar',)


def test_result_review_entry_and_context_exit_preserve_original_result(workbench):
    w = workbench
    analyzed(w, ManyCandidates())
    spin(w.app, lambda: w.bridge.feedback.state['ready'])
    original = w.bridge.pipeline.result
    w.click('nextCandidate')
    spin(w.app, lambda: not w.item('candidateFocusAnimation').property('running'))
    w.click('reviewSelectedCandidate')
    assert w.panel.property('requestedContext') == 'feedback'
    assert w.panel.property('lastReason') == 'REVIEW_REQUESTED'
    assert w.item('contextSwitcher').property('text') == '검수 ▾'
    assert w.state.property('feedbackVisible')
    assert w.bridge.feedback.state['eventsCount'] == 0
    # The newly integrated pickers use the existing lifecycle facade.
    for name in ('feedbackImportDialog', 'feedbackExportDialog'):
        picker = w.item(name)
        assert picker.property('managedNative') == w.bridge.nativeDialogs.enabled
        assert not picker.property('visible')
    w.bridge.feedback.configure('synthetic test reviewer', '1')
    w.bridge.feedback.setMode('add')
    assert w.bridge.feedback.state['mode'] == 'add'
    invoke(w.window, 'openContext', 'image')
    assert not w.state.property('feedbackVisible')
    assert w.bridge.feedback.state['mode'] == ''
    assert w.bridge.feedback.state['eventsCount'] == 0
    assert w.bridge.pipeline.result is original
    assert not w.warnings, w.warnings


def test_hidden_feedback_overlay_skips_geometry_and_repaints_on_entry(workbench):
    w = workbench
    analyzed(w, ManyCandidates())
    original = w.bridge.pipeline.result
    overlay = w.item('feedbackOverlay')
    setup = QQmlExpression(w.engine.rootContext(), overlay, '''(function() {
        var list = []; list.reads = 0;
        list.push(Object.defineProperty({y:80, objectness:true}, "x", {
            get: function() { list.reads++; return 80; }
        }));
        review = {overlay:list, selected:{}};
    })()''')
    setup.evaluate()
    assert not setup.hasError(), setup.error().toString()
    def reads():
        expr = QQmlExpression(w.engine.rootContext(), overlay, 'review.overlay.reads')
        value = expr.evaluate()[0]
        assert not expr.hasError(), expr.error().toString()
        return value
    for offset in [15., 30., 0.]:
        w.item('imageViewer').setProperty('panX', offset)
        w.window.grabWindow()
        QTest.qWait(20)
    assert reads() == 0
    invoke(w.window, 'openContext', 'feedback')
    w.window.grabWindow()
    spin(w.app, lambda: reads() > 0)
    assert w.bridge.pipeline.result is original
    assert not w.warnings, w.warnings
