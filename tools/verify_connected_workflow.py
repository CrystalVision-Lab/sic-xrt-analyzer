"""Actual-data Windows rendering QA. Results/screens stay in ignored task artifacts."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sic_xrt_analyzer.ui.bridge import FileBridge


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", type=Path, required=True)
    ap.add_argument("--folder", type=Path, required=True)
    ap.add_argument("--seed", type=int, nargs=3, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to(Path.cwd() / "artifacts")
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = FileBridge(
        parent=engine, settings=QSettings(str(out / "prefs.ini"), QSettings.IniFormat)
    )
    bridge.stack_viewer._preload_enabled = False
    bridge.stack_viewer._reader.preload_enabled = False
    engine.addImageProvider("tiff", bridge.provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    engine.load(
        QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve()))
    )
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    window.setTitle("XRT 131 connected defect validation")
    window.resize(1440, 900)
    window.show()
    state = window.findChild(QObject, "uiState")
    state.setProperty("workspaceIndex", 0)
    report = {"status": "FAIL"}

    def spin(pred, timeout=120):
        until = time.monotonic() + timeout
        while not pred():
            if time.monotonic() > until:
                raise TimeoutError("Windows QA timeout")
            app.processEvents()
            time.sleep(0.01)

    try:
        stack = args.stack.resolve()
        before = sha(stack)
        bridge.requestImage(QUrl.fromLocalFile(str(stack)).toString())
        spin(
            lambda: bridge.original_source is not None and not bridge.stack_viewer.busy
        )
        bridge.requestPage(args.seed[2])
        spin(
            lambda: (
                bridge.original_source.page_index == args.seed[2]
                and not bridge.stack_viewer.busy
            )
        )
        state.setProperty("workspaceIndex", 0)
        button = window.findChild(QObject, "openStackRoi3d")
        print(
            "UI_READY",
            {
                k: state.property(k)
                for k in [
                    "workspaceIndex",
                    "hasLoadedImage",
                    "stackFeaturesVisible",
                    "imageFormat",
                    "pageCount",
                ]
            },
            flush=True,
        )
        spin(lambda: button.property("visible") and button.property("enabled"))
        button.clicked.emit()
        app.processEvents()
        assert state.property("activeTool") == "Defect3D"
        viewer = window.findChild(QObject, "imageViewer")
        frame = window.findChild(QObject, "imageFrame")
        # Send an actual Qt mouse click through the same original-coordinate transform.
        point = frame.mapToScene(
            QPointF(
                args.seed[0] * viewer.property("displayScale"),
                args.seed[1] * viewer.property("displayScale"),
            )
        )
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        spin(lambda: state.property("workspaceIndex") == 3)
        spin(lambda: not bridge.defect3d.busy)
        assert bridge.defect3d.mesh is not None, bridge.defect3d.error
        spin(lambda: window.findChild(QObject, "defect3dPerspective") is not None)
        for _ in range(60):
            app.processEvents()
            time.sleep(0.02)
        assert window.grabWindow().save(str(out / "connected-defect.png"))
        assert (
            window.findChild(QObject, "stack3dTabs") is None
            and window.findChild(QObject, "stack3dPageSlider") is None
        )
        print("NATIVE_MESH", bridge.defect3d.state, flush=True)
        report.update(mesh=bridge.defect3d.state)
        state.setProperty("workspaceIndex", 1)
        bridge.folderMap.open(str(args.folder.resolve()))
        spin(lambda: not bridge.folderMap.busy)
        assert bridge.folderMap.state["ready"], bridge.folderMap.error
        for _ in range(25):
            app.processEvents()
            time.sleep(0.02)
        assert window.grabWindow().save(str(out / "wafer-mosaic.png"))
        wafer = window.findChild(QObject, "waferMapWorkspace")
        wafer.setProperty("scale", 0.05)
        bridge.folderMap.changed.emit()
        app.processEvents()
        assert wafer.property("scale") == 0.05
        after = sha(stack)
        assert before == after
        assert not warnings, warnings
        report.update(
            status="PASS",
            original_sha256=after,
            mosaic=bridge.folderMap.state["evidence"],
            qml_warnings=warnings,
            source_coordinate_click=True,
            zoom_floor_preserved=True,
        )
    except Exception as e:
        report.update(error=type(e).__name__ + ": " + str(e), qml_warnings=warnings)
        raise
    finally:
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        bridge.waitForLoads()
        window.hide()
        engine.deleteLater()
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
