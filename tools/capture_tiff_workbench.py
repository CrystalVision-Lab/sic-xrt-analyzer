"""TD09 reproducible QML screenshots and toolbar hit-target checks; synthetic pixels only."""

import argparse
import json
import os
import time
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QSG_RENDER_LOOP", "basic")
import numpy as np
import tifffile
from PIL import Image
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("docs/screenshots/tiff-workbench")
    )
    parser.add_argument("--layout-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        engine = QQmlApplicationEngine()
        bridge = FileBridge(
            parent=engine,
            settings=QSettings(str(folder / "prefs.ini"), QSettings.IniFormat),
        )
        engine.addImageProvider("tiff", bridge.provider)
        engine.rootContext().setContextProperty("fileBridge", bridge)
        warnings = []
        engine.warnings.connect(
            lambda items: warnings.extend(i.toString() for i in items)
        )
        engine.load(
            QUrl.fromLocalFile(
                str(
                    Path(__file__).resolve().parents[1]
                    / "src/sic_xrt_analyzer/ui/Main.qml"
                )
            )
        )
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        state = window.findChild(QObject, "uiState")

        def invoke(method, *values):
            assert QMetaObject.invokeMethod(
                window, method, *(Q_ARG("QVariant", a) for a in values)
            )

        def wait(predicate):
            deadline = time.monotonic() + 40
            while not predicate():
                if time.monotonic() > deadline:
                    raise TimeoutError("Capture preparation timeout")
                app.processEvents()
                time.sleep(.005)

        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)

        def item(name):
            return next(
                i for i in items(window.contentItem()) if i.objectName() == name
            )

        def click(name):
            node = item(name)
            assert node.isVisible() and node.isEnabled(), name
            QTest.mouseClick(
                window,
                Qt.LeftButton,
                Qt.NoModifier,
                node.mapToScene(QPointF(node.width() / 2, node.height() / 2)).toPoint(),
            )
            QTest.qWait(60)

        def capture(name):
            QTest.qWait(120)
            assert window.grabWindow().save(str(args.output / (name + ".png")))

        def open_image(path):
            bridge.roi_manager.clear()
            invoke("selectImagePath", str(path))
            wait(
                lambda: (
                    not state.property("loading")
                    and not bridge.stack_viewer.initial_loading
                )
            )

        layout = []
        try:
            y, x = np.mgrid[:512, :512]
            pixels = ((x // 16 + y // 16) % 2 * 1000 + 1000).astype(np.uint16)
            path = folder / "SYNTHETIC-frames.tif"
            tifffile.imwrite(
                path,
                np.stack([pixels, pixels + 500, pixels + 1000]),
                imagej=True,
                metadata={"axes": "TYX", "min": 0, "max": 4000},
            )
            open_image(path)
            for width, height in [(1100, 700), (1440, 900), (1920, 1080)]:
                window.resize(width, height)
                QTest.qWait(150)
                names = [
                    "toolbarOpen",
                    "toolbarPan",
                    "toolbarZoom",
                    "toolbarFit",
                    "tiffToolRectangle",
                    "tiffToolOval",
                    "tiffToolPolygon",
                    "tiffToolLine",
                    "tiffToolPoint",
                    "tiffToolWand",
                    "tiffMeasure",
                    "tiffContrast",
                    "tiffProcess",
                    "tiffMore",
                    "tiffStack",
                    "toolbarContextTools",
                ]
                boxes = []
                for name in names:
                    node = item(name)
                    p = node.mapToScene(QPointF())
                    assert (
                        node.isVisible() and node.width() >= 32 and node.height() >= 32
                    ), name
                    assert (
                        0 <= p.x()
                        and p.x() + node.width() <= width
                        and 30 <= p.y()
                        and p.y() + node.height() <= 92
                    ), (name, p, node.size())
                    boxes.append(
                        {
                            "name": name,
                            "x": p.x(),
                            "y": p.y(),
                            "width": node.width(),
                            "height": node.height(),
                        }
                    )
                for a, b in pairwise(boxes):
                    assert a["x"] + a["width"] <= b["x"] + 0.01, (a, b)
                assert not item("imagePrepareAnalysis").isVisible()
                layout.append(
                    {
                        "size": [width, height],
                        "dpr": window.devicePixelRatio(),
                        "targets": boxes,
                    }
                )
                capture("tiff-" + str(width))
            if not args.layout_only:
                window.resize(1440, 900)
                QTest.qWait(100)
                for tool, points in [
                    ("Rectangle", [[80, 80], [200, 200]]),
                    ("Polygon", [[100, 100], [240, 140], [160, 280]]),
                    ("Line", [[60, 60], [250, 200]]),
                    ("Polyline", [[60, 60], [200, 60], [200, 250]]),
                ]:
                    bridge.roi_manager.clear()
                    click("tiffTool" + tool)
                    bridge.workbench.gesture(tool, points)
                    capture(tool.lower())
                bridge.measurements.measure()
                invoke("openContext", "viewer")
                capture("measurement")
                click("closeContextPanel")
                bridge.roi_manager.clear()
                click("tiffToolWand")
                bridge.workbench.gesture("Wand", [[80, 80]])
                wait(lambda: not bridge.workbench.busy)
                assert not bridge.workbench.error, bridge.workbench.error
                capture("wand")
                click("tiffMore")
                window.findChild(QObject, "tiffAdvancedMenu").open()
                capture("advanced-menu")
                QTest.keyClick(window, Qt.Key_Escape)
                invoke("processTiff", "Gaussian")
                capture("processing-confirmation")
                window.findChild(QObject, "imagejProcessingDialog").close()
                rgb = np.repeat((pixels // 16).astype(np.uint8)[..., None], 3, axis=2)
                jpg = folder / "SYNTHETIC-image.jpg"
                Image.fromarray(rgb).save(jpg)
                open_image(jpg)
                capture("tiff-to-jpg")
                assert item("imagePrepareAnalysis").isVisible()
                capture("jpg-toolbar")
                open_image(folder / "SYNTHETIC-frames.tif")
                capture("tiff-reopened")
            assert not warnings, warnings
        finally:
            window.setProperty("allowQuit", True)
            window.close()
            bridge.waitForLoads()
            engine.deleteLater()
            app.processEvents()
    (args.output / "layout.json").write_text(
        json.dumps(
            {
                "kind": "synthetic QML capture; QTest input, not physical acceptance",
                "layout": layout,
                "qmlWarnings": warnings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("PASS synthetic QML captures:", args.output)


if __name__ == "__main__":
    main()
