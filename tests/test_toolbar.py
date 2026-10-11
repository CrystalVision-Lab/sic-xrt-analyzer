"""Real popup selection, Viewer gestures and shared commands after TD-02."""
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import create_source
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
            invoke(window, 'selectImagePath', str(path))
            spin(qt_app, lambda: self.state.property('hasLoadedImage') and not self.state.property('loading'))

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

    cases = [('Rectangle', 'roiToolDropdown', 'toolRectangle', 'drag'),
             ('Oval', 'roiToolDropdown', 'toolOval', 'drag'),
             ('Polygon', 'roiToolDropdown', 'toolPolygon', 'vertices'),
             ('Freehand', 'roiToolDropdown', 'toolFreehand', 'drag'),
             ('Point', 'roiToolDropdown', 'toolPoint', 'point'),
             ('Line', 'measurementToolDropdown', 'measurementLine', 'drag'),
             ('Polyline', 'measurementToolDropdown', 'measurementPolyline', 'vertices'),
             ('FreeLine', 'measurementToolDropdown', 'measurementFreeLine', 'drag'),
             ('Angle', 'measurementToolDropdown', 'measurementAngle', 'angle'),
             ('Text', 'measurementToolDropdown', 'measurementText', 'point'),
             ('Arrow', 'measurementToolDropdown', 'measurementArrow', 'drag')]
    for tool, button, menu_item, gesture in cases:
        count = len(w.bridge.roi_manager.records)
        context = w.panel.property('tabIndex')
        w.select(button, menu_item)
        assert w.state.property('activeTool') == tool
        assert not w.state.property('roiEditMode')
        assert w.panel.property('tabIndex') == context
        assert mouse.property('activeFocus')  # Enter/arrows work after the popup closes.
        assert w.item(menu_item).property('checked')
        indicator = w.item(menu_item).property('indicator')
        assert indicator.x() + indicator.width() <= w.item(menu_item).property('leftPadding')
        assert not w.item('toolbarPan').property('checked')
        assert not w.item('toolbarZoom').property('checked')
        # Selecting an already active action must not uncheck it.
        w.select(button, menu_item)
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

    w.select('roiToolDropdown', 'toolAnalysisRoi')
    assert w.item('menuRoiTool').property('checked') and w.item('roiToolDropdown').property('checked')
    QTest.keyClick(w.window, Qt.Key_H)
    assert not w.item('menuRoiTool').property('checked')
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
    assert w.item('menuRoiTool').property('checked')
    w.state.setProperty('roiEditMode', True)
    assert not w.item('menuRoiTool').property('checked')
    assert not w.item('roiToolDropdown').property('checked')


def test_overflow_shared_commands_stack_access_and_gating(workbench, tmp_path):
    w = workbench
    for left, right in [('toolbarOpen', 'menuOpenItem'), ('contextRunAnalysis', 'menuRunAnalysis'),
                        ('contextCancelAnalysis', 'menuCancelAnalysis'), ('toolbarMeasureItem', 'stackMeasurementMenuItem'),
                        ('toolbarMacro', 'menuMacroItem'), ('toolbarPlugin', 'menuPluginItem'),
                        ('toolbarFiji', 'menuFijiItem'), ('toolbarImagejCommands', 'menuImagejCommandsItem')]:
        w.same_action(left, right)
    for item, page in [('toolbarLastPage', 2), ('toolbarFirstPage', 0), ('toolbarNextPage', 1), ('toolbarPreviousPage', 0)]:
        w.click('advancedToolGroup')
        invoke(w.item('toolbarStackMenu'), 'open')
        QTest.qWait(30)
        w.click(item)
        spin(w.app, lambda page=page: w.state.property('pageIndex') == page and not w.state.property('pageLoading'))
    for item, mode, tab in [('toolbarMacro', 'macro', 0), ('toolbarPlugin', 'plugin', 0), ('toolbarFiji', None, 4)]:
        w.select('advancedToolGroup', item)
        dialog = w.item('imagejDialog')
        assert dialog.property('visible') and dialog.property('tabsIndex') == tab
        if mode:
            assert dialog.property('mode') == mode
        invoke(dialog, 'close')
    w.select('measurementToolDropdown', 'toolbarMeasureItem')
    assert w.item('stackMeasurementDialog').property('visible')
    invoke(w.item('stackMeasurementDialog'), 'close')
    w.click('advancedToolGroup')
    invoke(w.item('toolbarDrawingMenu'), 'open')
    QTest.qWait(30)
    w.click('toolBrush')
    assert w.state.property('activeTool') == 'Brush'
    w.select('advancedToolGroup', 'toolbarRecordCommands')
    assert w.bridge.imagej.state['recording']
    w.select('advancedToolGroup', 'toolbarRecordCommands')
    assert not w.bridge.imagej.state['recording']
    w.click('advancedToolGroup')
    invoke(w.item('toolbarLutMenu'), 'open')
    QTest.qWait(30)
    w.click('toolbarLutFire')
    assert w.item('imagejCommand').property('text') == 'Fire'
    invoke(w.item('imagejDialog'), 'close')
    # TIFF-derived working copies keep stack provenance, unrelated JPEG hides it.
    jpg = tmp_path/'plain.jpg'
    Image.fromarray(np.zeros((128, 128, 3), np.uint8)).save(jpg)
    w.open(jpg)
    assert not w.state.property('stackFeaturesVisible')
    assert not w.item('measurementToolDropdown').property('enabled')
    assert not w.item('toolbarStackMenu').property('available')
    assert not w.item('toolbarLutMenu').property('available')
    assert not w.item('toolRectangle').property('visible')
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
                     'roiToolDropdown', 'measurementToolDropdown', 'advancedToolGroup'):
            obj = w.item(name)
            p = obj.mapToScene(QPointF())
            assert obj.property('visible') and obj.property('width') >= 32 and obj.property('height') >= 32
            assert 0 <= p.x() and p.x() + obj.property('width') <= size[0]
            assert 30 <= p.y() and p.y() + obj.property('height') <= 70
            assert obj.property('tip')
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
    assert len(triggered) == 1
    spin(w.app, lambda: w.bridge.analysis['hasResult'] or w.bridge.analysis['state'] == 'FAILED')
    assert w.bridge.analysis['hasResult'], w.bridge.analysis
    assert w.bridge.research.state['total'] == 231
    assert w.panel.property('tabIndex') == 3  # No new automatic Context switch.
