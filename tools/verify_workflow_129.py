"""Explicit, read-only real XRT workflow QA; captures stay in the chosen artifact directory."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke
from validate_review_workspace import ReviewSession, click

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.analysis.model_adapter import CancellationToken


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "stack", "model", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--skip-folder", action="store_true")
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["SIC_XRT_REPORT_DIR"] = str(out / "reports")
    os.environ["SIC_XRT_SYNC_DIR"] = str(out / "outbox")
    before = {str(x): sha(x) for x in (a.image, a.stack, a.model / "model.onnx")}
    app = QApplication([])
    for font in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(font).exists():
            QFontDatabase.addApplicationFont(font)
    app.setFont(QFont("Segoe UI", 9))
    QQuickStyle.setStyle("Basic")
    s = ReviewSession(app, out)
    b = s.bridge
    u = s.ui
    report = {"status": "RUNNING", "checks": [], "before": before}

    def check(name, condition):
        assert condition, name
        report["checks"].append(name)
        print(name, flush=True)

    def capture(name):
        app.processEvents()
        s.window.grabWindow().save(str(out / (name + ".png")))

    try:
        b.research.loadModel(str(a.model))
        spin(app, lambda: not b.research.loading, 120)
        check("model loaded", b.pipeline.adapter is not None)
        s.open(a.image.resolve())
        capture("01-image")
        click(s, "imagePrepareAnalysis")
        check("confirmation modal", s.item("analysisDialog").property("visible"))
        capture("02-confirm")
        progress = []
        captured = []

        def observe():
            if b.pipeline.state == AnalysisState.RUNNING:
                progress.append(
                    (dict(b.pipeline.progress), len(b.pipeline.live_detections))
                )
                if b.pipeline.live_detections and not captured:
                    captured.append(True)
                    capture("03-live-analysis")

        b.analysisChanged.connect(observe)
        t = time.perf_counter()
        click(s, "confirmAnalysis")
        spin(app, lambda: b.pipeline.state != AnalysisState.RUNNING, 300)
        check("analysis completed", b.analysis["hasResult"])
        report["elapsed_s"] = time.perf_counter() - t
        report["progress_events"] = len(progress)
        result = b.pipeline.result
        report["candidates"] = len(result.detections)
        report["regions"] = sum(
            bool(d.metadata.get("bpd_region")) for d in result.detections
        )
        check("real incremental candidates", any(count for _, count in progress))
        capture("04-results")
        click(s, "nextCandidate")
        capture("05-selected")
        click(s, "closeContextPanel")
        check(
            "close preserves result",
            b.pipeline.result is result and u.property("hasResult"),
        )
        click(s, "showCachedResult")
        check("reopen without inference", b.pipeline.result is result)
        capture("06-reopened")
        invoke(s.window, "selectWorkspace", 1)
        check(
            "other workspace hides results",
            not s.item("inspectorPanel").property("visible"),
        )
        invoke(s.window, "selectWorkspace", 0)
        check("return restores result", s.item("resultExplorer").isVisible())
        b.displayLayers.add(1280, 2300, 128, 128)
        capture("07-roi-layer")
        radius = []
        for scale in (1, 2, 4):
            s.set_zoom(scale)
            s.settle()
            radius.append(s.overlay.property("markerRadius"))
            capture("zoom-" + str(scale))
        check("markers never shrink", radius == sorted(radius) and min(radius) >= 6)
        report["marker_radius"] = radius
        # Same original crop/classifier path, only display annotation enabled above.
        from dataclasses import replace

        plain = b.pipeline.adapter.analyze_source(
            replace(
                result.request,
                parameters={
                    **dict(result.request.parameters),
                    "include_regions": False,
                },
            ),
            CancellationToken(),
        )
        check(
            "scores and original coordinates identical",
            all(
                (x.geometry, x.class_name, x.confidence, x.metadata["scores"])
                == (y.geometry, y.class_name, y.confidence, y.metadata["scores"])
                for x, y in zip(result.detections, plain.detections, strict=True)
            ),
        )
        invoke(s.window, "closeImage")
        check(
            "no image no results",
            not u.property("hasResult")
            and not s.item("inspectorPanel").property("visible"),
        )
        capture("08-empty")
        s.open(a.image.resolve())
        check(
            "file reopen uses cache",
            b.pipeline.result.analysis_id == result.analysis_id,
        )
        if not a.skip_folder:
            b.folderMap.open(str(a.image.parent))
            spin(app, lambda: not b.folderMap.state["busy"], 600)
            report["folder_images"] = len(b.folderMap.rows)
            report["folder_error"] = b.folderMap.error
            check("folder contact sheet", bool(b.folderMap.rows))
            invoke(s.window, "selectWorkspace", 1)
            capture("09-map")
            m = s.item("waferMapWorkspace")
            for _ in range(40):
                m.setProperty("scale", max(0.05, m.property("scale") / 1.15))
                app.processEvents()
            check("zoom-out never resets", m.property("scale") <= 0.05 + 1e-8)
        invoke(s.window, "selectWorkspace", 0)
        s.open(a.stack.resolve())
        check(
            "stack has no analysis",
            not s.item("imagePrepareAnalysis").property("visible"),
        )
        capture("10-stack")
        # Selected actual original region, indexed page volume; no spatial Z claim.
        u.setProperty("hasRoi", True)
        u.setProperty("roiStartX", 1024 / u.property("imageWidth"))
        u.setProperty("roiStartY", 1024 / u.property("imageHeight"))
        u.setProperty("roiEndX", 1088 / u.property("imageWidth"))
        u.setProperty("roiEndY", 1088 / u.property("imageHeight"))
        check(
            "selected stack ROI entry",
            b.stack3d.openViewerSelection(1024, 1024, 64, 64),
        )
        spin(app, lambda: not b.stack3d.busy and b.stack3d.reader.task is None, 300)
        check(
            "original ROI volume",
            b.stack3d.volume is not None
            and b.stack3d.volume.pixels.shape[1:] == (64, 64),
        )
        u.setProperty("workspaceIndex", 3)
        s.item("stack3dTabs").setProperty("currentIndex", 1)
        capture("11-3d-xy")
        check("no QML warnings", not s.warnings)
        report["after"] = {
            str(x): sha(x) for x in (a.image, a.stack, a.model / "model.onnx")
        }
        check("original SHA preserved", report["after"] == before)
        report["status"] = "PASS"
    finally:
        report["warnings"] = s.warnings
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        s.close()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
