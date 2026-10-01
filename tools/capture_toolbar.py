"""Capture toolbar alignment in the real Qt UI with isolated settings."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPointF, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots/toolbar"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with TemporaryDirectory() as directory:
        engine = QQmlApplicationEngine()
        provider = TiffImageProvider()
        bridge = FileBridge(provider, engine, QSettings(str(Path(directory) / "ui.ini"), QSettings.IniFormat))
        engine.addImageProvider("tiff", provider)
        engine.rootContext().setContextProperty("fileBridge", bridge)
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
        window = engine.rootObjects()[0]
        toolbar = window.findChild(QObject, "topToolbar")

        def invoke(obj, method, *values):
            assert QMetaObject.invokeMethod(obj, method, *(Q_ARG("QVariant", value) for value in values))

        def capture(name, full=False):
            app.processEvents()
            QTest.qWait(150)
            image = window.grabWindow()
            if not full:
                origin = toolbar.mapToScene(QPointF(0, 0))
                ratio = image.devicePixelRatio()
                image = image.copy(round(origin.x() * ratio), round(origin.y() * ratio),
                                   round(toolbar.width() * ratio), round(toolbar.height() * ratio))
            assert image.save(str(args.output / f"{name}.png"))

        window.resize(1440, 900)
        capture("empty-1440")
        invoke(window, "showDemo")
        capture("demo-pan-1440")
        window.findChild(QObject, "uiState").setProperty("activeTool", "ROI")
        capture("demo-roi-1440")
        window.resize(1100, 700)
        capture("demo-roi-1100")
        settings = window.findChild(QObject, "settingsDialog")
        invoke(settings, "openPreferences")
        capture("settings-1100", full=True)
        invoke(settings, "reject")
        assert not warnings, "\n".join(warnings)
        window.close()
        engine.deleteLater()
        app.processEvents()
    print(f"Toolbar and settings captured in {args.output}; no QML warnings.")


if __name__ == "__main__":
    main()
