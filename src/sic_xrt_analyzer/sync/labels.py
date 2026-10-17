"""Append-only candidate review labels (review_label/v1), review queues and a durable outbox.

One event per human decision. Corrections never edit an event: a later event with
``parent_event_id`` supersedes it, and ``RETRACTED`` withdraws the previous decision.
"""

import base64
import hashlib
import json
import math
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from .client import SyncError
from .protocol import digest, encode

SCHEMA = "review_label/v1"
BATCH_SCHEMA = "review_label_batch/v1"
CLASSES = ("BPD", "TED", "TSD")
DECISIONS = (*CLASSES, "NOT_DEFECT", "UNSURE", "RETRACTED")
MODES = ("key", "batch_explicit", "batch_implicit")
QUEUES = ("uncertain", "class", "random", "list")
MAX_BATCH = 100
MAX_CROP_BYTES = 96 * 1024
CROP_EDGE = 128
FIELDS = {
    "schema", "event_id", "parent_event_id", "session_id", "created_at", "reviewer",
    "source", "run_id", "model", "candidate", "decision", "mode", "queue", "dwell_ms",
    "crop",
}


def _text(value, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError("INVALID_LABEL_TEXT")


def _number(value, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("INVALID_LABEL_NUMBER")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("INVALID_LABEL_RANGE")


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("INVALID_LABEL_ID")


def validate_label(value):
    """Strict shape check shared by the desktop outbox and the server."""
    if not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != SCHEMA:
        raise ValueError("INVALID_LABEL_FIELDS")
    _uuid(value["event_id"])
    _uuid(value["session_id"])
    if value["parent_event_id"] is not None:
        _uuid(value["parent_event_id"])
    _text(value["created_at"], 64)
    datetime.fromisoformat(value["created_at"])
    _text(value["reviewer"], 120)
    _text(value["run_id"], 256, empty=True)
    source = value["source"]
    if not isinstance(source, dict) or set(source) != {"sha256", "width", "height", "page"}:
        raise ValueError("INVALID_LABEL_SOURCE")
    if not isinstance(source["sha256"], str) or len(source["sha256"]) != 64:
        raise ValueError("INVALID_LABEL_SOURCE")
    int(source["sha256"], 16)
    w, h, page = source["width"], source["height"], source["page"]
    if any(type(n) is not int for n in (w, h, page)) or not (
        0 < w <= 10_000_000 and 0 < h <= 10_000_000 and page >= 0
    ):
        raise ValueError("INVALID_LABEL_SOURCE")
    model = value["model"]
    if not isinstance(model, dict) or set(model) != {"version", "sha256"}:
        raise ValueError("INVALID_LABEL_MODEL")
    _text(model["version"], 256, empty=True)
    _text(model["sha256"], 64, empty=True)
    c = value["candidate"]
    if not isinstance(c, dict) or set(c) != {"id", "x", "y", "predicted", "scores"}:
        raise ValueError("INVALID_LABEL_CANDIDATE")
    _text(c["id"], 256)
    _number(c["x"], 0, w)
    _number(c["y"], 0, h)
    if c["predicted"] not in (*CLASSES, ""):
        raise ValueError("INVALID_LABEL_CANDIDATE")
    if not isinstance(c["scores"], list) or len(c["scores"]) not in (0, 3):
        raise ValueError("INVALID_LABEL_SCORES")
    for score in c["scores"]:
        _number(score, 0, 1)
    if value["decision"] not in DECISIONS:
        raise ValueError("INVALID_LABEL_DECISION")
    if value["decision"] == "RETRACTED" and value["parent_event_id"] is None:
        raise ValueError("RETRACTION_REQUIRES_PARENT")
    if value["mode"] not in MODES:
        raise ValueError("INVALID_LABEL_MODE")
    q = value["queue"]
    if not isinstance(q, dict) or set(q) != {"kind", "seed", "rank"} or q["kind"] not in QUEUES:
        raise ValueError("INVALID_LABEL_QUEUE")
    if q["seed"] is not None and (type(q["seed"]) is not int or q["seed"] < 0):
        raise ValueError("INVALID_LABEL_QUEUE")
    if type(q["rank"]) is not int or q["rank"] < 0:
        raise ValueError("INVALID_LABEL_QUEUE")
    if type(value["dwell_ms"]) is not int or not 0 <= value["dwell_ms"] <= 86_400_000:
        raise ValueError("INVALID_LABEL_DWELL")
    crop = value["crop"]
    if crop is not None:
        _validate_crop(crop, w, h)
    if len(encode(value)) > 256 * 1024:
        raise ValueError("LABEL_TOO_LARGE")
    return value


def _validate_crop(crop, width, height):
    if not isinstance(crop, dict) or set(crop) != {"rect", "png", "sha256"}:
        raise ValueError("INVALID_LABEL_CROP")
    rect = crop["rect"]
    if not isinstance(rect, list) or len(rect) != 4 or any(type(n) is not int for n in rect):
        raise ValueError("INVALID_LABEL_CROP")
    x, y, cw, ch = rect
    if not (0 <= x and 0 <= y and 0 < cw <= CROP_EDGE and 0 < ch <= CROP_EDGE
            and x + cw <= width and y + ch <= height):
        raise ValueError("INVALID_LABEL_CROP")
    raw = base64.b64decode(crop["png"], validate=True)
    if (len(raw) > MAX_CROP_BYTES or not raw.startswith(b"\x89PNG\r\n\x1a\n")
            or hashlib.sha256(raw).hexdigest() != crop["sha256"]):
        raise ValueError("INVALID_LABEL_CROP")
    import io

    from PIL import Image

    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.size != (cw, ch):
            raise ValueError("INVALID_LABEL_CROP")
        image.verify()


def encode_crop(rgb, rect):
    """PNG-encode an original-pixel crop (uint8 RGB or gray) for a label."""
    import io

    import numpy as np
    from PIL import Image

    array = np.asarray(rgb)
    if array.dtype != np.uint8:
        raise ValueError("CROP_REQUIRES_UINT8")
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG", optimize=True)
    raw = buffer.getvalue()
    return {"rect": [int(v) for v in rect], "png": base64.b64encode(raw).decode(),
            "sha256": hashlib.sha256(raw).hexdigest()}


def crop_rect(x, y, width, height, edge=CROP_EDGE):
    """Square window centred on (x, y), shifted inside the image."""
    w, h = min(edge, width), min(edge, height)
    left = min(max(0, round(x) - w // 2), width - w)
    top = min(max(0, round(y) - h // 2), height - h)
    return [left, top, w, h]


def make_label(*, session_id, reviewer, source, run_id, model, candidate, decision,
               mode="key", queue=None, dwell_ms=0, parent_event_id=None, crop=None):
    value = {
        "schema": SCHEMA,
        "event_id": str(uuid4()),
        "parent_event_id": parent_event_id,
        "session_id": session_id,
        "created_at": datetime.now(UTC).isoformat(),
        "reviewer": reviewer,
        "source": source,
        "run_id": run_id or "",
        "model": model,
        "candidate": candidate,
        "decision": decision,
        "mode": mode,
        "queue": queue or {"kind": "list", "seed": None, "rank": 0},
        "dwell_ms": int(max(0, min(dwell_ms, 86_400_000))),
        "crop": crop,
    }
    return validate_label(value)


def resolve(events):
    """Effective decision per (reviewer, candidate) from ordered (id, candidate, decision, parent).

    A retraction removes exactly the event it names, so undo restores the decision
    that the retracted event had replaced.
    """
    history = {}
    owner = {}
    for ident, candidate, decision, parent in events:
        if decision == "RETRACTED":
            target = owner.pop(parent, None)
            if target is not None:
                history[target] = [e for e in history[target] if e[0] != parent]
        else:
            history.setdefault(candidate, []).append((ident, decision))
            owner[ident] = candidate
    return {c: h[-1] for c, h in history.items() if h}


def margin(scores):
    """Top-1 minus top-2 probability; small means the model is unsure."""
    if len(scores) < 2:
        return 1.0
    top = sorted(scores, reverse=True)
    return float(top[0] - top[1])


def build_queue(rows, kind, *, cls="", seed=0, size=50, done=()):
    """Return [(candidate_id, rank)] for a review queue.

    ``uncertain``: smallest score margin first. ``class``: one predicted class, least
    confident first. ``random``: a fixed-seed sample of the whole run (unbiased
    estimate of model accuracy) — reviewed items keep their rank so the sample is stable.
    """
    done = set(done)
    if kind == "random":
        ids = sorted(r["id"] for r in rows)
        random.Random(seed).shuffle(ids)
        return [(ident, rank) for rank, ident in enumerate(ids[:size])]
    if kind == "class":
        rows = [r for r in rows if r["type"] == cls]
    elif kind != "uncertain":
        rows = list(rows)
    key = (lambda r: (margin(r.get("scores") or []), r.get("score", 0), r["id"]))
    ordered = sorted(rows, key=key)
    pending = [r["id"] for r in ordered if r["id"] not in done]
    return [(ident, rank) for rank, ident in enumerate(pending)]


class LabelOutbox:
    """SQLite outbox: labels are durable locally first, then sent in batches."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS labels(id TEXT PRIMARY KEY,source TEXT NOT NULL,"
                "candidate TEXT NOT NULL,decision TEXT NOT NULL,parent TEXT,payload TEXT NOT NULL,"
                "hash TEXT NOT NULL,endpoint TEXT NOT NULL DEFAULT '',state TEXT NOT NULL "
                "DEFAULT 'PENDING',error TEXT NOT NULL DEFAULT '')"
            )
            db.execute("CREATE INDEX IF NOT EXISTS labels_target ON labels(source,candidate)")

    def db(self):
        return sqlite3.connect(self.path, timeout=10)

    def stage(self, label):
        validate_label(label)
        with self.db() as db:
            db.execute(
                "INSERT INTO labels(id,source,candidate,decision,parent,payload,hash) "
                "VALUES(?,?,?,?,?,?,?)",
                (label["event_id"], label["source"]["sha256"], label["candidate"]["id"],
                 label["decision"], label["parent_event_id"], encode(label).decode(),
                 digest(label)),
            )
        return label

    def current(self, source_sha256):
        """Latest effective decision per candidate: {candidate_id: (event_id, decision)}."""
        with self.db() as db:
            return resolve(db.execute(
                "SELECT id,candidate,decision,parent FROM labels WHERE source=? ORDER BY rowid",
                (source_sha256,),
            ).fetchall())

    def last_event(self, source_sha256, session_id):
        """Most recent non-retracted decision event of this session (for undo)."""
        with self.db() as db:
            rows = db.execute(
                "SELECT id,payload,decision,parent FROM labels WHERE source=? ORDER BY rowid DESC",
                (source_sha256,),
            ).fetchall()
        retracted = {parent for _i, _p, decision, parent in rows if decision == "RETRACTED"}
        for ident, payload, decision, _parent in rows:
            value = json.loads(payload)
            if (decision != "RETRACTED" and ident not in retracted
                    and value["session_id"] == session_id):
                return value
        return None

    def counts(self):
        with self.db() as db:
            values = dict(db.execute("SELECT state,COUNT(*) FROM labels GROUP BY state"))
        return sum(v for k, v in values.items() if k != "SENT"), values.get("SENT", 0)

    def pending(self, endpoint, limit=MAX_BATCH):
        with self.db() as db:
            return [
                {"id": r[0], "payload": json.loads(r[1]), "hash": r[2]}
                for r in db.execute(
                    "SELECT id,payload,hash FROM labels WHERE state!='SENT' AND endpoint IN ('',?) "
                    "ORDER BY rowid LIMIT ?",
                    (endpoint, limit),
                )
            ]

    def send(self, transport, limit=MAX_BATCH):
        """Send one batch; returns the number acknowledged. Failures stay queued."""
        rows = self.pending(transport.endpoint, limit)
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        with self.db() as db:
            db.execute(f"UPDATE labels SET endpoint=?,state='SENDING',error='' WHERE id IN ({marks})",
                       (transport.endpoint, *ids))
        body = {"schema": BATCH_SCHEMA, "labels": [r["payload"] for r in rows]}
        try:
            ack = transport.request("POST", "/api/v1/labels/batches", body)
            receipts = {r["event_id"]: r["payload_hash"] for r in ack.get("receipts", [])}
            if ack.get("status") != "ACKNOWLEDGED" or any(
                receipts.get(r["id"]) != r["hash"] for r in rows
            ):
                raise SyncError("LABEL_ACK_MISMATCH")
        except Exception as exc:  # noqa: BLE001 -- keep transport and storage failures queued
            code = str(exc) if isinstance(exc, SyncError) else "LABEL_SEND_FAILED"
            with self.db() as db:
                db.execute(f"UPDATE labels SET state='FAILED',error=? WHERE id IN ({marks})",
                           (code, *ids))
            raise SyncError(code) from None
        with self.db() as db:
            db.execute(f"UPDATE labels SET state='SENT',error='' WHERE id IN ({marks})", ids)
        return len(rows)
