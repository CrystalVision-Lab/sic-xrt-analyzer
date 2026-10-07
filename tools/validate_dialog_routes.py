"""QML accepted/rejected payload regression with read-only source files.

This injects selection payloads, not mouse input into a native Windows picker.
Use dialog_lifecycle_probe.py separately for actual native HWND stress.
Outputs (including copies) must be in ignored artifacts, outside source folders.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from roifile import ImagejRoi
from validate_rc_session import Session

from sic_xrt_analyzer.imaging.imagej_roi import load_rois


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jpeg", type=Path, required=True)
    parser.add_argument("--stack", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    for source in [args.jpeg, *args.stack]:
        if output.is_relative_to(source.resolve().parent):
            parser.error("Output must be separate from source folders")
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QSG_RENDER_LOOP", "basic")
    app = (QApplication if os.name == "nt" else QGuiApplication)([])
    QQuickStyle.setStyle("Basic")
    s = Session(app, output, Path("src/sic_xrt_analyzer/ui").resolve())

    report = None
    try:
        report = validate(s, args, output)
    finally:
        elapsed = s.close()
    report["shutdown_seconds"] = elapsed
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


def validate(s, args, output):
    def dialog(key):
        expression = QQmlExpression(
            QQmlEngine.contextForObject(s.window), s.window, key
        )
        value = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value[0] if isinstance(value, tuple) else value

    def accept(key, property_name, value):
        root = dialog(key)
        assert root.setProperty(property_name, value)
        assert QMetaObject.invokeMethod(root, "accepted")

    report = {
        "platform": s.app.platformName(),
        "method": "QML payload injection, not native human selection",
        "images": [],
    }
    single = output / "synthetic-single.tif"
    tifffile.imwrite(single, np.arange(512 * 512, dtype=np.uint16).reshape(512, 512))
    for source in [args.jpeg, single, *args.stack]:
        before = digest(source)
        accept("openDialog", "selectedFile", QUrl.fromLocalFile(str(source.resolve())))
        s.wait(
            lambda: (
                not s.state.property("opening")
                and not s.bridge.stack_viewer.initial_loading
            )
        )
        assert not s.state.property("loadError")
        assert s.bridge.original_source.path == str(source.resolve())
        assert s.panel.property("requestedContext") == "image"
        meta = s.bridge.original_source.metadata
        samples = []
        for index in sorted({0, meta.page_count // 2, meta.page_count - 1}):
            s.bridge.requestPage(index)
            s.wait(
                lambda: (
                    not s.bridge.stack_viewer.busy
                    and not s.bridge.stack_viewer.detail_busy
                )
            )
            assert s.state.property("pageIndex") == index
            samples.append(index)
        row = {
            "file": source.name,
            "width": meta.width,
            "height": meta.height,
            "dtype": meta.dtype,
            "pages": meta.page_count,
            "checked_pages": samples,
            "source_hash_unchanged": digest(source) == before,
        }
        assert row["source_hash_unchanged"]
        if meta.page_count == 1:
            copy = output / (source.stem + "-copy" + source.suffix)
            accept("imageSaveDialog", "selectedFile", QUrl.fromLocalFile(str(copy)))
            s.wait(lambda: not s.bridge.imagej.state["busy"])
            assert not s.bridge.imagej.state["error"], s.bridge.imagej.state["error"]
            assert digest(copy) == before
            row["copy_hash_exact"] = True
        report["images"].append(row)
        (output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf8"
        )
    # The model/result part uses a labelled synthetic adapter only.
    sys.path.insert(0, str(Path("tests").resolve()))
    from test_result_ux import DistributedCandidates

    rgb = output / "synthetic-rgb.tif"
    tifffile.imwrite(rgb, np.zeros((512, 512, 3), dtype=np.uint8), photometric="rgb")
    s.bridge.pipeline.adapter = DistributedCandidates()
    s.open(rgb)
    s.click("imagePrepareAnalysis")
    s.click("contextRunAnalysis")
    s.wait(lambda: s.bridge.analysis["hasResult"])
    result = s.bridge.pipeline.result
    roi = output / "synthetic.roi"
    ImagejRoi.frompoints([[40, 50], [100, 120], [160, 80]]).tofile(roi)
    accept("roiDialog", "selectedFiles", [QUrl.fromLocalFile(str(roi))])
    s.wait(lambda: bool(s.bridge.roi_manager.records))
    records = tuple(s.bridge.roi_manager.records)
    target = output / "RoiSet-copy.zip"
    accept("roiSaveDialog", "selectedFile", QUrl.fromLocalFile(str(target)))
    s.wait(
        lambda: (
            s.bridge.roi_exporter.task is None and s.bridge.roi_exporter.pending is None
        )
    )
    loaded, errors = load_rois([target], s.bridge.original_source.metadata)
    assert not errors and len(loaded) == len(records)
    assert (
        loaded[0].paths == records[0].paths
        and loaded[0].page_index == records[0].page_index
    )
    report["roi_import_export"] = "PASS"
    snapshot = (
        s.bridge.original_source.identity,
        result,
        tuple(s.bridge.roi_manager.records),
        s.state.property("activeTool"),
        s.panel.property("requestedContext"),
    )
    for key in (
        "openDialog",
        "imageSaveDialog",
        "roiDialog",
        "roiSaveDialog",
        "resultsDialog",
    ):
        root = dialog(key)
        assert QMetaObject.invokeMethod(root, "open")
        assert root.property("visible")
        assert QMetaObject.invokeMethod(root, "reject")
        s.app.processEvents()
        assert not root.property("visible")
        assert snapshot == (
            s.bridge.original_source.identity,
            s.bridge.pipeline.result,
            tuple(s.bridge.roi_manager.records),
            s.state.property("activeTool"),
            s.panel.property("requestedContext"),
        )
    report["pending_cancel_preserves_source_result_roi_context"] = "PASS"
    accept("resultsDialog", "selectedFolder", QUrl.fromLocalFile(str(output)))
    exported = Path(s.bridge.research.export_path)
    payload = json.loads((exported / "result.json").read_text(encoding="utf8"))
    with (exported / "predictions.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        count = len(list(csv.DictReader(stream)))
    assert count == len(result.detections) == 2946
    accept("resultsDialog", "selectedFolder", QUrl.fromLocalFile(str(output)))
    second = Path(s.bridge.research.export_path)
    assert payload == json.loads((second / "result.json").read_text(encoding="utf8"))
    report["result_json_csv"] = {
        "synthetic_adapter": True,
        "rows": count,
        "unchanged_after_cancel": True,
    }
    accept(
        "openDialog", "selectedFile", QUrl.fromLocalFile(str(output / "missing.tif"))
    )
    s.wait(lambda: not s.state.property("opening"))
    assert s.state.property("loadError")
    assert s.bridge.original_source.path == str(rgb.resolve())
    s.open(rgb)
    assert not s.state.property("loadError")
    assert not s.bridge.analysis["hasResult"] and not s.bridge.roi_manager.records
    report["invalid_open_and_file_switch_recovery"] = "PASS"
    report["qml_warnings"] = s.warnings
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    return report


if __name__ == "__main__":
    main()
