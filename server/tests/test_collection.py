from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from xrt_server.models import ENTITIES, Asset

from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.review_workspace import append_review
from sic_xrt_analyzer.sync.client import make_crop
from sic_xrt_analyzer.sync.protocol import digest, make_batch


def headers(token):
    return {"Authorization": "Bearer " + token}


def upload(api, project):
    http, _app, _s, _user, client, token, _admin, _cred = api
    value = make_batch(project, client)
    response = http.post("/api/v1/sync/batches", json=value, headers=headers(token))
    assert response.status_code == 200, response.text
    return value, response.json()


def rehash(value):
    for kind, rows in value["entities"].items():
        for ident, row in rows.items():
            value["inventory"][kind][ident] = digest(row)
    value["snapshot_hash"] = digest(
        {"project": value["project"], "inventory": value["inventory"]}
    )
    value["payload_hash"] = digest(
        {k: v for k, v in value.items() if k != "payload_hash"}
    )
    return value


def test_auth_scope_revocation_and_admin(api, project):
    http, _app, _s, _user, _client, token, admin, cred = api
    assert http.get("/api/v1/health").status_code == 401
    assert http.get("/api/v1/health", headers=headers("bad")).status_code == 401
    assert http.get("/api/v1/health", headers=headers(token)).status_code == 200
    assert (
        http.get("/api/v1/admin/statistics", headers=headers(token)).status_code == 403
    )
    assert (
        http.get(
            "/api/v1/projects/" + str(uuid4()) + "/summary", headers=headers(token)
        ).status_code
        == 403
    )
    assert http.get("/docs").status_code == 404
    assert http.get("/api/v1/admin/openapi", headers=headers(admin)).status_code == 200
    assert (
        http.post(
            "/api/v1/admin/credentials/" + cred + "/revoke",
            json={},
            headers=headers(admin),
        ).status_code
        == 200
    )
    assert http.get("/api/v1/health", headers=headers(token)).status_code == 401


def test_full_incremental_idempotency_and_actor_preserve(api, project):
    value, ack = upload(api, project)
    http, _app, sessions, user, client, token, _admin, _cred = api
    assert ack["accepted"]["review_events"] == 1
    repeated = http.post("/api/v1/sync/batches", json=value, headers=headers(token))
    assert repeated.status_code == 200 and repeated.json() == ack
    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "local-reviewer",
        "PRESENT",
        "BPD",
        "ACCEPTED",
        "revision",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    delta = make_batch(p, client, known=ack["inventory"])
    assert (
        not delta["entities"]["observations"]
        and len(delta["entities"]["review_events"]) == 1
    )
    assert (
        http.post(
            "/api/v1/sync/batches", json=delta, headers=headers(token)
        ).status_code
        == 200
    )
    stored = http.get(
        "/api/v1/projects/" + project.project_id + "/entities/review_events",
        headers=headers(token),
    ).json()
    assert len(stored) == 2 and all(
        r["authenticated_actor_id"] == user.id for r in stored
    )
    assert all(r["payload"]["reviewer_id"] == "local-reviewer" for r in stored)
    with sessions() as s:
        pred = s.scalar(
            select(ENTITIES["predictions"]).where(
                ENTITIES["predictions"].project_id == project.project_id
            )
        ).payload
    assert pred["assigned_class"] == "BPD" and pred["raw_scores"] == [0.9, 0.05, 0.05]


