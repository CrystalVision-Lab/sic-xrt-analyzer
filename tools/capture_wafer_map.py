"""Actual Main.qml/QTest map workflow with synthetic inputs; never expert acceptance."""

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_result_domain import MANIFEST, legacy, review

from sic_xrt_analyzer.analysis.contracts import AnalysisScope, Region
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.adapter import import_legacy_result
from sic_xrt_analyzer.results.contracts import (
    DefectInstance,
    ExistenceDecision,
    GeometryDecision,
    ReviewStatus,
)
from sic_xrt_analyzer.results.geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
    GraphEdge,
    GraphNode,
)
from sic_xrt_analyzer.results.workspace import add_source
from sic_xrt_analyzer.ui.bridge import FileBridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QGuiApplication([])
    for font_path in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/malgun.ttf"):
        if Path(font_path).exists():
            assert QFontDatabase.addApplicationFont(font_path) >= 0
    app.setFont(QFont("Malgun Gothic", 9))
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    with TemporaryDirectory(dir=args.output.resolve()) as temporary:
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
        window.setWidth(1440)
        window.setHeight(900)
        state = window.findChild(QObject, "uiState")
        state.setProperty("workspaceIndex", 1)
        c = bridge.waferMap

        def spin(test, timeout=45):
            until = time.monotonic() + timeout
            while not test():
                assert time.monotonic() < until, c.error
                app.processEvents()
                time.sleep(0.003)

        def settled():
            spin(
                lambda: (
                    not bridge.projects.busy and not c.busy and c.reader.task is None
                )
            )
            QTest.qWait(50)

        def nodes(node):
            yield node
            for child in node.childItems():
                yield from nodes(child)

        def item(name):
            return next(
                n for n in nodes(window.contentItem()) if n.objectName() == name
            )

        def click_node(n):
            assert n.isVisible() and n.isEnabled(), n.objectName()
            QTest.mouseClick(
                window,
                Qt.LeftButton,
                Qt.NoModifier,
                n.mapToScene(QPointF(n.width() / 2, n.height() / 2)).toPoint(),
            )
            app.processEvents()
            QTest.qWait(20)

        def click(name):
            click_node(item(name))

        def popup_button(name, text):
            popup = window.findChild(QObject, name)
            footer = popup.property("footer")
            button = next(
                n
                for n in nodes(footer)
                if str(n.property("text")).replace("&", "")
                in (text, {"Apply": "적용", "Save": "저장", "OK": "확인"}.get(text))
                and n.isVisible()
            )
            click_node(button)

        def fill(name, value):
            n = item(name)
            click_node(n)
            QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
            # QTest's QWindow overload has individual ASCII keys.
            for letter in str(value):
                if letter == "\n":
                    QTest.keyClick(window, Qt.Key_Return)
                else:
                    QTest.keyClick(window, letter)
            app.processEvents()
            assert n.property("text") == str(value), (name, n.property("text"))

        def capture(name):
            app.processEvents()
            QTest.qWait(70)
            image = window.grabWindow()
            assert not image.isNull()
            assert image.save(str(args.output / (name + ".png")))

        capture("01-empty")
        pixels = np.zeros((512, 640, 3), np.uint8) + 28
        yy, xx = np.indices((512, 640))
        pixels[:, :, 0] += (xx % 90).astype(np.uint8)
        pixels[:, :, 1] += (yy % 90).astype(np.uint8)
        pixels[180:280, 250:400, :] = [90, 125, 110]
        paths = [folder / "QA-before.jpg", folder / "QA-after.jpg"]
        for i, path in enumerate(paths):
            Image.fromarray(np.roll(pixels, i * 20, axis=1)).save(path, quality=95)
        source = JpegImageSource(paths[0])
        p = import_legacy_result(
            AnalysisProject("QA SYNTHETIC · actual wafer coordinates unavailable"),
            legacy(source, count=2946),
            model_manifest=MANIFEST,
        )
        roi = legacy(source, count=791)
        roi = replace(
            roi,
            request=replace(
                roi.request, scope=AnalysisScope.ROI, roi=Region(0, 0, 640, 512)
            ),
        )
        p = import_legacy_result(p, roi, model_manifest=MANIFEST)
        sid = p.image_sources[0].source_id
        p, other = add_source(p, JpegImageSource(paths[1]))
        shapes = [
            DefectGeometry(
                str(uuid4()),
                sid,
                0,
                DefectGeometryKind.POLYLINE,
                GeometrySource.HUMAN,
                points=((140, 120), (190, 210), (310, 290)),
            ),
            DefectGeometry(
                str(uuid4()),
                sid,
                0,
                DefectGeometryKind.POLYGON,
                GeometrySource.HUMAN,
                points=((380, 120), (520, 160), (450, 290)),
            ),
            DefectGeometry(
                str(uuid4()),
                sid,
                0,
                DefectGeometryKind.MASK_REFERENCE,
                GeometrySource.HUMAN,
                bbox=(240, 300, 120, 90),
                mask_reference="geometry/references/QA-mask.png",
                mask_encoding="png",
            ),
            DefectGeometry(
                str(uuid4()),
                sid,
                0,
                DefectGeometryKind.BRANCHED_GRAPH,
                GeometrySource.HUMAN,
                nodes=(
                    GraphNode("a", 180, 350),
                    GraphNode("b", 100, 450),
                    GraphNode("c", 320, 460),
                ),
                edges=(
                    GraphEdge("ab", "a", "b", ((180, 350), (150, 400), (100, 450))),
                    GraphEdge("ac", "a", "c"),
                ),
            ),
        ]
        instances = [
            DefectInstance(
                str(uuid4()),
                sid,
                g.geometry_id,
                class_label="BPD",
                instance_status="HUMAN" if n < 3 else "PROPOSED",
            )
            for n, g in enumerate(shapes)
        ]
        p = p.evolve(
            geometries=(*p.geometries, *shapes), defect_instances=tuple(instances)
        )
        corrected = review(
            p,
            status=ReviewStatus.CORRECTED,
            geometry_decision=GeometryDecision.CORRECTED,
            corrected_geometry_reference=shapes[0].geometry_id,
            existence=ExistenceDecision.PRESENT,
        )
        conflicting = review(
            p, reviewer="QA-disagreement", existence=ExistenceDecision.ABSENT
        )
        p = replace(p, schema_version="1.1.0").evolve(
            review_events=(corrected, conflicting)
        )
        path = folder / "project.json"
        ProjectStore().save(path, p)
        bridge.projects.open(str(path))
        settled()
        c.select(sid)
        capture("02-unplaced")
        click("mapPlace")
        capture("03-placement-dialog")
        for name, value in (
            ("mapX", 0),
            ("mapY", 0),
            ("mapAngle", 18),
            ("mapScaleX", 0.4),
            ("mapScaleY", 0.3),
        ):
            fill(name, value)
        popup_button("mapPlacementDialog", "Apply")
        settled()
        c.setRun(sid, p.analysis_runs[0].run_id)
        c.select(other.source_id)
        c.place(330, 45, -12, 0.4, 0.3)
        c.fit()
        settled()
        c.select(sid)
        capture("04-temporary-rotated-footprints")
        assert sum(c.state["summary"].get(k, 0) for k in ("BPD", "TED", "TSD")) == 2946
        canvas = item("waferMapCanvas")
        # Real drag in tile-edit mode followed by real Undo click.
        click("mapEdit")
        row = next(t for t in c.frame["tiles"] if t["source_id"] == sid)
        border = np.asarray(row["border"])
        xy = border.mean(0)
        pos = canvas.mapToScene(QPointF(*xy)).toPoint()
        initial = np.asarray(c.selectedPlacement()["matrix"])
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, pos)
        QTest.mouseMove(window, pos + QPointF(35, 25).toPoint(), 50)
        QTest.mouseRelease(
            window, Qt.LeftButton, Qt.NoModifier, pos + QPointF(35, 25).toPoint()
        )
        settled()
        assert not np.allclose(c.selectedPlacement()["matrix"], initial)
        capture("05-dragged")
        click("mapUndo")
        settled()
        assert np.allclose(c.selectedPlacement()["matrix"], initial)
        click("mapEdit")
        for only in ("BPD", "TED", "TSD"):
            for label in ("BPD", "TED", "TSD"):
                c.setLayer(label, label == only)
            settled()
            capture("06-layer-" + only)
        for label in ("BPD", "TED", "TSD"):
            c.setLayer(label, True)
        settled()
        capture("07-review-human-graph-mask-bounds")
        assert c.state["summary"]["human"] == 3
        assert c.state["summary"]["experimental"] == 1
        assert c.state["summary"]["conflicts"] == 1
        c.setRun(sid, p.analysis_runs[1].run_id)
        settled()
        assert sum(c.state["summary"].get(k, 0) for k in ("BPD", "TED", "TSD")) == 791
        capture("08-roi-run")
        c.setRun(sid, p.analysis_runs[0].run_id)
        settled()
        # Actual point click with persisted Source/Run/target, then Viewer focus.
        target = next(r for r in c.frame["paths"] if r["layer"] == "BPD")
        pt = target["paths"][0][0]
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            canvas.mapToScene(QPointF(*pt)).toPoint(),
        )
        app.processEvents()
        assert c.selected_target and c.selected_target["source_id"] == sid
        capture("09-target-selected")
        click("mapResult")
        spin(
            lambda: (
                state.property("workspaceIndex") == 0
                and not bridge.projects.busy
                and not bridge.stack_viewer.busy
                and bridge.projects.selected_source == sid
            )
        )
        capture("10-candidate-viewer")
        assert bridge.projects.selected_source == sid
        state.setProperty("workspaceIndex", 1)
        settled()
        c.select(sid)
        click("mapCompare")
        capture("11-comparison-dialog")
        click("mapCompareOpen")
        spin(lambda: state.property("workspaceIndex") == 2)
        assert {bridge.registration.before_id, bridge.registration.after_id} == {
            sid,
            other.source_id,
        }
        capture("12-comparison-workspace")
        state.setProperty("workspaceIndex", 1)
        settled()
        c.select(sid)
        click("mapSave")
        fill("mapEditor", "QA-local")
        capture("13-save-dialog")
        popup_button("mapSaveDialog", "Save")
        settled()
        assert not c.error and not c.dirty, c.error
        bridge.projects.close()
        bridge.projects.open(str(path))
        settled()
        c.fit()
        settled()
        capture("14-reopened")
        layouts = []
        for w, h in ((1100, 700), (1440, 900), (1920, 1080)):
            window.setWidth(w)
            window.setHeight(h)
            QTest.qWait(80)
            c.fit()
            settled()
            for name in (
                "waferMapCanvas",
                "mapFit",
                "mapSave",
                "mapResult",
                "mapCompare",
            ):
                node = item(name)
                point = node.mapToScene(QPointF(0, 0))
                assert (
                    point.x() >= 0
                    and point.y() >= 0
                    and point.x() + node.width() <= w + 1
                    and point.y() + node.height() <= h + 1
                ), (name, w, h, point, node.width())
            capture(f"layout-{w}x{h}")
            layouts.append(
                {
                    "size": [w, h],
                    "dpr": window.devicePixelRatio(),
                    "canvas": [c.width, c.height],
                }
            )
        # Real QML wheel dispatch; original-pixel anchor must stay fixed.
        tile_before = next(t for t in c.frame["tiles"] if t["source_id"] == sid)
        anchor = [c.width * 0.55, c.height * 0.45]
        from sic_xrt_analyzer.wafer_map.mapping import inverse, points

        original_anchor = points(inverse(tile_before["matrix"]), [anchor])[0]
        zoom_before = c.zoom
        canvas = item("waferMapCanvas")
        location = canvas.mapToScene(QPointF(*anchor))
        event = QWheelEvent(
            location,
            window.mapToGlobal(location),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        app.sendEvent(window, event)
        settled()
        assert c.zoom > zoom_before
        tile_after = next(t for t in c.frame["tiles"] if t["source_id"] == sid)
        anchor_error = float(
            np.linalg.norm(
                np.asarray(points(inverse(tile_after["matrix"]), [anchor])[0])
                - original_anchor
            )
        )
        assert anchor_error < 1e-9
        initial_urls = item("waferMapWorkspace").property("loadedUrls").toVariant()
        initial_decodes = c.scene.decode_count
        timings = []
        for n in range(20):
            ts = time.perf_counter()
            pos = canvas.mapToScene(QPointF(c.width / 2, c.height / 2)).toPoint()
            delta = QPoint(5 * (-1) ** n, 3)
            QTest.mousePress(window, Qt.RightButton, Qt.NoModifier, pos)
            QTest.mouseMove(window, pos + delta, 1)
            QTest.mouseRelease(window, Qt.RightButton, Qt.NoModifier, pos + delta)
            wheel = QWheelEvent(
                QPointF(pos),
                window.mapToGlobal(QPointF(pos)),
                QPoint(),
                QPoint(0, 120 if n % 2 else -120),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.NoScrollPhase,
                False,
            )
            app.sendEvent(window, wheel)
            settled()
            window.grabWindow()
            timings.append((time.perf_counter() - ts) * 1000)
        assert c.scene.decode_count == initial_decodes
        assert (
            item("waferMapWorkspace").property("loadedUrls").toVariant() == initial_urls
        )
        # Deliberate synthetic-only physical input; no actual wafer proof asserted.
        c.addGroup(
            "QA SYNTHETIC physical controls",
            "PHYSICAL",
            "QA-WAFER",
            "QA-XY",
            "mm",
            "QA measured origin",
            "X_RIGHT_Y_DOWN",
            "synthetic known geometry",
            "4 5 10",
            "QA-only",
        )
        c.select(sid)
        c.place(1, 2, 0, 0.01, 0.02)
        c.fit()
        settled()
        capture("15-physical-unverified")
        click("mapVerify")
        fill("mapCalibrationPoints", "10 10 1.1 2.2\n600 10 7 2.2\n10 480 1.1 11.6")
        fill("mapCalibrationSource", "QA-independent")
        fill("mapCalibrationReviewer", "QA-only")
        fill("mapCalibrationTolerance", "0.005")
        capture("16-physical-calibration-dialog")
        popup_button("mapVerifyDialog", "OK")
        settled()
        assert c.selectedPlacement()["status"] == "VERIFIED", c.error
        capture("17-physical-synthetic-verified")
        c.discard()
        settled()
        paths[0].unlink()
        c.requestFrame(c.width, c.height)
        settled()
        assert (
            next(t for t in c.frame["tiles"] if t["source_id"] == sid)["availability"]
            == "MISSING"
        )
        capture("18-original-missing-outline")
        assert not warnings, warnings
        report = {
            "status": "PASS",
            "input": "synthetic",
            "physical_mapping": "NOT_REAL_PHYSICAL_ACCEPTANCE",
            "acceptance": "automated_QTest_not_physical_mouse",
            "warnings": warnings,
            "layouts": layouts,
            "backend": window.rendererInterface().graphicsApi().name,
            "qtest_pan_wheel_settle_and_grab_ms_includes_50ms_wait": timings,
            "mouse_wheel_anchor_error_original_px": anchor_error,
            "pan_zoom_preview_urls_and_decode_count_stable": True,
            "cache_items": len(c.scene.previews),
            "counts_full": 2946,
            "counts_roi": 791,
            "human": 3,
            "experimental": 1,
            "review_conflicts": 1,
        }
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        bridge.waitForLoads()
        window.hide()
        engine.deleteLater()
        app.processEvents()
    print("PASS: Main.qml map QTest workflow, persistence, shapes and layouts")


if __name__ == "__main__":
    main()
