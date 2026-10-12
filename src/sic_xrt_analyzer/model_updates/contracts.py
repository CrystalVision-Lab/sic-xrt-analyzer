"""Versioned canonical release contract. Public keys are provisioned out of band."""

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

MAX_MODEL = 64 * 1024**2
MAX_METADATA = 1024**2
MODEL_QUOTA = 1024 * 1024**2
CLASSES = ["BPD", "TED", "TSD"]
INPUT = {
    "name": "images",
    "dtype": "float32",
    "shape": ["N", 3, 128, 128],
    "conversion": "uint8_RGB_to_NCHW_div255",
    "local_contrast_inside_model": True,
}
OUTPUT = {
    "name": "probabilities",
    "shape": ["N", 3],
    "meaning": "uncalibrated_class_scores",
}
FIELDS = {
    "schema",
    "release_id",
    "release_sequence",
    "registry_id",
    "model_id",
    "model_version",
    "model_sha256",
    "manifest_sha256",
    "model_bytes",
    "manifest_bytes",
    "channel",
    "artifact_identity",
    "minimum_app_version",
    "maximum_app_version",
    "release_status",
    "created_at",
    "expires_at",
    "signing_key_id",
    "change_notes",
    "candidate_id",
}


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(raw):
    if len(raw) > MAX_METADATA:
        raise ValueError("METADATA_SIZE")

    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[k] = v
        return result

    def bad(_):
        raise ValueError("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value
    ):
        raise ValueError("INVALID_MODEL_ID")
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("INVALID_SHA")
    return value


def safe_path(path):
    path = Path(path).absolute()
    if any(
        p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
        for p in (path, *path.parents)
    ):
        raise ValueError("LINK_NOT_ALLOWED")
    return path


def file_sha(path, maximum=MAX_MODEL):
    path = safe_path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError("ARTIFACT_SIZE")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def frozen_manifest(value):
    if not isinstance(value, dict):
        raise ValueError("MODEL_CONTRACT")  # noqa: TRY004 -- stable boundary error for untrusted JSON
    if (
        value.get("schema") != "frozen_xrt_patch_classifier"
        or value.get("schema_version") != 1
        or value.get("status") != "validated_export"
        or value.get("classes") != CLASSES
        or value.get("input") != INPUT
        or value.get("output") != OUTPUT
        or value.get("model_file") != "model.onnx"
        or value.get("research_only") is not True
        or value.get("background_class") is not False
        or value.get("localizes_defects") is not False
    ):
        raise ValueError("MODEL_CONTRACT")
    sha(value["model_sha256"])
    return value


def sign_release(metadata, private_key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return {
        "metadata": metadata,
        "signature": base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(private_key).sign(canonical(metadata))
        ).decode(),
    }


def verify_release(
    envelope,
    trust,
    origin,
    app_version="0.1.0",
    channel="STABLE",
    minimum_sequence=0,
    allow_expired=False,
):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from packaging.version import Version

    if (
        not isinstance(envelope, dict)
        or not isinstance(trust, dict)
        or set(envelope) != {"metadata", "signature"}
    ):
        raise ValueError("RELEASE_SCHEMA")
    m = envelope["metadata"]
    if (
        not isinstance(m, dict)
        or set(m) != FIELDS
        or m["schema"] != "xrt_signed_model_release/v1"
    ):
        raise ValueError("RELEASE_SCHEMA")
    safe_name(m["signing_key_id"])
    origins = trust.get("origins", {})
    if not isinstance(origins, dict):
        raise ValueError("UNTRUSTED_SIGNING_KEY")  # noqa: TRY004
    keys = origins.get(origin, {})
    if not isinstance(keys, dict) or not isinstance(keys.get("keys", {}), dict):
        raise ValueError("UNTRUSTED_SIGNING_KEY")  # noqa: TRY004 -- trust protocol boundary
    key = keys.get("keys", {}).get(m["signing_key_id"])
    if (
        not isinstance(key, dict)
        or key.get("status") != "TRUSTED"
        or keys.get("registry_id") != m["registry_id"]
    ):
        raise ValueError("UNTRUSTED_SIGNING_KEY")
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(key["public_key"], validate=True)
        ).verify(base64.b64decode(envelope["signature"], validate=True), canonical(m))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise ValueError("RELEASE_SIGNATURE") from exc
    for field in ("model_sha256", "manifest_sha256"):
        sha(m[field])
    for field in (
        "release_id",
        "model_id",
        "model_version",
        "candidate_id",
        "signing_key_id",
        "registry_id",
    ):
        safe_name(m[field])
    if (
        m["channel"] != channel
        or channel not in ("STABLE", "BETA", "INTERNAL_TEST")
        or m["release_status"] != "RELEASED"
        or type(m["release_sequence"]) is not int
        or m["release_sequence"] < minimum_sequence
        or m["release_sequence"] <= 0
        or m["artifact_identity"] != m["model_sha256"] + ":" + m["manifest_sha256"]
    ):
        raise ValueError("RELEASE_POLICY")
    for field, maximum in (
        ("model_bytes", MAX_MODEL),
        ("manifest_bytes", MAX_METADATA),
    ):
        if type(m[field]) is not int or not 0 < m[field] <= maximum:
            raise ValueError("RELEASE_SIZE")
    if (
        not Version(m["minimum_app_version"])
        <= Version(app_version)
        <= Version(m["maximum_app_version"])
    ):
        raise ValueError("APP_VERSION_UNSUPPORTED")
    created = datetime.fromisoformat(m["created_at"])
    expires = datetime.fromisoformat(m["expires_at"])
    if (
        not created.tzinfo
        or not expires.tzinfo
        or expires <= created
        or created > datetime.now(UTC)
    ):
        raise ValueError("RELEASE_TIME")
    if not allow_expired and expires < datetime.now(UTC):
        raise ValueError("RELEASE_EXPIRED")
    if (
        not isinstance(m["change_notes"], str)
        or not 1 <= len(m["change_notes"]) <= 4000
    ):
        raise ValueError("CHANGE_NOTES")
    return m
