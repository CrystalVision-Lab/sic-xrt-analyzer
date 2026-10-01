"""PySide6/QML application entry point."""

from pathlib import Path

from PySide6.QtCore import QObject, QSize, QUrl, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from sic_xrt_analyzer.imaging.tiff_preview import load_tiff_preview


class TiffImageProvider(QQuickImageProvider):
    """Keep the decoded preview available to QML without temporary files."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage()

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        return self.image


class FileBridge(QObject):
    """Open a local TIFF and report its preview and metadata to QML."""

    def __init__(self, provider: TiffImageProvider, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.provider = provider
        self.revision = 0

    @Slot(str, result=str)
    def localPath(self, url: str) -> str:
        return QUrl(url).toLocalFile()

    @Slot(str, result=str)
    def fileName(self, path: str) -> str:
        return Path(path).name

    @Slot(str, result="QVariantMap")
    def openImage(self, url: str) -> dict:
        path = self.localPath(url)
        if not path:
            return {"ok": False, "error": "로컬 TIFF 파일을 선택하세요"}
        try:
            preview = load_tiff_preview(path)
        # TIFF codecs can raise several library-specific errors for damaged input.
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self.provider.image = preview.image
        self.revision += 1
        return {
            "ok": True,
            "path": path,
            "name": self.fileName(path),
            "source": f"image://tiff/current?revision={self.revision}",
            "width": preview.width,
            "height": preview.height,
            "bitDepth": preview.bit_depth,
            "pageCount": preview.page_count,
            "sampled": preview.sampled,
        }


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", FileBridge(provider, engine))
    qml_path = Path(__file__).parent / "ui" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
