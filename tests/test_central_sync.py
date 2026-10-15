"""Transmission ledger, privacy projection and actual desktop controls."""

import threading
from copy import deepcopy

import pytest
from test_review_workspace import (
    prepare,
    render,
)
from test_review_workspace import (
    project as project_fixture,
)
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.review_workspace import append_review
from sic_xrt_analyzer.results.serialization import dumps
from sic_xrt_analyzer.sync.client import (
    Outbox,
    SyncError,
    Transport,
    endpoint_url,
    make_crop,
    synchronize,
)
from sic_xrt_analyzer.sync.protocol import (
    encode,
    make_batch,
    project_projection,
    validate_projection,
)

project = project_fixture
pytest_plugins = ("test_toolbar",)


def test_projection_no_paths_scores_reviews_and_version_roundtrip(project):
    before = dumps(project)
    root, entities = project_projection(project)
    text = encode(entities).decode()
    assert (
        project.image_sources[0].source_reference not in text
        and "canonical_path" not in text
    )
    reconstructed = validate_projection(root, entities)
    assert (
        reconstructed.predictions == project.predictions
        and reconstructed.review_events == project.review_events
        and reconstructed.geometries == project.geometries
    )
    assert dumps(project) == before
    batch = make_batch(project, "device-test")
    assert (
        batch["project_schema_version"] == "1.0.0"
        and batch["sync_protocol_version"] == 1
    )
    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "test-reviewer",
        "PRESENT",
        "TED",
        "ACCEPTED",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    root, entities = project_projection(p)
    assert (
        root["schema_version"] == "1.1.0"
        and validate_projection(root, entities).review_events == p.review_events
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://localhost:8000",
        "https://user:key@example.com",
        "https://example.com/?secret=value",
        "file:///tmp/server",
        "http://127.0.0.1:18766/other",
    ],
)
def test_non_tls_external_and_embedded_credentials_rejected(url):
    with pytest.raises(SyncError):
        endpoint_url(url)


def receipt(value):
    return {
        **{
            k: value[k]
            for k in (
                "batch_id",
                "project_id",
                "client_id",
                "payload_hash",
                "snapshot_hash",
                "project_revision",
                "inventory",
            )
        },
        "status": "ACKNOWLEDGED",
        "received_at": "2026-10-12T00:00:00+00:00",
    }


class RecordingTransport:
    endpoint = "http://127.0.0.1:18766"

    def __init__(self):
        self.values = []
        self.fail = True

    def request(self, _method, _path, value):
        self.values.append(deepcopy(value))
        if self.fail:
            self.fail = False
            raise SyncError("OFFLINE")
        return receipt(value)


def test_lost_ack_restart_same_batch_incremental_and_atomic_receipt(project, tmp_path):
    before = dumps(project)
    file = tmp_path / "outbox.sqlite"
    outbox = Outbox(file)
    transport = RecordingTransport()
    with pytest.raises(SyncError):
        synchronize(outbox, project, transport)
    first = transport.values[0]["batch_id"]
    restarted = Outbox(file)
    assert restarted.client_id == outbox.client_id
    synchronize(restarted, project, transport)
    assert transport.values[-1]["batch_id"] == first and not restarted.pending(
        transport.endpoint, project.project_id
    )
    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "test-reviewer",
        "PRESENT",
        "TED",
        "ACCEPTED",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    synchronize(restarted, p, transport)
    assert (
        not transport.values[-1]["entities"]["observations"]
        and len(transport.values[-1]["entities"]["review_events"]) == 1
    )
    assert dumps(project) == before
    staged = outbox.stage(transport.endpoint, p)
    bad = receipt(staged)
    bad["project_id"] = "wrong-project"
    with pytest.raises(SyncError):
        outbox.acknowledge(staged["batch_id"], bad)
    assert outbox.pending(transport.endpoint, p.project_id)


@pytest.mark.parametrize(
    "rectangle", [(0, 0, 96, 96), (-1, 0, 5, 5), (90, 90, 20, 20), (0, 0, 2048, 5)]
)
def test_crop_requires_consent_verified_source_and_local_bounds(project, rectangle):
    with pytest.raises(SyncError):
        make_crop(
            project,
            project.image_sources[0].source_id,
            project.analysis_runs[0].run_id,
            "OBSERVATION",
            project.observations[0].observation_id,
            rectangle,
            consent=False,
        )
    with pytest.raises(SyncError):
        make_crop(
            project,
            project.image_sources[0].source_id,
            project.analysis_runs[0].run_id,
            "OBSERVATION",
            project.observations[0].observation_id,
            rectangle,
            consent=True,
        )


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get(self, e, c):
        return self.values.get((e, c), "")

    def set(self, e, c, t):
        self.values[e, c] = t

    def delete(self, e, c):
        self.values.pop((e, c), None)


def test_actual_sync_panel_no_automatic_upload_dirty_and_credential_not_qsettings(
    workbench, tmp_path, monkeypatch
):
    w = workbench
    c, _r, _v, _ = prepare(w, tmp_path)
    sync = w.bridge.centralSync
    sync.vault = MemoryVault()
    calls = []
    monkeypatch.setattr(
        Transport,
        "request",
        lambda *a, **k: calls.append(a) or {"client_id": sync.outbox.client_id},
    )
    invoke(w.item("projectWorkspaceDialog"), "open")
    render(w)
    w.click("projectCentralSync")
    render(w)
    assert w.item("centralSyncDialog").property("visible") and not calls
    assert not w.item("syncCropConsent").property("checked")
    assert sync.configure(
        "http://127.0.0.1:18766", sync.outbox.client_id, "xrt_synthetic-test-only"
    )
    assert "xrt_synthetic-test-only" not in str(w.bridge._settings.allKeys())
    assert not any("credential" in k.lower() for k in w.bridge._settings.allKeys())
    c.dirty = True
    sync.changed.emit()
    sync.synchronize()
    assert sync.error == "SAVE_PROJECT_BEFORE_SYNC" and not calls
    assert not w.warnings, w.warnings


