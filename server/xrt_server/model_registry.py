"""Authenticated local registration; immutable CAS; independent scientific/release gates."""

import base64
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text

from sic_xrt_analyzer.model_updates.contracts import (
    MAX_METADATA,
    MODEL_QUOTA,
    digest,
    file_sha,
    frozen_manifest,
    read_json,
    safe_name,
    safe_path,
    sha,
    verify_release,
)

from .auth import audit
from .datasets import require_admin, version_status
from .models import DatasetVersion, ModelCandidate, ModelEvent, ModelRelease

BASELINE_SHA = "24368b8f6613cba5251c0bd8e63d7ddec726d6343a35ed878e823a0091369694"


def config():
    return {
        "root": os.getenv("XRT_MODEL_DIR", "/data/models"),
        "realm": os.getenv("XRT_MODEL_REALM", "PRODUCTION"),
        "registry_id": os.getenv("XRT_MODEL_REGISTRY_ID", "xrt-local-production"),
    }


def lock(s):
    s.execute(text("SELECT pg_advisory_xact_lock(11008)"))


def head(s, subject):
    return s.scalar(
        select(ModelEvent)
        .where(ModelEvent.subject_id == subject)
        .order_by(ModelEvent.revision.desc())
        .limit(1)
    )


def event(s, user, subject, action, payload, previous=None):
    require_admin(user)
    lock(s)
    old = head(s, subject)
    if previous is not None and (not old or old.id != previous):
        raise HTTPException(409, "MODEL_EVENT_CONFLICT")
    row = ModelEvent(
        id=str(uuid4()),
        subject_id=subject,
        revision=old.revision + 1 if old else 1,
        payload={**payload, "action": action},
        actor_id=user.id,
    )
    s.add(row)
    s.flush()
    audit(s, "MODEL_" + action, user.id, subject=subject, event_id=row.id)
    return row


def lookup(s, candidate_id, cfg):
    c = s.get(ModelCandidate, safe_name(candidate_id))
    if not c or c.realm != cfg["realm"]:
        raise HTTPException(404, "MODEL_NOT_FOUND")
    return c


def artifact(c, cfg):
    return safe_path(Path(cfg["root"]) / sha(c.payload["artifact_key"]))


def check_files(c, cfg):
    root = artifact(c, cfg)
    m = c.payload["manifest"]
    for name, expected, maximum in (
        ("model.onnx", m["model_sha256"], 64 * 1024**2),
        ("manifest.json", c.payload["manifest_sha256"], MAX_METADATA),
        ("candidate-registry.json", c.payload["registry_sha256"], MAX_METADATA),
    ):
        if file_sha(root / name, maximum) != expected:
            raise ValueError("REGISTERED_ARTIFACT_CHANGED")
    return root


