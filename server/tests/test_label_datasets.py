"""verified_xrt_dataset/v2: review-label consensus, background class, source splits, API."""

import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from xrt_server import label_datasets
from xrt_server.label_datasets import (
    CLASS_MAPPING,
    assign_splits,
    consensus,
    export_version,
    parameters,
)
from xrt_server.models import LabelDatasetVersion, User

from sic_xrt_analyzer.sync.labels import crop_rect, encode_crop, make_label

PREFIX = "/api/v1/admin/label-datasets"
DEFAULT = parameters({})


def ev(actor, cand, decision, *, parent=None, mode="key", queue="list", sha="a" * 64,
       crop=None):
    ident = str(uuid4())
    return {
        "event_id": ident, "digest": "0" * 64, "actor": actor, "source": sha, "page": 0,
        "width": 512, "height": 512, "candidate": cand, "decision": decision,
        "parent": parent, "created_at": "2026-01-01T00:00:00+00:00", "x": 1.0, "y": 2.0,
        "predicted": "TED", "scores": [0.2, 0.5, 0.3], "model_version": "m",
        "model_sha256": "d" * 64, "queue_kind": queue, "queue_seed": 7 if queue == "random"
        else None, "mode": mode, "crop_sha256": crop, "crop_rect": [0, 0, 8, 8] if crop else None,
    }


def run(events, **params):
    for i, e in enumerate(events):
        e["created_at"] = f"2026-01-01T00:00:{i:02d}+00:00"
    return consensus(events, {**DEFAULT, **params})


def by_candidate(rows):
    return {r["candidate_id"]: r for r in rows}


def test_consensus_majority_ties_unsure_and_retraction():
    first = ev("a", "undo", "TED")
    second = ev("a", "undo", "NOT_DEFECT", parent=first["event_id"])
    events = [
        ev("a", "agree", "TED", queue="random"), ev("b", "agree", "TED", mode="batch_explicit"),
        ev("a", "tie", "BPD"), ev("b", "tie", "NOT_DEFECT"),
        ev("a", "two-one", "TSD"), ev("b", "two-one", "TSD"), ev("c", "two-one", "BPD"),
        ev("a", "unsure", "UNSURE"),
        ev("a", "unsure-plus", "UNSURE"), ev("b", "unsure-plus", "TSD"),
        first, second, ev("a", "undo", "RETRACTED", parent=second["event_id"]),
        ev("a", "background", "NOT_DEFECT", crop="f" * 64),
    ]
    samples, conflicts, excluded = run(events)
    rows = by_candidate(samples)
    assert rows["agree"]["label"] == "TED" and rows["agree"]["agreement"] == 1.0
    assert rows["agree"]["n_reviewers"] == 2 and rows["agree"]["random_sample"]
    assert rows["agree"]["modes"] == ["batch_explicit", "key"]
    assert rows["agree"]["random_seeds"] == [7]
    assert rows["two-one"]["label"] == "TSD" and rows["two-one"]["agreement"] == 0.6667
    assert rows["two-one"]["votes"] == {"BPD": 1, "TSD": 2}
    assert rows["unsure-plus"]["n_reviewers"] == 1 and rows["unsure-plus"]["n_unsure"] == 1
    # Undo of the correction restores the original TED decision.
    assert rows["undo"]["label"] == "TED" and len(rows["undo"]["history_event_ids"]) == 3
    assert rows["undo"]["effective_event_ids"] == [first["event_id"]]
    background = rows["background"]
    assert background["label"] == "NOT_DEFECT" and background["is_background"]
    assert background["class_index"] == CLASS_MAPPING["NOT_DEFECT"] == 3
    assert background["crop"]["sha256"] == "f" * 64
    assert CLASS_MAPPING == {"BPD": 0, "TED": 1, "TSD": 2, "NOT_DEFECT": 3}
    assert [(c["candidate_id"], c["reason"], c["votes"]) for c in conflicts] == [
        ("tie", "TIE", {"BPD": 1, "NOT_DEFECT": 1})
    ]
    reasons = {e["candidate_id"]: e["reason"] for e in excluded}
    assert reasons == {"tie": "CONFLICT_TIE", "unsure": "UNSURE_ONLY"}

    _s, strict, _e = run(events, consensus="unanimous")
    assert {c["candidate_id"]: c["reason"] for c in strict}["two-one"] == "DISAGREEMENT"
    kept, _c, below = run(events, min_reviewers=2)
    assert "background" not in by_candidate(kept)
    assert {e["candidate_id"]: e["reason"] for e in below}["background"] == "BELOW_MIN_REVIEWERS"


