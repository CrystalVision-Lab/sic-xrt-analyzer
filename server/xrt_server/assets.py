import base64
import hashlib
import io
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select

from sic_xrt_analyzer.sync.protocol import digest

from .auth import audit
from .models import Asset
from .service import lock, rows_for

META_KEYS = {
    "source_id",
    "run_id",
    "target_id",
    "target_type",
    "crop_x",
    "crop_y",
    "crop_width",
    "crop_height",
    "source_dtype",
    "source_channels",
    "source_hash",
    "crop_hash",
    "pixel_hash",
    "linked_review_ids",
    "geometry_coordinate_space",
    "mime_type",
}


def store_crop(session, user, device, project, body, base):
    if (
        set(body) != {"metadata", "image_base64", "consent"}
        or body["consent"] is not True
    ):
        raise ValueError("EXPLICIT_CROP_CONSENT_REQUIRED")
    meta = body["metadata"]
    if set(meta) != META_KEYS:
        raise ValueError("CROP_METADATA_FIELDS")
    rows = rows_for(session, project.id)
    source = rows["image_sources"].get(meta["source_id"])
    run = rows["analysis_runs"].get(meta["run_id"])
    if not source or not run or run["source_id"] != meta["source_id"]:
        raise ValueError("CROP_SOURCE_RUN_MISMATCH")
    if not source["display_name"].lower().endswith((".jpg", ".jpeg")) or (
        source["dtype"],
        source["channels"],
        source["page_count"],
    ) != ("uint8", 3, 1):
        raise ValueError("JPEG_CROP_ONLY")
    if (
        not source["content_hash"]
        or source["content_hash"]["value"] != meta["source_hash"]
    ):
        raise ValueError("CROP_SOURCE_HASH_MISMATCH")
    if (
        meta["source_dtype"],
        meta["source_channels"],
        meta["geometry_coordinate_space"],
        meta["mime_type"],
    ) != ("uint8", 3, "ORIGINAL", "image/png"):
        raise ValueError("CROP_FORMAT")
    x, y, w, h = (meta[k] for k in ("crop_x", "crop_y", "crop_width", "crop_height"))
    if (
        any(type(v) is not int for v in (x, y, w, h))
        or min(x, y) < 0
        or min(w, h) < 1
        or max(w, h) > 1024
        or x + w > source["width"]
        or y + h > source["height"]
        or w * h >= source["width"] * source["height"]
    ):
        raise ValueError("CROP_BOUNDS_OR_WHOLE_SOURCE")
    table = {"OBSERVATION": "observations", "DEFECT_INSTANCE": "defect_instances"}.get(
        meta["target_type"]
    )
    target = rows.get(table, {}).get(meta["target_id"])
    if (
        not target
        or (table == "observations" and target["run_id"] != run["run_id"])
        or (table == "defect_instances" and target["source_id"] != source["source_id"])
    ):
        raise ValueError("CROP_TARGET_MISMATCH")
    if not meta["linked_review_ids"] or len(meta["linked_review_ids"]) > 100:
        raise ValueError("CROP_REVIEW_REQUIRED")
    for ident in meta["linked_review_ids"]:
        review = rows["review_events"].get(ident)
        if not review or (review["target_id"], review["target_type"]) != (
            meta["target_id"],
            meta["target_type"],
        ):
            raise ValueError("CROP_REVIEW_MISMATCH")
    if len(body["image_base64"]) > 6 * 1024**2:
        raise ValueError("CROP_TOO_LARGE")
    raw = base64.b64decode(body["image_base64"], validate=True)
    if len(raw) > 4 * 1024**2 or hashlib.sha256(raw).hexdigest() != meta["crop_hash"]:
        raise ValueError("CROP_HASH_OR_SIZE")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.mode != "RGB" or image.size != (w, h):
                raise ValueError("CROP_CONTENT_TYPE")
            if hashlib.sha256(image.tobytes()).hexdigest() != meta["pixel_hash"]:
                raise ValueError("CROP_PIXEL_HASH")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError("INVALID_CROP_IMAGE") from exc
    ident = digest(meta)
    lock(session, "project-crops:" + project.id)
    lock(session, "crop:" + meta["crop_hash"])
    old = session.get(Asset, (project.id, ident))
    if old:
        return {"status": "ACKNOWLEDGED", "asset_id": ident, "crop_hash": old.digest}
    count = session.scalar(
        select(func.count()).select_from(Asset).where(Asset.project_id == project.id)
    )
    if count >= 1000:
        raise HTTPException(409, "PROJECT_CROP_LIMIT")
    root = Path(base).resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = meta["crop_hash"] + ".png"
    path = root / key
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("ASSET_STORAGE_UNSAFE")
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["crop_hash"]:
            raise HTTPException(409, "ASSET_STORAGE_CONFLICT")
    else:
        fd, name = tempfile.mkstemp(prefix=".stage-", dir=root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    session.add(
        Asset(
            project_id=project.id,
            id=ident,
            digest=meta["crop_hash"],
            storage_key=key,
            payload=meta,
            actor_id=user.id,
            device_id=device.id,
        )
    )
    audit(session, "ASSET_UPLOAD", user.id, project.id, asset_id=ident)
    return {"status": "ACKNOWLEDGED", "asset_id": ident, "crop_hash": meta["crop_hash"]}
