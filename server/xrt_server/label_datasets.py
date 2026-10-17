"""Consensus training datasets from review labels (verified_xrt_dataset/v2).

Per reviewer, the effective decision comes from the shared ``resolve()``; per candidate a
weighted majority over BPD/TED/TSD/NOT_DEFECT decides the label. UNSURE never votes.
Ties and disagreements are excluded and listed. Splits are by source (never shared).
"""

import base64
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageStat
from sqlalchemy import select

from sic_xrt_analyzer.sync.labels import CLASSES, resolve
from sic_xrt_analyzer.sync.labels import SCHEMA as LABEL_SCHEMA
from sic_xrt_analyzer.sync.protocol import digest

from .auth import audit
from .datasets import require_admin
from .models import DatasetEvent, LabelDatasetVersion, ReviewLabel, now
from .service import lock

SCHEMA = "verified_xrt_dataset"
SCHEMA_VERSION = 2
BACKGROUND = "NOT_DEFECT"
LABELS = (*CLASSES, BACKGROUND)
# v1 indices stay put (model score order); background is appended.
CLASS_MAPPING = {name: index for index, name in enumerate(LABELS)}
CROP_CONTRACT = {
    "format": "png",
    "dtype": "uint8",
    "modes": ["L", "RGB"],
    "max_edge": 128,
    "geometry": "original_pixels_centered_shifted_inside_source",
    "resize": "none",
}
SPLIT_POLICY = {
    "unit": "source_sha256_component",
    "validation": 0.15,
    "test": 0.15,
    "hash": "sha256(canonical({seed, source}))",
    "dhash_max_hamming": 4,
    "dhash_min_gray_std": 2.0,
}
MIN_PER_SPLIT = {"train": 10, "validation": 5, "test": 5}
SAMPLE_LIMIT = 20000
SETTLE = timedelta(seconds=60)
CONSENSUS = ("majority", "unanimous")
PARAMS = {"seed", "min_reviewers", "consensus", "implicit_weight", "received_before"}
GROUP_KEYS = ("group_id", "wafer_id", "provider_group", "before_after_group", "duplicate_group")


def parameters(body):
    """Validated build parameters with defaults; ``received_before`` may stay None."""
    if not isinstance(body, dict) or not set(body) <= PARAMS:
        raise ValueError("LABEL_DATASET_FIELDS")
    p = {
        "seed": body.get("seed", 0),
        "min_reviewers": body.get("min_reviewers", 1),
        "consensus": body.get("consensus", "majority"),
        "implicit_weight": body.get("implicit_weight", 1.0),
        "received_before": body.get("received_before"),
    }
    if type(p["seed"]) is not int or not 0 <= p["seed"] < 2**32:
        raise ValueError("SPLIT_SEED")
    if type(p["min_reviewers"]) is not int or not 1 <= p["min_reviewers"] <= 20:
        raise ValueError("MIN_REVIEWERS")
    if p["consensus"] not in CONSENSUS:
        raise ValueError("CONSENSUS_RULE")
    w = p["implicit_weight"]
    if isinstance(w, bool) or not isinstance(w, (int, float)) or not 0 <= w <= 1:
        raise ValueError("IMPLICIT_WEIGHT")
    p["implicit_weight"] = float(w)
    if p["received_before"] is not None:
        p["received_before"] = cutoff_text(p["received_before"])
    return p


