"""Capture the native stack UI using temporary, explicitly synthetic uint16 frames."""
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def main():
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    output = Path(__file__).resolve().parents[1] / "docs/screenshots/stack"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        y, x = np.mgrid[:768, :1024]
        raw = np.stack([(4000 + x * 28 + y * 20 + i * 1000).astype(np.uint16) for i in range(9)])
        path = folder / "SYNTHETIC_TEST_STACK_16BIT.tif"
        tifffile.imwrite(path, raw, imagej=True, metadata={"axes": "TYX", "min": 1000, "max": 60000})
        engine = QQmlApplicationEngine()
        provider = TiffImageProvider()
        bridge = FileBridge(provider, engine, QSettings(str(folder / "capture.ini"), QSettings.IniFormat))
        engine.addImageProvider("tiff", provider)
        engine.rootContext().setContextProperty("fileBridge", bridge)
        errors = []
        engine.warnings.connect(lambda items: errors.extend(item.toString() for item in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
        window = engine.rootObjects()[0]
        state = window.findChild(QObject, "uiState")
        window.setPosition(20, 20)
        def settle():
            app.processEvents()
            time.sleep(.01)
            QTest.qWait(30)
        def wait_loaded():
            for _ in range(200):
                settle()
                if not bridge.stack_viewer.busy and not state.property("loading"):
                    settle()
                    return
            raise AssertionError("Page loading timed out")
        def capture(name):
            settle()
            assert window.grabWindow().save(str(output / (name + ".png")))
        try:
            assert QMetaObject.invokeMethod(window, "selectImagePath", Q_ARG("QVariant", str(path)))
            wait_loaded()
            assert state.property("pageCount") == 9
            capture("first-page")
            bridge.requestPage(4)
            wait_loaded()
            capture("middle-page")
            bridge.setDisplayRange(2000, 30000)
            wait_loaded()
            viewport = window.findChild(QObject, "viewerViewport")
            origin = viewport.mapToScene(QPoint(0, 0))
            QTest.mouseMove(window, QPoint(int(origin.x() + viewport.property("width") / 2),
                                          int(origin.y() + viewport.property("height") / 2)))
            capture("contrast-and-raw-pixel")
            bridge.resetDisplayRange()
            wait_loaded()
            bridge.requestPage(8)
            wait_loaded()
            capture("last-page")
            window.resize(1100, 700)
            capture("minimum-1100x700")
            assert not errors, "\n".join(errors)
        finally:
            bridge.waitForLoads()
            window.close()
            engine.deleteLater()
            settle()
    print("Synthetic uint16 stack captures complete; no QML warnings")


if __name__ == "__main__":
    main()
