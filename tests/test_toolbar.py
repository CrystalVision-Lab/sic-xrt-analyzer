"""Real popup selection, Viewer gestures and shared commands after TD-02."""
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import create_jpeg_source as create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.ui.bridge import TiffImageProvider


@pytest.fixture
def workbench(qt_app, tmp_path, bridge_factory):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = bridge_factory(provider=provider, settings=QSettings(str(tmp_path/'toolbar.ini'), QSettings.IniFormat))
    bridge.pipeline.adapter = ManyCandidates()
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    assert len(engine.rootObjects()) == 1, warnings
    window = engine.rootObjects()[0]

    class Workbench:
        def item(self, name):
            obj = window.findChild(QObject, name)
            if obj is not None:
                return obj
            pending = [window.contentItem()]
            # Closed menus detach their visual item from the window overlay.
            for popup in window.findChildren(QObject):
                if popup.inherits('QQuickPopup'):
                    content = popup.property('contentItem')
                    if content is not None:
                        pending.append(content)
            while pending:
                node = pending.pop()
                if node.objectName() == name:
                    return node
                pending.extend(node.childItems())
            raise AssertionError(name)

        def click(self, name):
            obj = self.item(name)
            assert obj.property('visible') and obj.property('enabled'), name
            point = obj.mapToScene(QPointF(obj.property('width')/2, obj.property('height')/2))
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name, point)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
            QTest.qWait(30)

        def select(self, button, menu_item):
            self.click(button)
            self.click(menu_item)

        def open(self, path):
            spin(qt_app, lambda: not bridge.projects.busy)
            invoke(window, 'selectImagePath', str(path))
            try:
                spin(qt_app, lambda: self.state.property('hasLoadedImage') and Path(self.state.property('filePath')) == Path(path) and not self.state.property('loading') and not bridge.stack_viewer.initial_loading)
            except AssertionError as exc:
                raise AssertionError({'target':str(path),'current':self.state.property('filePath'),'opening':self.state.property('opening'),'reviewPending':bridge.reviews.state['pending'],'roiDirty':bridge.roi_manager.dirty,'loadError':self.state.property('loadError'),'stackError':bridge.stack_viewer.error}) from exc
            window.grabWindow()  # Settle the actual layout after format/width changes.

        def same_action(self, left, right):
            engine.rootContext().setContextProperty('leftCommandItem', self.item(left))
            engine.rootContext().setContextProperty('rightCommandItem', self.item(right))
            expr = QQmlExpression(engine.rootContext(), window, 'leftCommandItem.action === rightCommandItem.action')
            assert expr.evaluate()[0] is True
            assert not expr.hasError()

    w = Workbench()
    w.window, w.bridge, w.engine, w.warnings, w.app = window, bridge, engine, warnings, qt_app
    w.state = w.item('uiState')
    w.panel = w.item('inspectorPanel')
    w.path = tmp_path/'generated-stack.tif'
    tifffile.imwrite(w.path, np.arange(3*512*512, dtype=np.uint16).reshape(3, 512, 512), photometric='minisblack')
    w.open(w.path)
    yield w
    window.setProperty('allowQuit', True)
    window.close()
    bridge.waitForLoads()
    engine.deleteLater()
    assert not warnings, warnings


def test_dropdown_gestures_exclusive_state_and_focus(workbench):
    w = workbench
    mouse, frame, viewer = w.item('viewerMouseArea'), w.item('imageFrame'), w.item('imageViewer')

    def at(x, y):
        scale = viewer.property('displayScale')
        p = mouse.mapToScene(QPointF(frame.property('x') + x*scale, frame.property('y') + y*scale))
        return QPoint(round(p.x()), round(p.y()))

    cases = [(tool, None if tool in ('Rectangle','Oval','Polygon','Freehand','Point','Line','Polyline') else 'tiffMore',
              'tiffTool'+tool if tool in ('Rectangle','Oval','Polygon','Freehand','Point','Line','Polyline') else 'tiffMore'+tool,
              gesture) for tool, gesture in [('Rectangle','drag'),('Oval','drag'),('Polygon','vertices'),
              ('Freehand','drag'),('Point','point'),('Line','drag'),('Polyline','vertices'),
              ('FreeLine','drag'),('Angle','angle'),('Text','point'),('Arrow','drag')]]
    for tool, button, menu_item, gesture in cases:
        count = len(w.bridge.roi_manager.records)
        context = w.panel.property('tabIndex')
        w.select(button, menu_item) if button else w.click(menu_item)
        assert w.state.property('activeTool') == tool
        assert not w.state.property('roiEditMode')
        assert w.panel.property('tabIndex') == context
        assert mouse.property('activeFocus')  # Enter/arrows work after the popup closes.
        assert w.item(menu_item).property('checked')
        if button:
            indicator = w.item(menu_item).property('indicator')
            assert indicator.x() + indicator.width() <= w.item(menu_item).property('leftPadding')
        assert not w.item('toolbarPan').property('checked')
        assert not w.item('toolbarZoom').property('checked')
        # Selecting an already active action must not uncheck it.
        w.select(button, menu_item) if button else w.click(menu_item)
        assert w.item(menu_item).property('checked') and w.state.property('activeTool') == tool
        if gesture == 'drag':
            QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, at(40, 40))
            QTest.mouseMove(w.window, at(70, 45), 10)
            QTest.mouseMove(w.window, at(100, 100), 10)
            QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, at(100, 100))
        elif gesture in ('vertices', 'angle'):
            for xy in ((40, 40), (100, 40), (100, 100)):
                QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, at(*xy))
            if gesture == 'vertices':
                QTest.keyClick(w.window, Qt.Key_Return)
        else:
            QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, at(50, 50))
        assert len(w.bridge.roi_manager.records) == count + 1, tool
        assert w.bridge.roi_manager.records[-1].tool == tool
        QTest.keyClick(w.window, Qt.Key_H)
        assert w.state.property('activeTool') == 'Pan'
        assert w.item('toolbarPan').property('checked') and not w.item(menu_item).property('checked')

    assert not w.item('imagePrepareAnalysis').property('visible')
    assert not w.item('roiToolDropdown').property('visible')
    w.click('toolbarZoom')
    before = w.state.property('effectiveZoom')
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, at(50, 50))
    assert w.state.property('effectiveZoom') > before
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.AltModifier, at(50, 50))
    assert w.state.property('effectiveZoom') == pytest.approx(before)
    w.click('toolbarFit')
    assert w.state.property('fitMode') and w.state.property('activeTool') == 'Zoom'
    # External state changes (keyboard, imported ROI editing) remain authoritative.
    QTest.keyClick(w.window, Qt.Key_R)
    assert w.state.property('activeTool') == 'Rectangle'
    w.state.setProperty('roiEditMode', True)
    assert not w.item('tiffToolRectangle').property('checked')