def cutoff_text(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("RECEIVED_BEFORE")
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError("RECEIVED_BEFORE_TIMEZONE")
    moment = moment.astimezone(UTC)
    # Labels committing late could still land before a too-recent cutoff.
    if moment > now() - SETTLE:
        raise ValueError("RECEIVED_BEFORE_TOO_RECENT")
    return moment.isoformat()


def load_events(session, received_before=None):
    """Label events in resolve order, without crop pixels."""
    p = ReviewLabel.payload
    statement = select(
        ReviewLabel.event_id, ReviewLabel.digest, ReviewLabel.actor_id,
        ReviewLabel.source_sha256, ReviewLabel.candidate_id, ReviewLabel.decision,
        ReviewLabel.parent_event_id, ReviewLabel.created_at, p["source"], p["candidate"],
        p["model"], p["queue"], p["mode"], p["crop"]["sha256"].astext, p["crop"]["rect"],
    ).order_by(ReviewLabel.created_at, ReviewLabel.received_at, ReviewLabel.event_id)
    if received_before is not None:
        statement = statement.where(
            ReviewLabel.received_at < datetime.fromisoformat(received_before)
        )
    events = []
    for r in session.execute(statement):
        source, cand, model, queue = r[8], r[9], r[10], r[11]
        events.append({
            "event_id": r.event_id, "digest": r.digest, "actor": r.actor_id,
            "source": r.source_sha256, "page": source["page"],
            "width": source["width"], "height": source["height"],
            "candidate": r.candidate_id, "decision": r.decision, "parent": r.parent_event_id,
            "created_at": r.created_at.isoformat(), "x": cand["x"], "y": cand["y"],
            "predicted": cand["predicted"], "scores": cand["scores"],
            "model_version": model["version"], "model_sha256": model["sha256"],
            "queue_kind": queue["kind"], "queue_seed": queue["seed"], "mode": r[12],
            "crop_sha256": r[13], "crop_rect": r[14],
        })
    return events


def event_set_hash(events):
    return digest(sorted([e["event_id"], e["digest"]] for e in events))


def target_key(e):
    return (e["source"], e["page"], e["candidate"])


def consensus(events, params):
    """Return (samples, conflicts, excluded) from ordered label events."""
    by_id = {e["event_id"]: e for e in events}
    effective = resolve(
        (e["event_id"], (e["actor"], *target_key(e)), e["decision"], e["parent"])
        for e in events
    )
    history = defaultdict(list)
    for e in events:
        history[target_key(e)].append(e)
    votes = defaultdict(dict)
    for (actor, *key), (ident, _decision) in effective.items():
        votes[tuple(key)][actor] = by_id[ident]
    samples, conflicts, excluded = [], [], []
    for key in sorted(votes):
        chosen = sorted(votes[key].values(), key=lambda e: (e["created_at"], e["event_id"]))
        base = {"source_sha256": key[0], "page": key[1], "candidate_id": key[2]}
        unsure = [e for e in chosen if e["decision"] == "UNSURE"]
        voting = []
        for e in chosen:
            if e["decision"] == "UNSURE":
                continue
            weight = params["implicit_weight"] if e["mode"] == "batch_implicit" else 1.0
            if weight > 0:
                voting.append((e, weight))
        if not voting:
            reason = "IMPLICIT_EXCLUDED" if len(unsure) < len(chosen) else "UNSURE_ONLY"
            excluded.append({**base, "reason": reason})
            continue
        if len(voting) < params["min_reviewers"]:
            excluded.append({**base, "reason": "BELOW_MIN_REVIEWERS"})
            continue
        counts = Counter(e["decision"] for e, _w in voting)
        weights = Counter()
        for e, w in voting:
            weights[e["decision"]] += w
        total = sum(weights.values())
        best = max(weights.values())
        winners = sorted(d for d, w in weights.items() if round(w - best, 9) == 0)
        reason = None
        if len(winners) > 1:
            reason = "TIE"
        elif params["consensus"] == "unanimous" and len(weights) > 1:
            reason = "DISAGREEMENT"
        elif round(best * 2 - total, 9) <= 0:
            reason = "NO_MAJORITY"
        if reason:
            conflict = {
                **base, "reason": reason, "votes": dict(sorted(counts.items())),
                "weighted_votes": {k: round(v, 6) for k, v in sorted(weights.items())},
                "unsure": len(unsure),
                "event_ids": sorted(e["event_id"] for e in chosen),
            }
            conflicts.append(conflict)
            excluded.append({**base, "reason": "CONFLICT_" + reason})
            continue
        label = winners[0]
        agree = [(e, w) for e, w in voting if e["decision"] == label]
        rep = agree[0][0]
        crop = pick_crop(history[key])
        samples.append({
            "sample_id": digest(list(key)),
            **base,
            "x": rep["x"], "y": rep["y"],
            "source_width": rep["width"], "source_height": rep["height"],
            "label": label,
            "class_index": CLASS_MAPPING[label],
            "is_background": label == BACKGROUND,
            "weight": round(max(w for _e, w in agree), 6),
            "n_reviewers": len(voting),
            "n_unsure": len(unsure),
            "agreement": round(len(agree) / len(voting), 4),
            "votes": dict(sorted(counts.items())),
            "modes": sorted({e["mode"] for e in chosen}),
            "batch_implicit_only": all(e["mode"] == "batch_implicit" for e, _w in agree),
            "queue_kinds": sorted({e["queue_kind"] for e in chosen}),
            "random_sample": any(e["queue_kind"] == "random" for e in chosen),
            "random_seeds": sorted({e["queue_seed"] for e in chosen
                                    if e["queue_kind"] == "random" and e["queue_seed"] is not None}),
            "predicted": rep["predicted"],
            "scores": rep["scores"],
            "model_version": rep["model_version"],
            "model_sha256": rep["model_sha256"],
            "model_agrees": rep["predicted"] == label,
            "model_predictions": sorted(
                {json.dumps([e["model_version"], e["model_sha256"], e["predicted"], e["scores"]])
                 for e in chosen}
            ),
            "reviewer_ids": sorted(votes[key]),
            "effective_event_ids": sorted(e["event_id"] for e in chosen),
            "history_event_ids": sorted(e["event_id"] for e in history[key]),
            "crop": crop,
        })
    for s in samples:
        s["model_predictions"] = [
            dict(zip(("model_version", "model_sha256", "predicted", "scores"), json.loads(m),
                     strict=True))
            for m in s["model_predictions"]
        ]
    return samples, conflicts, excluded


def pick_crop(events):
    """Most frequent crop of any non-retraction event for the candidate (pixels, not votes)."""
    found = Counter()
    first = {}
    for e in events:
        if e["decision"] != "RETRACTED" and e["crop_sha256"]:
            found[e["crop_sha256"]] += 1
            first.setdefault(e["crop_sha256"], e)
    if not found:
        return None
    sha = min(found, key=lambda k: (-found[k], k))
    e = first[sha]
    return {"sha256": sha, "rect": e["crop_rect"], "event_id": e["event_id"],
            "image_path": "images/" + sha + ".png"}


def group_mappings(session):
    """Latest administrator GROUP mapping per (project, source), keyed by source hash."""
    heads = {}
    for e in session.scalars(
        select(DatasetEvent).where(DatasetEvent.kind == "GROUP")
        .order_by(DatasetEvent.revision)
    ):
        heads[(e.project_id, e.subject_id)] = e
    by_hash = defaultdict(list)
    for e in sorted(heads.values(), key=lambda e: e.id):
        by_hash[e.payload["source_hash"]].append(e)
    return by_hash


def crop_png(session, event_id, sha):
    raw = session.scalar(
        select(ReviewLabel.payload["crop"]["png"].astext).where(ReviewLabel.event_id == event_id)
    )
    data = base64.b64decode(raw or "", validate=True)
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("CROP_HASH_MISMATCH")
    return data


def fingerprint(raw):
    """(pixel_hash, dhash or None for near-flat crops)."""
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.mode not in ("L", "RGB"):
            raise ValueError("CROP_FORMAT")
        pixels = image.tobytes()
        pixel = hashlib.sha256(f"{image.mode}:{image.width}x{image.height}:".encode()
                               + pixels).hexdigest()
        grey = image.convert("L")
        if ImageStat.Stat(grey).stddev[0] < SPLIT_POLICY["dhash_min_gray_std"]:
            return pixel, None
        a = list(grey.resize((9, 8)).tobytes())
    value = sum((a[y * 9 + x] > a[y * 9 + x + 1]) << (y * 8 + x)
                for y in range(8) for x in range(8))
    return pixel, value


def assign_splits(samples, mappings, seed):
    """Union sources sharing mapping groups, identical crop pixels or near-duplicate dHash."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    tokens = {}
    pinned = set()
    for s in samples:
        find(s["source_sha256"])
    for sha in sorted({s["source_sha256"] for s in samples}):
        for e in mappings.get(sha, []):
            if e.payload["evaluation_only"]:
                pinned.add(sha)
            for k in GROUP_KEYS:
                if e.payload.get(k) is not None:
                    union(sha, tokens.setdefault((k, e.payload[k]), sha))
    bands = defaultdict(list)
    for s in samples:
        if s["crop"] is None:
            continue
        union(s["source_sha256"],
              tokens.setdefault(("pixel", s["crop"]["pixel_hash"]), s["source_sha256"]))
        value = s["crop"]["dhash"]
        if value is None:
            continue
        # Hamming <= 4 over 64 bits leaves at least one of five bands identical.
        for band in range(5):
            bucket = bands[(band, (value >> (band * 13)) & 0x1FFF)]
            for other, sha in bucket:
                if (value ^ other).bit_count() <= SPLIT_POLICY["dhash_max_hamming"]:
                    union(s["source_sha256"], sha)
            bucket.append((value, s["source_sha256"]))
    components = defaultdict(set)
    for sha in list(parent):
        components[find(sha)].add(sha)
    assignment = {}
    for root, members in components.items():
        if members & pinned:
            name = "test"
        else:
            h = int(digest({"seed": seed, "source": root})[:12], 16) / 16**12
            v, t = SPLIT_POLICY["validation"], SPLIT_POLICY["test"]
            name = "validation" if h < v else "test" if h < v + t else "train"
        gid = digest(sorted(members))
        for sha in members:
            assignment[sha] = (name, gid, bool(members & pinned))
    for s in samples:
        s["split"], s["split_group_id"], s["evaluation_only"] = assignment[s["source_sha256"]]
    return samples


def apply_rights(samples, excluded, mappings):
    kept = []
    for s in samples:
        rows = mappings.get(s["source_sha256"], [])
        if any(not e.payload["training_use_authorized"] for e in rows):
            excluded.append({k: s[k] for k in ("source_sha256", "page", "candidate_id")}
                            | {"reason": "USE_RIGHTS_MISSING"})
            continue
        s["group_mapping_ids"] = [e.id for e in rows]
        s["data_origin"] = sorted({e.payload["data_origin"] for e in rows}) or None
        s["wafer_id"] = sorted({e.payload["wafer_id"] for e in rows
                                if e.payload["wafer_id"] is not None}) or None
        kept.append(s)
    return kept


def build(session, params):
    """Deterministic dataset content for ``params`` (``received_before`` must be set)."""
    events = load_events(session, params["received_before"])
    samples, conflicts, excluded = consensus(events, params)
    mappings = group_mappings(session)
    samples = apply_rights(samples, excluded, mappings)
    if len(samples) > SAMPLE_LIMIT:
        raise ValueError("DATASET_SAMPLE_LIMIT")
    for s in samples:
        if s["crop"] is not None:
            raw = crop_png(session, s["crop"]["event_id"], s["crop"]["sha256"])
            s["crop"]["pixel_hash"], s["crop"]["dhash"] = fingerprint(raw)
    # Identical pixels with different labels are unusable; identical twins keep one.
    labels = defaultdict(set)
    for s in samples:
        if s["crop"]:
            labels[s["crop"]["pixel_hash"]].add(s["label"])
    samples = assign_splits(samples, mappings, params["seed"])
    seen, rows = set(), []
    for s in sorted(samples, key=lambda s: s["sample_id"]):
        pixel = s["crop"]["pixel_hash"] if s["crop"] else None
        reason = ("DUPLICATE_LABEL_CONFLICT" if pixel and len(labels[pixel]) > 1
                  else "DUPLICATE_PIXELS" if pixel in seen else None)
        if reason:
            excluded.append({k: s[k] for k in ("source_sha256", "page", "candidate_id")}
                            | {"reason": reason})
            continue
        if pixel:
            seen.add(pixel)
            s["crop"]["dhash"] = (None if s["crop"]["dhash"] is None
                                  else f"{s['crop']['dhash']:016x}")
        rows.append(s)
    excluded.sort(key=lambda r: (r["source_sha256"], r["page"], r["candidate_id"], r["reason"]))
    files = {s["crop"]["image_path"]: s["crop"]["sha256"] for s in rows if s["crop"]}
    split_counts = {
        name: {c: sum(r["label"] == c for r in rows if r["split"] == name) for c in LABELS}
        for name in ("train", "validation", "test")
    }
    ready = all(split_counts[n][c] >= MIN_PER_SPLIT[n] for n in split_counts for c in LABELS)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "label_schema": LABEL_SCHEMA,
        "parameters": params,
        "label_events": len(events),
        "label_event_set_hash": event_set_hash(events),
        "class_mapping": CLASS_MAPPING,
        "background_class": BACKGROUND,
        "crop_contract": CROP_CONTRACT,
        "split_policy": SPLIT_POLICY,
        "included_source_sha256": sorted({r["source_sha256"] for r in rows}),
        "split_group_ids": sorted({r["split_group_id"] for r in rows}),
        "rows": rows,
        "files": files,
        "file_manifest_hash": digest(files),
        "split_class_counts": split_counts,
        "conflicts": conflicts,
        "conflict_counts": dict(sorted(Counter(c["reason"] for c in conflicts).items())),
        "excluded": excluded,
        "exclusion_counts": dict(sorted(Counter(r["reason"] for r in excluded).items())),
        "crop_coverage": round(len(files) / len(rows), 4) if rows else 0.0,
        "readiness": "READY" if ready else "DATA_NOT_READY",
    }


def content_hash(manifest):
    skip = {"dataset_id", "dataset_version", "created_at", "created_by", "dataset_hash",
            "content_hash"}
    return digest({k: v for k, v in manifest.items() if k not in skip})


def summary(manifest, created):
    return {
        "created": created,
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "dataset_hash": manifest["dataset_hash"],
        "content_hash": manifest["content_hash"],
        "samples": len(manifest["rows"]),
        "split_class_counts": manifest["split_class_counts"],
        "conflict_counts": manifest["conflict_counts"],
        "exclusion_counts": manifest["exclusion_counts"],
        "readiness": manifest["readiness"],
    }


def preview(session, user, body):
    require_admin(user)
    params = parameters(body)
    if params["received_before"] is None:
        params["received_before"] = (now() - SETTLE).isoformat()
    m = build(session, params)
    return {k: v for k, v in m.items() if k not in {"rows", "files", "excluded"}} | {
        "samples": len(m["rows"])
    }


def create_version(session, user, body):
    """Create an immutable version; an identical retry returns the stored one."""
    require_admin(user)
    if not isinstance(body, dict) or not isinstance(body.get("version"), str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", body["version"]
    ):
        raise ValueError("DATASET_FIELDS")
    params = parameters({k: v for k, v in body.items() if k != "version"})
    lock(session, "label-dataset-version:" + body["version"])
    old = session.scalar(
        select(LabelDatasetVersion).where(LabelDatasetVersion.version == body["version"])
    )
    if old is not None:
        verify(old)
        stored = old.payload["parameters"]
        asked = {k: v for k, v in params.items() if k != "received_before"}
        if asked != {k: v for k, v in stored.items() if k != "received_before"} or (
            params["received_before"] not in (None, stored["received_before"])
        ):
            raise HTTPException(409, "DATASET_VERSION_EXISTS")
        if content_hash(build(session, stored)) != old.content_digest:
            raise HTTPException(409, "DATASET_VERSION_EXISTS")
        return summary(old.payload, False)
    if params["received_before"] is None:
        params["received_before"] = (now() - SETTLE).isoformat()
    built = build(session, params)
    if not built["rows"]:
        raise HTTPException(409, "DATA_NOT_READY")
    manifest = {
        **built,
        "dataset_id": str(uuid4()),
        "dataset_version": body["version"],
        "created_at": now().isoformat(),
        "created_by": user.id,
    }
    manifest["content_hash"] = content_hash(manifest)
    manifest["dataset_hash"] = digest(manifest)
    session.add(LabelDatasetVersion(
        id=manifest["dataset_id"], version=body["version"], digest=manifest["dataset_hash"],
        content_digest=manifest["content_hash"], payload=manifest, actor_id=user.id,
    ))
    audit(session, "LABEL_DATASET_VERSION_CREATED", user.id, dataset_id=manifest["dataset_id"],
          dataset_hash=manifest["dataset_hash"])
    return summary(manifest, True)


def verify(record):
    m = record.payload
    if (digest({k: v for k, v in m.items() if k != "dataset_hash"}) != record.digest
            or content_hash(m) != record.content_digest):
        raise ValueError("DATASET_HASH_MISMATCH")


def usage(session, records):
    """AVAILABLE unless labels before the cutoff changed or a sample's label changed since."""
    current = {}
    mappings = group_mappings(session)
    everything = load_events(session)
    result = {}
    for record in records:
        verify(record)
        m = record.payload
        params = m["parameters"]
        reasons = []
        cutoff = datetime.fromisoformat(params["received_before"])
        if event_set_hash(load_events(session, params["received_before"])) != m[
            "label_event_set_hash"
        ]:
            reasons.append("LABEL_SET_CHANGED")
        key = digest({k: v for k, v in params.items() if k != "received_before"})
        if key not in current:
            samples, _c, _e = consensus(everything, params)
            samples = apply_rights(samples, [], mappings)
            current[key] = {s["sample_id"]: s["label"] for s in samples}
        labels = current[key]
        restricted = [r["sample_id"] for r in m["rows"] if labels.get(r["sample_id"]) != r["label"]]
        result[record.id] = {
            "usage_status": "RESTRICTED" if restricted or reasons else "AVAILABLE",
            "restricted_samples": restricted,
            "restriction_reasons": reasons + (["LABEL_CHANGED"] if restricted else []),
            "new_samples_available": len(set(labels) - {r["sample_id"] for r in m["rows"]}),
            "labels_since_cutoff": max(0, len(everything) - m["label_events"]),
            "cutoff": cutoff.isoformat(),
        }
    return result


def export_version(session, user, record, destination):
    """Write manifest, splits and content-addressed crops to a new private folder."""
    require_admin(user)
    if usage(session, [record])[record.id]["usage_status"] != "AVAILABLE":
        raise HTTPException(409, "DATASET_RESTRICTED")
    out = Path(destination).absolute()
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
           for p in (out, *out.parents)) or out.exists():
        raise ValueError("NEW_SAFE_EXPORT_DIRECTORY_REQUIRED")
    out.mkdir(parents=True, mode=0o700)
    (out / "images").mkdir(mode=0o700)
    (out / "splits").mkdir(mode=0o700)
    m = record.payload

    def write(name, value):
        (out / name).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    for row in m["rows"]:
        if row["crop"]:
            (out / row["crop"]["image_path"]).write_bytes(
                crop_png(session, row["crop"]["event_id"], row["crop"]["sha256"])
            )
    for split in ("train", "validation", "test"):
        (out / "splits" / (split + ".jsonl")).write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                    for r in m["rows"] if r["split"] == split),
            encoding="utf-8",
        )
    write("consensus-report.json", {k: m[k] for k in (
        "conflicts", "conflict_counts", "excluded", "exclusion_counts", "parameters")})
    # Manifest last: an interrupted export has no loadable manifest.
    write("manifest.json", m)
    audit(session, "LABEL_DATASET_EXPORTED", user.id, dataset_id=record.id,
          dataset_hash=record.digest)
    return {"dataset_id": record.id, "dataset_hash": record.digest, "images": len(m["files"])}