@pytest.mark.parametrize("mutation", ["event", "prediction", "batch", "revision"])
def test_immutable_and_revision_conflicts_atomic(api, project, mutation):
    value, _ack = upload(api, project)
    http, _app, _sessions, _u, _client, token, _a, _c = api
    bad = deepcopy(value)
    if mutation != "batch":
        bad["batch_id"] = str(uuid4())
    if mutation in ("event", "batch"):
        row = next(iter(bad["entities"]["review_events"].values()))
        row["comment"] = "conflicting payload"
    elif mutation == "prediction":
        next(iter(bad["entities"]["predictions"].values()))["raw_scores"] = [
            0.8,
            0.1,
            0.1,
        ]
    else:
        bad["project"]["updated_at"] = "2099-01-01T00:00:00+00:00"
    rehash(bad)
    assert (
        http.post("/api/v1/sync/batches", json=bad, headers=headers(token)).status_code
        == 409
    )
    assert (
        http.get(
            "/api/v1/projects/" + project.project_id + "/summary",
            headers=headers(token),
        ).json()["review_events"]
        == 1
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "protocol",
        "source",
        "geometry",
        "model",
        "parent",
        "path",
        "hash",
        "reviewer_escalation",
    ],
)
def test_invalid_reference_and_projection_rollback(api, project, mutation):
    http, _app, sessions, _u, client, token, _a, _c = api
    bad = make_batch(project, client)
    if mutation == "schema":
        bad["project_schema_version"] = bad["project"]["schema_version"] = "9.0.0"
    elif mutation == "protocol":
        bad["sync_protocol_version"] = 999
    elif mutation == "source":
        next(iter(bad["entities"]["analysis_runs"].values()))["source_id"] = str(
            uuid4()
        )
    elif mutation == "geometry":
        next(iter(bad["entities"]["review_events"].values()))[
            "corrected_geometry_reference"
        ] = str(uuid4())
    elif mutation == "model":
        next(iter(bad["entities"]["analysis_runs"].values()))["model_hash"] = "b" * 64
    elif mutation == "parent":
        next(iter(bad["entities"]["review_events"].values()))["parent_review_ids"] = [
            str(uuid4())
        ]
    elif mutation == "path":
        next(iter(bad["entities"]["image_sources"].values()))["source_reference"] = (
            "C:/secret.jpg"
        )
    elif mutation == "reviewer_escalation":
        next(iter(bad["entities"]["review_events"].values()))[
            "authenticated_actor_id"
        ] = "ADMIN"
    rehash(bad)
    if mutation == "hash":
        bad["payload_hash"] = "0" * 64
    assert (
        http.post("/api/v1/sync/batches", json=bad, headers=headers(token)).status_code
        == 422
    )
    with sessions() as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(ENTITIES["review_events"])
                .where(ENTITIES["review_events"].project_id == project.project_id)
            )
            == 0
        )


def test_duplicate_keys_size_and_mime(api, project):
    http, _app, _s, _u, _client, token, _a, _c = api
    assert (
        http.post(
            "/api/v1/sync/batches",
            content=b'{"project_id":"a","project_id":"b"}',
            headers={**headers(token), "Content-Type": "application/json"},
        ).status_code
        == 400
    )
    assert (
        http.post(
            "/api/v1/sync/batches",
            content=b"{}",
            headers={**headers(token), "Content-Type": "text/plain"},
        ).status_code
        == 415
    )
    assert (
        http.post(
            "/api/v1/sync/batches",
            content=b" " * (32 * 1024**2 + 1),
            headers={**headers(token), "Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_concurrent_same_batch_once(api, project):
    http, _app, _s, _u, client, token, _a, _c = api
    value = make_batch(project, client)

    def send(_):
        return http.post("/api/v1/sync/batches", json=value, headers=headers(token))

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)
    assert (
        http.get(
            "/api/v1/projects/" + project.project_id + "/summary",
            headers=headers(token),
        ).json()["review_events"]
        == 1
    )


def test_multiuser_local_reviewer_not_authenticated_identity(api, project):
    _value, _ack = upload(api, project)
    http, _app, _s, _u, _client, token, admin, _c = api
    other = http.post(
        "/api/v1/admin/users",
        json={
            "name": "Second researcher",
            "role": "RESEARCHER",
            "client_id": str(uuid4()),
        },
        headers=headers(admin),
    ).json()
    assert (
        http.post(
            "/api/v1/admin/grants",
            json={
                "user_id": other["user_id"],
                "project_id": project.project_id,
                "crops": False,
            },
            headers=headers(admin),
        ).status_code
        == 200
    )
    p, _ = append_review(
        project,
        ReviewTarget.OBSERVATION,
        project.observations[0].observation_id,
        "claimed-admin",
        "PRESENT",
        "BPD",
        "ACCEPTED",
        "not authenticated identity",
        source_id=project.image_sources[0].source_id,
        run_id=project.analysis_runs[0].run_id,
    )
    assert (
        http.post(
            "/api/v1/sync/batches",
            json=make_batch(p, other["client_id"]),
            headers=headers(other["credential"]),
        ).status_code
        == 200
    )
    summary = http.get(
        "/api/v1/projects/" + project.project_id + "/summary", headers=headers(token)
    ).json()
    assert (
        summary["review_events"] == 2
        and summary["conflict_targets"] == 1
        and summary["ground_truth_approved"] == 0
    )
    assert (
        http.get(
            "/api/v1/admin/statistics", headers=headers(other["credential"])
        ).status_code
        == 403
    )


def crop_body(project):
    return make_crop(
        project,
        project.image_sources[0].source_id,
        project.analysis_runs[0].run_id,
        "OBSERVATION",
        project.observations[0].observation_id,
        (20, 20, 16, 16),
        consent=True,
    )


def test_crop_original_pixels_dedup_and_failed_storage(api, project, monkeypatch):
    upload(api, project)
    http, _app, sessions, _u, _cl, token, _a, _c = api
    body = crop_body(project)
    url = "/api/v1/projects/" + project.project_id + "/crops"
    response = http.post(url, json=body, headers=headers(token))
    assert response.status_code == 200, response.text
    assert http.post(url, json=body, headers=headers(token)).json() == response.json()
    with sessions() as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(Asset)
                .where(Asset.project_id == project.project_id)
            )
            == 1
        )
    from xrt_server import assets

    def fail(*args):
        raise OSError("private internal path must not leak")

    monkeypatch.setattr(assets.os, "replace", fail)
    changed = make_crop(
        project,
        project.image_sources[0].source_id,
        project.analysis_runs[0].run_id,
        "OBSERVATION",
        project.observations[0].observation_id,
        (21, 20, 17, 16),
        consent=True,
    )
    failed = http.post(url, json=changed, headers=headers(token))
    # A constant synthetic image may deduplicate bytes; metadata nevertheless stays distinct.
    assert failed.status_code == 503 and "private internal" not in failed.text
    with sessions() as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(Asset)
                .where(Asset.project_id == project.project_id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "mutation",
    ["consent", "bounds", "size", "sha", "mime", "source", "review", "path", "tiff"],
)
def test_crop_security(api, project, mutation):
    upload(api, project)
    http, _app, _s, _u, _cl, token, _a, _c = api
    body = crop_body(project)
    if mutation == "consent":
        body["consent"] = False
    elif mutation == "bounds":
        body["metadata"]["crop_x"] = 1000
    elif mutation == "size":
        body["metadata"]["crop_width"] = 2048
    elif mutation == "sha":
        body["metadata"]["crop_hash"] = "0" * 64
    elif mutation == "mime":
        body["metadata"]["mime_type"] = "image/jpeg"
    elif mutation == "source":
        body["metadata"]["source_id"] = str(uuid4())
    elif mutation == "review":
        body["metadata"]["linked_review_ids"] = [str(uuid4())]
    elif mutation == "path":
        body["filename"] = "../../escape.png"
    else:
        body["metadata"]["source_channels"] = 1
    assert (
        http.post(
            "/api/v1/projects/" + project.project_id + "/crops",
            json=body,
            headers=headers(token),
        ).status_code
        == 422
    )


