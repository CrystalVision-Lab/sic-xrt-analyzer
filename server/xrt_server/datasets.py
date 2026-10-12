"""Administrator-adjudicated, immutable RGB patch datasets. No image transformations."""

import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select

from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.reviews import ReviewRepository
from sic_xrt_analyzer.sync.protocol import digest, safe_id, validate_projection

from .auth import audit, authorize
from .models import Asset, DatasetEvent, DatasetVersion, Project, now
from .service import lock, rows_for

CLASSES = ["BPD", "TED", "TSD"]
CONTRACT = {
    "shape": [3, 128, 128],
    "source": "uint8_RGB",
    "conversion": "uint8_RGB_to_NCHW_div255",
    "crop_policy": "exact_128_no_resize",
    "local_contrast_inside_model": True,
}
STATUSES = {"PENDING", "APPROVED", "REJECTED", "REVOKED", "NEEDS_ADJUDICATION"}


def require_admin(user):
    if user.role != "ADMIN" or not user.active:
        raise HTTPException(403, "ADMIN_REQUIRED")


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("EXPLICIT_VERIFIED_METADATA_REQUIRED")
    return value


def head(session, project, kind, subject):
    return session.scalar(
        select(DatasetEvent)
        .where(
            DatasetEvent.project_id == project,
            DatasetEvent.kind == kind,
            DatasetEvent.subject_id == subject,
        )
        .order_by(DatasetEvent.revision.desc())
        .limit(1)
    )


def append_event(session, user, project, kind, subject, previous, payload):
    require_admin(user)
    lock(session, "project:" + project)
    old = head(session, project, kind, subject)
    if previous != (old.id if old else None):
        raise HTTPException(409, "DATASET_EVENT_HEAD_CHANGED")
    event = DatasetEvent(
        id=str(uuid4()),
        project_id=project,
        kind=kind,
        subject_id=subject,
        revision=(old.revision + 1 if old else 1),
        actor_id=user.id,
        payload={
            **payload,
            "previous_event_id": previous,
            "adjudicator_id": user.id,
            "approval_time": now().isoformat(),
        },
    )
    session.add(event)
    session.flush()
    audit(
        session,
        "DATASET_" + kind,
        user.id,
        project,
        event_id=event.id,
        revision=event.revision,
    )
    return {"event_id": event.id, "revision": event.revision, "payload": event.payload}


def map_group(session, user, body):
    keys = {
        "project_id",
        "source_id",
        "source_hash",
        "group_id",
        "wafer_id",
        "provider_group",
        "before_after_group",
        "duplicate_group",
        "evaluation_only",
        "data_origin",
        "training_use_authorized",
        "evidence",
        "previous_event_id",
    }
    if set(body) != keys:
        raise ValueError("GROUP_FIELDS")
    project = authorize(session, user, safe_id(body["project_id"]))
    lock(session, "project:" + project.id)
    source = rows_for(session, project.id)["image_sources"].get(body["source_id"])
    if (
        not source
        or not source["content_hash"]
        or source["content_hash"]["value"] != body["source_hash"]
    ):
        raise ValueError("GROUP_SOURCE_HASH_MISMATCH")
    for key in ("group_id", "provider_group", "evidence"):
        text(body[key])
    for key in ("wafer_id", "before_after_group", "duplicate_group"):
        if body[key] is not None:
            text(body[key])
    if (
        type(body["evaluation_only"]) is not bool
        or type(body["training_use_authorized"]) is not bool
        or body["data_origin"] not in {"real_research", "synthetic_fixture"}
    ):
        raise ValueError("GROUP_VERIFICATION_REQUIRED")
    if body["wafer_id"] is not None and not re.fullmatch(
        r"0|[1-9][0-9]*", body["wafer_id"]
    ):
        raise ValueError("CANONICAL_EXPLICIT_WAFER_ID_REQUIRED")
    old = head(session, project.id, "GROUP", body["source_id"])
    if old and old.payload["data_origin"] != body["data_origin"]:
        raise ValueError("DATA_ORIGIN_IMMUTABLE_QA_CANNOT_BECOME_GROUND_TRUTH")
    if body["wafer_id"] == "8" and not body["evaluation_only"]:
        raise ValueError("WAFER8_TEST_ONLY")
    return append_event(
        session,
        user,
        project.id,
        "GROUP",
        body["source_id"],
        body["previous_event_id"],
        body,
    )


def review_state(projection, meta):
    state = ReviewRepository().current(
        projection, ReviewTarget(meta["target_type"]), meta["target_id"]
    )
    ids = sorted(i for group in state.tips_by_reviewer.values() for i in group)
    return ids, state.conflict, state.status.value