def register(s, user, bundle, model_id, version, dataset_id, cfg, validator=None):
    require_admin(user)
    lock(s)
    safe_name(model_id)
    safe_name(version)
    source = safe_path(bundle)
    if {p.name for p in source.iterdir()} != {
        "model.onnx",
        "manifest.json",
        "candidate-registry.json",
    }:
        raise ValueError("CANDIDATE_FILE_INVENTORY")
    file_sha(source / "manifest.json", MAX_METADATA)
    file_sha(source / "candidate-registry.json", MAX_METADATA)
    m = frozen_manifest(read_json((source / "manifest.json").read_bytes()))
    reg = read_json((source / "candidate-registry.json").read_bytes())
    for field in (
        "dataset_hash",
        "config_hash",
        "checkpoint_sha256",
        "evaluation_hash",
    ):
        sha(m[field])
    mh = file_sha(source / "manifest.json", MAX_METADATA)
    rh = file_sha(source / "candidate-registry.json", MAX_METADATA)
    evaluation = reg["evaluation"]
    if (
        reg.get("schema") != "xrt_model_candidate/v1"
        or reg.get("candidate_id") != m["model_sha256"]
        or reg.get("manifest_sha256") != mh
        or reg.get("dataset_hash") != m["dataset_hash"]
        or digest(evaluation) != m["evaluation_hash"]
        or evaluation.get("dataset_hash") != m["dataset_hash"]
        or evaluation.get("checkpoint_sha256") != m["checkpoint_sha256"]
        or reg.get("status") != m.get("candidate_status")
        or reg.get("distribution") != "NOT_AUTHORIZED"
    ):
        raise ValueError("CANDIDATE_PROVENANCE")
    file_sha(source / "model.onnx")
    dataset = s.get(DatasetVersion, dataset_id)
    if not dataset or dataset.digest != m["dataset_hash"]:
        raise ValueError("DATASET_REFERENCE")
    if not dataset.payload["rows"]:
        raise ValueError("EMPTY_DATASET")
    synthetic = any(
        r["data_origin"] != "real_research" for r in dataset.payload["rows"]
    )
    if synthetic != (m.get("synthetic_smoke") is True) or synthetic != (
        evaluation.get("scientific_metrics") is False
    ):
        raise ValueError("CANDIDATE_ORIGIN")
    if cfg["realm"] not in ("PRODUCTION", "INTERNAL_TEST") or (
        synthetic and cfg["realm"] != "INTERNAL_TEST"
    ):
        raise ValueError("SYNTHETIC_PRODUCTION_FORBIDDEN")
    previous = s.scalar(
        select(ModelCandidate).where(
            ModelCandidate.model_id == model_id, ModelCandidate.version == version
        )
    )
    if previous:
        if (
            previous.payload["manifest_sha256"] == mh
            and previous.payload["registry_sha256"] == rh
        ):
            check_files(previous, cfg)
            return previous
        raise HTTPException(409, "IMMUTABLE_MODEL_VERSION")
    from sic_xrt_analyzer.model_updates.validation import validate_bundle

    validation = (validator or validate_bundle)(source)
    if (
        validation.get("status") != "ARTIFACT_VERIFIED"
        or validation.get("model_sha256") != m["model_sha256"]
    ):
        raise ValueError("ARTIFACT_VALIDATION")
    root = safe_path(cfg["root"])
    root.mkdir(parents=True, exist_ok=True)
    if (
        sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        + sum(p.stat().st_size for p in source.iterdir())
        > MODEL_QUOTA
    ):
        raise ValueError("MODEL_STORAGE_QUOTA")
    key = digest({"model": m["model_sha256"], "manifest": mh, "registry": rh})
    final = root / key
    stage = root / (".stage-" + str(uuid4()))
    stage.mkdir(mode=0o700)
    try:
        for name, expected in (
            ("model.onnx", m["model_sha256"]),
            ("manifest.json", mh),
            ("candidate-registry.json", rh),
        ):
            shutil.copyfile(safe_path(source / name), stage / name)
            if (
                file_sha(
                    stage / name, 64 * 1024**2 if name == "model.onnx" else MAX_METADATA
                )
                != expected
            ):
                raise ValueError("ARTIFACT_CHANGED_DURING_COPY")
        if final.exists():
            for name in ("model.onnx", "manifest.json", "candidate-registry.json"):
                if file_sha(final / name) != file_sha(stage / name):
                    raise ValueError("CAS_COLLISION")
        else:
            stage.rename(final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    row = ModelCandidate(
        id=str(uuid4()),
        model_id=model_id,
        version=version,
        realm=cfg["realm"],
        dataset_id=dataset_id,
        payload={
            "manifest": m,
            "manifest_sha256": mh,
            "registry_sha256": rh,
            "artifact_key": key,
            "registry": reg,
            "validation": validation,
        },
        actor_id=user.id,
    )
    s.add(row)
    s.flush()
    event(s, user, row.id, "ARTIFACT_VERIFIED", {"validation": validation})
    return row


def valid_metrics(metrics, rows):
    """Recompute metric identities from integer confusion counts and actual test labels."""
    import math

    matrix = metrics["confusion_matrix"]
    if any(not isinstance(row, list) or len(row) != 3 for row in matrix):
        return False
    if any(type(v) is not int or v < 0 for row in matrix for v in row):
        return False
    total = len(rows)
    if not total or sum(map(sum, matrix)) != total:
        return False
    recalls, f1s = [], []
    for i, label in enumerate(("BPD", "TED", "TSD")):
        support = sum(r["class_label"] == label for r in rows)
        if sum(matrix[i]) != support or not support:
            return False
        tp, predicted = matrix[i][i], sum(row[i] for row in matrix)
        precision, recall = tp / predicted if predicted else 0, tp / support
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        values = metrics["per_class"][i]
        if any(
            not isinstance(values.get(k), (int, float))
            or not math.isclose(values[k], v, abs_tol=1e-6)
            for k, v in (("precision", precision), ("recall", recall), ("f1", f1))
        ):
            return False
        recalls.append(recall)
        f1s.append(f1)
    return all(
        math.isclose(metrics[k], v, abs_tol=1e-6)
        for k, v in (
            ("accuracy", sum(matrix[i][i] for i in range(3)) / total),
            ("balanced_accuracy", sum(recalls) / 3),
            ("macro_f1", sum(f1s) / 3),
        )
    )


def scientific_gate(s, c, asset_root, channel):
    dataset = s.get(DatasetVersion, c.dataset_id)
    if dataset:
        from .service import lock as project_lock

        for project in sorted(dataset.payload["project_ids"]):
            project_lock(s, project)
    reasons = []
    if (
        not dataset
        or version_status(s, dataset, asset_root)["usage_status"] != "AVAILABLE"
    ):
        reasons.append("DATASET_RESTRICTED")
    m = c.payload["manifest"]
    e = c.payload["registry"]["evaluation"]
    if channel == "INTERNAL_TEST":
        if c.realm != "INTERNAL_TEST":
            reasons.append("ISOLATED_REGISTRY_REQUIRED")
        return {"eligible": not reasons, "reasons": reasons, "scientific": False}
    if channel not in ("STABLE", "BETA") or c.realm != "PRODUCTION":
        reasons.append("CHANNEL_REALM")
    if (
        not dataset
        or not dataset.payload["rows"]
        or any(r["data_origin"] != "real_research" for r in dataset.payload["rows"])
        or m.get("synthetic_smoke") is not False
        or m.get("candidate_status") != "AWAITING_EXPERT_MODEL_ACCEPTANCE"
    ):
        reasons.append("REAL_GROUND_TRUTH_REQUIRED")
    if (
        e.get("status") != "INDEPENDENT_EVALUATION_COMPLETED"
        or e.get("scientific_metrics") is not True
    ):
        reasons.append("INDEPENDENT_TEST_REQUIRED")
    if (
        not e.get("same_inputs_and_labels")
        or e.get("baseline_model_sha256") != BASELINE_SHA
    ):
        reasons.append("COMPARABLE_BASELINE_REQUIRED")
    if dataset:
        rows = [r for r in dataset.payload["rows"] if r["split"] == "test"]
        expected = digest(
            [(r["sample_id"], r["class_label"], r["crop_hash"]) for r in rows]
        )
        if e.get("test_sample_hash") != expected:
            reasons.append("TEST_SAMPLE_REFERENCE")
        for split, minimum in (("train", 10), ("validation", 5), ("test", 5)):
            if any(
                dataset.payload["split_class_counts"].get(split, {}).get(k, 0) < minimum
                for k in ("BPD", "TED", "TSD")
            ):
                reasons.append("INSUFFICIENT_CLASS_SUPPORT")
                break
        for label in ("candidate", "baseline"):
            metrics = e.get(label) or {}
            if (
                metrics.get("class_order") != ["BPD", "TED", "TSD"]
                or metrics.get("samples") != len(rows)
                or any(
                    not isinstance(metrics.get(k), (int, float))
                    or not 0 <= metrics[k] <= 1
                    for k in ("accuracy", "balanced_accuracy", "macro_f1")
                )
                or len(metrics.get("per_class", [])) != 3
                or len(metrics.get("confusion_matrix", [])) != 3
            ):
                reasons.append("CLASS_METRICS_REQUIRED")
                continue
            if not valid_metrics(metrics, rows):
                reasons.append("METRIC_MATRIX_MISMATCH")
            per = metrics["per_class"]
            if any(
                x.get("class") != k
                or x.get("support") != sum(r["class_label"] == k for r in rows)
                or any(
                    not isinstance(x.get(p), (int, float)) or not 0 <= x[p] <= 1
                    for p in ("precision", "recall", "f1")
                )
                for x, k in zip(per, ("BPD", "TED", "TSD"), strict=True)
            ):
                reasons.append("BPD_CLASS_METRICS_REQUIRED")
    # Actual CPU measurements must be registered as a separate reviewed event, not fabricated from export status.
    measured = s.scalar(
        select(ModelEvent)
        .where(
            ModelEvent.subject_id == c.id,
            ModelEvent.payload["action"].astext == "CPU_COMPARISON",
        )
        .order_by(ModelEvent.revision.desc())
        .limit(1)
    )
    if not measured:
        reasons.append("CPU_COMPARISON_REQUIRED")
    else:
        for kind, expected in (
            ("candidate", m["model_sha256"]),
            ("baseline", BASELINE_SHA),
        ):
            value = measured.payload.get(kind, {})
            if (
                value.get("status") != "ARTIFACT_VERIFIED"
                or value.get("model_sha256") != expected
                or [b.get("batch") for b in value.get("batches", [])] != [1, 7]
                or any(
                    not isinstance(b.get("cpu_mean_ms"), (int, float))
                    or not 0 < b["cpu_mean_ms"] < 45000
                    for b in value.get("batches", [])
                )
            ):
                reasons.append("CPU_COMPARISON_REFERENCE")
    return {
        "eligible": not reasons,
        "reasons": sorted(set(reasons)),
        "scientific": True,
    }


def approve_model(s, user, c, cfg, asset_root, channel, reason, previous):
    require_admin(user)
    lock(s)
    if not previous:
        raise ValueError("EXPECTED_EVENT_REQUIRED")
    check_files(c, cfg)
    gate = scientific_gate(s, c, asset_root, channel)
    if not gate["eligible"]:
        raise HTTPException(409, {"code": "SCIENTIFIC_MODEL_NOT_READY", **gate})
    if not isinstance(reason, str) or not 10 <= len(reason) <= 4000:
        raise ValueError("APPROVAL_REASON")
    if head(s, c.id).payload["action"] in ("REVOKED", "REJECTED"):
        raise HTTPException(409, "MODEL_REVOKED")
    return event(
        s,
        user,
        c.id,
        "APPROVED",
        {"channel": channel, "reason": reason, "gate": gate},
        previous,
    )


def trusted_keys(s, cfg):
    keys = {}
    for row in s.scalars(
        select(ModelEvent)
        .where(ModelEvent.subject_id.like("key.%"))
        .order_by(ModelEvent.created_at, ModelEvent.revision)
    ):
        keys[row.subject_id[4:]] = row.payload
    return {
        "schema": "xrt_release_trust/v1",
        "origins": {"local": {"registry_id": cfg["registry_id"], "keys": keys}},
    }


def prepare_release(s, user, c, cfg, asset_root, channel, key_id, reason):
    require_admin(user)
    lock(s)
    check_files(c, cfg)
    gate = scientific_gate(s, c, asset_root, channel)
    approval = head(s, c.id)
    if (
        not gate["eligible"]
        or not approval
        or approval.payload["action"] != "APPROVED"
        or approval.payload["channel"] != channel
    ):
        raise HTTPException(409, "RELEASE_APPROVAL_REQUIRED")
    if not reason or len(reason) > 4000:
        raise ValueError("CHANGE_NOTES")
    root = check_files(c, cfg)
    now = datetime.now(UTC)
    sequence = (s.scalar(select(func.max(ModelRelease.sequence))) or 0) + 1
    return {
        "schema": "xrt_signed_model_release/v1",
        "release_id": str(uuid4()),
        "release_sequence": sequence,
        "registry_id": cfg["registry_id"],
        "model_id": c.model_id,
        "model_version": c.version,
        "candidate_id": c.id,
        "model_sha256": c.payload["manifest"]["model_sha256"],
        "manifest_sha256": c.payload["manifest_sha256"],
        "model_bytes": (root / "model.onnx").stat().st_size,
        "manifest_bytes": (root / "manifest.json").stat().st_size,
        "channel": channel,
        "artifact_identity": c.payload["manifest"]["model_sha256"]
        + ":"
        + c.payload["manifest_sha256"],
        "minimum_app_version": "0.1.0",
        "maximum_app_version": "0.1.0",
        "release_status": "RELEASED",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=14)).isoformat(),
        "signing_key_id": safe_name(key_id),
        "change_notes": reason,
    }


