"""Read-only actual TIFF ROI oracle/RHI/navigation and unchanged science in a new private project copy."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("QSG_RENDER_LOOP", "basic")

import numpy as np
import psutil
import tifffile
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.results.workspace import publish_dependencies
from sic_xrt_analyzer.ui.bridge import FileBridge

SCIENCE = (
    "analysis_runs",
    "observations",
    "predictions",
    "geometries",
    "defect_instances",
    "review_events",
    "model_provenance",
    "image_relationships",
)


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "FAIL",
        "physical_3d": "PHYSICAL_3D_NOT_READY",
        "tracking": "DEFECT_TRACKING_PRELIMINARY",
        "files": [],
        "new_inference": 0,
        "automatic_sync": 0,
        "physical_mouse_acceptance": False,
    }
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    b = FileBridge(
        parent=engine, settings=QSettings(str(out / "prefs.ini"), QSettings.IniFormat)
    )
    engine.addImageProvider("tiff", b.provider)
    engine.rootContext().setContextProperty("fileBridge", b)
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    engine.load(
        QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve()))
    )
    assert engine.rootObjects(), warnings
    w = engine.rootObjects()[0]
    w.setTitle("XRT TD-12 실제 TIFF ROI 검증")
    ui = w.findChild(QObject, "uiState")
    c = b.stack3d
    process = psutil.Process()
    rss = []
    frames = []
    w.frameSwapped.connect(lambda: frames.append(time.perf_counter()))

    def spin(predicate, timeout=180):
        end = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < end, (c.state, b.projects.state)
            app.processEvents()
            QTest.qWait(10)
            rss.append(process.memory_info().rss)

    def settled():
        spin(lambda: not c.busy and c.reader.task is None)

    def forbidden(*_args, **_kwargs):
        report["new_inference"] += 1
        raise AssertionError("No new TIFF/JPG inference allowed")

    b.pipeline.start = forbidden
    baseline = ProjectStore().load(args.project)
    snapshot = {name: getattr(baseline, name) for name in SCIENCE}
    originals = [Path(s.source_reference) for s in baseline.image_sources] + [
        args.project,
        Path("artifacts/models/research/model.onnx"),
        Path("artifacts/models/research/manifest.json"),
    ]
    before = {str(p): digest(p) for p in originals}
    project = out / "project.json"
    publish_dependencies(project, baseline, [], args.project)
    ProjectStore().save(project, baseline)
    try:
        b.projects.open(str(project))
        spin(lambda: not b.projects.busy and not c.busy and c.project is not None)
        # Existing 2D reader still handles original navigation. No global preload required for this test.
        b.stack_viewer._preload_enabled = False
        b.stack_viewer._reader.preload_enabled = False
        tiffs = [
            s
            for s in baseline.image_sources
            if s.acquisition_metadata.get("format") == "TIFF"
        ]
        assert len(tiffs) == 4
        for s in tiffs:
            ui.setProperty("workspaceIndex", 3)
            c.selectSource(s.source_id)
            settled()
            x, y = s.width // 2 - 128, s.height // 2 - 128
            assert c.configure(x, y, 256, 256, 0, s.page_count - 1, 1, 1)
            generate_started = time.perf_counter()
            start_frames = len(frames)
            c.generate()
            settled()
            ready = time.perf_counter()
            assert c.volume is not None and c.volume.pixels.dtype == np.uint16, c.state
            spin(
                lambda start_frames=start_frames: len(frames) > start_frames, timeout=15
            )
            QTest.qWait(120)
            assert c.state["rhi_available"] and w.findChild(
                QObject, "stack3dPerspective"
            ), c.state
            shape = c.volume.pixels.shape
            assert shape == (s.page_count, 256, 256)
            checks = []
            with tifffile.TiffFile(s.source_reference) as tif:
                for k in [0, s.page_count // 2, s.page_count - 1]:
                    oracle = tif.pages[k].asarray()[y : y + 256, x : x + 256]
                    assert np.array_equal(c.volume.pixels[k], oracle)
                    c.setPage(k)
                    settled()
                    c.setXY(120, 125)
                    settled()
                    assert c.state["position"] == [
                        x + 120,
                        y + 125,
                        k,
                        int(oracle[125, 120]),
                    ]
                    image = b.provider.stack3d_images[
                        next(
                            key
                            for key in b.provider.stack3d_images
                            if key.endswith("-xy")
                        )
                    ]
                    lo, hi = c.window
                    expected = int(
                        np.clip(
                            (float(oracle[125, 120]) - lo) * 255 / (hi - lo), 0, 255
                        )
                    )
                    assert abs(image.pixelColor(120, 125).red() - expected) <= 1
                    checks.append(
                        {
                            "page_1_based": k + 1,
                            "full_roi_uint16_equal": True,
                            "cursor_original_equal": True,
                            "display_window_equal": True,
                        }
                    )
                byte_order = tif.byteorder
            assert c.volume.byte_order == byte_order
            k, iy, ix = c.cursor
            assert c.hover(
                "xp", (ix + 0.5) / shape[2], (k + 0.5) / shape[0]
            ) == c.hover("xy", (ix + 0.5) / shape[2], (iy + 0.5) / shape[1])
            assert c.hover(
                "yp", (iy + 0.5) / shape[1], (k + 0.5) / shape[0]
            ) == c.hover("xy", (ix + 0.5) / shape[2], (iy + 0.5) / shape[1])
            # All pages' strips use the resident original array; compare independently on 3 sampled rows/columns.
            with tifffile.TiffFile(s.source_reference) as tif:
                for page in [0, s.page_count // 2, s.page_count - 1]:
                    oracle = tif.pages[page].asarray()[y : y + 256, x : x + 256]
                    assert np.array_equal(c.volume.pixels[page, iy, :], oracle[iy, :])
                    assert np.array_equal(c.volume.pixels[page, :, ix], oracle[:, ix])
            qml_im = w.grabWindow()
            assert not qml_im.isNull()
            qml_im.save(str(out / (s.source_id + "-3d-private.png")))
            c.newTrack("QA manual indexed observations", "QA-TD12")
            c.record("POINT", "QA-TD12", "UNCERTAIN")
            settled()
            c.setPage(0)
            settled()
            c.record("RECTANGLE", "QA-TD12", "PROPOSED")
            settled()
            save_start = time.perf_counter()
            c.save("QA-TD12")
            settled()
            save_ms = (time.perf_counter() - save_start) * 1000
            assert not c.manual_pending and c.session["coordinate_mode"] == "INDEXED"
            warm = []
            for page in [s.page_count // 2, s.page_count - 1, 0, s.page_count // 2]:
                start = time.perf_counter()
                c.setPage(page)
                settled()
                warm.append((time.perf_counter() - start) * 1000)
            original_expected = c.volume.original(*c.cursor)[:3]
            focus = []
            handler = lambda xx, yy, focus=focus: focus.append((xx, yy))
            c.focusRequested.connect(handler)
            c.openOriginal()
            try:
                spin(lambda focus=focus: bool(focus), timeout=360)
            except AssertionError:
                debug = {
                    "pending": str(c.pending_navigation),
                    "attempts": c.focus_attempts,
                    "timer": c.focus_timer.isActive(),
                    "stack": b.stackState,
                    "original": str(b.original_source),
                    "state": c.state,
                }
                out.joinpath("navigation-diagnostic.json").write_text(
                    json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                raise
            c.focusRequested.disconnect(handler)
            assert (
                b.original_source.path == s.source_reference
                and b.original_source.page_index == original_expected[2]
            )
            assert focus[-1] == tuple(map(float, original_expected[:2]))
            report["files"].append(
                {
                    "file": s.display_name,
                    "shape": list(shape),
                    "raw_bytes": c.volume.pixels.nbytes,
                    "byte_order": byte_order,
                    "pages": checks,
                    "all_selected_original_pages": list(range(s.page_count)),
                    "roi": [x, y, 256, 256],
                    "engine_extraction_ms": c.volume.seconds * 1000,
                    "generate_worker_ready_ms": (ready - generate_started) * 1000,
                    "slice_warm_ms": warm,
                    "texture_bytes": c.state["texture_bytes"],
                    "save_ms": save_ms,
                    "original_viewer_return": True,
                    "no_physical_depth": not c.physical,
                }
            )
        preserved = ProjectStore().load(project)
        assert all(
            getattr(preserved, name) == value for name, value in snapshot.items()
        )
        assert before == {str(p): digest(p) for p in originals}
        assert not warnings, warnings
        b.projects.open(str(project))
        spin(lambda: not b.projects.busy and not c.busy and c.session is not None)
        assert c.volume is None and c.tracks
        report.update(
            status="PASS",
            science_preserved={name: True for name in SCIENCE},
            original_model_baseline_sha_preserved=True,
            project_reopen_metadata=True,
            backend=c.state["backend"],
            qml_warnings=warnings,
            peak_rss_sampled_mib=max(rss) / 1024**2,
            render_loop=os.getenv("QSG_RENDER_LOOP"),
        )
    finally:
        out.joinpath("report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        b.waitForLoads()
        w.hide()
        engine.deleteLater()
    print(
        json.dumps(
            {
                "status": report["status"],
                "files": len(report["files"]),
                "peak_rss_mib": report["peak_rss_sampled_mib"],
            }
        )
    )


if __name__ == "__main__":
    main()
