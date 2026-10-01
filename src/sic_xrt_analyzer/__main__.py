"""PySide6/QML application entry point."""
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("sic-xrt-analyzer")
    app.setOrganizationName("CrystalVision-Lab")
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    engine.addImageProvider("tiff", provider)
    bridge = FileBridge(provider, engine)
    app.aboutToQuit.connect(bridge.waitForLoads)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "ui" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    if sys.platform == "win32":
        import ctypes
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(engine.rootObjects()[0].winId()), 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