def test_batch_implicit_can_be_excluded_or_down_weighted():
    events = [
        ev("a", "only-implicit", "TED", mode="batch_implicit"),
        ev("a", "mixed", "TED", mode="batch_implicit"), ev("b", "mixed", "BPD"),
    ]
    full, conflicts, _e = run(events)
    assert by_candidate(full)["only-implicit"]["batch_implicit_only"]
    assert [c["reason"] for c in conflicts] == ["TIE"]
    half, conflicts, _e = run(events, implicit_weight=0.5)
    assert by_candidate(half)["mixed"]["label"] == "BPD" and not conflicts
    assert by_candidate(half)["only-implicit"]["weight"] == 0.5
    none, _c, excluded = run(events, implicit_weight=0)
    assert by_candidate(none)["mixed"]["n_reviewers"] == 1
    assert {e["candidate_id"]: e["reason"] for e in excluded} == {
        "only-implicit": "IMPLICIT_EXCLUDED"
    }


def sample(source, ident, dhash=None, pixel=None):
    return {"sample_id": ident, "source_sha256": source, "label": "TED",
            "crop": None if pixel is None else {"pixel_hash": pixel, "dhash": dhash}}


def test_splits_are_deterministic_by_source_without_leakage():
    sources = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(60)]
    rows = [sample(s, f"{s}:{k}") for s in sources for k in range(3)]
    first = assign_splits([dict(r) for r in rows], {}, 5)
    again = assign_splits([dict(r) for r in reversed(rows)], {}, 5)
    split = {r["sample_id"]: r["split"] for r in first}
    assert split == {r["sample_id"]: r["split"] for r in again}
    per_source = {}
    for r in first:
        per_source.setdefault(r["source_sha256"], set()).add(r["split"])
    assert all(len(v) == 1 for v in per_source.values())
    assert {"train", "validation", "test"} <= {r["split"] for r in first}
    other = assign_splits([dict(r) for r in rows], {}, 6)
    assert split != {r["sample_id"]: r["split"] for r in other}
    # Growing the dataset keeps existing sources in their split.
    extra = [sample(hashlib.sha256(b"new").hexdigest(), "new")]
    grown = assign_splits([dict(r) for r in rows] + extra, {}, 5)
    assert all(split[r["sample_id"]] == r["split"] for r in grown if r["sample_id"] in split)

    # Near-duplicate crops and shared mapping groups join sources; evaluation-only pins test.
    a, b, c, d = sources[:4]
    near = [sample(a, "a", 0b1011 << 20, "p1"), sample(b, "b", 0b1010 << 20, "p2"),
            sample(c, "c", None, "p3"), sample(d, "d")]
    mappings = {c: [SimpleNamespace(id="m1", payload={"evaluation_only": True,
                                                      "group_id": "g", "wafer_id": "8"})],
                d: [SimpleNamespace(id="m2", payload={"evaluation_only": False,
                                                      "group_id": "g", "wafer_id": None})]}
    joined = {r["sample_id"]: r for r in assign_splits(near, mappings, 5)}
    assert joined["a"]["split_group_id"] == joined["b"]["split_group_id"]
    assert joined["c"]["split"] == joined["d"]["split"] == "test"
    assert joined["d"]["evaluation_only"]


def test_parameters_are_validated():
    assert DEFAULT == {"seed": 0, "min_reviewers": 1, "consensus": "majority",
                       "implicit_weight": 1.0, "received_before": None}
    for bad in ({"seed": -1}, {"min_reviewers": 0}, {"consensus": "vote"},
                {"implicit_weight": 2}, {"unknown": 1}, {"received_before": "2026-01-01"},
                {"received_before": "2999-01-01T00:00:00+00:00"}):
        with pytest.raises(ValueError):
            parameters(bad)


def headers(token):
    return {"Authorization": "Bearer " + token}


def crop_for(seed, x, y):
    rect = crop_rect(x, y, 512, 512)
    rng = np.random.default_rng(seed)
    return encode_crop(rng.integers(0, 256, (rect[3], rect[2]), dtype=np.uint8), rect)


def label(sha, cand, decision, *, parent=None, crop=None, mode="key", queue="uncertain"):
    return make_label(
        session_id=str(uuid4()), reviewer="local-name", run_id="run-1",
        source={"sha256": sha, "width": 512, "height": 512, "page": 0},
        model={"version": "frozen", "sha256": "d" * 64},
        candidate={"id": cand, "x": 100.0, "y": 120.0, "predicted": "TED",
                   "scores": [0.2, 0.5, 0.3]},
        decision=decision, parent_event_id=parent, crop=crop, mode=mode,
        queue={"kind": queue, "seed": 3 if queue == "random" else None, "rank": 0},
    )


def send(http, token, *labels):
    r = http.post("/api/v1/labels/batches",
                  json={"schema": "review_label_batch/v1", "labels": list(labels)},
                  headers=headers(token))
    assert r.status_code == 200, r.text