def verify_asset(asset, rows, root):
    m = asset.payload
    source = rows["image_sources"].get(m["source_id"])
    run = rows["analysis_runs"].get(m["run_id"])
    if (
        not source
        or not run
        or run["source_id"] != m["source_id"]
        or not source["content_hash"]
        or source["content_hash"]["value"] != m["source_hash"]
    ):
        raise ValueError("SOURCE_RUN_HASH_MISMATCH")
    if (source["dtype"], source["channels"], source["page_count"]) != (
        "uint8",
        3,
        1,
    ) or not source["display_name"].lower().endswith((".jpg", ".jpeg")):
        raise ValueError("JPG_RGB8_ONLY")
    table = {"OBSERVATION": "observations", "DEFECT_INSTANCE": "defect_instances"}.get(
        m["target_type"]
    )
    target = rows.get(table, {}).get(m["target_id"])
    if (
        not target
        or (table == "observations" and target["run_id"] != m["run_id"])
        or (table == "defect_instances" and target["source_id"] != m["source_id"])
    ):
        raise ValueError("TARGET_RELATION_MISMATCH")
    if any(
        i not in rows["review_events"]
        or rows["review_events"][i]["target_id"] != m["target_id"]
        or rows["review_events"][i]["target_type"] != m["target_type"]
        for i in m["linked_review_ids"]
    ):
        raise ValueError("REVIEW_RELATION_MISMATCH")
    if (
        m["source_dtype"],
        m["source_channels"],
        m["geometry_coordinate_space"],
        m["mime_type"],
    ) != ("uint8", 3, "ORIGINAL", "image/png"):
        raise ValueError("CROP_FORMAT")
    x, y, w, h = (m[k] for k in ("crop_x", "crop_y", "crop_width", "crop_height"))
    if (
        any(type(v) is not int for v in (x, y, w, h))
        or min(x, y) < 0
        or x + w > source["width"]
        or y + h > source["height"]
    ):
        raise ValueError("CROP_BOUNDS")
    if (w, h) != (128, 128):
        raise ValueError("PATCH_CONTRACT_MISMATCH")
    if asset.storage_key != m["crop_hash"] + ".png" or not re.fullmatch(
        r"[0-9a-f]{64}\.png", asset.storage_key
    ):
        raise ValueError("ASSET_PATH")
    root = Path(root).resolve()
    path = root / asset.storage_key
    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve().parent != root
        or path.stat().st_size > 4 * 1024**2
    ):
        raise ValueError("IMAGE_ASSET_MISSING_OR_UNSAFE")
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != m["crop_hash"]
        or asset.digest != m["crop_hash"]
    ):
        raise ValueError("CROP_HASH_MISMATCH")
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != (128, 128):
            raise ValueError("CROP_FORMAT")
        pixels = image.tobytes()
        if hashlib.sha256(pixels).hexdigest() != m["pixel_hash"]:
            raise ValueError("PIXEL_HASH_MISMATCH")
        # Conservative near-duplicate grouping; no claim of complete duplicate detection.
        grey = image.convert("L").resize((9, 8))
        a = list(grey.tobytes())
        dhash = sum(
            (a[y * 9 + x] > a[y * 9 + x + 1]) << (y * 8 + x)
            for y in range(8)
            for x in range(8)
        )
    provenance = rows["model_provenance"].get(run["provenance_id"])
    if not provenance:
        raise ValueError("MODEL_PROVENANCE_MISSING")
    return source, run, provenance, f"{dhash:016x}"


