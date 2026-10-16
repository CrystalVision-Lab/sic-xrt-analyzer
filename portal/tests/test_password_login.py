"""Password entry retains the upstream ADMIN boundary and expiring cookie sessions."""

import httpx
import pytest
from test_portal import website
from xrt_portal.admin_login import provision

__all__ = ["website"]  # Re-export the shared pytest fixture.

PASSWORD = "SYNTHETIC-only-password-162!"
CONFIG = {"client_id": "qa-client", "credential": "SYNTHETIC_ADMIN_TOKEN"}


def setup(c, store, name="qa-admin", password=PASSWORD, config=None):
    provision(store, c.app.state.client, name, password, config or CONFIG)


def login(c, name="qa-admin", password=PASSWORD, origin="https://portal.test"):
    return c.post("/portal-api/login", headers={"Origin": origin},
                  json={"username": name, "password": password})


def test_password_login_cookie_authority_logout_and_secret_storage(website):
    c, store, state, path = website
    setup(c, store)
    assert c.get("/portal-api/admin/releases").status_code == 401
    response = login(c, "QA-ADMIN")
    assert response.status_code == 200
    assert response.json()["user"]["name"] == "qa-admin"
    assert "password" not in response.text and "credential" not in response.text
    cookie = response.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("secure", "httponly", "samesite=strict"))
    assert c.get("/portal-api/research/admin/statistics").status_code == 200
    assert c.post("/portal-api/logout", headers={"Origin": "https://portal.test"}).status_code == 403
    assert c.post("/portal-api/logout", headers={"Origin": "https://portal.test",
                  "X-Xrt-Csrf": response.json()["csrf"]}).status_code == 200
    assert c.get("/portal-api/session").status_code == 401
    for file in (path / "state").glob("*"):
        if file.is_file():
            assert PASSWORD.encode() not in file.read_bytes()
            assert CONFIG["credential"].encode() not in file.read_bytes()
    assert all(method == "GET" for method, _ in state["calls"])


def test_rotation_invalidates_old_sessions_and_password_but_not_other_account(website):
    c, store, _state, _path = website
    setup(c, store)
    setup(c, store, "other-admin")
    assert login(c).status_code == 200
    old_cookie = c.cookies.get("xrt_portal_session")
    assert login(c, "other-admin").status_code == 200
    other_cookie = c.cookies.get("xrt_portal_session")
    setup(c, store, password=PASSWORD + "new")
    assert store.get_session(old_cookie) is None
    assert store.get_session(other_cookie) is not None
    assert login(c).status_code == 401
    assert login(c, password=PASSWORD + "new").status_code == 200
    with store.connect() as db:
        hashes = [r[0] for r in db.execute("SELECT password_hash FROM admin_logins")]
    assert all(h.startswith("scrypt-v1$") for h in hashes)
    setup(c, store, password=PASSWORD)
    with store.connect() as db:
        hashes = [r[0] for r in db.execute("SELECT password_hash FROM admin_logins")]
    assert hashes[0] != hashes[1]  # Equal passwords still have independent salts.


def test_unknown_and_wrong_password_share_failure_and_rate_limit(website):
    c, store, state, _path = website
    setup(c, store)
    state["calls"].clear()
    missing = login(c, "missing-admin")
    wrong = login(c, password="wrong")
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()
    assert state["calls"] == []
    for _ in range(7):
        assert login(c, password="wrong").status_code == 401
    assert login(c, "QA-ADMIN").status_code == 429


def test_password_login_keeps_origin_fields_and_revocation_checks(website):
    c, store, state, _path = website
    setup(c, store)
    assert login(c, origin="https://evil.test").status_code == 403
    for name, password in (("x", PASSWORD), ("qa-admin", ""), ("qa-admin", "x" * 257), ("qa-admin", 123)):
        assert login(c, name, password).status_code == 422
    assert login(c).status_code == 200
    state["revoked"] = True
    assert c.get("/portal-api/session").status_code == 401
    assert login(c).status_code == 401


def test_provision_requires_live_admin_and_matching_device(website):
    c, store, _state, _path = website
    for config in (
        {**CONFIG, "credential": "SYNTHETIC_RESEARCHER_TOKEN"},
        {**CONFIG, "client_id": "wrong-client"},
    ):
        with pytest.raises(ValueError):
            setup(c, store, config=config)
    with pytest.raises(ValueError):
        setup(c, store, password="short")
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM admin_logins").fetchone()[0] == 0
    # A rejected reset must leave the original password usable.
    setup(c, store)
    def denied(_request):
        return httpx.Response(403, json={"detail": "ADMIN_REQUIRED"})
    with httpx.Client(base_url="http://research", transport=httpx.MockTransport(denied)) as client, pytest.raises(ValueError):
        provision(store, client, "qa-admin", PASSWORD + "new", CONFIG)
    assert login(c).status_code == 200
