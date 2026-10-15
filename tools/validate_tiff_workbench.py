"""Read-only actual TIFF acceptance of TD09 QML tools, measurement and working-copy display."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("QSG_RENDER_LOOP", "basic")
import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.ui.bridge import FileBridge


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    project = ProjectStore().load(args.project)
    paths = [
        Path(s.source_reference)
        for s in project.image_sources
        if Path(s.source_reference).suffix.lower() in (".tif", ".tiff")
    ]
    assert len(paths) == 4
    before = {p: sha(p) for p in paths}
    project_sha = sha(args.project)
    report = {
        "status": "FAIL",
        "files": [],
        "automatic_model_inference": 0,
        "automatic_bpd_requests": 0,
        "automatic_sync_requests": 0,
        "qmlWarnings": [],
        "original_sha_preserved": False,
        "physical_mouse_acceptance": False,
    }
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = FileBridge(
        parent=engine,
        settings=QSettings(str(args.output / "settings.ini"), QSettings.IniFormat),
    )
    engine.addImageProvider("tiff", bridge.provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    engine.warnings.connect(
        lambda items: report["qmlWarnings"].extend(i.toString() for i in items)
    )
    engine.load(
        QUrl.fromLocalFile(
            str(
                Path(__file__).resolve().parents[1] / "src/sic_xrt_analyzer/ui/Main.qml"
            )
        )
    )
    assert engine.rootObjects(), report["qmlWarnings"]
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")

    def invoke(method, *values):
        assert QMetaObject.invokeMethod(
            window, method, *(Q_ARG("QVariant", a) for a in values)
        )

    def wait(predicate, timeout=240):
        end = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > end:
                report["timeout_state"] = {
                    "current": state.property("filePath"),
                    "opening": state.property("opening"),
                    "loadError": state.property("loadError"),
                    "preload": bridge.stack_viewer.preload_state,
                    "initialLoading": bridge.stack_viewer.initial_loading,
                    "busy": bridge.stack_viewer.busy,
                    "error": bridge.stack_viewer.error,
                    "preloadError": bridge.stack_viewer.preload_error,
                }
                raise TimeoutError(
                    "Real workbench preparation timed out: "
                    + repr(report["timeout_state"])
                )
            # Yield the Python GIL to TIFF/background workers while pumping Qt.
            app.processEvents()
            time.sleep(0.005)

    def items(node):
        yield node
        for child in node.childItems():
            yield from items(child)

    def item(name):
        return next(i for i in items(window.contentItem()) if i.objectName() == name)

    def forbidden(*a, **k):
        report["automatic_model_inference"] += 1
        raise AssertionError("TIFF inference is forbidden")

    bridge.pipeline.start = forbidden

    def forbidden_bpd(*a, **k):
        report["automatic_bpd_requests"] += 1
        raise AssertionError("Automatic BPD load forbidden")

    bridge.research_controller.experiments.load = forbidden_bpd

    def forbidden_sync(*a, **k):
        report["automatic_sync_requests"] += 1
        raise AssertionError("Automatic sync/crop is forbidden")

    bridge.centralSync.synchronize = forbidden_sync
    bridge.centralSync.uploadCrop = forbidden_sync
    try:
        for path in paths:
            bridge.roi_manager.clear()
            invoke("selectImagePath", str(path))
            print("Preparing " + path.name, flush=True)
            wait(
                lambda path=path: (
                    Path(state.property("filePath")) == path
                    and not state.property("loading")
                    and not bridge.stack_viewer.initial_loading
                )
            )
            row = {"file": path.name, "pages": [], "sha256": before[path]}
            count = state.property("pageCount")
            for index in sorted({0, count // 2, count - 1}):
                assert bridge.requestPage(index)
                wait(
                    lambda index=index: (
                        state.property("pageIndex") == index
                        and not bridge.stack_viewer.busy
                    )
                )
                assert (
                    not state.property("canAnalyze")
                    and not item("imagePrepareAnalysis").isVisible()
                )
                assert not bridge.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
                assert not bridge.reviews.state["pending"]
                frame = bridge.stack_viewer.frame
                with tifffile.TiffFile(path) as t:
                    oracle = t.pages[index].asarray(maxworkers=1)
                np.testing.assert_array_equal(frame.source.read_full(), oracle)
                assert frame.source.metadata.dtype == "uint16"
                bridge.roi_manager.clear()
                window.grabWindow()
                node = item("tiffToolRectangle")
                assert node.isVisible() and node.isEnabled()
                QTest.mouseClick(
                    window,
                    Qt.LeftButton,
                    Qt.NoModifier,
                    node.mapToScene(
                        QPointF(node.width() / 2, node.height() / 2)
                    ).toPoint(),
                )
                assert state.property("activeTool") == "Rectangle"
                bridge.workbench.gesture("Rectangle", [[10, 10], [42, 42]])
                assert not bridge.workbench.error, bridge.workbench.error
                assert bridge.roi_manager.records[-1].page_index == index
                bridge.measurements.measure()
                assert (
                    bridge.measurements.rows[-1]["value"] == 1024
                    and bridge.measurements.rows[-1]["page"] == index + 1
                )
                bridge.workbench.runtime.session += 1
                result = bridge.workbench.runtime.run(
                    frame, command="Multiply...", options="value=1"
                )
                processed = tifffile.imread(result["path"])
                np.testing.assert_array_equal(processed, oracle)
                assert processed.dtype == np.uint16
                row["pages"].append(
                    {
                        "page": index + 1,
                        "raw_uint16_equal": True,
                        "imagej_selection": True,
                        "area_pixel2": 1024,
                        "working_copy_equal": True,
                    }
                )
                if index == count - 1:
                    records_before = [
                        (r.id, r.paths, r.page_index)
                        for r in bridge.roi_manager.records
                    ]
                    bridge.requestWorkingCopy(result["path"])
                    wait(
                        lambda result=result: (
                            bridge.original_source.path == result["path"]
                            and not state.property("loading")
                        )
                    )
                    np.testing.assert_array_equal(
                        bridge.original_source.read_full(), oracle
                    )
                    assert (
                        state.property("tiffMode")
                        and not item("imagePrepareAnalysis").isVisible()
                    )
                    assert [
                        (r.id, r.paths, r.page_index)
                        for r in bridge.roi_manager.records
                    ] == records_before
                    row["roi_geometry_preserved"] = True
                    row["working_copy_viewer"] = "PASS"
                print(path.name + " page " + str(index + 1) + " PASS", flush=True)
                del frame, oracle, processed
            row["status"] = "PASS"
            report["files"].append(row)
        assert not report["qmlWarnings"], report["qmlWarnings"]
        assert (
            all(sha(p) == before[p] for p in paths) and sha(args.project) == project_sha
        )
        assert (
            not report["automatic_model_inference"]
            and not report["automatic_bpd_requests"]
            and not report["automatic_sync_requests"]
        )
        report["original_sha_preserved"] = True
        report["private_project_sha_preserved"] = True
        report["status"] = "PASS"
    finally:
        window.setProperty("allowQuit", True)
        window.close()
        bridge.waitForLoads()
        engine.deleteLater()
        app.processEvents()
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("PASS actual TIFF workbench:", args.output)


if __name__ == "__main__":
    main()
