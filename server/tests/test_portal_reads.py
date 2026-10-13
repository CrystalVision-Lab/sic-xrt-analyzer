"""New feeds keep the original ADMIN Bearer boundary and research schema."""

import hashlib
from pathlib import Path


def test_read_only_feeds_require_original_admin(api):
    http, app, _sessions, _user, _client, token, admin_token, _cred = api
    admin = {"Authorization": "Bearer " + admin_token}
    researcher = {"Authorization": "Bearer " + token}
    for path in ["projects", "batches", "audit", "users"]:
        url = "/api/v1/admin/portal/" + path
        assert http.get(url).status_code == 401
        assert http.get(url, headers=researcher).status_code == 403
        assert http.get(url, headers=admin).status_code == 200
    assert (
        http.get("/api/v1/admin/portal/projects?limit=1000", headers=admin).status_code
        == 422
    )
    assert (
        http.get("/api/v1/admin/portal/projects?offset=-1", headers=admin).status_code
        == 422
    )
    users = http.get("/api/v1/admin/portal/users", headers=admin).json()
    assert "credential" not in str(users).replace("credentials", "")
    assert token not in str(users) and admin_token not in str(users)
    assert app.state.engine.dialect.name == "postgresql"


def test_portal_crop_scope_and_digest(api, project):
    from xrt_server.models import Asset

    http, app, sessions, user, client, _token, admin_token, _cred = api
    raw = b"SYNTHETIC PNG integrity fixture"
    sha = hashlib.sha256(raw).hexdigest()
    root = Path(app.state.asset_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / (sha + ".png")).write_bytes(raw)
    with sessions.begin() as s:
        s.add(
            Asset(
                project_id=project.project_id,
                id="a" * 64,
                digest=sha,
                storage_key=sha + ".png",
                payload={},
                actor_id=user.id,
                device_id=client,
            )
        )
    headers = {"Authorization": "Bearer " + admin_token}
    base = "/api/v1/admin/portal/projects/" + project.project_id + "/crops/" + "a" * 64
    assert http.get(base, headers=headers).content == raw
    assert (
        http.get(
            base.replace(project.project_id, "wrong-project"), headers=headers
        ).status_code
        == 404
    )
    (root / (sha + ".png")).write_bytes(b"CORRUPTED")
    assert http.get(base, headers=headers).status_code == 409


def test_batch_feed_does_not_duplicate_full_project_snapshots(api, project):
    from xrt_server.models import Batch

    http, _app, sessions, user, client, _token, admin_token, _cred = api
    payload = {
        "status": "ACKNOWLEDGED",
        "accepted": {"observations": 1},
        "project_snapshot": {"observations": ["synthetic fixture"]},
        "inventory": {"synthetic": "large inventory omitted"},
    }
    with sessions.begin() as s:
        s.add(
            Batch(
                id="qa-batch-summary",
                project_id=project.project_id,
                client_id=client,
                actor_id=user.id,
                digest="1" * 64,
                receipt=payload,
            )
        )
    r = http.get(
        "/api/v1/admin/portal/batches?project_id=" + project.project_id,
        headers={"Authorization": "Bearer " + admin_token},
    )
    assert r.status_code == 200
    record = r.json()["items"][0]["receipt"]
    assert record["status"] == "ACKNOWLEDGED" and record["accepted"] == {
        "observations": 1
    }
    assert "project_snapshot" not in record and "inventory" not in record
    with sessions() as s:
        assert s.get(Batch, "qa-batch-summary").receipt == payload
