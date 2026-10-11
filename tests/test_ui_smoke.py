"""Integration checks for the workstation UI using generated data only."""
import os
import time
from pathlib import Path

import numpy as np
import tifffile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def invoke(obj, method, *args):
    assert QMetaObject.invokeMethod(obj, method, *(Q_ARG("QVariant", arg) for arg in args))


def settle(app):
    for _ in range(4):
        app.processEvents()
    QTest.qWait(30)


def wait_loaded(app, state):
    for _ in range(100):
        time.sleep(0.01)  # Allow the decoder's Python worker to acquire the GIL.
        settle(app)
        if not state.property("loading"):
            return
    raise AssertionError("TIFF loading did not complete")


def test_workstation_flow(tmp_path):
    app = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(str(item.toString()) for item in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    assert len(engine.rootObjects()) == 1, warnings
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    viewer = window.findChild(QObject, "imageViewer")
    inspector = window.findChild(QObject, "inspectorPanel")
    settings = window.findChild(QObject, "settingsDialog")
    menu = window.findChild(QObject, "appMenuBar")
    settle(app)
    assert menu.property("count") == 8
    assert [window.findChild(QObject, name + "Menu").property("title") for name in
            ("file", "edit", "view", "process", "analysis", "tools", "settings", "help")] == [
                "파일", "편집", "이미지 (Image)", "처리 (Process)", "분석 (Analyze)", "플러그인 (Plugins)", "창 (Window)", "도움말"]
    assert not state.property("hasImage")
    assert not window.findChild(QObject, "runAction").property("enabled")
    assert window.findChild(QObject, "settingsMenu").property("count") == 3
    assert window.findChild(QObject, "menuOpenItem").property("text") == window.findChild(QObject, "openAction").property("text")

    QTest.keyClick(window, Qt.Key_F, Qt.AltModifier)
    settle(app)
    assert window.findChild(QObject, "fileMenu").property("visible")
    QTest.keyClick(window, Qt.Key_Down)
    assert window.findChild(QObject, "fileMenu").property("currentIndex") >= 0
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.keyClick(window, Qt.Key_F11)
    settle(app)
    assert window.visibility() == QWindow.FullScreen
    QTest.keyClick(window, Qt.Key_F11)
    settle(app)

    invoke(window, "showDemo")
    settle(app)
    assert state.property("canNavigateImage")
    QTest.keyClick(window, Qt.Key_R)
    assert state.property("activeTool") == "ROI"
    QTest.keyClick(window, Qt.Key_H)
    assert state.property("activeTool") == "Pan"
    fit_zoom = state.property("effectiveZoom")
    assert state.property("zoomLabel") == "FIT"
    invoke(viewer, "zoomIn")
    assert state.property("effectiveZoom") > fit_zoom
    invoke(viewer, "zoomOut")
    assert abs(state.property("effectiveZoom") - fit_zoom) < .001
    assert not state.property("fitMode")
    QTest.keyClick(window, Qt.Key_0, Qt.ControlModifier)
    assert state.property("fitMode")
    assert state.property("zoomLabel") == "FIT"

    old_width = viewer.property("viewportWidth")
    invoke(window.findChild(QObject, "inspectorPanelAction"), "trigger")
    settle(app)
    assert window.property("inspectorCollapsed")
    assert viewer.property("viewportWidth") > old_width
    invoke(window, "resetLayout")
    settle(app)

    # Independent settings: draft changes are not persisted until applied.
    invoke(settings, "openPreferences")
    settle(app)
    assert settings.property("visible"), (warnings, settings.metaObject().className(), settings.property("title"), settings.property("opened"))
    assert settings.property("title") == "설정"
    assert settings.property("categories").toVariant() == ["일반", "뷰어", "이미지", "분석", "AI / 모델", "보정", "성능", "내보내기", "단축키", "진단"]
    assert inspector.property("tabIndex") == 0
    for category in range(10):
        settings.setProperty("category", category)
        settle(app)
    settings.setProperty("category", 1)
    combo = window.findChild(QObject, "defaultZoomCombo")
    invoke(combo, "forceActiveFocus")
    QTest.keyClick(window, Qt.Key_Space)
    QTest.keyClick(window, Qt.Key_Down)
    QTest.keyClick(window, Qt.Key_Return)
    settle(app)
    assert settings.property("draftView") == "actual"
    settings.setProperty("draftSmooth", False)
    settings.setProperty("draftView", "200")
    invoke(settings, "reject")
    assert bridge.preferences()["smoothImages"]
    invoke(settings, "openPreferences")
    assert settings.property("draftSmooth")
    settings.setProperty("draftSmooth", False)
    settings.setProperty("draftView", "125")
    invoke(settings, "applyDraft")
    assert settings.property("visible"), (warnings, settings.metaObject().className(), settings.property("title"), settings.property("opened"))
    assert not state.property("smoothImages")
    assert bridge.preferences()["defaultView"] == "125"
    # Cancel after Apply retains applied values but discards later edits.
    settings.setProperty("draftSmooth", True)
    invoke(settings, "reject")
    assert not bridge.preferences()["smoothImages"]
    invoke(settings, "openPreferences")
    assert not settings.property("draftSmooth")
    reset = window.findChild(QObject, "resetConfirmation")
    invoke(reset, "open")
    invoke(reset, "reject")
    assert not bridge.preferences()["smoothImages"]
    invoke(reset, "open")
    invoke(reset, "accept")
    assert bridge.preferences() == bridge.defaultPreferences()
    assert state.property("smoothImages")
    settings.setProperty("draftView", "200")
    ok = window.findChild(QObject, "okSettingsButton")
    invoke(ok, "clicked")
    assert not settings.property("visible")
    assert bridge.preferences()["defaultView"] == "200"
    bridge.applyPreferences(bridge.defaultPreferences())
    invoke(window, "applyPreferences", bridge.preferences())

    path = tmp_path / "generated-16bit.tiff"
    tifffile.imwrite(path, np.arange(512 * 256, dtype=np.uint16).reshape(256, 512))
    invoke(window, "selectImagePath", str(path))
    assert state.property("loading")
    wait_loaded(app, state)
    assert state.property("hasLoadedImage")
    assert not state.property("demoMode")
    assert (state.property("imageWidth"), state.property("imageHeight"), state.property("bitDepth")) == (512, 256, 16)
    frame = window.findChild(QObject, "imageFrame")
    assert abs(frame.property("width") / frame.property("height") - 2) < 0.001
    assert bridge.recentFiles == [str(path)]
    assert not state.property("canAnalyze")

    # Absolute view choices use original pixels and display pixel density.
    for mode, scale in [("actual", 1), ("125", 1.25), ("200", 2)]:
        settings.setProperty("draftView", mode)
        invoke(settings, "applyDraft")
        invoke(window, "selectImagePath", str(path))
        wait_loaded(app, state)
        assert not state.property("fitMode")
        assert state.property("effectiveZoom") == scale
        assert abs(frame.property("width") * state.property("displayPixelRatio") - 512 * scale) < .001
        assert state.property("zoomLabel") == f"{scale * 100:g}%"
    invoke(window.findChild(QObject, "actualSizeAction"), "trigger")
    assert state.property("zoomLabel") == "100%"
    state.setProperty("displayPixelRatio", 2)
    assert abs(frame.property("width") - 256) < .001
    state.setProperty("displayPixelRatio", window.devicePixelRatio())
    invoke(viewer, "fitView")
    assert state.property("zoomLabel") == "FIT"
    original_fit = state.property("effectiveZoom")
    window.resize(1200, 800)
    settle(app)
    assert state.property("fitMode") and state.property("effectiveZoom") != original_fit
    assert state.property("zoomLabel") == "FIT"
    window.resize(1440, 900)
    settle(app)

    # Mouse coordinates and ROI use original pixels, independent of zoom.
    state.setProperty("activeTool", "ROI")
    viewport = window.findChild(QObject, "viewerViewport")
    origin = viewport.mapToScene(QPoint(0, 0))
    start = QPoint(int(origin.x() + frame.property("x") + frame.property("width") * .2),
                   int(origin.y() + frame.property("y") + frame.property("height") * .2))
    end = QPoint(int(origin.x() + frame.property("x") + frame.property("width") * .6),
                 int(origin.y() + frame.property("y") + frame.property("height") * .6))
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, end, 20)
    assert state.property("selectingRoi")
    overlay = window.findChild(QObject, "roiOverlay")
    assert QQmlExpression(engine.rootContext(), overlay, "border.width").evaluate()[0] == 2
    assert .07 < overlay.property("color").alphaF() < .09
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
    settle(app)
    assert state.property("hasRoi")
    assert not state.property("selectingRoi")
    assert QQmlExpression(engine.rootContext(), overlay, "border.width").evaluate()[0] == 1
    assert .03 < overlay.property("color").alphaF() < .05
    assert state.property("workflowLabel") == "ROI 선택됨"
    assert state.property("viewerStatus") == "준비 완료"
    assert 200 <= state.property("roiWidth") <= 210
    assert state.property("cursorX") >= 0
    invoke(window, "copyRoiInfo")
    assert "ROI (original pixels)" in app.clipboard().text()
    state.setProperty("activeTool", "Pan")
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, start + QPoint(20, 10), 20)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPoint(20, 10))
    assert viewer.property("panX") == 20
    invoke(viewer, "fitView")
    assert viewer.property("panX") == 0

    old_source = state.property("imageSource")
    bad = tmp_path / "damaged.tif"
    bad.write_bytes(b"not a TIFF")
    invoke(window, "selectImagePath", str(bad))
    wait_loaded(app, state)
    assert state.property("loadError")
    assert state.property("imageSource") == old_source
    assert bridge.recentFiles == [str(path)]
    assert state.property("workflowLabel") == "파일 오류"
    for index in range(3):
        inspector.setProperty("tabIndex", index)
        settle(app)
    window.resize(1100, 700)
    settle(app)
    assert viewer.property("viewportWidth") > 500
    invoke(settings, "openPreferences")
    settings.setProperty("category", 1)
    settle(app)
    assert settings.property("width") <= window.width()
    assert settings.property("height") < window.height() - 100
    invoke(settings, "reject")
    invoke(window, "closeImage")
    assert not state.property("hasImage")
    assert provider.image.isNull()
    assert not state.property("analysisRunning") and not state.property("hasResult")
    assert not warnings, "\n".join(warnings)
    window.close()
    engine.deleteLater()
    settle(app)
