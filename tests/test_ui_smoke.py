"""Exercise the QML shell with generated, non-inspection TIFF data."""

import os
from pathlib import Path

import numpy as np
import tifffile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.__main__ import FileBridge, TiffImageProvider


def test_initial_ui_flow(tmp_path: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", FileBridge(provider, engine))
    qml = Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))

    assert len(engine.rootObjects()) == 1
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    viewer = window.findChild(QObject, "imageViewer")
    image = window.findChild(QObject, "tiffImage")
    menu_bar = window.findChild(QObject, "appMenuBar")
    inspector = window.findChild(QObject, "inspectorPanel")
    assert all(item is not None for item in (state, viewer, image, menu_bar, inspector))
    assert menu_bar.property("count") == 7
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
    assert QMetaObject.invokeMethod(window, "clearRoi")
    assert not state.property("hasRoi")

    assert QMetaObject.invokeMethod(window, "selectWorkspace", Q_ARG("QVariant", 1))
    app.processEvents()
    assert state.property("workspaceIndex") == 1
    assert not state.property("canNavigateImage")
    state.setProperty("workspaceIndex", 0)
    window.setProperty("inspectorCollapsed", True)
    assert QMetaObject.invokeMethod(window, "openInspectorTab", Q_ARG("QVariant", 1))
    assert not window.property("inspectorCollapsed")
    assert inspector.property("tabIndex") == 1
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

    selected = tmp_path / "sample.tiff"
    tifffile.imwrite(selected, np.arange(120, dtype=np.uint16).reshape(10, 12))
    url = QUrl.fromLocalFile(str(selected)).toString()
    assert QMetaObject.invokeMethod(window, "selectImageFile", Q_ARG("QVariant", url))
    app.processEvents()
    assert state.property("fileName") == selected.name
    assert state.property("imageWidth") == 12
    assert state.property("imageHeight") == 10
    assert state.property("bitDepth") == 16
    assert not state.property("demoMode")
    assert state.property("canNavigateImage")
    assert not provider.image.isNull()
    assert image.property("implicitWidth") == 12
    assert image.property("implicitHeight") == 10
    assert QMetaObject.invokeMethod(viewer, "zoomIn")
    assert state.property("zoom") > 1

    invalid = tmp_path / "invalid.tif"
    invalid.write_text("not a TIFF")
    invalid_url = QUrl.fromLocalFile(str(invalid)).toString()
    assert QMetaObject.invokeMethod(window, "selectImageFile", Q_ARG("QVariant", invalid_url))
    assert state.property("fileName") == selected.name
    assert state.property("loadError")
    assert state.property("canNavigateImage")
    window.close()
