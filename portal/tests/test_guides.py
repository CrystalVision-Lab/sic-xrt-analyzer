"""Guide credentials never grant admin access; source screens follow upstream project grants."""

import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from xrt_portal.api import create_app


@pytest.fixture
def guide_site(tmp_path):
    project = str(uuid4())
    private = tmp_path / "private"
    private.mkdir()
    raw = b"\x89PNG\r\n\x1a\nSYNTHETIC TEST BYTES"
    (private / "viewer.png").write_bytes(raw)
    (private / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "xrt_research_guide/v1",
                "groups": [
                    {
                        "id": "viewer",
                        "title": "Viewer",
                        "project_id": project,
                        "tabs": [{"id": "open", "image_id": "viewer"}],
                    }
                ],
                "images": {
                    "viewer": {
                        "filename": "viewer.png",
                        "size": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                },
            }
        )
    )
    authority = {"revoked": False, "grant": True, "calls": []}

    def upstream(req):
        authority["calls"].append((req.method, req.url.path))
        if (
            authority["revoked"]
            or req.headers.get("authorization") != "Bearer SYNTHETIC_GUIDE_KEY"
        ):
            return httpx.Response(401, json={"detail": "AUTH"})
        if req.url.path.endswith("/health"):
            return httpx.Response(
                200, json={"user_id": "qa-researcher", "client_id": "qa-guide"}
            )
        if req.url.path == "/api/v1/projects/" + project + "/summary":
            return httpx.Response(200 if authority["grant"] else 403, json={})
        return httpx.Response(403, json={"detail": "ADMIN_REQUIRED"})

    app = create_app(
        tmp_path / "state",
        tmp_path / "releases",
        Fernet.generate_key(),
        "http://research",
        httpx.MockTransport(upstream),
        guides=private,
    )
    with TestClient(app, base_url="https://guide.test") as c:
        yield c, authority, private, raw


def login(c):
    return c.post(
        "/portal-api/guide/login",
        headers={"Origin": "https://guide.test"},
        json={"client_id": "qa-guide", "credential": "SYNTHETIC_GUIDE_KEY"},
    )


def test_anonymous_cannot_read_real_screens(guide_site):
    c, _, _, _ = guide_site
    assert c.get("/portal-api/guide").status_code == 401
    assert c.get("/portal-api/guide/images/viewer").status_code == 401


def test_researcher_reads_only_scoped_guide_and_not_admin(guide_site):
    c, a, _, raw = guide_site
    r = login(c)
    assert r.status_code == 200
    assert all(
        s in r.headers["set-cookie"].lower()
        for s in ("httponly", "secure", "samesite=strict")
    )
    data = c.get("/portal-api/guide")
    assert data.status_code == 200
    assert "project_id" not in data.json()["groups"][0]
    assert "images" not in data.json()
    assert c.get("/portal-api/guide/images/viewer").content == raw
    for path in ("admin/releases", "admin/audit", "research/admin/statistics"):
        assert c.get("/portal-api/" + path).status_code == 401
    assert all(method == "GET" for method, _ in a["calls"])
    assert c.get("/portal-api/session").json()["user"]["role"] == "RESEARCHER"


def test_revoked_project_grant_blocks_previously_visible_screen(guide_site):
    c, a, _, _ = guide_site
    login(c)
    assert c.get("/portal-api/guide/images/viewer").status_code == 200
    a["grant"] = False
    assert c.get("/portal-api/guide").status_code == 403
    assert c.get("/portal-api/guide/images/viewer").status_code == 403


def test_revoked_credential_and_image_integrity(guide_site):
    c, a, p, _ = guide_site
    login(c)
    (p / "viewer.png").write_bytes(b"changed")
    assert c.get("/portal-api/guide/images/viewer").status_code == 404
    a["revoked"] = True
    assert c.get("/portal-api/guide").status_code == 401


def test_guide_login_origin_and_logout_csrf(guide_site):
    c, _, _, _ = guide_site
    assert c.post("/portal-api/guide/login", json={}).status_code == 403
    r = login(c)
    assert (
        c.post(
            "/portal-api/logout", headers={"Origin": "https://guide.test"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/portal-api/logout",
            headers={"Origin": "https://guide.test", "X-Xrt-Csrf": r.json()["csrf"]},
        ).status_code
        == 200
    )
    assert c.get("/portal-api/guide/images/viewer").status_code == 401


def publish(p):
    path = p / "manifest.json"
    data = json.loads(path.read_text())
    data["public_tabs"] = [
        {
            "group_id": "viewer",
            "tab_id": "open",
            "image_id": "viewer",
            "sha256": data["images"]["viewer"]["sha256"],
        }
    ]
    path.write_text(json.dumps(data))


def test_public_guide_is_opt_in_and_does_not_grant_admin_access(guide_site):
    c, a, p, raw = guide_site
    assert c.get("/portal-api/guide/public").json()["groups"] == []
    assert c.get("/portal-api/guide/public/images/viewer").status_code == 404
    publish(p)
    data = c.get("/portal-api/guide/public").json()
    assert data["groups"][0]["tabs"][0]["image_id"] == "viewer"
    assert "project_id" not in data["groups"][0]
    assert "images" not in data
    assert c.get("/portal-api/guide/public/images/viewer").content == raw
    for path in (
        "session",
        "guide",
        "admin/releases",
        "admin/audit",
        "research/admin/statistics",
    ):
        assert c.get("/portal-api/" + path).status_code == 401
    assert a["calls"] == []  # Public screens never use administrator credentials.


def test_new_tabs_and_changed_images_require_new_publication(guide_site):
    c, _, p, _ = guide_site
    publish(p)
    path = p / "manifest.json"
    data = json.loads(path.read_text())
    data["groups"][0]["tabs"].append({"id": "future", "image_id": "viewer"})
    path.write_text(json.dumps(data))
    assert len(c.get("/portal-api/guide/public").json()["groups"][0]["tabs"]) == 1
    data["images"]["viewer"]["sha256"] = "a" * 64
    path.write_text(json.dumps(data))
    assert c.get("/portal-api/guide/public").json()["groups"] == []
    assert c.get("/portal-api/guide/public/images/viewer").status_code == 404


def test_public_image_integrity_allowlist_and_path_boundaries(guide_site):
    c, _, p, _ = guide_site
    publish(p)
    for ident in ("unknown", "manifest.json", "..%2Fmanifest.json"):
        assert c.get("/portal-api/guide/public/images/" + ident).status_code == 404
    (p / "viewer.png").write_bytes(b"changed")
    assert c.get("/portal-api/guide/public/images/viewer").status_code == 404
    path = p / "manifest.json"
    data = json.loads(path.read_text())
    data["images"]["viewer"]["filename"] = "../outside.png"
    path.write_text(json.dumps(data))
    assert c.get("/portal-api/guide/public/images/viewer").status_code == 404
