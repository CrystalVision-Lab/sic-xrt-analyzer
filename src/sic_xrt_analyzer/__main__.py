"""PySide6/QML application entry point."""

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot


class FileBridge(QObject):
    """Convert the native file dialog URL to a local path for UI state."""

    @Slot(str, result=str)
    def localPath(self, url: str) -> str:
        return QUrl(url).toLocalFile()

    @Slot(str, result=str)
    def fileName(self, path: str) -> str:
        return Path(path).name


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("fileBridge", FileBridge(engine))
    qml_path = Path(__file__).parent / "ui" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
