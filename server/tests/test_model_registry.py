"""Real PostgreSQL, isolated synthetic registry; never promotes QA to production."""

import base64
import copy
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from model_update_fixtures import bundle
from test_collection import headers
from test_datasets import approval, large, mapping, post
from test_datasets import register as register_crop
from xrt_server.auth import authenticate
from xrt_server.model_registry import (
    approve_model,
    event,
    head,
    prepare_release,
    publish,
    register,
    register_key,
    release_status,
    scientific_gate,
)
from xrt_server.models import ModelCandidate, ModelRelease

from sic_xrt_analyzer.model_updates.client import UpdateClient
from sic_xrt_analyzer.model_updates.contracts import canonical, sign_release
from sic_xrt_analyzer.model_updates.store import ModelStore


@pytest.fixture
def candidate(api, project, tmp_path):
    p = large(project, tmp_path, seed=11008)
    asset = register_crop(api, p)
    post(api, "/groups", mapping(p, group="qa-" + str(uuid4())))
    approve = post(api, "/approvals", approval(p, asset))
    d = post(
        api,
        "",
        {
            "version": "model-qa-" + str(uuid4()),
            "project_ids": [p.project_id],
            "seed": 2026,
        },
    )
    root = tmp_path / "qa-candidate"
    bundle(root, d["dataset_hash"])
    cfg = api[1].state.model_config
    cfg.update(
        root=str(tmp_path / "models"),
        realm="INTERNAL_TEST",
        registry_id="qa-" + str(uuid4()),
    )
    with api[2].begin() as s:
        user, _ = authenticate(s, "Bearer " + api[6])
        c = register(s, user, root, "qa-" + str(uuid4()), "0.1.0", d["dataset_id"], cfg)
        cid = c.id
    return cid, cfg, d, p, asset, approve, root


def release(api, candidate):
    cid, cfg, *_ = candidate
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        c = s.get(ModelCandidate, cid)
        approve_model(
            s,
            u,
            c,
            cfg,
            api[1].state.asset_dir,
            "INTERNAL_TEST",
            "Generated internal functional QA only",
            head(s, cid).id,
        )
        register_key(s, u, "qa-" + cid, public)
        m = prepare_release(
            s,
            u,
            c,
            cfg,
            api[1].state.asset_dir,
            "INTERNAL_TEST",
            "qa-" + cid,
            "Synthetic updater acceptance only",
        )
        r = publish(s, u, sign_release(m, raw), cfg, api[1].state.asset_dir)
        rid = r.id
    return rid, raw, public


def test_registration_immutable_version_role_and_real_stable_gate(api, candidate):
    cid, cfg, d, _p, _a, _e, root = candidate
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        c = s.get(ModelCandidate, cid)
        assert (
            register(s, u, root, c.model_id, c.version, d["dataset_id"], cfg).id == cid
        )
        assert not scientific_gate(s, c, api[1].state.asset_dir, "STABLE")["eligible"]
        assert not scientific_gate(s, c, api[1].state.asset_dir, "BETA")["eligible"]
        with pytest.raises(HTTPException):
            approve_model(
                s,
                u,
                c,
                cfg,
                api[1].state.asset_dir,
                "STABLE",
                "QA cannot become stable",
                head(s, cid).id,
            )
        ordinary, _ = authenticate(s, "Bearer " + api[5])
        with pytest.raises(HTTPException):
            register(s, ordinary, root, "forbidden", "1.0", d["dataset_id"], cfg)
    release(api, candidate)
    for table in ("model_candidates", "model_events", "model_releases"):
        with api[2]() as s, pytest.raises(DBAPIError):
            s.execute(text(f"UPDATE {table} SET actor_id=actor_id"))
            s.commit()


