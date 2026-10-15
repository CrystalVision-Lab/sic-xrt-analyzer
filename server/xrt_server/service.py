from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, text

from sic_xrt_analyzer.results.reviews import ReviewRepository
from sic_xrt_analyzer.sync.protocol import (
    SPECS,
    digest,
    validate_batch,
    validate_projection,
)

from .auth import audit
from .models import ENTITIES, Batch, Snapshot


def lock(session, key):
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
    )


def rows_for(session, project_id):
    return {
        kind: {
            r.id: r.payload
            for r in session.scalars(select(cls).where(cls.project_id == project_id))
        }
        for kind, cls in ENTITIES.items()
    }


def collect(session, user, device, project, value):
    validate_batch(value)
    if value["client_id"] != device.id:
        raise HTTPException(403, "DEVICE_MISMATCH")
    lock(session, "batch:" + value["batch_id"])
    old = session.get(Batch, value["batch_id"])
    if old:
        if (old.digest, old.actor_id, old.client_id, old.project_id) != (
            value["payload_hash"],
            user.id,
            device.id,
            project.id,
        ):
            raise HTTPException(409, "BATCH_ID_CONFLICT")
        return old.receipt
    lock(session, "project:" + project.id)
    session.refresh(project)
    root = value["project"]
    if project.payload and any(
        project.payload[k] != root[k]
        for k in ("project_id", "project_name", "created_at")
    ):
        raise HTTPException(409, "PROJECT_IDENTITY_CONFLICT")
    snapshot = session.get(Snapshot, (project.id, device.id, root["revision"]))
    if snapshot and snapshot.snapshot_hash != value["snapshot_hash"]:
        raise HTTPException(409, "PROJECT_REVISION_CONFLICT")
    revisions = session.scalars(
        select(Snapshot.revision).where(
            Snapshot.project_id == project.id, Snapshot.client_id == device.id
        )
    ).all()
    if revisions and root["revision"] < max(revisions) and not snapshot:
        raise HTTPException(409, "STALE_PROJECT_REVISION")
    stored = rows_for(session, project.id)
    existing_ids = {k: set(rows) for k, rows in stored.items()}
    inserted = {k: 0 for k in SPECS}
    for kind, incoming in value["entities"].items():
        for ident, row in incoming.items():
            if ident in stored[kind] and digest(stored[kind][ident]) != digest(row):
                raise HTTPException(409, "IMMUTABLE_ENTITY_CONFLICT")
            if ident not in stored[kind]:
                inserted[kind] += 1
                stored[kind][ident] = row
    local = {k: {} for k in SPECS}
    for kind, hashes in value["inventory"].items():
        for ident, sha in hashes.items():
            if ident not in stored[kind] or digest(stored[kind][ident]) != sha:
                raise HTTPException(409, "INVENTORY_MISSING_OR_CONFLICT")
            local[kind][ident] = stored[kind][ident]
    checked = validate_projection(root, local)
    if any(
        i.assessment.ground_truth_eligible or i.assessment.adjudicated_label is not None
        for i in checked.defect_instances
    ):
        raise ValueError("SERVER_ADJUDICATION_NOT_SUPPORTED")
    union_root = dict(root)
    if project.payload and project.payload["schema_version"] == "1.1.0":
        union_root["schema_version"] = "1.1.0"
    validate_projection(union_root, stored)
    if not project.payload:
        project.payload = root
    elif union_root["schema_version"] != project.payload["schema_version"]:
        project.payload = {
            **project.payload,
            "schema_version": union_root["schema_version"],
        }
    for kind, incoming in value["entities"].items():
        cls = ENTITIES[kind]
        for ident, row in incoming.items():
            if ident not in existing_ids[kind]:
                session.add(
                    cls(
                        project_id=project.id,
                        id=ident,
                        digest=digest(row),
                        payload=row,
                        actor_id=user.id,
                        device_id=device.id,
                        **{
                            k: row.get(k)
                            for k in (
                                "source_id",
                                "run_id",
                                "geometry_id",
                                "target_id",
                                "provenance_id",
                            )
                        },
                    )
                )
    receipt = {
        "batch_id": value["batch_id"],
        "project_id": project.id,
        "client_id": device.id,
        "payload_hash": value["payload_hash"],
        "snapshot_hash": value["snapshot_hash"],
        "project_revision": root["revision"],
        "project_snapshot": root,
        "status": "ACKNOWLEDGED",
        "accepted": inserted,
        "inventory": value["inventory"],
        "received_at": datetime.now(UTC).isoformat(),
    }
    session.add(
        Batch(
            id=value["batch_id"],
            project_id=project.id,
            client_id=device.id,
            actor_id=user.id,
            digest=value["payload_hash"],
            receipt=receipt,
        )
    )
    session.flush()
    if not snapshot:
        session.add(
            Snapshot(
                project_id=project.id,
                client_id=device.id,
                revision=root["revision"],
                snapshot_hash=value["snapshot_hash"],
                batch_id=value["batch_id"],
            )
        )
    audit(
        session,
        "SYNC_SUCCESS",
        user.id,
        project.id,
        batch_id=value["batch_id"],
        accepted=inserted,
    )
    return receipt


def review_summary(project, rows):
    if not project.payload:
        return {
            "review_events": 0,
            "reviewed_targets": 0,
            "conflict_targets": 0,
            "ground_truth_approved": 0,
        }
    p = validate_projection(project.payload, rows)
    targets = {(e.target_type, e.target_id) for e in p.review_events}
    repo = ReviewRepository()
    return {
        "review_events": len(p.review_events),
        "reviewed_targets": len(targets),
        "conflict_targets": sum(
            repo.current(p, typ, ident).conflict for typ, ident in targets
        ),
        "ground_truth_approved": sum(
            i.assessment.ground_truth_eligible for i in p.defect_instances
        ),
        "manual_instances": sum(
            i.instance_status == "HUMAN" for i in p.defect_instances
        ),
        "reviewer_events": {
            r: sum(e.reviewer_id == r for e in p.review_events)
            for r in {e.reviewer_id for e in p.review_events}
        },
        "status_distribution": {
            s: sum(e.review_status.value == s for e in p.review_events)
            for s in {e.review_status.value for e in p.review_events}
        },
    }
