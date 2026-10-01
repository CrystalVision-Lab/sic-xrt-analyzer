"""PySide6/QML application entry point."""

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication


class FileBridge(QObject):
    """Keep local file and desktop integration outside QML."""

    recentFilesChanged = Signal()

    def __init__(self, parent: QObject | None = None, settings: QSettings | None = None):
        super().__init__(parent)
        self._settings = settings or QSettings("CrystalVision-Lab", "sic-xrt-analyzer")
        stored = self._settings.value("recentFiles", [])
        self._recent_files = list(stored) if isinstance(stored, list) else [stored]

    @Property("QStringList", notify=recentFilesChanged)
    def recentFiles(self) -> list[str]:
        return self._recent_files

    @Property(str, constant=True)
    def appVersion(self) -> str:
        try:
            return version("sic-xrt-analyzer")
        except PackageNotFoundError:
            return "설치된 패키지 버전을 확인할 수 없습니다"

    @Slot(str, result=str)
    def localPath(self, url: str) -> str:
        return QUrl(url).toLocalFile()

    @Slot(str, result=str)
    def fileName(self, path: str) -> str:
        return Path(path).name

    @Slot(str)
    def recordRecentFile(self, path: str) -> None:
        normalized = str(Path(path).resolve())
        self._recent_files = [
            normalized,
            *(old for old in self._recent_files if os.path.normcase(old) != os.path.normcase(normalized)),
        ][:10]
        self._settings.setValue("recentFiles", self._recent_files)
        self.recentFilesChanged.emit()

    @Slot()
    def clearRecentFiles(self) -> None:
        self._recent_files = []
        self._settings.remove("recentFiles")
        self.recentFilesChanged.emit()

    @Slot(str, result=bool)
    def isAccessible(self, path: str) -> bool:
        candidate = Path(path)
        return candidate.is_file() and os.access(candidate, os.R_OK)

    @Slot(str)
    def copyText(self, value: str) -> None:
        QGuiApplication.clipboard().setText(value)

    @Slot(result=bool)
    def openIssueTracker(self) -> bool:
        return QDesktopServices.openUrl(
            QUrl("https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues")
        )


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
