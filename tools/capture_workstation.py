"""Capture real Qt rendering with generated TIFF data and isolated settings."""
import ctypes
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def invoke(obj, name, *args):
    assert QMetaObject.invokeMethod(obj, name, *(Q_ARG("QVariant", value) for value in args))


def main():
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    output = Path(__file__).resolve().parents[1] / "docs/screenshots/polish"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        engine = QQmlApplicationEngine()
        provider = TiffImageProvider()
        bridge = FileBridge(provider, engine, QSettings(str(folder / "capture.ini"), QSettings.IniFormat))
        engine.addImageProvider("tiff", provider)
        engine.rootContext().setContextProperty("fileBridge", bridge)
        errors = []
        engine.warnings.connect(lambda items: errors.extend(item.toString() for item in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
        window = engine.rootObjects()[0]
        window.setPosition(30, 30)
        window.requestActivate()
        if sys.platform == "win32":
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window.winId()), 20, ctypes.byref(dark), ctypes.sizeof(dark))

        def settle():
            app.processEvents()
            time.sleep(0.02)
            QTest.qWait(200)

        names = {"main-image": "01-main-image", "main-roi": "02-main-roi", "analysis-roi": "03-analysis", "result-empty": "04-result-empty", "settings-general": "05-settings-general", "settings-viewer": "06-settings-viewer", "minimum": "07-minimum-1100x700"}

        def capture(name):
            settle()
            assert window.grabWindow().save(str(output / (names.get(name, name) + ".png")))

        state = window.findChild(QObject, "uiState")
        inspector = window.findChild(QObject, "inspectorPanel")
        settings = window.findChild(QObject, "settingsDialog")
        capture("empty")
        # Generated, labelled test data. No real XRT input is included in Git.
        y, x = np.mgrid[:768, :1024]
        image = (10000 + 25000 * np.exp(-((x - 512)**2 + (y - 384)**2) / 110000) + 5000 * np.sin(x / 14) * np.cos(y / 18)).astype(np.uint16)
        path = folder / "SYNTHETIC_TEST_16BIT.tiff"
        tifffile.imwrite(path, image)
        invoke(window, "selectImagePath", str(path))
        for _ in range(50):
            settle()
            if not state.property("loading"):
                break
        assert state.property("hasLoadedImage"), (state.property("loading"), state.property("loadError"), errors, bridge._task, bridge.provider.image.size())
        capture("main-image")
        invoke(window.findChild(QObject, "actualSizeAction"), "trigger")
        capture("actual-size-100")
        invoke(window.findChild(QObject, "fitAction"), "trigger")
        QTest.keyClick(window, Qt.Key_R)
        viewport = window.findChild(QObject, "viewerViewport")
        frame = window.findChild(QObject, "imageFrame")
        origin = viewport.mapToScene(QPoint(0, 0))
        start = QPoint(int(origin.x() + frame.property("x") + frame.property("width") * .3), int(origin.y() + frame.property("y") + frame.property("height") * .3))
        end = QPoint(int(origin.x() + frame.property("x") + frame.property("width") * .6), int(origin.y() + frame.property("y") + frame.property("height") * .6))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, end, 30)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
        capture("main-roi")
        inspector.setProperty("tabIndex", 1)
        capture("analysis-roi")
        inspector.setProperty("tabIndex", 2)
        capture("result-empty")
        inspector.setProperty("tabIndex", 0)
        invoke(settings, "openPreferences")
        capture("settings-general")
        settings.setProperty("category", 1)
        capture("settings-viewer")
        settings.setProperty("category", 4)
        capture("settings-model-unavailable")
        invoke(window.findChild(QObject, "resetConfirmation"), "open")
        capture("settings-reset-confirm")
        invoke(window.findChild(QObject, "resetConfirmation"), "reject")
        invoke(settings, "reject")
        invoke(window.findChild(QObject, "aboutAction"), "trigger")
        capture("about")
        invoke(window.findChild(QObject, "infoDialog"), "reject")
        for key, name in [(Qt.Key_F, "menu-file"), (Qt.Key_V, "menu-view"), (Qt.Key_S, "menu-settings")]:
            QTest.keyClick(window, key, Qt.AltModifier)
            capture(name)
            QTest.keyClick(window, Qt.Key_Escape)
        window.resize(1100, 700)
        capture("minimum")
        invoke(settings, "openPreferences")
        settings.setProperty("category", 1)
        capture("minimum-settings")
        invoke(settings, "reject")
        window.resize(1440, 900)
        bad = folder / "damaged.tif"
        bad.write_bytes(b"invalid TIFF")
        invoke(window, "selectImagePath", str(bad))
        for _ in range(50):
            settle()
            if not state.property("loading"):
                break
        capture("error-retained")
        invoke(window, "showDemo")
        window.resize(1100, 700)
        capture("demo-1100")
        assert not errors, "\n".join(errors)
        window.close()
        engine.deleteLater()
        settle()
    print("Windows Qt screenshots captured; no QML warnings.")


if __name__ == "__main__":
    main()
