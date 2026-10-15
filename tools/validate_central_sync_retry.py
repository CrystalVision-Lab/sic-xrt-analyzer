"""Private real Desktop restart/Crop retry and TIFF page integrity acceptance."""

import argparse
import faulthandler
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtCore import QPointF
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke
from validate_central_sync import compose, worker
from validate_review_workspace import ReviewSession, click, digest, wait

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.sync.client import Transport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=args.resume)
    faulthandler.dump_traceback_later(180, repeat=True)
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    p = ProjectStore().load(args.project)
    original_hash = digest(args.project)
    admin = Transport(
        "http://127.0.0.1:18766",
        json.loads((args.private / "admin.json").read_text(encoding="utf-8"))[
            "credential"
        ],
    )
    event = next(
        e for e in p.review_events if e.reviewer_id == "td106-local-reviewer-a"
    )
    obs = next(o for o in p.observations if o.observation_id == event.target_id)
    report = {
        "status": "FAIL",
        "new_inference": 0,
        "restart_crop_retry": False,
        "tiff": [],
    }
    if args.resume:
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    s = None
    stopped = False

    def new_session():
        session = ReviewSession(app, out)

        def forbidden(*args, **kwargs):
            report["new_inference"] += 1
            raise AssertionError("Inference is not allowed in sync acceptance")

        session.bridge.pipeline.start = forbidden
        print("Open fresh Desktop session", flush=True)
        c = session.bridge.projects
        c.open(str(args.project.resolve()))
        wait(session)
        c.selectRun(obs.run_id)
        wait(session)
        spin(
            app,
            lambda: (
                session.bridge.research.pixels_available
                and not session.bridge.stack_viewer.initial_loading
            ),
            240,
        )
        session.bridge.reviews.select("OBSERVATION", obs.observation_id)
        invoke(session.item("projectWorkspaceDialog"), "open")
        click(session, "projectCentralSync")
        spin(app, lambda: not session.bridge.centralSync.busy, 240)
        return session

    def button(name):
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
                - 180,
            ),
        )
        QTest.qWait(70)
        click(s, name)
        spin(app, lambda: not s.bridge.centralSync.busy, 240)

    try:
        if not args.resume:
            s = new_session()
            sync = s.bridge.centralSync
            user = worker(
                app,
                lambda: admin.request(
                    "POST",
                    "/api/v1/admin/users",
                    {
                        "name": "TD106 restart QA",
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
                        "project_id": p.project_id,
                        "crops": True,
                    },
                ),
            )
            for name, value in [
                ("syncServerInput", admin.endpoint),
                ("syncClientInput", user["client_id"]),
                ("syncCredentialInput", user["credential"]),
            ]:
                s.item(name).setProperty("text", value)
            button("syncConfigure")
            button("syncExecute")
            assert not sync.error, sync.error
            s.item("centralSyncDialog").setProperty("rectangle", [24, 24, 64, 64])
            s.item("syncCropConsent").setProperty("checked", True)
            compose("stop", "api")
            stopped = True
            button("syncUploadCrop")
            assert sync.error == "OFFLINE", sync.error
            pending = sync.outbox.pending(admin.endpoint, p.project_id, "crop")
            assert len(pending) == 1
            queued_id, queued_body = pending[0]
            assert digest(args.project) == original_hash
            print("Queued crop survives application restart", flush=True)
            report["queued_id"] = queued_id
            report["queued_crop_hash"] = queued_body["metadata"]["crop_hash"]
            s.close()
            s = None
            compose("start", "api")
            stopped = False
            for _ in range(40):
                try:
                    worker(app, lambda: admin.request("GET", "/api/v1/health"))
                    break
                except Exception:  # noqa: BLE001 -- bounded health recovery polling
                    QTest.qWait(500)
            (out / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            try:
                subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "--project",
                        str(args.project.resolve()),
                        "--private",
                        str(args.private.resolve()),
                        "--output",
                        str(out),
                        "--resume",
                    ],
                    check=True,
                )
            finally:
                report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            return
        queued_id = report["queued_id"]
        queued_body = {"metadata": {"crop_hash": report["queued_crop_hash"]}}
        s = new_session()
        sync = s.bridge.centralSync
        assert sync.pending_crops == 1 and not s.item("syncCropConsent").property(
            "checked"
        )
        s.item("syncCropConsent").setProperty("checked", True)
        button("syncRetryCrops")
        assert (
            not sync.error
            and sync.status == "CROP_ACKNOWLEDGED"
            and sync.pending_crops == 0
        ), sync.error
        with sync.outbox.db() as db:
            assert (
                db.execute(
                    "SELECT state FROM batches WHERE id=?", (queued_id,)
                ).fetchone()[0]
                == "ACKNOWLEDGED"
            )
        report["restart_crop_retry"] = True
        report["fresh_os_process"] = True
        report["crop_hash"] = queued_body["metadata"]["crop_hash"]
        assert s.window.grabWindow().save(str(out / "sync-ui.png"))
        invoke(s.item("centralSyncDialog"), "close")
        invoke(s.item("projectWorkspaceDialog"), "close")
        s.bridge.reviews.cancel()
        for source in p.image_sources:
            if Path(source.source_reference).suffix.lower() not in (".tif", ".tiff"):
                continue
            print("TIFF page regression " + source.display_name, flush=True)
            c = s.bridge.projects
            c.selectSource(source.source_id, "")
            wait(s)
            stack = s.bridge.stack_viewer
            spin(
                app,
                lambda stack=stack, source=source: (
                    stack.frame is not None
                    and Path(stack.frame.source.path).resolve()
                    == Path(source.source_reference).resolve()
                    and not stack.initial_loading
                ),
                240,
            )
            pages = [0, source.page_count // 2, source.page_count - 1]
            for page in pages:
                assert stack.page(page)
                spin(
                    app,
                    lambda page=page, stack=stack, source=source: (
                        stack.frame is not None
                        and Path(stack.frame.source.path).resolve()
                        == Path(source.source_reference).resolve()
                        and stack.frame.source.page_index == page
                        and not stack.initial_loading
                        and not stack.busy
                    ),
                    120,
                )
                frame = stack.frame
                pixels = worker(
                    app, lambda frame=frame: frame.source.read_region(0, 0, 8, 8)
                )

                def original(source=source, page=page):
                    with tifffile.TiffFile(source.source_reference) as file:
                        return file.pages[page].asarray()[:8, :8].copy()

                expected = worker(app, original)
                assert (
                    pixels.dtype.kind == "u"
                    and pixels.dtype.itemsize == 2
                    and np.array_equal(pixels, expected)
                ), (
                    source.display_name,
                    page,
                    Path(frame.source.path).name,
                    frame.source.page_index,
                    pixels.dtype.name,
                    pixels.shape,
                    expected.shape,
                    pixels.tolist(),
                    expected.tolist(),
                )
                assert (
                    s.bridge.research.saved is None
                    and not s.bridge.reviews.state["ready"]
                )
            report["tiff"].append(
                {
                    "name": source.display_name,
                    "pages_1_based": [i + 1 for i in pages],
                    "raw_uint16_equal": True,
                    "analysis_disabled": True,
                }
            )
        assert report["new_inference"] == 0 and not s.warnings, s.warnings
        report["input_project_sha_preserved"] = digest(args.project) == original_hash
        report["original_sha_preserved"] = {
            source.display_name: worker(
                app, lambda source=source: digest(source.source_reference)
            )
            for source in p.image_sources
        }
        report["server_summary"] = worker(
            app,
            lambda: admin.request("GET", f"/api/v1/projects/{p.project_id}/summary"),
        )
        report["qml_warnings"] = s.warnings
        report["status"] = "PASS"
        print("Restart/Crop/TIFF PASS", flush=True)
    finally:
        faulthandler.cancel_dump_traceback_later()
        if stopped:
            compose("start", "api")
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if s is not None:
            s.bridge.centralSync.forgetCredential()
            s.close()


if __name__ == "__main__":
    main()