def test_credential_reissue_after_revocation(api):
    http, _app, _s, _user, client, token, admin, cred = api
    assert (
        http.post(
            f"/api/v1/admin/credentials/{cred}/revoke", json={}, headers=headers(admin)
        ).status_code
        == 200
    )
    reply = http.post(
        f"/api/v1/admin/devices/{client}/credentials", json={}, headers=headers(admin)
    )
    assert reply.status_code == 200
    assert reply.json()["one_time"] and reply.json()["client_id"] == client
    assert http.get("/api/v1/health", headers=headers(token)).status_code == 401
    assert (
        http.get(
            "/api/v1/health", headers=headers(reply.json()["credential"])
        ).status_code
        == 200
    )


def test_unavailable_actual_database_has_safe_error(tmp_path):
    from fastapi.testclient import TestClient
    from xrt_server.api import create_app

    app = create_app(
        "postgresql+psycopg://xrt:synthetic-private@127.0.0.1:1/xrt_offline_test",
        tmp_path / "isolated",
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as http:
            response = http.get("/api/v1/health", headers=headers("xrt_synthetic"))
            assert response.status_code == 503
            assert response.json() == {"detail": "STORAGE_UNAVAILABLE"}
    finally:
        app.state.engine.dispose()


def test_project_crop_count_limit(api, project):
    upload(api, project)
    http, _app, sessions, user, client, token, _admin, _cred = api
    with sessions.begin() as db:
        db.add_all(
            [
                Asset(
                    project_id=project.project_id,
                    id=f"quota-{i}",
                    digest="0" * 64,
                    storage_key="0" * 64 + ".png",
                    payload={},
                    actor_id=user.id,
                    device_id=client,
                )
                for i in range(1000)
            ]
        )
    response = http.post(
        f"/api/v1/projects/{project.project_id}/crops",
        json=crop_body(project),
        headers=headers(token),
    )
    assert (
        response.status_code == 409
        and response.json()["detail"] == "PROJECT_CROP_LIMIT"
    )


def test_corrupt_crop_is_validation_error_and_never_asset(api, project):
    import base64
    import hashlib

    upload(api, project)
    http, _app, sessions, _user, _client, token, _admin, _cred = api
    body = crop_body(project)
    raw = b"invalid image bytes"
    body["image_base64"] = base64.b64encode(raw).decode()
    body["metadata"]["crop_hash"] = hashlib.sha256(raw).hexdigest()
    response = http.post(
        f"/api/v1/projects/{project.project_id}/crops",
        json=body,
        headers=headers(token),
    )
    assert response.status_code == 422
    with sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Asset)
                .where(Asset.project_id == project.project_id)
            )
            == 0
        )
