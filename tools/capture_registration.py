"""Actual Qt/QTest comparison workflow captures. Synthetic pixels, no expert labels."""

import argparse
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.registration.engine import transform_points
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.workspace import add_source
from sic_xrt_analyzer.ui.bridge import FileBridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layout-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda rows: warnings.extend(r.toString() for r in rows))
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        bridge = FileBridge(
            parent=engine,
            settings=QSettings(str(folder / "prefs.ini"), QSettings.IniFormat),
        )
        engine.addImageProvider("tiff", bridge.provider)
        engine.rootContext().setContextProperty("fileBridge", bridge)
        engine.load(
            QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve()))
        )
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        state = window.findChild(QObject, "uiState")
        state.setProperty("workspaceIndex", 2)
        c = bridge.registration

        def spin(test):
            until = time.monotonic() + 45
            while not test():
                assert time.monotonic() < until, c.error
                app.processEvents()
                time.sleep(0.005)

        def settled():
            spin(lambda: not c.busy and not c.render_busy and c.reader.task is None)

        def all_items(node):
            yield node
            for child in node.childItems():
                yield from all_items(child)

        def item(name):
            return next(
                n for n in all_items(window.contentItem()) if n.objectName() == name
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
            app.processEvents()

        def capture(name):
            app.processEvents()
            QTest.qWait(40)
            assert window.grabWindow().save(str(args.output / (name + ".png")))

        rng = np.random.default_rng(114)
        pixels = np.zeros((1024, 1024, 3), np.uint8) + 30
        for i in range(600):
            cv2.circle(
                pixels,
                tuple(rng.integers(20, 1000, 2).tolist()),
                int(rng.integers(2, 10)),
                tuple(rng.integers(70, 240, 3).tolist()),
                -1,
            )
        matrix = np.array([[1, 0, 25], [0, 1, -15], [0, 0, 1]], float)
        after = cv2.warpAffine(pixels, matrix[:2], (1024, 1024))
        before_path = folder / "before.jpg"
        after_path = folder / "after.jpg"
        Image.fromarray(pixels).save(before_path, quality=98)
        Image.fromarray(after).save(after_path, quality=98)
        p = AnalysisProject("Before/After 합성 정합 검사")
        p, a = add_source(p, JpegImageSource(before_path))
        p, b = add_source(p, JpegImageSource(after_path))
        path = folder / "project.json"
        ProjectStore().save(path, p)
        bridge.projects.open(str(path))
        spin(lambda: not bridge.projects.busy)
        c.select(a.source_id, b.source_id)
        window.setWidth(1440)
        window.setHeight(900)
        QTest.qWait(60)
        capture("01-selection")
        click("registrationPrepare")
        capture("02-loading")
        settled()
        assert c.session is not None, c.error
        click("registrationRun")
        capture("03-estimating")
        settled()
        assert c.asset["status"] == "NEEDS_REVIEW", c.error
        capture("04-side")
        click("registrationMode-overlay")
        settled()
        capture("05-overlay")
        root = item("registrationWorkspace")
        root.setProperty("opacityValue", 0.8)
        capture("06-opacity")
        click("registrationMode-split")
        settled()
        root.setProperty("divider", 0.35)
        capture("07-split")
        click("registrationMode-difference")
        settled()
        capture("08-difference")
        c.fit()
        settled()
        c.beginLandmarks()
        root.setProperty("mode", "side")
        item("registrationMethod").setProperty("currentIndex", 4)
        item("registrationModel").setProperty("currentIndex", 1)
        QTest.qWait(100)
        settled()
        viewport = item("registrationViewport")
        width = viewport.width() / 2
        dpr = window.devicePixelRatio()
        # Actual point selection via QTest, not a prepopulated landmark mock.
        for xy in ([180, 190], [780, 220], [240, 790], [760, 730]):
            for side, index, pt in [
                ("before", 0, xy),
                ("after", 1, transform_points(matrix, [xy])[0]),
            ]:
                mapped = transform_points(c.frame["mapping"][index], [pt])[0] / dpr
                pos = viewport.mapToScene(
                    QPointF(mapped[0] + (width if index else 0), mapped[1])
                )
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, pos.toPoint())
                app.processEvents()
                QTest.qWait(30)
                settled()
        assert len(c.landmarks) == 4, c.landmarks
        capture("09-landmarks")
        click("registrationRun")
        settled()
        capture("10-quality")
        item("registrationReviewer").setProperty("text", "synthetic-qa-only")
        click("registrationApprove")
        settled()
        assert c.asset["status"] == "ACCEPTED", c.error
        capture("11-approved")
        bridge.projects.close()
        bridge.projects.open(str(path))
        spin(lambda: not bridge.projects.busy)
        settled()
        capture("12-reopened")
        assert c.asset["status"] == "ACCEPTED"
        layout = []
        for w, h in ((1100, 700), (1440, 900), (1920, 1080)):
            window.setWidth(w)
            window.setHeight(h)
            QTest.qWait(80)
            settled()
            capture(f"layout-{w}x{h}")
            for name in (
                "registrationPrepare",
                "registrationRun",
                "registrationApprove",
                "registrationViewport",
            ):
                node = item(name)
                pos = node.mapToScene(QPointF(0, 0))
                assert (
                    pos.x() >= 0
                    and pos.y() >= 0
                    and pos.x() + node.width() <= w + 1
                    and pos.y() + node.height() <= h + 1
                ), (name, w, h)
            layout.append(
                {
                    "size": [w, h],
                    "dpr": window.devicePixelRatio(),
                    "viewport": [c.width, c.height],
                    "coordinate_roundtrip_error": float(
                        np.linalg.norm(
                            transform_points(
                                np.linalg.inv(c.frame["mapping"][1]),
                                transform_points(c.frame["mapping"][1], [[500, 500]]),
                            )
                            - [500, 500]
                        )
                    ),
                }
            )
        root.setProperty("mode", "overlay")
        QTest.qWait(100)
        settled()
        frame_count = [0]

        def swapped():
            frame_count[0] += 1

        window.frameSwapped.connect(swapped)
        responses = []
        for value in np.linspace(0.05, 0.95, 20):
            before_frames = frame_count[0]
            ts = time.perf_counter()
            root.setProperty("opacityValue", float(value))
            window.update()
            spin(lambda: frame_count[0] > before_frames)
            responses.append((time.perf_counter() - ts) * 1000)
        render_count = c.revision
        root.setProperty("mode", "split")
        QTest.qWait(100)
        settled()
        split_revision = c.revision
        split_responses = []
        for value in np.linspace(0.05, 0.95, 20):
            before_frames = frame_count[0]
            ts = time.perf_counter()
            root.setProperty("divider", float(value))
            window.update()
            spin(lambda: frame_count[0] > before_frames)
            split_responses.append((time.perf_counter() - ts) * 1000)
        assert c.revision == split_revision, "divider must not decode/warp again"
        qt_performance = {
            "input": "synthetic",
            "alpha_to_frame_swapped_ms": responses,
            "split_to_frame_swapped_ms": split_responses,
            "alpha_frame_start_revision": render_count,
            "split_revision_stable": True,
            "decoder_count": c.session.decode_count,
            "backend": window.rendererInterface().graphicsApi().name,
            "dpr": window.devicePixelRatio(),
        }
        (args.output / "qt-performance.json").write_text(
            json.dumps(qt_performance, indent=2), encoding="utf-8"
        )
        if not args.layout_only:
            c.landmarks = [{"before": [10, 10], "after": [10, 10], "inlier": True}]
            c.run("manual", "affine")
            settled()
            assert c.asset["status"] == "REJECTED"
            capture("13-failed")
            bridge.projects.save()
            spin(lambda: not bridge.projects.busy)
            bridge.projects.close()
            before_path.unlink()
            bridge.projects.open(str(path))
            spin(lambda: not bridge.projects.busy)
            settled()
            assert not c.state["ready"]
            capture("14-missing-original")
        (args.output / "layout.json").write_text(
            json.dumps(
                {
                    "layouts": layout,
                    "warnings": warnings,
                    "manual_qtest_point_count": 4,
                    "input": "synthetic",
                    "acceptance": "automated_QTest_not_physical_mouse",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        assert not warnings, warnings
        bridge.waitForLoads()
        window.hide()
        engine.deleteLater()
        app.processEvents()
    print("PASS: Qt comparison workflow, landmarks, persistence and layouts")


if __name__ == "__main__":
    main()
