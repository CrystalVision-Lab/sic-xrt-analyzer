"""Opt-in private Qt/real HTTP/PostgreSQL acceptance; never mutates originals."""

import argparse
import json
import subprocess
import sys
import threading
import time
from itertools import pairwise
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QPointF
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke
from validate_review_workspace import (
    ReviewSession,
    click,
    digest,
    exports,
    science,
    wait,
)

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.review_workspace import append_review
from sic_xrt_analyzer.sync.client import Outbox, Transport, make_crop, synchronize
from sic_xrt_analyzer.sync.protocol import SPECS, encode, project_projection


def compose(*args):
    subprocess.run(
        ["docker", "compose", "-f", "deploy/docker-compose.yml", *args], check=True
    )


def worker(app, fn):
    result = {}

    def run():
        try:
            result["value"] = fn()
        except Exception as e:  # noqa: BLE001 -- propagate worker failure on GUI test thread
            result["error"] = e

    thread = threading.Thread(target=run)
    thread.start()
    spin(app, lambda: not thread.is_alive(), 240)
    if "error" in result:
        raise result["error"]
    return result["value"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    original = ProjectStore().load(args.project)
    files = [Path(s.source_reference) for s in original.image_sources]
    files += [
        args.project,
        Path("artifacts/models/research/model.onnx"),
        Path("artifacts/models/research/manifest.json"),
    ]
    before = {str(p): digest(p) for p in files}
    endpoint = "http://127.0.0.1:18766"
    admin_value = json.loads((args.private / "admin.json").read_text(encoding="utf-8"))
    admin = Transport(endpoint, admin_value["credential"])
    s = ReviewSession(app, out)
    s.window.setTitle("Central sync private acceptance")
    c = s.bridge.projects
    r = s.bridge.research
    v = s.bridge.reviews
    sync = s.bridge.centralSync
    report = {
        "status": "FAIL",
        "external_deployment": "NOT DEPLOYED",
        "physical_native_dialog": "PENDING",
        "new_inference": 0,
    }
    s.bridge.pipeline.start = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Unexpected inference")
    )

    def completed():
        spin(app, lambda: not sync.busy, 240)

    def action(name):
        start = time.perf_counter()
        if name == "syncUploadCrop":
            scroll = s.item("syncScroll")
            item = s.item(name)
            flick = scroll.property("contentItem")
            flick.setProperty(
                "contentY",
                max(
                    0,
                    item.mapToScene(QPointF()).y()
                    - scroll.mapToScene(QPointF()).y()
                    + float(flick.property("contentY"))
                    - 200,
                ),
            )
            QTest.qWait(60)
        click(s, name)
        completed()
        assert not sync.error, (name, sync.error)
        return time.perf_counter() - start

    try:
        print("Open saved actual project", flush=True)
        c.open(str(args.project.resolve()))
        wait(s)
        c.save(str(out / "workspace.json"), "")
        wait(s)
        legacy = {}
        for run in original.analysis_runs:
            print("Replay saved run " + run.run_id, flush=True)
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
            legacy[run.run_id] = exports(s, out / ("legacy-before-" + run.run_id))
        event = next(
            e
            for e in original.review_events
            if e.target_type == ReviewTarget.OBSERVATION
        )
        c.selectRun(event.source_run_id)
        wait(s)
        spin(
            app,
            lambda: (
                r.saved is not None
                and r.saved.run.run_id == event.source_run_id
                and r.pixels_available
                and not s.bridge.stack_viewer.initial_loading
            ),
            240,
        )
        full_source_id = next(
            run.source_id
            for run in c.project.analysis_runs
            if run.run_id == event.source_run_id
        )
        obs = next(
            o for o in c.project.observations if o.observation_id == event.target_id
        )
        r.selectCandidate(obs.source_candidate_id)
        v.setReviewer("td106-local-reviewer-a")
        invoke(s.window, "requestContext", "result", "MANUAL")
        s.window.setProperty("inspectorCollapsed", False)
        assert v.enter()
        v.decisions("PRESENT", "TED", "ACCEPTED", "Explicit local review before sync")
        assert v.commit(False), v.error
        c.save("", "")
        wait(s)
        user = worker(
            app,
            lambda: admin.request(
                "POST",
                "/api/v1/admin/users",
                {
                    "name": "TD106 researcher A",
                    "role": "RESEARCHER",
                    "client_id": sync.outbox.client_id,
                },
            ),
        )
        worker(
            app,
            lambda: admin.request(
                "POST",
                "/api/v1/admin/grants",
                {
                    "user_id": user["user_id"],
                    "project_id": c.project.project_id,
                    "crops": True,
                },
            ),
        )
        invoke(s.item("projectWorkspaceDialog"), "open")
        click(s, "projectCentralSync")
        completed()
        for name, value in [
            ("syncServerInput", endpoint),
            ("syncClientInput", user["client_id"]),
            ("syncCredentialInput", user["credential"]),
        ]:
            s.item(name).setProperty("text", value)
        click(s, "syncConfigure")
        assert not sync.error, sync.error
        assert s.item("syncCredentialInput").property("text") == ""
        report["connection_seconds"] = action("syncTestConnection")
        saved_hash = digest(out / "workspace.json")
        scientific = science(c.project)
        print("Actual HTTP initial sync 22550+ entities", flush=True)
        first_start = len(s.beats)
        report["initial_sync_seconds"] = action("syncExecute")
        assert (
            sync.status == "ACKNOWLEDGED"
            and digest(out / "workspace.json") == saved_hash
        )
        beats = s.beats[first_start:]
        report["sync_gui_timer_max_gap_ms"] = max(
            (b - a) * 1000 for a, b in pairwise(beats)
        )
        ack = sync.outbox.receipt(endpoint, c.project.project_id)
        report["initial_counts"] = {k: len(v) for k, v in ack["inventory"].items()}
        with sync.outbox.db() as db:
            body = json.loads(
                db.execute(
                    "SELECT payload FROM batches WHERE id=?", (ack["batch_id"],)
                ).fetchone()[0]
            )
        report["initial_bytes"] = len(encode(body))
        assert (
            worker(
                app,
                lambda: Transport(endpoint, user["credential"]).request(
                    "POST", "/api/v1/sync/batches", body
                ),
            )
            == ack
        )
        report["repeat_sync_seconds"] = action("syncExecute")
        assert sync.pending_reviews == 0
        print("Offline review and durable retry", flush=True)
        invoke(s.item("centralSyncDialog"), "close")
        invoke(s.item("projectWorkspaceDialog"), "close")
        v.setReviewer("td106-local-reviewer-a")
        assert v.enter()
        v.decisions("PRESENT", "TED", "ACCEPTED", "Offline local event")
        assert v.commit(False), v.error
        c.save("", "")
        wait(s)
        offline_revision = c.project.revision
        compose("stop", "api")
        sync.synchronize()
        completed()
        assert sync.error == "OFFLINE", sync.error
        pending = sync.outbox.pending(endpoint, c.project.project_id)
        assert len(pending) == 1
        offline_batch = pending[0][0]
        offline_bytes = len(encode(pending[0][1]))
        assert not pending[0][1]["entities"]["predictions"]
        compose("restart", "postgres")
        compose("start", "api")
        for _ in range(60):
            try:
                worker(app, lambda: admin.request("GET", "/api/v1/health"))
                break
            except Exception:  # noqa: BLE001 -- bounded health recovery polling
                QTest.qWait(500)
        sync.synchronize()
        completed()
        assert not sync.error, sync.error
        assert (
            sync.outbox.receipt(endpoint, c.project.project_id)["batch_id"]
            == offline_batch
        )
        assert c.project.revision == offline_revision and not c.dirty
        report["offline_retry_same_batch"] = True
        report["incremental_bytes"] = offline_bytes
        client_b = str(uuid4())
        user_b = worker(
            app,
            lambda: admin.request(
                "POST",
                "/api/v1/admin/users",
                {
                    "name": "TD106 researcher B",
                    "role": "RESEARCHER",
                    "client_id": client_b,
                },
            ),
        )
        worker(
            app,
            lambda: admin.request(
                "POST",
                "/api/v1/admin/grants",
                {
                    "user_id": user_b["user_id"],
                    "project_id": c.project.project_id,
                    "crops": False,
                },
            ),
        )
        branch_b, _ = append_review(
            c.project,
            ReviewTarget.OBSERVATION,
            obs.observation_id,
            "td106-local-reviewer-b",
            "PRESENT",
            "BPD",
            "ACCEPTED",
            "Independent second user",
            source_id=full_source_id,
            run_id=obs.run_id,
        )
        outbox_b = Outbox(out / "device-b.sqlite3")
        outbox_b.set_client_id(client_b)
        worker(
            app,
            lambda: synchronize(
                outbox_b, branch_b, Transport(endpoint, user_b["credential"])
            ),
        )
        summary = worker(
            app,
            lambda: admin.request(
                "GET", f"/api/v1/projects/{c.project.project_id}/summary"
            ),
        )
        assert (
            summary["conflict_targets"] >= 1 and summary["ground_truth_approved"] == 0
        )
        report["server_summary"] = summary
        print("Original-pixel consent crop", flush=True)
        v.cancel()
        r.selectCandidate(obs.source_candidate_id)
        assert v.enter()
        invoke(s.item("projectWorkspaceDialog"), "open")
        click(s, "projectCentralSync")
        completed()
        assert not s.item("syncCropConsent").property("checked") and not s.item(
            "syncUploadCrop"
        ).property("enabled")
        source = next(
            i for i in c.project.image_sources if i.source_id == full_source_id
        )
        geometry = next(
            g for g in c.project.geometries if g.geometry_id == obs.geometry_id
        )
        # Bounds are explicit original pixels; no screenshot or preview is used.
        rect = (
            max(0, int((geometry.points[0] if geometry.points else geometry.bbox)[0])),
            max(0, int((geometry.points[0] if geometry.points else geometry.bbox)[1])),
            128,
            128,
        )
        rect = (
            min(rect[0], source.width - 128),
            min(rect[1], source.height - 128),
            128,
            128,
        )
        crop = worker(
            app,
            lambda: make_crop(
                c.project,
                source.source_id,
                obs.run_id,
                "OBSERVATION",
                obs.observation_id,
                rect,
                consent=True,
            ),
        )
        s.item("centralSyncDialog").setProperty("rectangle", list(rect))
        s.item("syncCropConsent").setProperty("checked", True)
        report["crop_seconds"] = action("syncUploadCrop")
        assert sync.status == "CROP_ACKNOWLEDGED"
        assert not s.item("syncCropConsent").property("checked")
        crop_ack = worker(
            app,
            lambda: Transport(endpoint, user["credential"]).request(
                "POST", f"/api/v1/projects/{c.project.project_id}/crops", crop
            ),
        )
        assert crop_ack["crop_hash"] == crop["metadata"]["crop_hash"]
        report["crop_hash"] = crop_ack["crop_hash"]
        report["pixel_hash"] = crop["metadata"]["pixel_hash"]
        _root, expected = project_projection(branch_b)
        for kind, id_field in SPECS.items():
            values = worker(
                app,
                lambda kind=kind: admin.request(
                    "GET", f"/api/v1/projects/{c.project.project_id}/entities/{kind}"
                ),
            )
            received = {v["payload"][id_field]: v["payload"] for v in values}
            assert all(
                received.get(ident) == payload
                for ident, payload in expected[kind].items()
            ), kind
            if kind != "review_events":
                assert received == expected[kind], kind
            if kind == "review_events":
                assert any(
                    e["authenticated_actor_id"] == user["user_id"]
                    and e["payload"]["reviewer_id"] == "td106-local-reviewer-a"
                    for e in values
                )
                assert any(
                    e["authenticated_actor_id"] == user_b["user_id"]
                    and e["payload"]["reviewer_id"] == "td106-local-reviewer-b"
                    for e in values
                )
        assert science(c.project) == scientific
        invoke(s.item("centralSyncDialog"), "close")
        invoke(s.item("projectWorkspaceDialog"), "close")
        for run in original.analysis_runs:
            print("Replay saved run " + run.run_id, flush=True)
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
            assert (
                exports(s, out / ("legacy-after-" + run.run_id)) == legacy[run.run_id]
            )
        report["legacy_export_equal"] = True
        print("Read-only TIFF workspace regression", flush=True)
        report["tiff"] = []
        for source in c.project.image_sources:
            if Path(source.source_reference).suffix.lower() not in (".tif", ".tiff"):
                continue
            c.selectSource(source.source_id, "")
            wait(s)
            spin(app, lambda: not s.bridge.stack_viewer.initial_loading, 240)
            assert r.saved is None and not v.state["ready"]
            report["tiff"].append(
                {
                    "pages": source.page_count,
                    "dtype": source.dtype,
                    "analysis_disabled": True,
                }
            )
        report["original_sha_preserved"] = before == {
            str(p): worker(app, lambda p=p: digest(p)) for p in files
        }
        assert report["original_sha_preserved"] and not s.warnings, s.warnings
        report["qml_warnings"] = s.warnings
        report["status"] = "PASS"
        report["project_id"] = c.project.project_id
        report["admin_statistics"] = worker(
            app, lambda: admin.request("GET", "/api/v1/admin/statistics")
        )
        print("Real Desktop/HTTP/PostgreSQL PASS", flush=True)
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        sync.forgetCredential()
        s.close()


if __name__ == "__main__":
    main()