@pytest.mark.parametrize(
    "kind",
    [
        "classes",
        "registry_hash",
        "evaluation_hash",
        "dataset",
        "corrupt_onnx",
        "synthetic_production",
    ],
)
def test_invalid_candidate_rejected(api, candidate, kind):
    _cid, cfg, d, _p, _a, _e, root = candidate
    import json

    m = json.loads((root / "manifest.json").read_bytes())
    reg = json.loads((root / "candidate-registry.json").read_bytes())
    if kind == "classes":
        m["classes"].reverse()
    if kind == "registry_hash":
        reg["manifest_sha256"] = "f" * 64
    if kind == "evaluation_hash":
        m["evaluation_hash"] = "e" * 64
    if kind == "corrupt_onnx":
        (root / "model.onnx").write_bytes(b"bad")
    if kind == "synthetic_production":
        cfg = {**cfg, "realm": "PRODUCTION"}
    if kind in ("classes", "evaluation_hash"):
        (root / "manifest.json").write_bytes(canonical(m))
        reg["manifest_sha256"] = (
            __import__("hashlib")
            .sha256((root / "manifest.json").read_bytes())
            .hexdigest()
        )
    (root / "candidate-registry.json").write_bytes(canonical(reg))
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        with pytest.raises((ValueError, HTTPException)):
            register(
                s,
                u,
                root,
                "bad-" + uuid4().hex,
                "1.0",
                str(uuid4()) if kind == "dataset" else d["dataset_id"],
                cfg,
            )


def test_signed_release_internal_download_roles_revocation_and_restart(
    api, candidate, tmp_path
):
    rid, _raw, public = release(api, candidate)
    _cid, cfg, *_ = candidate
    path = "/api/v1/models/releases"
    assert (
        api[0].get(path + "?channel=INTERNAL_TEST", headers=headers(api[5])).status_code
        == 403
    )
    assert (
        api[0].get(path + "/" + rid + "/download", headers=headers(api[5])).status_code
        == 404
    )
    rows = api[0].get(path + "?channel=INTERNAL_TEST", headers=headers(api[6])).json()
    assert rows[0]["status"] == "AVAILABLE"
    envelope = rows[0]["release"]
    trust = {
        "schema": "xrt_release_trust/v1",
        "origins": {
            "http://127.0.0.1:18766": {
                "registry_id": cfg["registry_id"],
                "keys": {
                    envelope["metadata"]["signing_key_id"]: {
                        "status": "TRUSTED",
                        "public_key": public,
                    }
                },
            }
        },
    }
    import httpx

    def request(r):
        answer = api[0].get(
            str(r.url).removeprefix("http://127.0.0.1:18766"), headers=headers(api[6])
        )
        return httpx.Response(
            answer.status_code, headers=dict(answer.headers), content=answer.content
        )

    c = UpdateClient(
        "http://127.0.0.1:18766", "test-adapter", transport=httpx.MockTransport(request)
    )
    store = ModelStore(tmp_path / "desktop-models")
    try:
        record = store.install(c, envelope, trust, "INTERNAL_TEST")
    finally:
        c.close()
    assert store.verify_installed(record, trust).is_dir()
    store.activate(record)
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        r = s.get(ModelRelease, rid)
        assert publish(s, u, envelope, cfg, api[1].state.asset_dir).id == rid
        event(
            s,
            u,
            "release." + rid,
            "REVOKED",
            {"reason": "Generated revocation QA"},
            head(s, "release." + rid).id,
        )
        assert release_status(s, r, cfg, api[1].state.asset_dir) == "REVOKED"
    assert (
        api[0].get(path + "/" + rid + "/download", headers=headers(api[6])).status_code
        == 409
    )
    assert (
        api[0].get(path + "/" + rid, headers=headers(api[6])).json()["status"]
        == "REVOKED"
    )


def test_dataset_revocation_blocks_new_release_and_marks_old_review(api, candidate):
    rid, *_ = release(api, candidate)
    cid, cfg, _d, p, asset, old, _root = candidate
    post(api, "/approvals", approval(p, asset, "REVOKED", old["event_id"]))
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        c = s.get(ModelCandidate, cid)
        assert not scientific_gate(s, c, api[1].state.asset_dir, "INTERNAL_TEST")[
            "eligible"
        ]
        assert (
            release_status(s, s.get(ModelRelease, rid), cfg, api[1].state.asset_dir)
            == "DATASET_REVIEW_REQUIRED"
        )
        with pytest.raises(HTTPException):
            approve_model(
                s,
                u,
                c,
                cfg,
                api[1].state.asset_dir,
                "INTERNAL_TEST",
                "Revoked dataset cannot approve",
                head(s, cid).id,
            )