def publish(s, user, envelope, cfg, asset_root):
    require_admin(user)
    lock(s)
    m = verify_release(
        envelope, trusted_keys(s, cfg), "local", channel=envelope["metadata"]["channel"]
    )
    c = lookup(s, m["candidate_id"], cfg)
    root = check_files(c, cfg)
    approval = head(s, c.id)
    gate = scientific_gate(s, c, asset_root, m["channel"])
    if (
        not gate["eligible"]
        or not approval
        or approval.payload["action"] != "APPROVED"
        or approval.payload["channel"] != m["channel"]
    ):
        raise HTTPException(409, "RELEASE_APPROVAL_REQUIRED")
    if (
        m["model_bytes"] != (root / "model.onnx").stat().st_size
        or m["manifest_bytes"] != (root / "manifest.json").stat().st_size
        or m["model_id"] != c.model_id
        or m["model_version"] != c.version
        or m["model_sha256"] != c.payload["manifest"]["model_sha256"]
        or m["manifest_sha256"] != c.payload["manifest_sha256"]
    ):
        raise ValueError("RELEASE_CANDIDATE_MISMATCH")
    existing = s.get(ModelRelease, m["release_id"])
    if existing:
        if existing.payload == envelope:
            return existing
        raise HTTPException(409, "IMMUTABLE_RELEASE")
    if (
        m["release_sequence"]
        != (s.scalar(select(func.max(ModelRelease.sequence))) or 0) + 1
    ):
        raise HTTPException(409, "RELEASE_SEQUENCE_CONFLICT")
    if s.scalar(
        select(ModelRelease).where(
            ModelRelease.candidate_id == c.id, ModelRelease.channel == m["channel"]
        )
    ):
        raise HTTPException(409, "DUPLICATE_RELEASE")
    r = ModelRelease(
        id=m["release_id"],
        sequence=m["release_sequence"],
        candidate_id=c.id,
        channel=m["channel"],
        payload=envelope,
        actor_id=user.id,
    )
    s.add(r)
    s.flush()
    event(
        s,
        user,
        "release." + r.id,
        "RELEASED",
        {"candidate_id": c.id, "channel": m["channel"]},
    )
    return r


