"""Versioned, path-free projection, canonical hashes and strict domain validation."""

import hashlib
import json
import re
from collections import deque
from copy import deepcopy
from dataclasses import fields

from sic_xrt_analyzer.results.contracts import AnalysisProject
from sic_xrt_analyzer.results.serialization import _decode, _pairs, plain

PROTOCOL = 1
MAX_BYTES = 32 * 1024**2
SPECS = {
    "image_sources": "source_id",
    "analysis_runs": "run_id",
    "observations": "observation_id",
    "predictions": "prediction_id",
    "defect_instances": "instance_id",
    "geometries": "geometry_id",
    "review_events": "review_id",
    "image_relationships": "relationship_id",
    "model_provenance": "provenance_id",
}
ROOT = {
    "project_id",
    "project_name",
    "schema_version",
    "created_at",
    "updated_at",
    "revision",
}
SOURCE_KEYS = {
    "source_id",
    "display_name",
    "file_size",
    "mtime_ns",
    "width",
    "height",
    "dtype",
    "bit_depth",
    "channels",
    "page_count",
    "role",
    "content_hash",
    "calibration",
}
# Acquisition/wafer metadata is deliberately absent. Structural science fields are explicit.
SAFE_MAPPING_KEYS = {
    "point_mode",
    "proposal_threshold",
    "max_candidates",
    "coordinates",
    "no_subtype_or_conversion_claim",
    "patch_size",
    "candidate_limit_reached",
    "classified_count",
    "counts_are",
    "excluded",
    "human_verified",
    "low_score_count",
    "model_sha256",
    "research_only",
    "schema",
    "created_at",
    "bundle_id",
    "classes",
    "source_pointer_sha256",
    "training_manifest_sha256",
    "code_revision",
    "recipe",
    "mode",
    "independent_test_passed",
    "background_class",
    "localizes_defects",
    "parity",
    "status",
    "limitations",
    "kind",
    "bundle_sha256",
    "mapping",
    "original_project_id",
    "experiment_id",
    "source_id",
    "validation_status",
    "file_size",
    "mtime_ns",
    "conversion",
    "local_contrast_inside_model",
    "meaning",
    "width",
    "height",
    "dtype",
    "bit_depth",
    "channels",
    "page_count",
    "page_index",
    "model_id",
    "model_version",
    "model_hash",
    "schema_version",
    "contract_version",
    "input",
    "output",
    "input_contract",
    "output_contract",
    "class_names",
    "labels",
    "name",
    "shape",
    "layout",
    "color_order",
    "normalization",
    "scale",
    "mean",
    "std",
    "tensor_name",
    "candidate_method",
    "tile_size",
    "tile_overlap",
    "batch_size",
    "score_threshold",
    "threshold",
    "method",
    "roi",
    "scope",
    "device",
    "duration",
    "count",
    "total",
    "counts",
    "BPD",
    "TED",
    "TSD",
    "UNKNOWN",
    "proposal_count",
    "geometry_count",
    "algorithm",
    "sigma",
    "sigmas",
    "polarity",
    "min_length",
    "version",
    "class_order",
    "channel_order",
    "input_size",
    "preprocessing",
    "score_meaning",
    "candidate_count",
    "source_class_id",
    "format",
    "resize",
}


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def read_json(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE")
    return json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")),
    )


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value
    ):
        raise ValueError("INVALID_ID")
    return value


def safe_mapping(value):
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k not in SAFE_MAPPING_KEYS:
                continue
            if k == "mapping" and isinstance(v, dict):
                result[k] = {safe_id(old): safe_id(new) for old, new in v.items()}
            else:
                result[k] = safe_mapping(v)
        return result
    if isinstance(value, list):
        return [safe_mapping(v) for v in value]
    if isinstance(value, str) and (
        re.search(r"[A-Za-z]:[\\/]", value)
        or value.startswith(("/", "\\"))
        or "://" in value
    ):
        return None
    return value