def test_overflow_shared_commands_stack_access_and_gating(workbench, tmp_path):
    w = workbench
    w.same_action('toolbarOpen', 'menuOpenItem')
    assert not w.item('imagePrepareAnalysis').property('visible')
    assert not w.item('menuRunAnalysis').property('rowAvailable')
    assert w.item('roiAction').property('enabled')
    assert not w.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{})
    for action, page in [('advancedLastAction',2),('advancedFirstAction',0),('advancedNextAction',1),('advancedPreviousAction',0)]:
        w.item(action).trigger(None)
        spin(w.app, lambda page=page: w.state.property('pageIndex') == page and not w.state.property('pageLoading'))
    for action, mode, tab in [('advancedMacroAction','macro',0),('advancedPluginAction','plugin',0),('advancedModernAction',None,4)]:
        w.item(action).trigger(None)
        dialog=w.item('imagejDialog')
        assert dialog.property('visible') and dialog.property('tabsIndex') == tab
        if mode: assert dialog.property('mode') == mode
        invoke(dialog,'close')
    w.item('advancedMeasurementAction').trigger(None)
    assert w.item('stackMeasurementDialog').property('visible')
    invoke(w.item('stackMeasurementDialog'),'close')
    QTest.qWait(80)
    w.window.grabWindow()
    active=[(o.objectName(),o.property('title')) for o in w.window.findChildren(QObject) if o.inherits('QQuickPopup') and o.property('visible')]
    assert not active, active
    w.select('tiffMore','tiffMoreBrush')
    assert w.state.property('activeTool') == 'Brush'
    w.open(create_source(tmp_path).path)
    assert not w.state.property('tiffMode')
    assert w.item('imagePrepareAnalysis').property('visible')
    assert w.item('roiToolDropdown').property('visible')
    assert not w.item('stackViewerToolGroup').property('visible')
    assert w.item('toolAnalysisRoi').property('enabled')
    assert w.item('topToolbar').property('height') == 40


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_toolbar_layout_and_analysis_menu_entry(workbench, size):
    w = workbench
    w.window.resize(*size)
    # Longest supported selected labels still fit with all seven hit targets.
    for tool in ('Pan', 'Freehand', 'Text', 'Arrow'):
        w.state.setProperty('activeTool', tool)
        QTest.qWait(30)
        for name in ('toolbarOpen', 'toolbarPan', 'toolbarZoom', 'toolbarFit',
                     'tiffToolRectangle', 'tiffToolOval', 'tiffToolPolygon', 'tiffToolLine', 'tiffToolPoint', 'tiffToolWand', 'tiffMeasure', 'tiffContrast', 'tiffMore'):
            obj = w.item(name)
            p = obj.mapToScene(QPointF())
            assert obj.property('visible') and obj.property('width') >= 32 and obj.property('height') >= 32
            assert 0 <= p.x() and p.x() + obj.property('width') <= size[0]
            assert 30 <= p.y() and p.y() + obj.property('height') <= 70
            assert obj.property('tip') or name.startswith('tiffTool')
    assert w.window.findChild(QObject, 'analysisToolGroup') is None
    # The synthetic research classifier uses an RGB input contract.
    w.open(create_source(w.path.parent).path)
    w.state.setProperty('analysisScope', 'FULL_IMAGE')
    assert w.item('runAction').property('enabled'), w.bridge.analysis
    triggered = []
    w.item('runAction').triggered.connect(lambda *args: triggered.append(True))
    invoke(w.item('analysisMenu'), 'open')
    QTest.qWait(30)
    w.click('menuRunAnalysis')
    assert len(triggered) == 0
    assert w.item('analysisDialog').property('visible')
    w.click('confirmAnalysis')
    assert len(triggered) == 1
    spin(w.app, lambda: w.bridge.analysis['hasResult'] or w.bridge.analysis['state'] == 'FAILED')
    assert w.bridge.analysis['hasResult'], w.bridge.analysis
    assert w.bridge.research.state['total'] == 231
    assert w.panel.property('requestedContext') == 'result'  # TD-03 completion milestone.
    assert w.panel.property('lastReason') == 'ANALYSIS_COMPLETE'