def test_stale_ack_canceled_and_project_switch_cannot_update_active_state(
    workbench, tmp_path
):
    w = workbench
    c, _r, _v, _ = prepare(w, tmp_path)
    sync = w.bridge.centralSync
    old = sync.fingerprint()
    sync._done(
        {"context": old, "value": {"status": "ACKNOWLEDGED", "last": "old-ack"}}, ""
    )
    c.project = None
    c.path = ""
    c.changed.emit()
    sync._done(
        {"context": old, "value": {"status": "ACKNOWLEDGED", "last": "late-ack"}}, ""
    )
    assert sync.last_sync != "late-ack" and not sync.busy
    event = threading.Event()
    event.set()
    with pytest.raises(SyncError, match="CANCELED"):
        Transport("http://127.0.0.1:18766", "xrt_test", event).request(
            "GET", "/api/v1/health"
        )


def test_crop_outbox_restart_reuses_pending_content_with_explicit_action(tmp_path):
    box = Outbox(tmp_path / "outbox.sqlite3")
    body = {
        "metadata": {"crop_hash": "test"},
        "consent": True,
        "image_base64": "synthetic",
    }
    ident = box.stage_crop("http://127.0.0.1:18766", "project", body)
    box.failed(ident, "OFFLINE")
    restarted = Outbox(tmp_path / "outbox.sqlite3")
    assert restarted.stage_crop("http://127.0.0.1:18766", "project", body) == ident
    assert len(restarted.pending("http://127.0.0.1:18766", "project", "crop")) == 1
    assert not restarted.pending("http://127.0.0.1:18766", "project")


def test_parent_review_order_survives_sorted_json_object_keys(project):
    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "reader",
        "PRESENT",
        "TED",
        "ACCEPTED",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    p, _ = append_review(
        p,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "reader",
        "PRESENT",
        "BPD",
        "ACCEPTED",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    root, rows = project_projection(p)
    # Force child before parent, matching unordered JSONB/SQL retrieval.
    rows["review_events"] = dict(reversed(list(rows["review_events"].items())))
    restored = validate_projection(root, rows)
    assert {r.review_id: r for r in restored.review_events} == {
        r.review_id: r for r in p.review_events
    }


@pytest.mark.parametrize("cancel", [False, True])
def test_real_loopback_timeout_retry_and_cancel(monkeypatch, cancel):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import httpx

    entered = threading.Event()
    release = threading.Event()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(1)
            entered.set()
            release.wait(0.15)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real_client = httpx.Client

    def short_client(**kwargs):
        kwargs["timeout"] = httpx.Timeout(0.03, connect=0.1)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", short_client)
    token = threading.Event()

    def cancel_when_entered():
        entered.wait(2)
        token.set()

    if cancel:
        threading.Thread(target=cancel_when_entered, daemon=True).start()
    try:
        with pytest.raises(SyncError, match="CANCELED" if cancel else "TIMEOUT"):
            Transport(
                f"http://127.0.0.1:{server.server_port}", "xrt_synthetic", token
            ).request("GET", "/slow")
        assert len(calls) == (1 if cancel else 3)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_crop_rejects_changed_original_and_preserves_rgb_pixels(project):
    import base64
    import hashlib
    import io
    from dataclasses import replace
    from pathlib import Path

    from PIL import Image

    from sic_xrt_analyzer.results.contracts import VerifiedContentHash

    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "reader",
        "PRESENT",
        "TED",
        "ACCEPTED",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    source = p.image_sources[0]
    path = Path(source.source_reference)
    hashed = VerifiedContentHash(
        value=hashlib.sha256(path.read_bytes()).hexdigest(),
        verified_at=p.updated_at,
        source_reference=source.source_reference,
        file_size=source.file_identity.file_size,
        mtime_ns=source.file_identity.mtime_ns,
    )
    p = p.evolve(image_sources=(replace(source, content_hash=hashed),))
    args = (
        p,
        source.source_id,
        p.analysis_runs[0].run_id,
        "OBSERVATION",
        p.observations[0].observation_id,
        (20, 20, 16, 16),
    )
    crop = make_crop(*args, consent=True)
    with (
        Image.open(path) as original,
        Image.open(io.BytesIO(base64.b64decode(crop["image_base64"]))) as sent,
    ):
        assert original.crop((20, 20, 36, 36)).tobytes() == sent.tobytes()
    path.write_bytes(b"synthetic original changed")
    with pytest.raises(SyncError, match="SOURCE_CHANGED"):
        make_crop(*args, consent=True)


def test_crop_retry_requires_new_explicit_consent(workbench, tmp_path):
    w = workbench
    prepare(w, tmp_path)
    sync = w.bridge.centralSync
    sync.retryCrops(False)
    assert sync.error == "EXPLICIT_CROP_CONSENT_REQUIRED" and not sync.busy


def test_entity_delta_limit_does_not_claim_all_pending_confirmed(project, tmp_path):
    box = Outbox(tmp_path / "outbox.sqlite3")
    transport = RecordingTransport()
    transport.fail = False
    for index in range(21):
        snapshot = project.evolve(project_name=f"Project {index}")
        box.stage(transport.endpoint, snapshot)
    with pytest.raises(SyncError, match="MORE_PENDING_BATCHES_RETRY"):
        synchronize(box, snapshot, transport)
    assert box.pending_count(transport.endpoint, project.project_id) == 1
