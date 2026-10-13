"""Security and immutable release contract on isolated portal state + explicit mock research authority."""

import hashlib
import time

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from xrt_portal.api import create_app


@pytest.fixture
def website(tmp_path):
    state = {"revoked": False, "calls": []}

    def upstream(req):
        state["calls"].append((req.method, req.url.path))
        credential = req.headers.get("authorization")
        if state["revoked"] or credential not in (
            "Bearer SYNTHETIC_ADMIN_TOKEN",
            "Bearer SYNTHETIC_RESEARCHER_TOKEN",
        ):
            return httpx.Response(401, json={"detail": "AUTH_REQUIRED"})
        if req.url.path.endswith("/health"):
            return httpx.Response(
                200, json={"user_id": "qa-admin", "client_id": "qa-client"}
            )
        if credential != "Bearer SYNTHETIC_ADMIN_TOKEN":
            return httpx.Response(403, json={"detail": "ADMIN_REQUIRED"})
        return httpx.Response(200, json={"projects": 0, "items": []})

    app = create_app(
        tmp_path / "state",
        tmp_path / "downloads",
        Fernet.generate_key(),
        "http://research",
        httpx.MockTransport(upstream),
    )
    with TestClient(app, base_url="https://portal.test") as client:
        yield client, app.state.store, state, tmp_path


def login(c, credential="SYNTHETIC_ADMIN_TOKEN", client="qa-client"):
    return c.post(
        "/portal-api/login",
        headers={"Origin": "https://portal.test"},
        json={"client_id": client, "credential": credential},
    )


def artifact(store, tmp_path, version="0.1.0"):
    file = tmp_path / "synthetic-qa-only.exe"
    file.write_bytes(b"MZ synthetic fixture; not a distributable installer")
    m = {
        "schema": "xrt_app_release/v1",
        "version": version,
        "platform": "windows-x64",
        "source_revision": "1" * 40,
        "filename": f"SiCXrtAnalyzer-{version}-windows-x64-setup.exe",
        "size": file.stat().st_size,
        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        "components": ["VIEWER"],
        "model_included": False,
        "signature": "UNSIGNED",
        "distribution_clearance": {
            "status": "APPROVED",
            "reference": "SYNTHETIC NON-DISTRIBUTABLE TEST FIXTURE ONLY",
        },
        "notes": "Synthetic test fixture only, never published to operational portal.",
        "minimum_os": "Windows 10/11",
    }
    return store.register(m, file, "qa-admin"), file, m


def test_anonymous_and_non_admin_cannot_read_research(website):
    c, _store, _state, _path = website
    for path in [
        "admin/releases",
        "admin/audit",
        "research/admin/statistics",
        "research/admin/portal/projects",
    ]:
        assert c.get("/portal-api/" + path).status_code == 401
    assert login(c, "SYNTHETIC_RESEARCHER_TOKEN").status_code == 401
    assert login(c, client="wrong-client").status_code == 401


def test_https_same_origin_body_and_login_rate(website):
    c, _store, _state, _path = website
    assert c.post("/portal-api/login", json={}).status_code == 403
    assert (
        c.post(
            "/portal-api/login", headers={"Origin": "https://evil.test"}, json={}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/portal-api/login",
            headers={"Origin": "https://portal.test"},
            content="x" * 9000,
        ).status_code
        == 415
    )
    assert (
        c.post(
            "/portal-api/login",
            headers={
                "Origin": "https://portal.test",
                "Content-Type": "application/json",
            },
            content="x" * 9000,
        ).status_code
        == 413
    )
    for _ in range(8):
        assert login(c, "bad").status_code == 401
    assert login(c, "bad").status_code == 429


def test_secure_cookie_encrypted_session_and_no_research_writes(website):
    c, _store, state, path = website
    r = login(c)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert "credential" not in r.json()
    assert c.get("/portal-api/session").status_code == 200
    assert c.get("/portal-api/research/admin/statistics").status_code == 200
    for p in [
        "admin/models/approvals",
        "admin/models/revocations",
        "admin/credentials/qa/revoke",
        "sync/batches",
    ]:
        assert c.post("/portal-api/research/" + p, json={}).status_code == 405
    assert all(method == "GET" for method, _ in state["calls"])
    assert c.get("/portal-api/research/../../private").status_code == 404
    for file in (path / "state").glob("*"):
        if file.is_file():
            assert b"SYNTHETIC_ADMIN_TOKEN" not in file.read_bytes()
    state["revoked"] = True
    assert c.get("/portal-api/session").status_code == 401
    assert c.get("/portal-api/admin/releases").status_code == 401


