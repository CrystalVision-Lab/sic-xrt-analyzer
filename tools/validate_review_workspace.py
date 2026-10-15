"""Private real/synthetic Qt researcher-review QA. Originals are read-only."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from benchmark_viewer_interaction import Session
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.results.serialization import plain


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(data)
    return sha.hexdigest()


def progress(message):
    print(message, flush=True)


def settle(s):
    s.window.grabWindow()
    QTest.qWait(70)


def wait(s):
    spin(s.app, lambda: not s.bridge.projects.busy, 240)
    assert not s.bridge.projects.error, s.bridge.projects.error


def click(s, name, scroll=False):
    settle(s)
    item = s.item(name)
    if scroll:
        workspace = s.item("reviewWorkspace")
        flick = workspace.property("contentItem")
        y = (
            item.mapToScene(QPointF()).y()
            - workspace.mapToScene(QPointF()).y()
            + float(flick.property("contentY"))
            - 130
        )
        flick.setProperty("contentY", max(0, y))
        settle(s)
    assert item.isVisible() and item.property("enabled"), name
    pos = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    assert 0 <= pos.x() < s.window.width() and 0 <= pos.y() < s.window.height(), (
        name,
        pos,
    )
    QTest.mouseClick(
        s.window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y()))
    )
    QTest.qWait(60)


def science(p):
    return {
        name: plain(getattr(p, name))
        for name in ("analysis_runs", "observations", "predictions", "model_provenance")
    }


def exports(s, folder):
    assert s.bridge.research.exportResult(str(folder)), s.bridge.research.error
    return {
        p.name: p.read_bytes() for p in Path(s.bridge.research.export_path).iterdir()
    }


class ReviewSession(Session):
    def item(self, name):
        obj = self.window.findChild(QObject, name)
        if obj is not None:
            return obj
        pending = [self.window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise AssertionError(name)


def replay_workspace(args, app, out):
    original_sha = digest(args.project)
    original = ProjectStore().load(args.project)
    folder = out / "session"
    folder.mkdir()
    s = ReviewSession(app, folder)
    report = {"status": "FAIL", "fresh_os_process": True, "new_model_inference": 0}
    try:
        c = s.bridge.projects
        r = s.bridge.research
        v = s.bridge.reviews
        c.open(str(args.project.resolve()))
        wait(s)
        event = next(
            e
            for e in original.review_events
            if e.target_type.value == "OBSERVATION"
            and e.reviewer_id == "qa-researcher-a"
            and e.class_decision.value == "TED"
        )
        c.selectRun(event.source_run_id)
        wait(s)
        spin(
            app,
            lambda: (
                r.saved is not None
                and r.pixels_available
                and not s.bridge.stack_viewer.initial_loading
            ),
            240,
        )
        observation = next(
            o for o in original.observations if o.observation_id == event.target_id
        )
        r.selectCandidate(observation.source_candidate_id)
        v.setReviewer(event.reviewer_id)
        assert v.enter() and v.state["history"] and v.classification == "TED"
        assert v.state["selected"]["conflict"]
        for e in original.review_events:
            if e.corrected_geometry_reference:
                v.cancel()
                assert v.select(e.target_type.value, e.target_id)
                assert any(
                    g["geometry_id"] == e.corrected_geometry_reference
                    for g in v.state["corrected"]
                )
        manual = next(
            i
            for i in original.defect_instances
            if i.instance_status == "HUMAN" and not i.linked_observations
        )
        v.cancel()
        assert v.select("DEFECT_INSTANCE", manual.instance_id)
        assert v.state["selected"]["manual"] and v.state["history"]
        assert (
            c.project == original and not c.dirty and s.bridge.pipeline.result is None
        )
        assert digest(args.project) == original_sha and not s.warnings, s.warnings
        report.update(
            status="PASS",
            review_events=len(original.review_events),
            human_geometries=sum(
                g.geometry_source.value == "HUMAN" for g in original.geometries
            ),
            manual_instances=sum(
                i.instance_status == "HUMAN" for i in original.defect_instances
            ),
            conflict_restored=True,
            manifest_sha_unchanged=True,
            qml_warnings=s.warnings,
        )
    finally:
        s.close()
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replay-only", action="store_true")
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--model", type=Path)
    ap.add_argument(
        "--hash-baseline",
        type=Path,
        help="Reuse a prior QA before-SHA snapshot; all hashes are still re-read after this QA",
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--tiff", type=Path, action="append", default=[])
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    if args.replay_only:
        replay_workspace(args, app, out)
        return
    report = {
        "manual_mouse_acceptance": "PENDING",
        "tests": [],
        "screens": [],
        "tiff": [],
        "status": "FAIL",
    }
    original = ProjectStore().load(args.project)
    prior = science(original)
    paths = {
        str(Path(source.source_reference).resolve())
        for source in original.image_sources
    }
    paths.update(str(path.resolve()) for path in args.tiff)
    paths.add(str(args.project.resolve()))
    if args.model:
        paths.update(
            str((args.model / name).resolve())
            for name in ("model.onnx", "manifest.json")
        )
    if args.hash_baseline:
        baseline = json.loads(args.hash_baseline.read_text(encoding="utf-8"))[
            "original_hashes_before"
        ]
        originals = {path: baseline[path] for path in paths}
        assert all(
            len(sha) == 64 and set(sha) <= set("0123456789abcdef")
            for sha in originals.values()
        )
        report["before_sha_origin"] = str(args.hash_baseline.resolve())
    else:
        originals = {path: digest(path) for path in paths}
    report["original_hashes_before"] = originals
    folder = out / "session"
    folder.mkdir()
    s = ReviewSession(app, folder)
    s.window.setTitle("XRT-RESULT-TD-05 automated review QA")
    c = s.bridge.projects
    r = s.bridge.research
    v = s.bridge.reviews
    try:
        progress("open verified project")
        c.open(str(args.project.resolve()))
        wait(s)
        c.save(str(out / "workspace.json"), "")
        wait(s)
        runs = [
            run
            for run in original.analysis_runs
            if sum(o.run_id == run.run_id for o in original.observations) in (2946, 791)
        ]
        assert len(runs) >= 2
        old_exports = {}
        for run in runs:
            progress("saved run " + run.run_id)
            c.selectRun(run.run_id)
            wait(s)
            spin(
                app,
                lambda run=run: (
                    r.saved is not None
                    and r.saved.run.run_id == run.run_id
                    and r.pixels_available
                    and not s.bridge.stack_viewer.initial_loading
                ),
                240,
            )
            counts = dict(Counter(row["type"] for row in r.rows))
            assert counts == (
                {"BPD": 245, "TED": 1398, "TSD": 1303}
                if len(r.rows) == 2946
                else {"BPD": 3, "TED": 779, "TSD": 9}
            )
            old_exports[run.run_id] = exports(s, out / ("before-" + run.run_id))
            report["tests"].append(
                {
                    "scope": run.scope.value,
                    "count": len(r.rows),
                    "counts": counts,
                    "run": run.run_id,
                }
            )
        full = next(
            run
            for run in runs
            if sum(o.run_id == run.run_id for o in original.observations) == 2946
        )
        c.selectRun(full.run_id)
        wait(s)
        spin(
            app,
            lambda: (
                r.saved is not None
                and r.saved.run.run_id == full.run_id
                and r.pixels_available
                and not s.bridge.stack_viewer.initial_loading
            ),
            240,
        )
        candidate = next(row for row in r.rows if row["type"] == "BPD")
        r.selectCandidate(candidate["id"])
        spin(app, lambda: bool(r.thumbnail_source), 40)
        v.setReviewer("qa-researcher-a")
        invoke(s.window, "requestContext", "result", "MANUAL")
        s.window.setProperty("inspectorCollapsed", False)
        for width, height in ((1100, 700), (1440, 900), (1920, 1080)):
            progress("actual review clicks " + str(width))
            v.cancel()
            r.selectCandidate(candidate["id"])
            s.window.resize(width, height)
            settle(s)
            click(s, "projectReviewEnter")
            click(s, "reviewExistencePRESENT")
            click(s, "reviewClassTED")
            note = s.item("reviewComment")
            flick = s.item("reviewWorkspace").property("contentItem")
            flick.setProperty(
                "contentY",
                max(
                    0,
                    note.mapToScene(QPointF()).y()
                    - s.item("reviewWorkspace").mapToScene(QPointF()).y()
                    + float(flick.property("contentY"))
                    - 100,
                ),
            )
            settle(s)
            note.forceActiveFocus()
            QTest.keyClick(s.window, Qt.Key_A, Qt.ControlModifier)
            for char in "research review: bpd to ted":
                QTest.keyClick(
                    s.window,
                    Qt.Key(ord(char.upper())),
                    Qt.ShiftModifier if char.isupper() else Qt.NoModifier,
                )
            QTest.qWait(70)
            click(s, "reviewCommit", True)
            assert (
                not v.pending and c.project.review_events[-1].corrected_class == "TED"
            ), v.error
            assert (
                c.project.review_events[-1].comment == "research review: bpd to ted"
            ), repr(c.project.review_events[-1].comment)
            c.save("", "")
            wait(s)
            settle(s)
            screenshot = folder / f"{width}-review.png"
            assert s.window.grabWindow().save(str(screenshot))
            report["screens"].append(
                {"size": [width, height], "qml_clicks": True, "path": str(screenshot)}
            )
        v.setReviewer("qa-researcher-b")
        v.decisions("PRESENT", "BPD", "ACCEPTED", "Independent disagreement")
        assert v.commit(False)
        assert (
            v.state["selected"]["conflict"]
            and not c.project.defect_instances[0].assessment.ground_truth_eligible
        )
        report["conflict"] = True
        v.setReviewer("qa-researcher-a")
        # Imported TD02 structure corrections; all original nodes/edges remain unchanged.
        for kind in ("POLYLINE", "BRANCHED_GRAPH"):
            progress("actual geometry drag " + kind)
            v.cancel()
            instance = next(
                i
                for i in c.project.defect_instances
                if next(
                    g for g in c.project.geometries if g.geometry_id == i.geometry_id
                ).kind.value
                == kind
            )
            assert v.select("DEFECT_INSTANCE", instance.instance_id)
            v.edit()
            assert v.draft
            d = v.draft
            before = plain(
                next(
                    g
                    for g in c.project.geometries
                    if g.geometry_id == instance.geometry_id
                )
            )
            handle = d.handles()[0]
            if kind == "BRANCHED_GRAPH":
                degrees = Counter(
                    node
                    for edge in d.data["edges"]
                    for node in (edge["start_node"], edge["end_node"])
                )
                junction = next(
                    node for node in d.data["nodes"] if degrees[node["node_id"]] >= 3
                )
                handle = next(
                    h for h in d.handles() if h["key"] == "n:" + junction["node_id"]
                )
                report["actual_junction_degree"] = degrees[junction["node_id"]]
            # Exercise the same QML MouseArea mapping as the native user gesture.
            invoke(s.item("candidateFocusAnimation"), "stop")
            invoke(s.viewer, "setActualZoom", 4)
            scale = float(s.viewer.property("displayScale"))
            s.viewer.setProperty(
                "panX", (s.ui.property("contentWidth") / 2 - handle["x"]) * scale
            )
            s.viewer.setProperty(
                "panY", (s.ui.property("contentHeight") / 2 - handle["y"]) * scale
            )
            settle(s)
            frame = s.item("imageFrame")
            pos = frame.mapToScene(QPointF(handle["x"] * scale, handle["y"] * scale))
            start = QPoint(round(pos.x()), round(pos.y()))
            end = start + QPoint(5, 6)
            QTest.mousePress(s.window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(s.window, end, 70)
            QTest.mouseRelease(s.window, Qt.LeftButton, Qt.NoModifier, end)
            settle(s)
            moved = next(h for h in d.handles() if h["key"] == handle["key"])
            assert abs(moved["x"] - handle["x"] - 5 / scale) < 1 / scale
            assert abs(moved["y"] - handle["y"] - 6 / scale) < 1 / scale
            if kind == "BRANCHED_GRAPH":
                click(s, "reviewGraphPath", True)
                QTest.mouseClick(
                    s.window, Qt.LeftButton, Qt.NoModifier, start + QPoint(9, 10)
                )
                settle(s)
                d.finish()
            click(s, "reviewExistencePRESENT", True)
            click(s, "reviewClassBPD", True)
            v.decisions(
                "PRESENT", "BPD", "CORRECTED", "Original pixels manually adjusted"
            )
            assert v.commit(False), v.error
            assert (
                plain(
                    next(
                        g
                        for g in c.project.geometries
                        if g.geometry_id == instance.geometry_id
                    )
                )
                == before
            )
            report["tests"].append(
                {
                    "edit": kind,
                    "target": instance.instance_id,
                    "original_preserved": True,
                    "corrected": c.project.review_events[
                        -1
                    ].corrected_geometry_reference,
                }
            )
        v.cancel()
        v.addManual("POLYLINE")
        assert v.draft
        v.press(4200, 8800, 1)
        v.press(4220, 8820, 1)
        v.press(4240, 8810, 1)
        v.decisions(
            "PRESENT", "BPD", "ACCEPTED", "Missed defect proposal, not ground truth"
        )
        assert v.commit(False), v.error
        manual = c.project.defect_instances[-1]
        assert manual.linked_observations == () and manual.instance_status == "HUMAN"
        c.save("", "")
        wait(s)
        v.cancel()
        replay = ProjectStore().load(c.path)
        assert science(replay) == prior
        assert replay.geometries[: len(original.geometries)] == original.geometries
        assert (
            replay.review_events[: len(original.review_events)]
            == original.review_events
        )
        assert replay.defect_instances[-1].linked_observations == ()
        report["save_reopen_domain_equal"] = replay == c.project
        assert report["save_reopen_domain_equal"]
        c.open(c.path)
        wait(s)
        for run in runs:
            progress("saved run " + run.run_id)
            c.selectRun(run.run_id)
            wait(s)
            spin(
                app,
                lambda run=run: (
                    r.saved is not None
                    and r.saved.run.run_id == run.run_id
                    and r.pixels_available
                    and not s.bridge.stack_viewer.initial_loading
                ),
                240,
            )
            assert exports(s, out / ("after-" + run.run_id)) == old_exports[run.run_id]
        report[
            "original_predictions_scores_ids_runs_geometry_and_legacy_export_bytes"
        ] = True
        for path in args.tiff:
            progress("tiff stack " + path.name)
            v.cancel()
            s.open(path.resolve())
            wait(s)
            assert not v.state["ready"]
            v.addManual("POLYLINE")
            assert v.draft is None
            assert (
                not s.bridge.analysis["hasResult"]
                and s.bridge.analysis["state"] != "RUNNING"
            )
            assert s.ui.property("stackFeaturesVisible")
            report["tiff"].append(
                {
                    "file": path.name,
                    "pages": s.bridge.original_source.metadata.page_count,
                    "review_disabled": True,
                    "new_inference": 0,
                    "stack_imagej_visible": True,
                }
            )
        progress("after SHA verification")
        assert all(digest(path) == sha for path, sha in originals.items())
        report["originals_sha_preserved"] = True
        report["scientific_reanalysis"] = False
        report["new_model_inference"] = 0
        report["qml_warnings"] = s.warnings
        assert not s.warnings, s.warnings
        report["status"] = "PASS"
    finally:
        s.close()
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
