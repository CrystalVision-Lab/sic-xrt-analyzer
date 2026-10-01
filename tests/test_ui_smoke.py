"""Exercise the QML shell and its state transitions without inspection data."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.__main__ import FileBridge


def test_initial_ui_flow(tmp_path: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = FileBridge(engine, QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    engine.rootContext().setContextProperty("fileBridge", bridge)
    qml = Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))

    assert len(engine.rootObjects()) == 1
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    viewer = window.findChild(QObject, "imageViewer")
    toolbar = window.findChild(QObject, "topToolbar")
    open_action = window.findChild(QObject, "openAction")
    menu_open_item = window.findChild(QObject, "menuOpenItem")
    open_dialog = window.findChild(QObject, "openImageDialog")
    menu_bar = window.findChild(QObject, "appMenuBar")
    file_menu = window.findChild(QObject, "fileMenu")
    navigation_menu_item = window.findChild(QObject, "navigationPanelMenuItem")
    navigation_action = window.findChild(QObject, "navigationPanelAction")
    info_menu_item = window.findChild(QObject, "infoPanelMenuItem")
    status_menu_item = window.findChild(QObject, "statusBarMenuItem")
    info_dialog = window.findChild(QObject, "infoDialog")
    assert state is not None and viewer is not None
    assert all(item is not None for item in (toolbar, open_action, menu_open_item, open_dialog))
    assert toolbar.property("openAction") == open_action
    assert viewer.property("openAction") == open_action
    assert menu_bar is not None and menu_bar.property("count") == 6
    assert all(item is not None for item in (file_menu, navigation_menu_item, navigation_action, info_menu_item, status_menu_item, info_dialog))
    assert (window.width(), window.height()) == (1440, 900)
    assert not state.property("canNavigateImage")

    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(25, 17))
    app.processEvents()
    assert file_menu.property("visible")
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.keyClick(window, Qt.Key_F11)
    app.processEvents()
    assert window.visibility() == QWindow.FullScreen
    QTest.keyClick(window, Qt.Key_F11)
    app.processEvents()
    assert window.visibility() != QWindow.FullScreen
    app.processEvents()
    assert not file_menu.property("visible")
    QTest.keyClick(window, Qt.Key_F, Qt.AltModifier)
    app.processEvents()
    assert file_menu.property("visible")
    QTest.keyClick(window, Qt.Key_Down)
    app.processEvents()
    assert file_menu.property("currentIndex") >= 0
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.keyClick(window, Qt.Key_H, Qt.AltModifier)
    QTest.keyClick(window, Qt.Key_Down)
    QTest.keyClick(window, Qt.Key_Return)
    app.processEvents()
    assert info_dialog.property("visible")
    QTest.keyClick(window, Qt.Key_Escape)

    assert QMetaObject.invokeMethod(window, "showDemo")
    app.processEvents()
    assert state.property("canNavigateImage")
    assert QMetaObject.invokeMethod(viewer, "zoomIn")
    assert state.property("zoom") > 1
    assert QMetaObject.invokeMethod(viewer, "fitView")
    assert state.property("zoom") == 1

    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(670, 440))
    QTest.mouseMove(window, QPoint(730, 480), 40)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(730, 480))
    app.processEvents()
    assert viewer.property("panX") != 0

    state.setProperty("activeTool", "영역 선택")
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(580, 380))
    QTest.mouseMove(window, QPoint(740, 510), 40)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(740, 510))
    app.processEvents()
    assert state.property("hasRoi")

    assert QMetaObject.invokeMethod(window, "clearRoi")
    assert not state.property("hasRoi")
    assert QMetaObject.invokeMethod(window, "openInspectorTab", Q_ARG("QVariant", 0))
    assert info_menu_item.property("checked")
    window.setProperty("inspectorCollapsed", True)
    app.processEvents()
    assert not info_menu_item.property("checked")
    window.setProperty("statusBarVisible", False)
    app.processEvents()
    assert not status_menu_item.property("checked")
    assert QMetaObject.invokeMethod(navigation_action, "trigger")
    app.processEvents()
    assert window.property("navigationCollapsed")
    assert not navigation_menu_item.property("checked")
    assert QMetaObject.invokeMethod(navigation_action, "trigger")
    app.processEvents()
    assert not window.property("navigationCollapsed")

    state.setProperty("workspaceIndex", 1)
    app.processEvents()
    assert not state.property("canNavigateImage")
    state.setProperty("workspaceIndex", 0)
    window.setWidth(1100)
    window.setHeight(700)
    app.processEvents()
    assert viewer.property("width") >= 500
    standard_width = viewer.property("width")
    window.setProperty("navigationCollapsed", True)
    window.setProperty("inspectorCollapsed", True)
    QTest.qWait(100)
    app.processEvents()
    assert viewer.property("width") > standard_width

    selected = tmp_path / "selection-only.tiff"
    selected.touch()
    url = QUrl.fromLocalFile(str(selected)).toString()
    assert QMetaObject.invokeMethod(window, "selectImageFile", Q_ARG("QVariant", url))
    assert state.property("fileName") == selected.name
    assert bridge.recentFiles == [str(selected)]
    assert not state.property("demoMode")
    assert not state.property("canNavigateImage")
    QTest.keyClick(window, Qt.Key_O, Qt.ControlModifier)
    app.processEvents()
    assert open_dialog.property("visible")
    assert QMetaObject.invokeMethod(open_dialog, "reject")
    app.processEvents()
    assert state.property("fileName") == selected.name

    missing = tmp_path / "missing.tif"
    assert QMetaObject.invokeMethod(window, "selectImagePath", Q_ARG("QVariant", str(missing)))
    assert state.property("fileName") == selected.name
    assert len(bridge.recentFiles) == 1
    assert QMetaObject.invokeMethod(window, "selectImageFile", Q_ARG("QVariant", ""))
    assert state.property("fileName") == selected.name
    assert QMetaObject.invokeMethod(window, "closeImage")
    assert not state.property("hasSelectedFile")
    window.close()
