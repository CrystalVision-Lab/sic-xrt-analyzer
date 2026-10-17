"""Page-to-page same-defect tracking proposals (AUTO, PROPOSED; not confirmed defects)."""

from .detection import detect_page, normalize_page
from .engine import SeedTrack, nearest_detection, track_from_seed, track_stack
from .model import SCHEMA, Detection, Link, Track, TrackResult, TrackSettings

__all__ = [
    "SCHEMA", "Detection", "Link", "SeedTrack", "Track", "TrackResult", "TrackSettings",
    "detect_page", "nearest_detection", "normalize_page", "track_from_seed", "track_stack",
]
