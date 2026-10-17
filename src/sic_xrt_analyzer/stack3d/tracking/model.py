"""Serializable page-track proposals. AUTO output is never a confirmed defect."""

import math
from dataclasses import asdict, dataclass, field, fields

import numpy as np

SCHEMA = "xrt_page_track_result/v1"
ALGORITHM_VERSION = "1.0.0"
KINDS = ("BLOB", "SEGMENT")
POLARITIES = ("DARK", "BRIGHT")
LINK_KINDS = ("CONTINUE", "GAP", "SPLIT", "MERGE")
STATUSES = ("PROPOSED", "REVIEWED", "REJECTED")
SOURCES = ("AUTO", "MANUAL")


@dataclass(frozen=True)
class TrackSettings:
    """All lengths are source pixels; pages are scan order, not physical depth."""

    polarity: str = "DARK"  # DARK | BRIGHT | BOTH
    background_px: int = 31  # fixed median kernel, independent of crop size
    smooth_sigma: float = 1.0
    low_z: float = 2.5
    high_z: float = 5.0
    line_length_px: int = 15  # oriented line integration length
    line_orientations: int = 12
    line_low_z: float = 3.0
    line_high_z: float = 5.5
    blob_sigma: float = 2.0
    blob_low_z: float = 3.0
    blob_high_z: float = 6.0
    support_z: float = 1.0  # filter responses need pixel-level support
    relative_floor: float = 0.25  # of the 7x7 local peak; trims halos
    min_area_px: int = 4
    blob_core_px: float = 2.5
    blob_max_extent_px: float = 10.0
    min_segment_px: float = 5.0
    join_gap_px: float = 6.0
    join_angle_deg: float = 25.0
    gate_px: float = 12.0
    orientation_weight: float = 4.0
    contrast_weight: float = 1.0
    kind_penalty: float = 1.0  # BLOB<->SEGMENT change (a point may look elongated)
    no_link_cost: float = 7.0  # per side; a link must cost < 2x this
    velocity_smoothing: float = 0.5
    max_gap: int = 3  # missing pages bridged by gap closing
    gap_penalty: float = 1.5
    split_merge_px: float = 4.0
    confidence_scale: float = 2.0
    review_below: float = 0.5

    def __post_init__(self):
        if self.polarity not in ("DARK", "BRIGHT", "BOTH"):
            raise ValueError("polarity must be DARK, BRIGHT or BOTH")
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "polarity":
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid tracking setting {f.name}")
        if self.background_px < 3 or self.line_orientations < 1 or self.max_gap > 16:
            raise ValueError("tracking setting out of range")
        if self.low_z > self.high_z or self.line_low_z > self.line_high_z:
            raise ValueError("hysteresis low threshold must not exceed high")


@dataclass(frozen=True)
class Detection:
    id: str
    page: int
    kind: str
    centroid: tuple[float, float]  # x, y in original ROI coordinates
    points: np.ndarray = field(repr=False, compare=False)  # (N, 2) int x, y
    orientation: float  # radians in [0, pi)
    length: float
    contrast_z: float
    polarity: str

    def to_dict(self):
        return {
            "id": self.id,
            "page": self.page,
            "kind": self.kind,
            "centroid": [round(v, 3) for v in self.centroid],
            "points": self.points.astype(int).tolist(),
            "orientation": round(self.orientation, 5),
            "length": round(self.length, 3),
            "contrast_z": round(self.contrast_z, 3),
            "polarity": self.polarity,
        }

    @classmethod
    def from_dict(cls, d):
        points = np.asarray(d["points"], np.int32).reshape(-1, 2)
        if d["kind"] not in KINDS or d["polarity"] not in POLARITIES or not len(points):
            raise ValueError("invalid detection")
        return cls(
            str(d["id"]), int(d["page"]), d["kind"], tuple(map(float, d["centroid"])),
            points, float(d["orientation"]), float(d["length"]),
            float(d["contrast_z"]), d["polarity"],
        )


@dataclass(frozen=True)
class Link:
    source_id: str
    target_id: str
    kind: str
    cost: float
    confidence: float
    review: bool
    status: str = "PROPOSED"
    source: str = "AUTO"

    def to_dict(self):
        d = asdict(self)
        d["cost"] = round(self.cost, 4)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, d):
        link = cls(**d)
        if (
            link.kind not in LINK_KINDS
            or link.status not in STATUSES
            or link.source not in SOURCES
            or not 0 <= link.confidence <= 1
        ):
            raise ValueError("invalid link")
        return link


@dataclass(frozen=True)
class Track:
    id: str
    detection_ids: tuple[str, ...]  # one per page, ascending page
    pages: tuple[int, ...]
    min_confidence: float
    review: bool
    status: str = "PROPOSED"
    source: str = "AUTO"

    def to_dict(self):
        d = asdict(self)
        d["detection_ids"] = list(self.detection_ids)
        d["pages"] = list(self.pages)
        d["min_confidence"] = round(self.min_confidence, 4)
        return d

    @classmethod
    def from_dict(cls, d):
        track = cls(
            str(d["id"]), tuple(d["detection_ids"]), tuple(int(p) for p in d["pages"]),
            float(d["min_confidence"]), bool(d["review"]), d["status"], d["source"],
        )
        if (
            len(track.pages) != len(track.detection_ids)
            or list(track.pages) != sorted(set(track.pages))
            or track.status not in STATUSES
            or track.source not in SOURCES
        ):
            raise ValueError("invalid track")
        return track


@dataclass(frozen=True)
class TrackResult:
    shape: tuple[int, int, int]  # pages, height, width of the analysed volume
    origin: tuple[int, int]  # x, y of the volume in the original page
    first_page: int
    settings: TrackSettings
    detections: tuple[Detection, ...]
    links: tuple[Link, ...]  # CONTINUE/GAP links inside tracks + SPLIT/MERGE candidates
    tracks: tuple[Track, ...]

    def detection(self, detection_id):
        return self._index()[detection_id]

    def _index(self):
        index = self.__dict__.get("_by_id")
        if index is None:
            index = {d.id: d for d in self.detections}
            object.__setattr__(self, "_by_id", index)
        return index

    def track_of(self, detection_id):
        return next((t for t in self.tracks if detection_id in t.detection_ids), None)

    def to_dict(self):
        return {
            "schema": SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "shape": list(self.shape),
            "origin": list(self.origin),
            "first_page": self.first_page,
            "settings": asdict(self.settings),
            "detections": [d.to_dict() for d in self.detections],
            "links": [link.to_dict() for link in self.links],
            "tracks": [t.to_dict() for t in self.tracks],
        }

    @classmethod
    def from_dict(cls, d):
        if d.get("schema") != SCHEMA:
            raise ValueError("Unsupported page-track schema")
        detections = tuple(Detection.from_dict(x) for x in d["detections"])
        ids = {x.id for x in detections}
        links = tuple(Link.from_dict(x) for x in d["links"])
        tracks = tuple(Track.from_dict(x) for x in d["tracks"])
        if len(ids) != len(detections) or any(
            x.source_id not in ids or x.target_id not in ids for x in links
        ) or any(i not in ids for t in tracks for i in t.detection_ids):
            raise ValueError("page-track references unknown detection")
        return cls(
            tuple(d["shape"]), tuple(d["origin"]), int(d["first_page"]),
            TrackSettings(**d["settings"]), detections, links, tracks,
        )
