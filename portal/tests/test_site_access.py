"""Exercise the real access gate, requests and admin decisions on synthetic files."""

import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_portal import artifact, login, website
from xrt_portal.devices import DEVICE_COOKIE, Devices

__all__ = ["website"]
ORIGIN = {"Origin": "https://portal.test"}
FIELDS = {"name": "QA", "affiliation": "Synthetic lab", "device_name": "QA PC", "platform": "Test OS"}
PROTECTED = ["releases", "releases/unknown/download", "releases/unknown/source",
             "guide/public", "guide/public/images/viewer", "guide", "guide/images/viewer",
             "access/check"]


def request_device(c):
    return c.post("/portal-api/access/request", headers=ORIGIN, json=FIELDS)


def decide(admin, csrf, ident, status, revision=0, reason="Synthetic identity verified"):
    return admin.post(f"/portal-api/admin/site-devices/{ident}/state",
                      headers={**ORIGIN, "X-Xrt-Csrf": csrf},
                      json={"status": status, "revision": revision, "reason": reason})


def test_anonymous_pending_and_rejected_cannot_bypass_gate(website):
    c, store, _, _path = website
    c.cookies.clear()
    assert c.get("/portal-api/access").json() == {"allowed": False, "device": None}
    for route in PROTECTED:
        for headers in ({}, {"Range": "bytes=0-1"}, {"Authorization": "Bearer fake"}):
            r = c.get("/portal-api/" + route, headers=headers)
            assert r.status_code == 403
            assert r.headers["cache-control"] == "no-store"
    r = request_device(c)
    assert r.status_code == 201
    ident = r.json()["id"]
    token = c.cookies.get(DEVICE_COOKIE)
    assert all(v in r.headers["set-cookie"].lower() for v in ("secure", "httponly", "samesite=strict", "path=/"))
    assert token not in r.text
    assert request_device(c).json()["id"] == ident
    assert c.get("/portal-api/releases").status_code == 403
    assert c.get("/portal-api/admin/site-devices").status_code == 401
    # A forged browser/UA/platform or request body cannot confer an approval.
    assert c.post("/portal-api/access/request", headers=ORIGIN,
                  json={**FIELDS, "status": "APPROVED"}).status_code == 422
    with TestClient(c.app, base_url="https://portal.test") as admin:
        csrf = login(admin).json()["csrf"]
        listing = admin.get("/portal-api/admin/site-devices").json()
        assert token not in str(listing) and "digest" not in str(listing)
        assert decide(admin, csrf, ident, "REJECTED").status_code == 200
    assert c.get("/portal-api/access").json()["device"]["status"] == "REJECTED"
    assert request_device(c).json()["status"] == "REJECTED"
    assert c.get("/portal-api/releases").status_code == 403
    for file in store.state.glob("*"):
        if file.is_file():
            assert token.encode() not in file.read_bytes()
    assert Devices(store).get(token)["status"] == "REJECTED"  # restart persistence


def test_approval_range_download_revocation_expiry_and_admin_bootstrap(website):
    c, store, state, path = website
    ident, _file, _ = artifact(store, path)
    event = store.listing()[0]["event_id"]
    store.transition(ident, "PUBLISHED", "BETA", "Synthetic publication", event, "qa-admin")
    c.cookies.clear()
    device = request_device(c).json()
    with TestClient(c.app, base_url="https://portal.test") as admin:
        csrf = login(admin).json()["csrf"]
        assert admin.get("/portal-api/access/check").status_code == 204
        assert decide(admin, "bad", device["id"], "APPROVED").status_code == 403
        assert decide(admin, csrf, device["id"], "APPROVED").status_code == 200
        assert decide(admin, csrf, device["id"], "REVOKED", 0).status_code == 409
        assert c.get("/portal-api/access").json()["allowed"]
        assert c.get("/portal-api/releases").status_code == 200
        for suffix in ("download", "source"):
            r = c.get(f"/portal-api/releases/{ident}/{suffix}", headers={"Range": "bytes=0-1"})
            assert r.status_code == 206 and len(r.content) == 2
        assert c.get("/portal-api/admin/site-devices").status_code == 401
        assert decide(admin, csrf, device["id"], "REVOKED", 1).status_code == 200
        assert not c.get("/portal-api/access").json()["allowed"]
        assert c.get(f"/portal-api/releases/{ident}/download").status_code == 403
        assert decide(admin, csrf, device["id"], "APPROVED", 2).status_code == 200
        with store.connect() as db:
            db.execute("UPDATE site_devices SET expires=? WHERE id=?", (time.time()-1, device["id"]))
        assert c.get("/portal-api/access/check").status_code == 403
        assert decide(admin, csrf, device["id"], "REVOKED", 3).status_code == 409
        state["revoked"] = True
        assert admin.get("/portal-api/access/check").status_code == 401
        assert admin.get("/portal-api/admin/site-devices").status_code == 401


def test_requests_need_origin_valid_fields_and_persistent_rate_limit(website):
    c, store, _, _ = website
    c.cookies.clear()
    assert c.post("/portal-api/access/request", json=FIELDS).status_code == 403
    assert c.post("/portal-api/access/request", headers={"Origin": "https://evil.test"}, json=FIELDS).status_code == 403
    for value in (None, [], "", " " * 5, "x" * 121):
        assert c.post("/portal-api/access/request", headers=ORIGIN, json={**FIELDS, "name": value}).status_code == 422
    for _ in range(30):
        assert request_device(c).status_code == 201
        c.cookies.clear()
    assert request_device(c).status_code == 429
    # Restarting the in-memory gate does not reset the persisted request budget.
    with pytest.raises(HTTPException) as error:
        Devices(store).request(FIELDS, "Browser", "testclient")
    assert error.value.status_code == 429
