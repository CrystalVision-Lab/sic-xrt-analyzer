"""Explicit source availability/hash/relink operations; never decode pixels, copy or upload data."""

import hashlib
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

from .contracts import FileIdentity, VerifiedContentHash


@dataclass(frozen=True)
class SourceAvailability:
    status: str
    pixels_available: bool
    detail: str


def _metadata(path):
    # TIFF headers, including ImageJ stack layout, use the existing authoritative reader.
    try:
        meta = OriginalImageSource(path).metadata
        return (
            meta.width,
            meta.height,
            meta.dtype,
            meta.bit_depth,
            meta.channels,
            meta.page_count,
        )
    except ValueError:
        from PIL import Image

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != "JPEG" or image.mode != "RGB":
                    raise ValueError("Source is not the recorded TIFF/RGB JPEG format")
                return (image.width, image.height, "uint8", 8, 3, 1)


def _hash_snapshot(path):
    before = path.stat()
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during hash verification")
    return VerifiedContentHash(
        sha.hexdigest(), utc_now(), str(path), after.st_size, after.st_mtime_ns
    )


def inspect_source(source, *, reference=None, verify_hash=False):
    path = Path(reference or source.source_reference).resolve()
    if not path.is_file():
        return SourceAvailability(
            "MISSING",
            False,
            "Metadata is readable; original pixels/crops are unavailable",
        )
    try:
        stat = path.stat()
        shape = _metadata(path)
        expected = (
            source.width,
            source.height,
            source.dtype,
            source.bit_depth,
            source.channels,
            source.page_count,
        )
        if shape != expected:
            return SourceAvailability(
                "IDENTITY_MISMATCH", False, "Original image metadata differs"
            )
        same_path = str(path) == source.file_identity.canonical_path
        if verify_hash:
            if source.content_hash is None:
                return SourceAvailability(
                    "HASH_UNAVAILABLE",
                    False,
                    "No previously verified content hash; cannot prove a relocated source",
                )
            if _hash_snapshot(path).value != source.content_hash.value:
                return SourceAvailability(
                    "IDENTITY_MISMATCH", False, "Content hash differs"
                )
            return SourceAvailability(
                "HASH_MATCH", True, "Explicit content verification passed"
            )
        if not same_path or (stat.st_size, stat.st_mtime_ns) != (
            source.file_identity.file_size,
            source.file_identity.mtime_ns,
        ):
            return SourceAvailability(
                "IDENTITY_MISMATCH",
                False,
                "Path/stat identity differs; explicit hash-based relink required",
            )
        return SourceAvailability(
            "METADATA_MATCH",
            True,
            "Original metadata/stat match; content hash was not recalculated",
        )
    except (OSError, ValueError) as exc:
        return SourceAvailability("UNREADABLE", False, str(exc))


def verify_content_hash(source):
    status = inspect_source(source)
    if not status.pixels_available:
        raise ValueError(status.detail)
    path = Path(source.source_reference).resolve()
    snapshot = _hash_snapshot(path)
    if source.content_hash and snapshot.value != source.content_hash.value:
        raise ValueError("Content differs from previously verified hash")
    return replace(source, content_hash=snapshot)


def relink_source(source, reference):
    if source.content_hash is None:
        raise ValueError(
            "Relinking requires a previously explicitly verified content hash"
        )
    path = Path(reference).resolve(strict=True)
    shape = _metadata(path)
    if shape != (
        source.width,
        source.height,
        source.dtype,
        source.bit_depth,
        source.channels,
        source.page_count,
    ):
        raise ValueError("Relinked original metadata differs")
    snapshot = _hash_snapshot(path)
    if snapshot.value != source.content_hash.value:
        raise ValueError("Relinked source hash differs")
    return replace(
        source,
        source_reference=str(path),
        file_identity=FileIdentity(str(path), snapshot.file_size, snapshot.mtime_ns),
        content_hash=snapshot,
    )