def test_signature_changed_sequence_and_public_key_revoked(api, candidate):
    rid, _raw, _ = release(api, candidate)
    _cid, cfg, *_ = candidate
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        r = s.get(ModelRelease, rid)
        changed = copy.deepcopy(r.payload)
        changed["metadata"]["release_sequence"] += 1
        with pytest.raises(ValueError):
            publish(s, u, changed, cfg, api[1].state.asset_dir)
        key_subject = "key." + r.payload["metadata"]["signing_key_id"]
        e = head(s, key_subject)
        event(
            s, u, key_subject, "KEY_REVOKED", {**e.payload, "status": "REVOKED"}, e.id
        )
        assert (
            release_status(s, r, cfg, api[1].state.asset_dir)
            == "KEY_OR_RELEASE_UNAVAILABLE"
        )


def test_registry_admin_api_cannot_upload_or_self_approve(api, candidate):
    cid, _cfg, *_ = candidate
    prefix = "/api/v1/admin/models"
    for route in ("/validate", "/approvals", "/revocations"):
        assert (
            api[0]
            .post(prefix + route, json={"candidate_id": cid}, headers=headers(api[5]))
            .status_code
            == 403
        )
    assert (
        api[0]
        .post(
            prefix + "/candidates",
            json={"bundle": "../../private"},
            headers=headers(api[6]),
        )
        .status_code
        == 405
    )
    assert (
        api[0].get(prefix + "/statistics", headers=headers(api[6])).json()["candidates"]
        >= 1
    )


def test_concurrent_approval_conflict_and_persistent_registry(api, candidate):
    from concurrent.futures import ThreadPoolExecutor

    cid, cfg, *_ = candidate
    with api[2]() as s:
        previous = head(s, cid).id

    def attempt(_):
        try:
            with api[2].begin() as s:
                u, _ = authenticate(s, "Bearer " + api[6])
                approve_model(
                    s,
                    u,
                    s.get(ModelCandidate, cid),
                    cfg,
                    api[1].state.asset_dir,
                    "INTERNAL_TEST",
                    "Concurrent functional QA only",
                    previous,
                )
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 409]
    # A fresh session/application sees the committed append-only state.
    from fastapi.testclient import TestClient
    from xrt_server.api import create_app

    fresh = create_app(api[2].kw["bind"].url, api[1].state.asset_dir)
    fresh.state.model_config.update(cfg)
    with TestClient(fresh) as http:
        rows = http.get(
            "/api/v1/admin/models/candidates", headers=headers(api[6])
        ).json()
        assert any(r["candidate_id"] == cid for r in rows)


def test_blob_failure_rolls_back_registration(api, candidate, monkeypatch):
    from sqlalchemy import select
    from xrt_server import model_registry as module

    cid, cfg, d, *_rest, root = candidate
    with api[2]() as s:
        model_id = s.get(ModelCandidate, cid).model_id

    def fail(*a):
        raise OSError("Synthetic blob failure")

    monkeypatch.setattr(module.shutil, "copyfile", fail)
    with pytest.raises(OSError), api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        register(s, u, root, model_id, "0.2.0", d["dataset_id"], cfg)
    with api[2]() as s:
        assert not s.scalar(
            select(ModelCandidate).where(
                ModelCandidate.model_id == model_id, ModelCandidate.version == "0.2.0"
            )
        )
    assert not list(Path(cfg["root"]).glob(".stage-*"))


def test_same_version_changed_manifest_denied(api, candidate):
    from sic_xrt_analyzer.model_updates.contracts import file_sha

    cid, cfg, d, *_rest, root = candidate
    m = __import__("json").loads((root / "manifest.json").read_bytes())
    m["config_hash"] = "e" * 64
    (root / "manifest.json").write_bytes(canonical(m))
    reg = __import__("json").loads((root / "candidate-registry.json").read_bytes())
    reg["manifest_sha256"] = file_sha(root / "manifest.json")
    (root / "candidate-registry.json").write_bytes(canonical(reg))
    with api[2].begin() as s:
        u, _ = authenticate(s, "Bearer " + api[6])
        c = s.get(ModelCandidate, cid)
        with pytest.raises(HTTPException, match="IMMUTABLE_MODEL_VERSION"):
            register(s, u, root, c.model_id, c.version, d["dataset_id"], cfg)


