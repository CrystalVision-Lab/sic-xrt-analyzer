"""review_label/v1 receipt (idempotent, append-only) and the administrator summary."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from sic_xrt_analyzer.sync.labels import make_label
from sic_xrt_analyzer.sync.protocol import digest


def headers(token):
    return {"Authorization": "Bearer " + token}


def label(candidate, decision, *, predicted="TED", parent=None, queue="uncertain", sha=None):
    return make_label(
        session_id=str(uuid4()), reviewer="local-name", run_id="run-1",
        source={"sha256": sha or "c" * 64, "width": 512, "height": 512, "page": 0},
        model={"version": "frozen", "sha256": "d" * 64},
        candidate={"id": candidate, "x": 10.0, "y": 12.0, "predicted": predicted,
                   "scores": [0.2, 0.5, 0.3]},
        decision=decision, parent_event_id=parent,
        queue={"kind": queue, "seed": 7 if queue == "random" else None, "rank": 0},
    )


def batch(*labels):
    return {"schema": "review_label_batch/v1", "labels": list(labels)}


def test_labels_are_idempotent_append_only_and_validated(api):
    http, _app, sessions, _user, _client, token, _admin, _cred = api
    first = label("lab-a", "TED")
    r = http.post("/api/v1/labels/batches", json=batch(first), headers=headers(token))
    assert r.status_code == 200
    assert r.json()["receipts"] == [{"event_id": first["event_id"], "payload_hash": digest(first)}]
    assert r.json()["accepted"] == 1
    # A retry after a lost acknowledgement is accepted without a duplicate row.
    again = http.post("/api/v1/labels/batches", json=batch(first), headers=headers(token))
    assert again.status_code == 200 and again.json()["accepted"] == 0
    changed = dict(first, decision="TSD")
    assert http.post("/api/v1/labels/batches", json=batch(changed),
                     headers=headers(token)).status_code == 409
    broken = dict(first, event_id=str(uuid4()), decision="MAYBE")
    assert http.post("/api/v1/labels/batches", json=batch(broken),
                     headers=headers(token)).status_code == 422
    assert http.post("/api/v1/labels/batches", json=batch(first)).status_code == 401
    with sessions.begin() as s, pytest.raises(DBAPIError):
        s.execute(text("UPDATE review_labels SET decision='BPD' WHERE event_id=:i"),
                  {"i": first["event_id"]})


def test_summary_resolves_undo_conflicts_and_is_admin_only(api):
    http, _app, _s, _user, _client, token, admin, _cred = api
    other = http.post("/api/v1/admin/users", json={
        "name": "Second reviewer", "role": "RESEARCHER", "client_id": str(uuid4())},
        headers=headers(admin)).json()
    sha = "e" * 64
    base = http.get("/api/v1/admin/labels/summary", headers=headers(admin)).json()
    first = label("sum-1", "TED", sha=sha)
    second = label("sum-1", "NOT_DEFECT", parent=first["event_id"], sha=sha)
    undo = label("sum-1", "RETRACTED", parent=second["event_id"], sha=sha)
    sample = label("sum-2", "TSD", predicted="TSD", queue="random", sha=sha)
    assert http.post("/api/v1/labels/batches", json=batch(first, second, undo, sample),
                     headers=headers(token)).status_code == 200
    disagree = label("sum-1", "NOT_DEFECT", sha=sha)
    assert http.post("/api/v1/labels/batches", json=batch(disagree),
                     headers=headers(other["credential"])).status_code == 200
    assert http.get("/api/v1/admin/labels/summary",
                    headers=headers(token)).status_code == 403
    s = http.get("/api/v1/admin/labels/summary", headers=headers(admin)).json()
    assert s["events"] == base["events"] + 5
    # The undo restores TED for the first reviewer; the second reviewer says not a defect.
    assert s["class_labels"]["TED"] == base["class_labels"]["TED"] + 1
    assert s["class_labels"]["TSD"] == base["class_labels"]["TSD"] + 1
    assert s["not_defect"] == base["not_defect"] + 1
    assert s["conflicts"] == base["conflicts"] + 1
    assert s["random_sample"]["labels"] == base["random_sample"]["labels"] + 1
    names = {r["name"] for r in s["reviewers"]}
    assert "Second reviewer" in names
    assert s["weekly"] and sum(w.get("TED", 0) for w in s["weekly"]) >= 1