def approve(session, user, body, root):
    require_admin(user)
    keys = {
        "project_id",
        "asset_id",
        "status",
        "approved_class",
        "review_ids",
        "reason",
        "resolve_conflict",
        "previous_event_id",
    }
    if (
        set(body) != keys
        or body["status"] not in STATUSES
        or type(body["resolve_conflict"]) is not bool
    ):
        raise ValueError("APPROVAL_FIELDS")
    text(body["reason"])
    project = authorize(session, user, safe_id(body["project_id"]))
    lock(session, "project:" + project.id)
    asset = session.get(Asset, (project.id, body["asset_id"]))
    if not asset:
        raise ValueError("IMAGE_ASSET_MISSING")
    rows = rows_for(session, project.id)
    p = validate_projection(project.payload, rows)
    ids, conflict, status = review_state(p, asset.payload)
    if sorted(body["review_ids"]) != ids or not ids:
        raise ValueError("CURRENT_REVIEW_HEADS_REQUIRED")
    if body["status"] == "APPROVED":
        verify_asset(asset, rows, root)
        mapping = head(session, project.id, "GROUP", asset.payload["source_id"])
        if not mapping or not mapping.payload["training_use_authorized"]:
            raise ValueError("GROUP_OR_USE_RIGHTS_NOT_READY")
        if body["approved_class"] not in CLASSES:
            raise ValueError("CLASS_UNCONFIRMED")
        if conflict and not body["resolve_conflict"]:
            raise ValueError("NEEDS_ADJUDICATION")
        tips = [r for r in p.review_events if r.review_id in ids]
        if any(
            r.existence.value != "PRESENT"
            or r.class_decision.value not in CLASSES
            or r.geometry_decision.value not in {"ACCEPTED", "CORRECTED"}
            for r in tips
        ):
            raise ValueError("REVIEW_UNCERTAIN_OR_ABSENT")
        if not conflict and status not in {"CONFIRMED", "CORRECTED"}:
            raise ValueError("REVIEW_UNCONFIRMED")
    m = asset.payload
    payload = {
        **body,
        "source_id": m["source_id"],
        "run_id": m["run_id"],
        "target_id": m["target_id"],
        "source_hash": m["source_hash"],
        "crop_hash": m["crop_hash"],
        "eligibility_status": body["status"],
        "review_head_hash": digest(ids),
    }
    return append_event(
        session,
        user,
        project.id,
        "APPROVAL",
        asset.id,
        body["previous_event_id"],
        payload,
    )


def eligibility(session, project_ids, root):
    included, excluded, total = [], [], 0
    for ident in sorted(set(project_ids)):
        project = session.get(Project, safe_id(ident))
        if not project or not project.payload:
            raise ValueError("PROJECT_NOT_READY")
        rows = rows_for(session, ident)
        p = validate_projection(project.payload, rows)
        assets = session.scalars(
            select(Asset).where(Asset.project_id == ident).order_by(Asset.id)
        ).all()
        total += len(assets)
        targets = {(a.payload["target_type"], a.payload["target_id"]) for a in assets}
        for target in sorted(
            {(r["target_type"], r["target_id"]) for r in rows["review_events"].values()}
            - targets
        ):
            excluded.append(
                {
                    "project_id": ident,
                    "target_id": target[1],
                    "reason": "IMAGE_ASSET_MISSING",
                }
            )
        for asset in assets:
            reason = None
            try:
                source, _run, provenance, dhash = verify_asset(asset, rows, root)
                ids, conflict, _status = review_state(p, asset.payload)
                approval = head(session, ident, "APPROVAL", asset.id)
                mapping = head(session, ident, "GROUP", asset.payload["source_id"])
                if not mapping:
                    reason = "GROUP_NOT_READY"
                elif not mapping.payload["training_use_authorized"]:
                    reason = "USE_RIGHTS_MISSING"
                elif not approval:
                    reason = "REVIEW_CONFLICT" if conflict else "APPROVAL_MISSING"
                elif approval.payload["status"] != "APPROVED":
                    reason = approval.payload["status"]
                elif approval.payload["review_head_hash"] != digest(ids):
                    reason = "APPROVAL_STALE"
                elif conflict and not approval.payload["resolve_conflict"]:
                    reason = "REVIEW_CONFLICT"
                elif approval.payload["approved_class"] not in CLASSES:
                    reason = "CLASS_UNCONFIRMED"
                if reason:
                    raise ValueError(reason)
                m, g = asset.payload, mapping.payload
                included.append(
                    {
                        "sample_id": ident + ":" + asset.id,
                        "project_id": ident,
                        "asset_id": asset.id,
                        "source_id": m["source_id"],
                        "source_hash": m["source_hash"],
                        "source_width": source["width"],
                        "source_height": source["height"],
                        "run_id": m["run_id"],
                        "target_id": m["target_id"],
                        "review_ids": ids,
                        "approval_id": approval.id,
                        "approval_revision": approval.revision,
                        "adjudicator_id": approval.actor_id,
                        "approval_time": approval.payload["approval_time"],
                        "approval_reason": approval.payload["reason"],
                        "approval_status": "APPROVED",
                        "review_head_hash": approval.payload["review_head_hash"],
                        "group_mapping_id": mapping.id,
                        "group_mapping_revision": mapping.revision,
                        "group_evidence": g["evidence"],
                        "class_label": approval.payload["approved_class"],
                        "crop_hash": m["crop_hash"],
                        "pixel_hash": m["pixel_hash"],
                        "dhash": dhash,
                        "crop": [m["crop_x"], m["crop_y"], 128, 128],
                        "image_path": "images/" + m["crop_hash"] + ".png",
                        "model_provenance": provenance,
                        "group_id": g["group_id"],
                        "wafer_id": g["wafer_id"],
                        "provider_group": g["provider_group"],
                        "before_after_group": g["before_after_group"],
                        "duplicate_group": g["duplicate_group"],
                        "evaluation_only": g["evaluation_only"],
                        "data_origin": g["data_origin"],
                        "training_use_authorized": True,
                    }
                )
            except (ValueError, OSError) as exc:
                excluded.append(
                    {
                        "project_id": ident,
                        "asset_id": asset.id,
                        "reason": str(exc)
                        if isinstance(exc, ValueError)
                        else "IMAGE_DECODE_ERROR",
                    }
                )
    unique = {}
    conflicting_pixels = {
        h
        for h in {r["pixel_hash"] for r in included}
        if len({r["class_label"] for r in included if r["pixel_hash"] == h}) > 1
    }
    for row in included:
        if row["pixel_hash"] in conflicting_pixels:
            excluded.append(
                {
                    "project_id": row["project_id"],
                    "asset_id": row["asset_id"],
                    "reason": "DUPLICATE_LABEL_CONFLICT",
                }
            )
            continue
        if row["pixel_hash"] in unique:
            excluded.append(
                {
                    "project_id": row["project_id"],
                    "asset_id": row["asset_id"],
                    "reason": "DUPLICATE_PIXELS",
                }
            )
        else:
            unique[row["pixel_hash"]] = row
    included = sorted(unique.values(), key=lambda r: r["sample_id"])
    return {
        "collected_crops": total,
        "approved_usable_crops": len(included),
        "class_counts": dict(Counter(r["class_label"] for r in included)),
        "exclusion_counts": dict(Counter(r["reason"] for r in excluded)),
        "included": included,
        "excluded": excluded,
        "source_verification": "Registered intake identity; full original JPG absent on server",
    }