def test_csrf_release_lifecycle_range_and_immutable_history(website):
    c, store, _state, path = website
    ident, file, m = artifact(store, path)
    r = login(c)
    csrf = r.json()["csrf"]
    assert c.get("/portal-api/releases").json() == []
    assert c.get(f"/portal-api/releases/{ident}/download").status_code == 404
    head = store.listing()[0]["event_id"]
    b = {
        "status": "PUBLISHED",
        "channel": "BETA",
        "reason": "Explicit synthetic QA publication",
        "previous_event_id": head,
    }
    route = f"/portal-api/admin/releases/{ident}/state"
    assert (
        c.post(route, headers={"Origin": "https://portal.test"}, json=b).status_code
        == 403
    )
    assert (
        c.post(
            route, headers={"Origin": "https://evil.test", "X-Xrt-Csrf": csrf}, json=b
        ).status_code
        == 403
    )
    assert (
        c.post(
            route, headers={"Origin": "https://portal.test", "X-Xrt-Csrf": csrf}, json=b
        ).status_code
        == 200
    )
    assert (
        c.post(
            route, headers={"Origin": "https://portal.test", "X-Xrt-Csrf": csrf}, json=b
        ).status_code
        == 409
    )
    public = c.get("/portal-api/releases").json()
    assert public[0]["manifest"]["sha256"] == m["sha256"]
    assert c.get(f"/portal-api/releases/{ident}/download").content == file.read_bytes()
    response = c.get(
        f"/portal-api/releases/{ident}/download", headers={"Range": "bytes=0-1"}
    )
    assert response.status_code == 206 and response.content == b"MZ"
    b.update(status="WITHDRAWN", previous_event_id=store.listing()[0]["event_id"])
    assert (
        c.post(
            route, headers={"Origin": "https://portal.test", "X-Xrt-Csrf": csrf}, json=b
        ).status_code
        == 200
    )
    assert c.get("/portal-api/releases").json() == []
    assert len(store.history(ident)) == 3
    assert c.get(f"/portal-api/releases/{ident}/download").status_code == 404
    import sqlite3

    with pytest.raises(sqlite3.DatabaseError), store.connect() as db:
        db.execute("UPDATE events SET payload='{}'")


def test_manifest_conflict_corruption_expiry_and_logout(website):
    c, store, _state, path = website
    ident, file, m = artifact(store, path)
    assert store.register(m, file, "qa-admin") == ident
    with pytest.raises(ValueError):
        store.register({**m, "model_included": True}, file, "qa-admin")
    with pytest.raises(ValueError):
        store.register(
            {**m, "notes": "Different content for same version"}, file, "qa-admin"
        )
    file.write_bytes(b"changed")
    with pytest.raises(ValueError):
        store.register(m, file, "qa-admin")
    r = login(c)
    csrf = r.json()["csrf"]
    with store.connect() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert c.get("/portal-api/session").status_code == 401
    r = login(c)
    csrf = r.json()["csrf"]
    assert (
        c.post(
            "/portal-api/logout",
            headers={"Origin": "https://portal.test", "X-Xrt-Csrf": csrf},
            json={},
        ).status_code
        == 200
    )
    assert c.get("/portal-api/session").status_code == 401


def test_backup_preserves_release_history_but_removes_sessions(website):
    import json
    import sqlite3

    from xrt_portal.store import sha

    c, store, _state, path = website
    ident, _file, m = artifact(store, path)
    assert login(c).status_code == 200
    output = path / "backup"
    assert store.backup(output)["sessions_included"] is False
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["files"].items():
        assert sha(output / name) == entry["sha256"]
    with sqlite3.connect(output / "portal.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT id FROM releases").fetchone()[0] == ident
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert c.get("/portal-api/session").status_code == 200
    assert not (output / "portal.sqlite3-wal").exists()
    assert not (output / "portal.sqlite3-shm").exists()
    assert (output / "releases" / (m["sha256"] + ".exe")).is_file()
    with pytest.raises(FileExistsError):
        store.backup(output)


def test_pending_distribution_cannot_be_published(website):
    _c, store, _state, path = website
    _ident, file, m = artifact(store, path)
    m["version"] = "0.2.0"
    m["distribution_clearance"] = {
        "status": "PENDING",
        "reference": "Publisher distribution decision required",
    }
    ident = store.register(m, file, "qa-admin")
    pending = next(r for r in store.listing() if r["id"] == ident)
    with pytest.raises(ValueError, match="DISTRIBUTION_NOT_CLEARED"):
        store.transition(
            ident,
            "PUBLISHED",
            "BETA",
            "Must not publish without clearance",
            pending["event_id"],
            "qa-admin",
        )
    assert store.listing(public=True) == []
