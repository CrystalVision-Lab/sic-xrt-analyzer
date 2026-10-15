from uuid import uuid4

from sic_xrt_analyzer.sync.protocol import digest


def payload():
    return {
        "schema": "xrt_correction/v1",
        "report_id": str(uuid4()),
        "created_at": "2026-10-15T01:00:00Z",
        "reason": "결함 아님",
        "comment": "검토",
        "candidates": [{"id": "a", "x": 24, "y": 36, "type": "BPD", "score": 0.8}],
        "run_id": "run-1",
        "source": {
            "sha256": "a" * 64,
            "width": 128,
            "height": 128,
            "dtype": "uint8",
            "page": 0,
        },
        "roi": None,
        "roi_geometry": None,
        "model_version": "model-1",
        "correction": "",
        "crops": [],
        "approval": "UNVERIFIED",
    }


def test_http_report_requires_auth_acknowledges_and_rejects_conflicts(
    tmp_path, monkeypatch
):
    from contextlib import nullcontext
    from pathlib import Path
    from types import SimpleNamespace

    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "server"))
    from xrt_server import api

    class Sessions:
        def __call__(self):
            return nullcontext(None)

        def begin(self):
            return nullcontext(None)

    def identity(session, authorization):
        if authorization != "Bearer synthetic-test-only":
            raise HTTPException(401, "AUTH_REQUIRED")
        return SimpleNamespace(id="test-user", role="RESEARCHER"), SimpleNamespace(
            id="test-device"
        )

    monkeypatch.setattr(api, "connect", lambda url: (None, Sessions()))
    monkeypatch.setattr(api, "authenticate", identity)
    monkeypatch.setattr(api, "audit", lambda *args, **kwargs: None)
    app = api.create_app(asset_dir=str(tmp_path))
    with TestClient(app) as client:
        p = payload()
        assert client.post("/api/v1/reports", json=p).status_code == 401
        auth = {"Authorization": "Bearer synthetic-test-only"}
        first = client.post("/api/v1/reports", json=p, headers=auth)
        assert first.status_code == 200 and first.json()["payload_hash"] == digest(p)
        assert (
            client.post("/api/v1/reports", json=p, headers=auth).json() == first.json()
        )
        p["comment"] = "different payload"
        assert client.post("/api/v1/reports", json=p, headers=auth).status_code == 409
        p = payload()
        p["source_path"] = "C:/private/source.jpg"
        assert client.post("/api/v1/reports", json=p, headers=auth).status_code == 422
