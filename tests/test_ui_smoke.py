"""Exercise the QML shell and its state transitions without inspection data."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.__main__ import FileBridge


def test_initial_ui_flow(tmp_path: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("fileBridge", FileBridge(engine))
    qml = Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))

    assert len(engine.rootObjects()) == 1
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    viewer = window.findChild(QObject, "imageViewer")
    assert state is not None and viewer is not None
    assert (window.width(), window.height()) == (1440, 900)
    assert not state.property("canNavigateImage")

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
    app.processEvents()
    assert viewer.property("width") > standard_width

    selected = tmp_path / "selection-only.tiff"
    selected.touch()
    url = QUrl.fromLocalFile(str(selected)).toString()
    assert QMetaObject.invokeMethod(window, "selectImageFile", Q_ARG("QVariant", url))
    assert state.property("fileName") == selected.name
    assert not state.property("demoMode")
    assert not state.property("canNavigateImage")
    window.close()