def split_rows(rows, seed):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("SPLIT_SEED")
    parents = list(range(len(rows)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen = {}
    for i, row in enumerate(rows):
        for key in (
            "source_hash",
            "run_id",
            "target_id",
            "group_id",
            "wafer_id",
            "provider_group",
            "before_after_group",
            "duplicate_group",
            "pixel_hash",
        ):
            if row[key] is not None:
                token = (key, row[key])
                if token in seen:
                    parents[find(i)] = find(seen[token])
                seen[token] = i
        for j in range(i):
            if (int(row["dhash"], 16) ^ int(rows[j]["dhash"], 16)).bit_count() <= 4:
                parents[find(i)] = find(j)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)
    ordered = sorted(
        groups.values(),
        key=lambda group: digest(
            {"seed": seed, "samples": sorted(r["sample_id"] for r in group)}
        ),
    )
    ordinary = [g for g in ordered if not any(r["evaluation_only"] for r in g)]
    assignment = {}
    nval = max(1, round(len(ordinary) * 0.15))
    pinned = len(ordered) - len(ordinary)
    ntest = max(0, max(1, round(len(ordered) * 0.15)) - pinned)
    for rank, group in enumerate(ordinary):
        # Three groups minimum: first validation, second test, remainder train.
        assignment[id(group)] = (
            "validation" if rank < nval else "test" if rank < nval + ntest else "train"
        )
    result = []
    for group in ordered:
        name = (
            "test"
            if any(r["evaluation_only"] for r in group)
            else assignment[id(group)]
        )
        gid = digest(sorted(r["sample_id"] for r in group))
        result.extend({**r, "split": name, "split_group_id": gid} for r in group)
    return sorted(result, key=lambda r: r["sample_id"])


def create_version(session, user, body, root):
    require_admin(user)
    if set(body) != {"version", "project_ids", "seed"} or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", body["version"]
    ):
        raise ValueError("DATASET_FIELDS")
    for pid in sorted(set(body["project_ids"])):
        lock(session, "project:" + safe_id(pid))
    lock(session, "dataset-version:" + body["version"])
    if session.scalar(
        select(DatasetVersion).where(DatasetVersion.version == body["version"])
    ):
        raise HTTPException(409, "DATASET_VERSION_EXISTS")
    if (
        not isinstance(body["project_ids"], list)
        or not 1 <= len(body["project_ids"]) <= 32
    ):
        raise ValueError("PROJECT_LIMIT")
    report = eligibility(session, body["project_ids"], root)
    if not report["included"]:
        raise HTTPException(409, "DATA_NOT_READY")
    if len(report["included"]) > 4096:
        raise ValueError("DATASET_SAMPLE_LIMIT")
    rows = split_rows(report["included"], body["seed"])
    files = {r["image_path"]: r["crop_hash"] for r in rows}
    split_counts = {
        s: dict(Counter(r["class_label"] for r in rows if r["split"] == s))
        for s in ("train", "validation", "test")
    }
    manifest = {
        "schema": "verified_xrt_dataset",
        "schema_version": 1,
        "dataset_id": str(uuid4()),
        "dataset_version": body["version"],
        "created_at": now().isoformat(),
        "created_by": user.id,
        "project_ids": sorted(set(body["project_ids"])),
        "included_source_ids": sorted({r["source_id"] for r in rows}),
        "included_review_ids": sorted({i for r in rows for i in r["review_ids"]}),
        "approval_ids": sorted({r["approval_id"] for r in rows}),
        "split_group_ids": sorted({r["split_group_id"] for r in rows}),
        "class_mapping": {c: i for i, c in enumerate(CLASSES)},
        "preprocessing_contract": CONTRACT,
        "seed": body["seed"],
        "rows": rows,
        "files": files,
        "file_manifest_hash": digest(files),
        "split_class_counts": split_counts,
        "eligibility_report": report,
        "readiness": "READY"
        if all(
            split_counts[s].get(c, 0) >= (10 if s == "train" else 5)
            for s in split_counts
            for c in CLASSES
        )
        and all(r["data_origin"] == "real_research" for r in rows)
        else "DATA_NOT_READY",
    }
    manifest["dataset_hash"] = digest(manifest)
    record = DatasetVersion(
        id=manifest["dataset_id"],
        version=body["version"],
        digest=manifest["dataset_hash"],
        payload=manifest,
        actor_id=user.id,
    )
    session.add(record)
    audit(
        session,
        "DATASET_VERSION_CREATED",
        user.id,
        dataset_id=record.id,
        dataset_hash=record.digest,
    )
    return manifest


