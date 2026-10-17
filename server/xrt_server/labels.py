"""Receipt and aggregation of append-only candidate review labels (review_label/v1)."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from sic_xrt_analyzer.sync.labels import (
    BATCH_SCHEMA,
    CLASSES,
    MAX_BATCH,
    resolve,
    validate_label,
)
from sic_xrt_analyzer.sync.protocol import digest

from .models import ReviewLabel, User


def store_batch(session, user, device, body):
    if not isinstance(body, dict) or set(body) != {"schema", "labels"} or body["schema"] != BATCH_SCHEMA:
        raise ValueError("INVALID_LABEL_BATCH")
    labels = body["labels"]
    if not isinstance(labels, list) or not 1 <= len(labels) <= MAX_BATCH:
        raise ValueError("LABEL_BATCH_SIZE")
    receipts, accepted = [], 0
    seen = set()
    for label in labels:
        validate_label(label)
        ident, signature = label["event_id"], digest(label)
        if ident in seen:
            raise ValueError("DUPLICATE_LABEL_IN_BATCH")
        seen.add(ident)
        old = session.get(ReviewLabel, ident)
        if old is not None:
            # Idempotent retry from the same author; any other reuse is a conflict.
            if old.digest != signature or old.actor_id != user.id:
                raise HTTPException(409, "LABEL_ID_CONFLICT")
        else:
            session.add(ReviewLabel(
                event_id=ident,
                digest=signature,
                actor_id=user.id,
                device_id=device.id,
                source_sha256=label["source"]["sha256"],
                candidate_id=label["candidate"]["id"],
                parent_event_id=label["parent_event_id"],
                decision=label["decision"],
                predicted=label["candidate"]["predicted"],
                queue_kind=label["queue"]["kind"],
                has_crop=label["crop"] is not None,
                created_at=datetime.fromisoformat(label["created_at"]),
                payload=label,
            ))
            accepted += 1
        receipts.append({"event_id": ident, "payload_hash": signature})
    session.flush()
    return {"status": "ACKNOWLEDGED", "accepted": accepted, "receipts": receipts}


def summary(session, weeks=12):
    """Labeling progress for administrators: effective decisions, throughput, conflicts."""
    rows = session.execute(
        select(
            ReviewLabel.event_id, ReviewLabel.actor_id, ReviewLabel.source_sha256,
            ReviewLabel.candidate_id, ReviewLabel.decision, ReviewLabel.parent_event_id,
            ReviewLabel.predicted, ReviewLabel.queue_kind, ReviewLabel.has_crop,
            ReviewLabel.created_at,
        ).order_by(ReviewLabel.created_at, ReviewLabel.received_at, ReviewLabel.event_id)
    ).all()
    names = dict(session.execute(select(User.id, User.name)).all())
    meta = {r.event_id: r for r in rows}
    # Effective decision per reviewer and candidate; undo restores the prior decision.
    effective = resolve(
        (r.event_id, (r.actor_id, r.source_sha256, r.candidate_id), r.decision, r.parent_event_id)
        for r in rows
    )
    decisions = Counter()
    confusion = defaultdict(Counter)
    by_target = defaultdict(dict)
    reviewer = defaultdict(lambda: {"labels": 0, "events": 0, "last_at": None, "recent": 0})
    random_total = random_agree = model_total = model_agree = crops = 0
    for (actor, source, candidate), (ident, decision) in effective.items():
        r = meta[ident]
        decisions[decision] += 1
        confusion[r.predicted or "-"][decision] += 1
        by_target[(source, candidate)][actor] = decision
        reviewer[actor]["labels"] += 1
        crops += r.has_crop
        if decision in CLASSES or decision == "NOT_DEFECT":
            model_total += 1
            model_agree += decision == r.predicted
            if r.queue_kind == "random":
                random_total += 1
                random_agree += decision == r.predicted
    since = datetime.now(UTC) - timedelta(days=7)
    start = datetime.now(UTC) - timedelta(weeks=weeks)
    weekly = defaultdict(Counter)
    for r in rows:
        stats = reviewer[r.actor_id]
        stats["events"] += 1
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
        if stats["last_at"] is None or created > stats["last_at"]:
            stats["last_at"] = created
        if created >= since and r.decision != "RETRACTED":
            stats["recent"] += 1
        if created >= start and r.decision != "RETRACTED":
            year, week, _ = created.isocalendar()
            weekly[f"{year}-W{week:02d}"][r.decision] += 1
    conflicts = [
        {"source_sha256": s, "candidate_id": c, "decisions": d}
        for (s, c), d in by_target.items()
        if len(set(d.values()) - {"UNSURE"}) > 1
    ]
    return {
        "schema": "review_label_summary/v1",
        "events": len(rows),
        "labeled_candidates": len(by_target),
        "decisions": dict(decisions),
        "class_labels": {c: decisions.get(c, 0) for c in CLASSES},
        "not_defect": decisions.get("NOT_DEFECT", 0),
        "unsure": decisions.get("UNSURE", 0),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "model_agreement": round(model_agree / model_total, 4) if model_total else None,
        "random_sample": {
            "labels": random_total,
            "model_agreement": round(random_agree / random_total, 4) if random_total else None,
        },
        "crops": crops,
        "weekly": [{"week": w, **dict(c)} for w, c in sorted(weekly.items())],
        "reviewers": sorted(
            (
                {
                    "user_id": actor,
                    "name": names.get(actor, actor),
                    "labels": v["labels"],
                    "events": v["events"],
                    "last_7_days": v["recent"],
                    "last_at": v["last_at"].isoformat() if v["last_at"] else None,
                }
                for actor, v in reviewer.items()
            ),
            key=lambda v: -v["labels"],
        ),
        "conflicts": len(conflicts),
        "conflict_examples": conflicts[:50],
    }