def project_projection(project):
    p = plain(project)
    root = {k: p[k] for k in ROOT}
    entities = {}
    for kind, key in SPECS.items():
        entities[kind] = {}
        for original in p[kind]:
            row = deepcopy(original)
            if kind == "image_sources":
                row["file_size"] = original["file_identity"]["file_size"]
                row["mtime_ns"] = original["file_identity"]["mtime_ns"]
                row = {k: row[k] for k in SOURCE_KEYS}
                row["display_name"] = (
                    row["display_name"].replace("\\", "/").split("/")[-1]
                )
                h = row["content_hash"]
                row["content_hash"] = (
                    {k: h[k] for k in ("value", "verified_at", "algorithm")}
                    if h
                    else None
                )
                row["calibration"] = {**row["calibration"], "calibration_source": None}
                if row["calibration"]["calibration_status"] == "VERIFIED":
                    row["calibration"]["calibration_source"] = (
                        "explicit source calibration (local reference withheld)"
                    )
            elif kind == "model_provenance":
                for k in ("input_contract", "output_contract", "manifest_snapshot"):
                    row[k] = safe_mapping(row[k])
            elif kind == "analysis_runs":
                for k in (
                    "candidate_parameters",
                    "classification_parameters",
                    "source_identity",
                    "parameters",
                    "summary",
                    "preprocessing",
                ):
                    row[k] = safe_mapping(row[k])
                row["error"] = (
                    {"code": "REDACTED_LOCAL_ERROR"} if row["error"] else None
                )
            elif kind == "observations":
                row["metadata"] = safe_mapping(row["metadata"])
            elif kind == "image_relationships":
                row["transform_reference"] = None
                row["registration_id"] = None
                row["verification_status"] = "UNVERIFIED"
            # Reviewer IDs/notes are intentional research data, not path metadata.
            ident = safe_id(row[key])
            entities[kind][ident] = row
    validate_projection(root, entities)
    return root, entities


def validate_projection(root, entities):
    if set(root) != ROOT or set(entities) != set(SPECS):
        raise ValueError("UNKNOWN_PROJECTION_FIELDS")
    safe_id(root["project_id"])
    if root["schema_version"] not in ("1.0.0", "1.1.0"):
        raise ValueError("UNSUPPORTED_PROJECT_SCHEMA")
    p = dict(root)
    for kind, key in SPECS.items():
        p[kind] = []
        for ident, original in entities[kind].items():
            safe_id(ident)
            row = deepcopy(original)
            if row.get(key) != ident:
                raise ValueError("ENTITY_ID_MISMATCH")
            if kind == "image_sources":
                if set(row) != SOURCE_KEYS:
                    raise ValueError("SOURCE_FIELD_ALLOWLIST")
                if "/" in row["display_name"] or "\\" in row["display_name"]:
                    raise ValueError("LOCAL_PATH_NOT_ALLOWED")
                row.update(
                    source_reference="sync:" + ident,
                    file_identity={
                        "canonical_path": "sync:" + ident,
                        "file_size": row.pop("file_size"),
                        "mtime_ns": row.pop("mtime_ns"),
                    },
                    acquisition_metadata={},
                    wafer_placement={
                        "wafer_id": None,
                        "tile_position": None,
                        "alignment_reference": None,
                        "coordinate_system": "UNKNOWN",
                        "calibration_status": "UNKNOWN",
                    },
                )
                if row["content_hash"]:
                    if set(row["content_hash"]) != {
                        "value",
                        "verified_at",
                        "algorithm",
                    }:
                        raise ValueError("HASH_FIELD_ALLOWLIST")
                    row["content_hash"].update(
                        source_reference="sync:" + ident,
                        file_size=row["file_identity"]["file_size"],
                        mtime_ns=row["file_identity"]["mtime_ns"],
                    )
            if kind == "model_provenance":
                for k in ("input_contract", "output_contract", "manifest_snapshot"):
                    if row[k] != safe_mapping(row[k]):
                        raise ValueError("METADATA_FIELD_ALLOWLIST")
            if kind == "analysis_runs":
                for k in (
                    "candidate_parameters",
                    "classification_parameters",
                    "source_identity",
                    "parameters",
                    "summary",
                    "preprocessing",
                ):
                    if row[k] != safe_mapping(row[k]):
                        raise ValueError("METADATA_FIELD_ALLOWLIST")
            if kind == "analysis_runs":
                row["source_identity"]["canonical_path"] = "sync:" + row["source_id"]
            if kind == "observations" and row["metadata"] != safe_mapping(
                row["metadata"]
            ):
                raise ValueError("METADATA_FIELD_ALLOWLIST")
            p[kind].append(row)
    if set(p) != {f.name for f in fields(AnalysisProject)}:
        raise ValueError("PROJECT_FIELDS")
    # JSON object keys and PostgreSQL rows have no append order. Preserve each
    # event verbatim, reconstructing only the domain validation parent order.
    reviews = {r["review_id"]: r for r in p["review_events"]}
    dependents = {ident: [] for ident in reviews}
    degrees = {}
    for ident, row in reviews.items():
        parents = row["parent_review_ids"]
        if len(set(parents)) != len(parents) or any(
            parent not in reviews for parent in parents
        ):
            raise ValueError("REVIEW_PARENT_MISSING_OR_DUPLICATE")
        degrees[ident] = len(parents)
        for parent in parents:
            dependents[parent].append(ident)
    ready = deque(ident for ident in reviews if not degrees[ident])
    ordered = []
    while ready:
        ident = ready.popleft()
        ordered.append(reviews[ident])
        for child in dependents[ident]:
            degrees[child] -= 1
            if not degrees[child]:
                ready.append(child)
    if len(ordered) != len(reviews):
        raise ValueError("REVIEW_PARENT_CYCLE")
    p["review_events"] = ordered
    return _decode(AnalysisProject, p)


