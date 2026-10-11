"""Rendered usability gates: reachability, clipping, focus and logical DPI."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_desktop_research import create_source
from test_result_ux import analyzed
from test_ui_analysis_contract import invoke

pytest_plugins = ('test_toolbar',)
SIZES = [(1100, 700), (1440, 900), (1920, 1080)]


def in_window(w, name):
    node = w.item(name)
    assert node.property('visible'), name
    origin = node.mapToScene(QPointF())
    assert origin.x() >= -1 and origin.y() >= -1, name
    assert origin.x()+node.property('width') <= w.window.width()+1, name
    assert origin.y()+node.property('height') <= w.window.height()-28+1, name
    return node


def expression(w, node, code):
    exp = QQmlExpression(QQmlEngine.contextForObject(node), node, code)
    result = exp.evaluate()[0]
    assert not exp.hasError(), exp.error().toString()
    return result


@pytest.mark.parametrize('size', SIZES)
def test_shell_geometry_preserves_viewer_and_toolbar_targets(workbench, size):
    w = workbench
    w.window.resize(*size); QTest.qWait(50)
    choose(w, 'image')
    for name in ('toolbarOpen','toolbarPan','toolbarZoom','toolbarFit','roiToolDropdown','measurementToolDropdown','advancedToolGroup'):
        node = in_window(w, name)
        assert node.property('height') >= 32 and node.property('width') >= 32
    for name in ('contextSwitcher','viewerHeader','viewerFileName','viewerPageMetadata'):
        in_window(w, name)
    assert w.panel.property('width') == 282
    viewer = w.item('imageViewer')
    assert viewer.property('width') == size[0]-184-282
    assert viewer.property('height') == size[1]-98
    assert w.item('contextSwitcher').property('labelSize') >= 14
    assert w.item('viewerFileName').property('font').pixelSize() >= 13
    expected_dpr = float(os.environ.get('QT_SCALE_FACTOR','1'))
    assert w.window.devicePixelRatio() == pytest.approx(expected_dpr)


@pytest.mark.parametrize('size', SIZES)
def test_analysis_decisions_and_footer_remain_reachable(workbench, size):
    w = workbench
    w.open(create_source(w.path.parent).path)
    w.window.resize(*size); QTest.qWait(50); choose(w, 'analysis')
    for name in ('analysisModelName','researchModelButton','analysisScopeCombo','analysisLifecycleState','contextRunAnalysis'):
        in_window(w, name)
    assert w.item('analysisScopeCombo').property('height') >= 32
    assert w.item('contextRunAnalysis').property('height') >= 34
    assert w.state.property('canAnalyze')
    w.click('analysisAdvancedToggle')
    for name in ('analysisPointModeCombo','contextRunAnalysis'):
        in_window(w, name)
    w.click('contextRunAnalysis')
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    assert w.bridge.research.state['total'] == 231


@pytest.mark.parametrize('size', SIZES)
def test_result_summary_selection_and_export_in_bounds(workbench, size):
    w = workbench
    w.window.resize(*size); QTest.qWait(50)
    analyzed(w)
    w.click('resultFilterBPD'); w.click('nextCandidate')
    for name in ('resultTotal','resultFilterBPD','candidateIndex','selectedCandidateHeader','candidateConfidence','candidateList','analysisExportButton'):
        node = in_window(w, name)
        if node.inherits('QQuickText'):
            assert node.property('font').pixelSize() >= 11
    assert w.panel.property('width') == 380
    assert w.item('candidateList').property('height') >= 80
    row = w.item('candidateRow1')
    assert row.property('height') >= 36
    assert expression(w, row, 'Accessible.selected')
    assert w.bridge.research.state['selected']['type'] == 'BPD'
    original = w.bridge.pipeline.result
    w.click('candidateDetails')
    assert w.item('candidateDetailDialog').property('visible')
    invoke(w.item('candidateDetailDialog'), 'close')
    assert w.bridge.pipeline.result is original


@pytest.mark.parametrize('size', SIZES)
def test_roi_summary_edit_and_list_remain_reachable(workbench, size):
    w = workbench
    w.window.resize(*size); QTest.qWait(50); choose(w, 'roi')
    w.bridge.workbench.gesture('Polygon', [[40,40],[150,40],[150,150],[40,150]])
    w.click('roiEditButton')
    for name in ('analysisRoiState','roiSpecifyArea','imagejRoiState','selectedRoiSummary','roiEditButton','roiRecordList','roiSaveEntry'):
        in_window(w, name)
    assert w.item('roiRecordList').property('height') >= 60
    assert w.item('selectedRoiBounds').property('font').pixelSize() >= 11
    original = w.bridge.roi_manager.records[0]
    w.click('roiEditorDetails')
    dialog = w.item('roiEditorDialog')
    assert dialog.property('visible') and dialog.property('width') <= size[0]-40
    assert w.item('roiNameField').property('height') >= 32
    assert w.item('roiVertexSpin').property('height') >= 32
    invoke(dialog, 'close')
    assert w.bridge.roi_manager.records[0] == original


@pytest.mark.parametrize('size', SIZES[:2])
@pytest.mark.parametrize('button,menu', [('roiToolDropdown','toolbarRoiMenu'),('advancedToolGroup','toolbarMoreMenu')])
def test_popup_rows_fit_and_keep_keyboard_focus(workbench, size, button, menu):
    w = workbench
    w.window.resize(*size); QTest.qWait(50); w.click(button)
    popup = w.item(menu)
    assert popup.property('visible')
    content = popup.property('contentItem')
    origin = content.mapToScene(QPointF())
    assert origin.y() >= 0 and origin.y()+content.property('height') <= size[1]+1
    QTest.keyClick(w.window, Qt.Key_Down)
    QTest.keyClick(w.window, Qt.Key_Escape)
    QTest.qWait(30)
    assert not popup.property('visible')
    assert w.item(button).property('activeFocus') or w.item('viewerMouseArea').property('activeFocus')


def test_focus_hover_pressed_checked_and_disabled_feedback(workbench):
    w = workbench
    button = w.item('toolbarFit')
    button.forceActiveFocus(); QTest.qWait(20)
    assert expression(w, button, 'background.border.width') >= 1
    p = button.mapToScene(QPointF(button.property('width')/2, button.property('height')/2))
    QTest.mouseMove(w.window, p.toPoint()); QTest.qWait(20)
    assert button.property('hovered')
    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, p.toPoint())
    assert button.property('down')
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, p.toPoint())
    assert w.state.property('fitMode')
    w.click('toolbarPan')
    assert w.item('toolbarPan').property('checked')
    invoke(w.window, 'closeImage')
    assert not w.item('toolbarFit').property('enabled')
    assert w.item('toolbarFit').property('visible')


def test_long_filename_is_elided_without_changing_panel_width(workbench):
    w = workbench
    # Long enough to elide, within Linux's 255-byte filename component limit.
    path = w.path.parent/(('긴파일이름_'*14)+'.jpg')
    Image.fromarray(np.full((48,64,3),120,np.uint8)).save(path)
    w.open(path); w.window.resize(1100,700); QTest.qWait(50)
    title = in_window(w, 'viewerFileName')
    assert title.property('text') == path.name and title.property('truncated')
    assert w.item('currentFileName').property('text') == path.name
    assert w.panel.property('width') == 282
    assert w.bridge.original_source.metadata.width == 64


def test_text_contrast_and_readable_disabled_colors(workbench):
    theme = workbench.window.property('shellTheme')
    def luminance(color):
        values = [color.redF(),color.greenF(),color.blueF()]
        values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(values,[.2126,.7152,.0722]))
    background = luminance(theme.property('surface'))
    for name,minimum in [('text',7),('muted',4.5),('disabled',3)]:
        foreground = luminance(theme.property(name))
        assert (max(background,foreground)+.05)/(min(background,foreground)+.05) >= minimum


@pytest.mark.parametrize('scale', ['1.25','1.5'])
def test_logical_dpi_scaling_in_separate_qt_process(tmp_path, scale):
    env = os.environ.copy(); env['QT_SCALE_FACTOR'] = scale
    env['QT_QPA_PLATFORM'] = 'offscreen'; env['QSG_RENDER_LOOP'] = 'basic'
    result = subprocess.run([sys.executable,'-m','pytest','-q',str(Path(__file__).resolve()),
                             '-k','test_shell_geometry','--basetemp',str(tmp_path/'scaled'),
                             '-o','tmp_path_retention_policy=failed'], env=env,capture_output=True,text=True,timeout=90,check=False)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '3 passed' in result.stdout
