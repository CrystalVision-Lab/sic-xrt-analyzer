"""Actual Main.qml/RHI automated input and synthetic-only screenshots. No physical acceptance."""

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QSG_RENDER_LOOP", "basic")

import numpy as np
import psutil
import tifffile
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source
from sic_xrt_analyzer.ui.bridge import FileBridge


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plane(k):
    y, x = np.indices((768, 768))
    a = (8000 + (x * 18 + y * 10 + k * 200) % 45000).astype(np.uint16)
    a[300 + k % 60, 300 + k % 60] = 65535
    a[350:370, 350 + k % 40] = 60000
    a[360, 350:390] = 60000
    if k % 19 == 0:
        a[320:380, 320:400] = 8000
    return a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    for f in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/malgun.ttf"]:
        if Path(f).exists():
            QFontDatabase.addApplicationFont(f)
    app.setFont(QFont("Segoe UI", 9))
    report = {
        "status": "RUNNING",
        "input": "SYNTHETIC",
        "physical_3d": "PHYSICAL_3D_NOT_READY",
        "tracking": "DEFECT_TRACKING_PRELIMINARY",
        "acceptance": "QTest automated, not physical mouse",
        "render_loop": os.getenv("QSG_RENDER_LOOP"),
        "layouts": [],
    }
    process = psutil.Process()
    rss = []
    with TemporaryDirectory(dir=args.output.resolve()) as folder:
        folder = Path(folder)
        assert folder.resolve().is_relative_to(args.output.resolve())
        path = folder / "QA-synthetic-stack.tif"
        tifffile.imwrite(
            path,
            data=(plane(k) for k in range(96)),
            shape=(96, 768, 768),
            dtype=np.uint16,
            photometric="minisblack",
            imagej=True,
            metadata={"axes": "TYX"},
        )
        original_sha = digest(path)
        p, s = add_source(
            AnalysisProject("QA SYNTHETIC indexed structure"), OriginalImageSource(path)
        )
        s = verify_content_hash(s)
        p = p.evolve(image_sources=(s,))
        project = folder / "project.json"
        ProjectStore().save(project, p)
        engine = QQmlApplicationEngine()
        b = FileBridge(
            parent=engine,
            settings=QSettings(str(folder / "prefs.ini"), QSettings.IniFormat),
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
        w.setTitle("XRT TD-12 3D 검증")
        ui = w.findChild(QObject, "uiState")
        c = b.stack3d
        times = []
        w.frameSwapped.connect(lambda: times.append(time.perf_counter()))

        def spin(predicate, timeout=120):
            end = time.monotonic() + timeout
            while not predicate():
                assert time.monotonic() < end, ("timeout", c.state, warnings)
                app.processEvents()
                QTest.qWait(5)

        def settled():
            spin(lambda: not c.busy and c.reader.task is None)

        def shot(name):
            previous = (w.width(), w.height())
            controls = w.findChild(QObject, "stack3dControls")
            flick = controls.property("contentItem")
            show_track = name[:2] in {"11", "12", "13", "14"}
            for width, height in [(1100, 700), (1440, 900), (1920, 1080)]:
                w.resize(width, height)
                app.processEvents()
                QTest.qWait(120)
                reviewer = w.findChild(QObject, "stack3dReviewer")
                if show_track:
                    fy = reviewer.mapToItem(
                        flick.property("contentItem"), QPointF(0, 0)
                    ).y()
                    flick.setProperty(
                        "contentY",
                        max(
                            0,
                            min(
                                fy - 70,
                                flick.property("contentHeight") - flick.height(),
                            ),
                        ),
                    )
                else:
                    flick.setProperty("contentY", 0)
                app.processEvents()
                QTest.qWait(50)
                im = w.grabWindow()
                assert not im.isNull()
                target = args.output / f"{width}x{height}"
                target.mkdir(exist_ok=True)
                assert im.save(str(target / (name + ".png")))
                rss.append(process.memory_info().rss)
            w.resize(*previous)
            app.processEvents()

        def tab(index):
            w.findChild(QObject, "stack3dTabs").setProperty("currentIndex", index)
            QTest.qWait(120)

        def click(name):
            item = w.findChild(QObject, name)
            assert item, name
            xy = item.mapToScene(item.boundingRect().center())
            QTest.mouseClick(
                w, Qt.LeftButton, Qt.NoModifier, QPoint(round(xy.x()), round(xy.y()))
            )

        ui.setProperty("workspaceIndex", 3)
        shot("01-entry-empty")
        b.projects.open(str(project))
        spin(lambda: not b.projects.busy and c.source is not None and not c.busy)
        shot("02-tiff-source")
        c.configure(256, 256, 256, 256, 0, 95, 1, 1)
        shot("03-original-roi")
        shot("04-page-range")
        start = time.perf_counter()
        c.generate()
        shot("05-generating")
        settled()
        report["volume_ready_ms"] = (time.perf_counter() - start) * 1000
        assert c.state["rhi_available"], c.state["backend"]
        report["backend"] = c.state["backend"]
        shot("06-perspective")
        report["engine_extraction_ms"] = c.volume.seconds * 1000
        report["display_prepare_ms"] = c.state["slice_prepare_ms"]
        report["shape"] = c.state["shape"]
        report["raw_bytes"] = c.state["raw_bytes"]
        report["texture_bytes"] = c.state["texture_bytes"]
        report["frames_after_ready"] = len(times)
        for index, name in [(1, "07-xy"), (2, "08-x-page"), (3, "09-y-page")]:
            tab(index)
            shot(name)
        c.setPage(47)
        settled()
        shot("10-page-slider")
        # Root window receives actual input. 3D picking uses the current rendered plane revision.
        tab(0)
        area = w.findChild(QObject, "stack3dOrbitInput")
        assert area
        centre = area.mapToScene(area.boundingRect().center())
        pos = QPoint(round(centre.x()), round(centre.y()))
        input_timings = []
        swap_delays = []
        start_frames = len(times)
        for n in range(8):
            before = len(times)
            started = time.perf_counter()
            QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, pos)
            QTest.mouseMove(w, pos + QPoint(30 + n, 12))
            QTest.mouseRelease(
                w, Qt.LeftButton, Qt.NoModifier, pos + QPoint(30 + n, 12)
            )
            submit = time.perf_counter()
            spin(lambda before=before: len(times) > before, timeout=10)
            input_timings.append((submit - started) * 1000)
            swap_delays.append((times[before] - started) * 1000)
        camera_before = list(c.camera)
        for _n in range(4):
            event = QWheelEvent(
                QPointF(pos),
                QPointF(pos),
                QPoint(),
                QPoint(0, 120),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.NoScrollPhase,
                False,
            )
            QGuiApplication.sendEvent(w, event)
            QTest.qWait(20)
        assert c.camera[4] < camera_before[4]
        QTest.mousePress(w, Qt.RightButton, Qt.NoModifier, pos)
        QTest.mouseMove(w, pos + QPoint(30, 20))
        QTest.mouseRelease(w, Qt.RightButton, Qt.NoModifier, pos + QPoint(30, 20))
        assert c.camera[2:4] != [0, 0]
        report["qtest_orbit_submit_ms"] = input_timings
        report["qtest_orbit_to_qt_frameSwapped_ms"] = swap_delays
        report["frameSwapped_is_not_physical_display_latency"] = True
        report["window_active_at_benchmark"] = w.isActive()
        report["window_exposed"] = w.isExposed()
        report["orbit_frames"] = len(times) - start_frames
        c.newTrack("QA manual observations", "QA")
        c.setPage(0)
        settled()
        c.setXY(60, 60)
        settled()
        c.record("POINT", "QA", "PROPOSED")
        settled()
        shot("11-manual-track")
        c.setPage(47)
        settled()
        c.setXY(100, 96)
        settled()
        c.record("RECTANGLE", "QA", "UNCERTAIN")
        settled()
        c.setPage(95)
        settled()
        c.setXY(120, 112)
        settled()
        c.record("POINT", "QA", "REVIEWED")
        settled()
        shot("12-track-3d-overlay")
        assert len(c.scene["markers"]) == 3 and len(c.scene["segments"]) == 28
        c.save("QA")
        settled()
        shot("13-saved-session")
        assert c.session["revision"] == 1
        b.projects.open(str(project))
        spin(lambda: not b.projects.busy and not c.busy and c.session is not None)
        shot("14-restored-metadata")
        assert c.volume is None and len(c.tracks) == 1
        c.generate()
        settled()
        shot("16-indexed-depth-unverified")
        assert not c.configure(0, 0, 768, 768, 0, 95, 1, 1)
        shot("17-memory-limit")
        assert "64 MiB" in c.error
        c.generate()
        c.cancel()
        spin(lambda: c.reader.task is None)
        shot("18-cancelled")
        assert c.volume is None
        c.generate()
        settled()
        tab(0)
        for width, height in [(1100, 700), (1440, 900), (1920, 1080)]:
            w.resize(width, height)
            app.processEvents()
            QTest.qWait(200)
            shot(f"layout-{width}x{height}")
            workspace = w.findChild(QObject, "stack3dWorkspace")
            assert workspace.width() > 0 and workspace.height() > 0
            report["layouts"].append(
                {
                    "size": [width, height],
                    "dpr": w.devicePixelRatio(),
                    "workspace": [workspace.width(), workspace.height()],
                }
            )
        report["original_sha_preserved"] = digest(path) == original_sha
        assert report["original_sha_preserved"]
        path.rename(folder / "missing-original.tif")
        b.projects.open(str(project))
        spin(lambda: not b.projects.busy and not c.busy and c.session is not None)
        shot("15-original-missing")
        assert c.volume is None and c.state["source"]["status"] == "MISSING"
        assert not warnings, warnings
        report["warnings"] = warnings
        report["peak_rss_sampled_mib"] = max(rss) / 1024**2
        report["status"] = "PASS"
        b.waitForLoads()
        w.hide()
        engine.deleteLater()
    args.output.joinpath("report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "backend": report["backend"],
                "peak_rss_mib": report["peak_rss_sampled_mib"],
                "orbit_frame_median_ms": statistics.median(
                    report["qtest_orbit_to_qt_frameSwapped_ms"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