def inventory(entities):
    return {
        kind: {ident: digest(row) for ident, row in rows.items()}
        for kind, rows in entities.items()
    }


def make_batch(project, client_id, *, known=None, batch_id=None):
    from uuid import uuid4

    root, entities = project_projection(project)
    inv = inventory(entities)
    known = known or {}
    delta = {
        k: {i: row for i, row in rows.items() if known.get(k, {}).get(i) != inv[k][i]}
        for k, rows in entities.items()
    }
    value = {
        "sync_protocol_version": PROTOCOL,
        "batch_id": batch_id or str(uuid4()),
        "client_id": safe_id(client_id),
        "project_id": root["project_id"],
        "project_revision": root["revision"],
        "project_schema_version": root["schema_version"],
        "project": root,
        "inventory": inv,
        "entities": delta,
        "snapshot_hash": digest({"project": root, "inventory": inv}),
    }
    value["payload_hash"] = digest(value)
    if len(encode(value)) > MAX_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE")
    return value


def validate_batch(value):
    keys = {
        "sync_protocol_version",
        "batch_id",
        "client_id",
        "project_id",
        "project_revision",
        "project_schema_version",
        "project",
        "inventory",
        "entities",
        "snapshot_hash",
        "payload_hash",
    }
    if (
        set(value) != keys
        or type(value["sync_protocol_version"]) is not int
        or value["sync_protocol_version"] != PROTOCOL
    ):
        raise ValueError("UNSUPPORTED_SYNC_PROTOCOL")
    for k in ("batch_id", "client_id", "project_id"):
        safe_id(value[k])
    if (
        digest({k: v for k, v in value.items() if k != "payload_hash"})
        != value["payload_hash"]
    ):
        raise ValueError("PAYLOAD_HASH_MISMATCH")
    root = value["project"]
    if (root["project_id"], root["revision"], root["schema_version"]) != (
        value["project_id"],
        value["project_revision"],
        value["project_schema_version"],
    ):
        raise ValueError("PROJECT_ENVELOPE_MISMATCH")
    if set(value["entities"]) != set(SPECS) or set(value["inventory"]) != set(SPECS):
        raise ValueError("UNKNOWN_ENTITY_KIND")
    total = sum(len(v) for v in value["inventory"].values())
    if total > 100_000:
        raise ValueError("ENTITY_LIMIT")
    for kind, hashes in value["inventory"].items():
        for ident, sha in hashes.items():
            safe_id(ident)
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("INVALID_ENTITY_HASH")
        for ident, row in value["entities"][kind].items():
            if hashes.get(ident) != digest(row):
                raise ValueError("ENTITY_HASH_MISMATCH")
    if value["snapshot_hash"] != digest(
        {"project": root, "inventory": value["inventory"]}
    ):
        raise ValueError("SNAPSHOT_HASH_MISMATCH")
    return value