@pytest.mark.parametrize(
    "missing", ["ground_truth", "independent", "bpd", "matrix", "cpu", "restricted"]
)
def test_scientific_gate_rejects_incomplete_expert_metadata(
    api, candidate, monkeypatch, missing
):
    # In-memory QA metadata exercises the scientific predicate; never stored/published as real research.
    from types import SimpleNamespace

    from xrt_server import model_registry as module
    from xrt_server.models import DatasetVersion

    from sic_xrt_analyzer.model_updates.contracts import digest

    cid, *_ = candidate
    rows = [
        {
            "sample_id": str(i),
            "class_label": k,
            "crop_hash": "f" * 64,
            "split": split,
            "data_origin": "real_research",
        }
        for split, n in (("train", 10), ("validation", 5), ("test", 5))
        for k in ("BPD", "TED", "TSD")
        for i in range(n)
    ]
    test = [r for r in rows if r["split"] == "test"]
    metrics = {
        "class_order": ["BPD", "TED", "TSD"],
        "samples": 15,
        "accuracy": 1.0,
        "balanced_accuracy": 1.0,
        "macro_f1": 1.0,
        "confusion_matrix": [[5, 0, 0], [0, 5, 0], [0, 0, 5]],
        "per_class": [
            {"class": k, "support": 5, "precision": 1.0, "recall": 1.0, "f1": 1.0}
            for k in ("BPD", "TED", "TSD")
        ],
    }
    dataset = SimpleNamespace(
        payload={
            "project_ids": [],
            "rows": rows,
            "split_class_counts": {
                split: {k: n for k in ("BPD", "TED", "TSD")}
                for split, n in (("train", 10), ("validation", 5), ("test", 5))
            },
        }
    )
    evaluation = {
        "status": "INDEPENDENT_EVALUATION_COMPLETED",
        "scientific_metrics": True,
        "same_inputs_and_labels": True,
        "baseline_model_sha256": module.BASELINE_SHA,
        "test_sample_hash": digest(
            [(r["sample_id"], r["class_label"], r["crop_hash"]) for r in test]
        ),
        "candidate": copy.deepcopy(metrics),
        "baseline": copy.deepcopy(metrics),
    }
    c = SimpleNamespace(
        id=cid,
        realm="PRODUCTION",
        dataset_id="qa",
        payload={
            "manifest": {
                "synthetic_smoke": False,
                "model_sha256": "a" * 64,
                "candidate_status": "AWAITING_EXPERT_MODEL_ACCEPTANCE",
            },
            "registry": {"evaluation": evaluation},
        },
    )

    class Session:
        def get(self, cls, ident):
            assert cls is DatasetVersion
            return dataset

        def scalar(self, query):
            return (
                None
                if missing == "cpu"
                else SimpleNamespace(
                    payload={
                        "action": "CPU_COMPARISON",
                        **{
                            k: {
                                "status": "ARTIFACT_VERIFIED",
                                "model_sha256": h,
                                "batches": [
                                    {"batch": b, "cpu_mean_ms": 1.0} for b in (1, 7)
                                ],
                            }
                            for k, h in (
                                ("candidate", "a" * 64),
                                ("baseline", module.BASELINE_SHA),
                            )
                        },
                    }
                )
            )

    monkeypatch.setattr(
        module,
        "version_status",
        lambda *a: {
            "usage_status": "RESTRICTED" if missing == "restricted" else "AVAILABLE"
        },
    )
    if missing == "ground_truth":
        dataset.payload["rows"] = []
    if missing == "independent":
        evaluation["status"] = "SYNTHETIC_FUNCTIONAL_EVALUATION"
    if missing == "bpd":
        evaluation["candidate"]["per_class"][0].pop("recall")
    if missing == "matrix":
        evaluation["candidate"]["confusion_matrix"][0][0] = 4
    assert not scientific_gate(Session(), c, "unused", "STABLE")["eligible"]
    assert not scientific_gate(Session(), c, "unused", "BETA")["eligible"]
