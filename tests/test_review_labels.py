"""review_label/v1 contract, queue ordering, undo semantics and the durable outbox."""
import copy

import numpy as np
import pytest

from sic_xrt_analyzer.sync.client import SyncError
from sic_xrt_analyzer.sync.labels import (
    LabelOutbox,
    build_queue,
    crop_rect,
    encode_crop,
    make_label,
    resolve,
    validate_label,
)
from sic_xrt_analyzer.sync.protocol import digest

SESSION = "6b2f3c9e-8a51-4c52-9f0e-0d6f3c2a1b10"
SOURCE = {"sha256": "a" * 64, "width": 1000, "height": 800, "page": 0}
MODEL = {"version": "frozen_xrt_patch_classifier", "sha256": "b" * 64}


def label(candidate="c1", decision="TED", parent=None, crop=None, **queue):
    return make_label(
        session_id=SESSION, reviewer="QA", source=SOURCE, run_id="run-1", model=MODEL,
        candidate={"id": candidate, "x": 10.0, "y": 20.0, "predicted": "TED",
                   "scores": [0.1, 0.5, 0.4]},
        decision=decision, queue=queue or None, parent_event_id=parent, crop=crop,
    )


def test_label_round_trip_and_strict_validation():
    value = label()
    assert validate_label(copy.deepcopy(value)) == value
    for mutate in (
        lambda v: v.update(extra=1),
        lambda v: v.update(decision="DEFECT"),
        lambda v: v["candidate"].update(x=5000.0),
        lambda v: v["candidate"].update(scores=[0.2, 1.4, 0.1]),
        lambda v: v["source"].update(sha256="z" * 64),
        lambda v: v.update(event_id="not-a-uuid"),
        lambda v: v.update(decision="RETRACTED"),  # retraction needs a parent
        lambda v: v["queue"].update(kind="manual"),
    ):
        broken = copy.deepcopy(value)
        mutate(broken)
        with pytest.raises(ValueError):
            validate_label(broken)


def test_crop_is_bound_to_original_rectangle():
    rect = crop_rect(5, 790, 1000, 800)
    assert rect == [0, 672, 128, 128]
    pixels = np.random.default_rng(1).integers(0, 255, (128, 128, 3), dtype=np.uint8)
    value = label(crop=encode_crop(pixels, rect))
    assert value["crop"]["rect"] == rect
    tampered = copy.deepcopy(value)
    tampered["crop"]["rect"] = [0, 0, 64, 64]
    with pytest.raises(ValueError):
        validate_label(tampered)


def test_undo_restores_the_decision_it_replaced():
    events = [("e1", "c1", "TED", None), ("e2", "c1", "NOT_DEFECT", "e1"),
              ("e3", "c2", "TSD", None), ("r1", "c1", "RETRACTED", "e2"),
              ("r2", "c2", "RETRACTED", "e3")]
    assert resolve(events) == {"c1": ("e1", "TED")}


def test_queues_uncertain_class_and_stable_random_sample():
    rows = [{"id": f"c{i}", "type": "TED" if i % 2 else "TSD", "score": 0.5,
             "scores": [0.0, 0.5 + i / 100, 0.5 - i / 100]} for i in range(10)]
    uncertain = build_queue(rows, "uncertain", done={"c0"})
    assert [i for i, _ in uncertain][:3] == ["c1", "c2", "c3"] and "c0" not in dict(uncertain)
    assert {i for i, _ in build_queue(rows, "class", cls="TED")} == {f"c{i}" for i in range(1, 10, 2)}
    first = build_queue(rows, "random", seed=7, size=4)
    assert first == build_queue(rows, "random", seed=7, size=4, done={"c1"})
    assert len(first) == 4 and first != build_queue(rows, "random", seed=8, size=4)


class Transport:
    endpoint = "https://server.test"

    def __init__(self, broken=False):
        self.broken, self.bodies = broken, []

    def request(self, method, path, body):
        assert (method, path) == ("POST", "/api/v1/labels/batches")
        self.bodies.append(body)
        receipts = [{"event_id": v["event_id"], "payload_hash": "0" * 64 if self.broken else digest(v)}
                    for v in body["labels"]]
        return {"status": "ACKNOWLEDGED", "accepted": len(receipts), "receipts": receipts}


def test_outbox_current_undo_and_batched_send(tmp_path):
    box = LabelOutbox(tmp_path / "labels.sqlite3")
    first = box.stage(label("c1", "TED"))
    second = box.stage(label("c1", "NOT_DEFECT", parent=first["event_id"]))
    box.stage(label("c2", "TSD"))
    assert box.current("a" * 64) == {"c1": (second["event_id"], "NOT_DEFECT"),
                                    "c2": (box.current("a" * 64)["c2"][0], "TSD")}
    last = box.last_event("a" * 64, SESSION)
    assert last["candidate"]["id"] == "c2"
    box.stage(label("c2", "RETRACTED", parent=last["event_id"]))
    assert "c2" not in box.current("a" * 64)
    assert box.last_event("a" * 64, SESSION)["event_id"] == second["event_id"]
    with pytest.raises(SyncError):
        box.send(Transport(broken=True))
    assert box.counts() == (4, 0)  # a failed acknowledgement keeps everything queued
    transport = Transport()
    assert box.send(transport, limit=3) == 3 and box.send(transport, limit=3) == 1
    assert box.send(transport) == 0 and box.counts() == (0, 4)
    assert transport.bodies[0]["schema"] == "review_label_batch/v1"