def release_status(s, r, cfg, asset_root):
    current = head(s, "release." + r.id)
    c = lookup(s, r.candidate_id, cfg)
    if (current and current.payload["action"] in ("REVOKED", "DEPRECATED")) or head(
        s, c.id
    ).payload["action"] in ("REVOKED", "REJECTED"):
        return "REVOKED"
    keys = trusted_keys(s, cfg)
    try:
        verify_release(r.payload, keys, "local", channel=r.channel)
    except ValueError:
        return "KEY_OR_RELEASE_UNAVAILABLE"
    d = s.get(DatasetVersion, c.dataset_id)
    if version_status(s, d, asset_root)["usage_status"] != "AVAILABLE":
        return "DATASET_REVIEW_REQUIRED"
    return "AVAILABLE"


def channel_allowed(s, user, channel, cfg):
    if channel == "INTERNAL_TEST":
        return user.role == "ADMIN" and cfg["realm"] == "INTERNAL_TEST"
    if cfg["realm"] != "PRODUCTION":
        return False
    if channel == "STABLE":
        return True
    grant = head(s, "beta." + user.id)
    return (
        channel == "BETA"
        and grant is not None
        and grant.payload["action"] == "BETA_GRANTED"
    )


def register_key(s, user, key_id, public_key):
    safe_name(key_id)
    if len(base64.b64decode(public_key, validate=True)) != 32:
        raise ValueError("ED25519_PUBLIC_KEY")
    old = head(s, "key." + key_id)
    if old:
        raise HTTPException(409, "KEY_ID_IMMUTABLE")
    return event(
        s,
        user,
        "key." + key_id,
        "KEY_REGISTERED",
        {"public_key": public_key, "status": "TRUSTED"},
    )