def version_status(session, record, root):
    if (
        digest({k: v for k, v in record.payload.items() if k != "dataset_hash"})
        != record.digest
    ):
        raise ValueError("DATASET_HASH_MISMATCH")
    current = eligibility(session, record.payload["project_ids"], root)
    available = {r["sample_id"]: r for r in current["included"]}
    restricted = []
    for row in record.payload["rows"]:
        new = available.get(row["sample_id"])
        if not new or (new["approval_id"], new["group_mapping_id"]) != (
            row["approval_id"],
            row["group_mapping_id"],
        ):
            restricted.append(row["sample_id"])
    return {
        "usage_status": "RESTRICTED" if restricted else "AVAILABLE",
        "restricted_samples": restricted,
    }


def export_version(session, user, record, root, destination):
    require_admin(user)
    for pid in record.payload["project_ids"]:
        lock(session, "project:" + pid)
    if version_status(session, record, root)["usage_status"] != "AVAILABLE":
        raise HTTPException(409, "DATASET_RESTRICTED")
    out = Path(destination).absolute()
    if (
        any(
            p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
            for p in (out, *out.parents)
        )
        or out.exists()
    ):
        raise ValueError("NEW_SAFE_EXPORT_DIRECTORY_REQUIRED")
    out.mkdir(parents=True, mode=0o700)
    manifest = record.payload
    (out / "images").mkdir(mode=0o700)
    (out / "splits").mkdir(mode=0o700)

    def write(name, value):
        (out / name).write_text(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )

    # manifest written LAST: interrupted exports have no loadable manifest.
    for name, sha in sorted(manifest["files"].items()):
        source = Path(root) / (sha + ".png")
        raw = source.read_bytes()
        if (
            source.is_symlink()
            or len(raw) > 4 * 1024**2
            or hashlib.sha256(raw).hexdigest() != sha
        ):
            raise ValueError("EXPORT_ASSET_CHANGED")
        (out / name).write_bytes(raw)
    for split in ("train", "validation", "test"):
        (out / "splits" / (split + ".jsonl")).write_text(
            "".join(
                json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                for r in manifest["rows"]
                if r["split"] == split
            ),
            encoding="utf-8",
        )
    write("eligibility-report.json", manifest["eligibility_report"])
    write("manifest.json", manifest)
    audit(
        session,
        "DATASET_EXPORTED",
        user.id,
        dataset_id=record.id,
        dataset_hash=record.digest,
    )
    return {
        "dataset_id": record.id,
        "dataset_hash": record.digest,
        "images": len(manifest["files"]),
    }
