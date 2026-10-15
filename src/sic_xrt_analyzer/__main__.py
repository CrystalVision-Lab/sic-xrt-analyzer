"""PySide6/QML application entry point."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def main() -> int:
    # Python-painted items run on the GUI thread; avoid render-thread/GIL waits.
    os.environ.setdefault('QSG_RENDER_LOOP', 'basic')
    if sys.platform == 'win32':
        from PySide6.QtWidgets import QApplication
        app = QApplication(sys.argv)
    else:
        app = QGuiApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui/assets/app-logo.png")))
    app.setApplicationName("sic-xrt-analyzer")
    app.setOrganizationName("CrystalVision-Lab")
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    engine.addImageProvider("tiff", provider)
    bridge = FileBridge(provider, engine)
    QTimer.singleShot(0, bridge.research_controller.load_saved)
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
    QTimer.singleShot(1000, bridge.app_update_controller.checkOnStartup)
    result = app.exec()
    bridge.app_update_controller.launch_after_exit()
    if bridge.app_update_controller.launch_error:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "프로그램 업데이트", bridge.app_update_controller.launch_error)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
