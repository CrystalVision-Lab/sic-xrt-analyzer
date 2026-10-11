"""Wide default viewer and explicit, reversible task-panel entry."""
import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import create_source
from test_ui_analysis_contract import invoke

pytest_plugins = ('test_toolbar',)


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_wide_default_analysis_entry_and_panel_roundtrip(workbench, size):
    w = workbench
    jpg = w.path.parent / 'wide.jpg'
    Image.fromarray(np.zeros((600, 800, 3), dtype=np.uint8)).save(jpg)
    w.open(jpg)
    w.window.resize(*size)
    QTest.qWait(50)
    viewer = w.item('imageViewer')
    assert w.window.property('inspectorCollapsed') and not w.panel.property('visible')
    wide = viewer.property('width')
    assert wide == pytest.approx(size[0] - 184)
    origin = viewer.mapToScene(QPointF())
    assert origin.x() + wide == pytest.approx(size[0])
    button = w.item('imagePrepareAnalysis')
    pos = button.mapToScene(QPointF())
    assert pos.x() > size[0] - 150
    assert pos.x() + button.property('width') <= size[0] - 5
    assert pos.y() + button.property('height') <= 70
    w.window.grabWindow().save(str(w.path.parent / 'wide-viewer.png'))
    w.select('toolbarContextTools', 'toolbarContextimage')
    assert w.panel.property('visible') and w.panel.property('requestedContext') == 'image'
    assert viewer.property('width') == pytest.approx(wide - 282)
    w.click('closeContextPanel')
    assert not w.panel.property('visible') and viewer.property('width') == pytest.approx(wide)
    assert w.item('viewerMouseArea').property('activeFocus')
    # The mock classifier accepts RGB8; uint16 stack remains navigation-only.
    w.open(create_source(w.path.parent).path)
    w.click('imagePrepareAnalysis')
    assert w.panel.property('visible') and w.panel.property('requestedContext') == 'analysis'
    assert not w.bridge.analysis['hasResult'] and not w.state.property('analysisRunning')
    w.window.grabWindow().save(str(w.path.parent / 'analysis-panel.png'))
    w.state.setProperty('analysisScope', 'FULL_IMAGE')
    w.click('contextRunAnalysis')
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    assert w.panel.property('visible') and w.panel.property('requestedContext') == 'result'
    QTest.qWait(50)  # Let the wider result-panel layout reach its displayed geometry.
    result = w.bridge.pipeline.result
    w.click('closeContextPanel')
    assert viewer.property('width') == pytest.approx(wide)
    w.select('toolbarContextTools', 'toolbarContextresult')
    assert w.bridge.pipeline.result is result and w.panel.property('visible')
    invoke(w.window, 'resetLayout')
    QTest.qWait(35)
    assert not w.panel.property('visible') and viewer.property('width') == pytest.approx(wide)
    invoke(w.window, 'closeImage')
    assert not w.panel.property('visible') and not button.property('enabled')


def test_stack_and_roi_task_access_when_default_panel_is_hidden(workbench):
    w = workbench
    w.select('toolbarContextTools', 'toolbarContextviewer')
    assert w.panel.property('visible') and w.item('pageSlider').property('visible')
    w.click('closeContextPanel')
    w.bridge.requestPage(1)
    spin(w.app, lambda: w.state.property('pageIndex') == 1 and not w.state.property('pageLoading'))
    assert not w.panel.property('visible')
    w.select('toolbarContextTools', 'toolbarContextroi')
    w.bridge.workbench.gesture('Polygon', [[40, 40], [150, 40], [150, 150]])
    record = w.bridge.roi_manager.records[0]
    w.click('closeContextPanel')
    w.select('toolbarContextTools', 'toolbarContextroi')
    assert w.bridge.roi_manager.records[0] == record
    invoke(w.window, 'selectImagePath', str(w.path))
    assert w.item('roiDiscardDialog').property('visible')
    invoke(w.item('roiDiscardDialog'), 'discarded')
    invoke(w.item('roiDiscardDialog'), 'close')
    spin(w.app, lambda: not w.state.property('loading') and not w.bridge.stack_viewer.initial_loading)
    assert w.panel.property('visible') and w.panel.property('requestedContext') == 'viewer'