def test_label_dataset_api_versions_are_immutable_idempotent_and_admin_only(
        api, monkeypatch, tmp_path):
    http, _app, sessions, _user, _client, token, admin, _cred = api
    monkeypatch.setattr(label_datasets, "SETTLE", timedelta(0))
    other = http.post("/api/v1/admin/users", json={
        "name": "Second reviewer", "role": "RESEARCHER", "client_id": str(uuid4())},
        headers=headers(admin)).json()["credential"]
    tag = uuid4().hex
    shas = [hashlib.sha256(f"{tag}-{i}".encode()).hexdigest() for i in range(8)]
    for i, sha in enumerate(shas):
        send(http, token,
             label(sha, "defect", "TSD", crop=crop_for(i, 100, 120), queue="random"),
             label(sha, "background", "NOT_DEFECT", crop=crop_for(100 + i, 300, 300)))
        send(http, other, label(sha, "defect", "TSD"))
    send(http, token, label(shas[0], "split", "BPD"))
    send(http, other, label(shas[0], "split", "TED"))

    assert http.get(PREFIX, headers=headers(token)).status_code == 403
    assert http.get(PREFIX).status_code == 401
    assert http.post(PREFIX, json={"version": "x"}, headers=headers(token)).status_code == 403

    view = http.get(PREFIX + "/preview", params={"seed": 9}, headers=headers(admin))
    assert view.status_code == 200 and "rows" not in view.json()
    assert view.json()["background_class"] == "NOT_DEFECT"

    version = "labels-" + tag[:12]
    body = {"version": version, "seed": 9, "min_reviewers": 1}
    made = http.post(PREFIX, json=body, headers=headers(admin))
    assert made.status_code == 200, made.text
    created = made.json()
    assert created["created"] is True
    retry = http.post(PREFIX, json=body, headers=headers(admin)).json()
    assert retry["created"] is False and retry["dataset_hash"] == created["dataset_hash"]
    changed = http.post(PREFIX, json={**body, "min_reviewers": 2}, headers=headers(admin))
    assert changed.status_code == 409

    detail = http.get(f"{PREFIX}/{created['dataset_id']}", headers=headers(admin)).json()
    assert detail["usage_status"] == "AVAILABLE"
    manifest = detail["manifest"]
    assert (manifest["schema"], manifest["schema_version"]) == ("verified_xrt_dataset", 2)
    mine = [r for r in manifest["rows"] if r["source_sha256"] in shas]
    assert len(mine) == 16
    defect = next(r for r in mine if r["candidate_id"] == "defect")
    assert defect["n_reviewers"] == 2 and defect["agreement"] == 1.0
    assert defect["random_sample"] and defect["crop"]["rect"] == crop_rect(100, 120, 512, 512)
    assert defect["predicted"] == "TED" and defect["scores"] == [0.2, 0.5, 0.3]
    backgrounds = [r for r in mine if r["label"] == "NOT_DEFECT"]
    assert len(backgrounds) == 8 and all(r["class_index"] == 3 for r in backgrounds)
    assert any(c["candidate_id"] == "split" and c["source_sha256"] == shas[0]
               for c in manifest["conflicts"])
    splits = {}
    for r in manifest["rows"]:
        splits.setdefault(r["source_sha256"], set()).add(r["split"])
    assert all(len(v) == 1 for v in splits.values())
    page = http.get(f"{PREFIX}/{created['dataset_id']}/samples",
                    params={"label": "NOT_DEFECT", "limit": 3}, headers=headers(admin)).json()
    assert len(page["items"]) == 3 and page["total"] >= 8

    with sessions() as s:
        record = s.get(LabelDatasetVersion, created["dataset_id"])
        assert record.digest == created["dataset_hash"]
    with sessions.begin() as s, pytest.raises(DBAPIError):
        s.execute(text("UPDATE label_dataset_versions SET version='x' WHERE id=:i"),
                  {"i": created["dataset_id"]})

    admin_id = http.get("/api/v1/health", headers=headers(admin)).json()["user_id"]
    out = tmp_path / "export"
    with sessions.begin() as s:
        admin_user = s.get(User, admin_id)
        result = export_version(s, admin_user, s.get(LabelDatasetVersion, created["dataset_id"]),
                                out)
    written = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert written["dataset_hash"] == created["dataset_hash"]
    assert result["images"] == len(written["files"])
    for path, sha in written["files"].items():
        assert hashlib.sha256((out / path).read_bytes()).hexdigest() == sha
    lines = sum(len((out / "splits" / f"{n}.jsonl").read_text().splitlines())
                for n in ("train", "validation", "test"))
    assert lines == len(written["rows"])

    # A later disagreement changes a sample's consensus: the version becomes restricted.
    third = http.post("/api/v1/admin/users", json={
        "name": "Third reviewer", "role": "RESEARCHER", "client_id": str(uuid4())},
        headers=headers(admin)).json()["credential"]
    send(http, third, label(shas[1], "background", "BPD"))
    listing = {d["dataset_id"]: d for d in http.get(PREFIX, headers=headers(admin)).json()}
    status = listing[created["dataset_id"]]
    assert status["usage_status"] == "RESTRICTED"
    assert status["restriction_reasons"] == ["LABEL_CHANGED"]
    with sessions.begin() as s, pytest.raises(HTTPException):
        export_version(s, admin_user, s.get(LabelDatasetVersion, created["dataset_id"]),
                       tmp_path / "again")
    # Stored versions never move: the retry still returns the original content.
    assert http.post(PREFIX, json=body, headers=headers(admin)).json()["dataset_hash"] == \
        created["dataset_hash"]
