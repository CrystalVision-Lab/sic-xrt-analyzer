"""Framework-independent analysis contract v1. All published coordinates are original pixels."""
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from uuid import uuid4

from sic_xrt_analyzer.imaging.original_source import OriginalPixelSource, SourceIdentity

CONTRACT_VERSION = "1.0"


def utc_now():
    return datetime.now(UTC)


def freeze(value):
    """Copy JSON-like data recursively, rejecting mutable/custom object leaves."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Contract mappings require string keys")
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Contract metadata must contain finite JSON-like values")


class AnalysisScope(str, Enum):
    FULL_IMAGE = "FULL_IMAGE"
    ROI = "ROI"


class AnalysisState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def validate(self, source):
        source.validate_region(self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class AnalysisRequest:
    source: OriginalPixelSource
    scope: AnalysisScope
    model_id: str
    model_version: str
    roi: Region | None = None
    parameters: Mapping = field(default_factory=dict)
    analysis_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    source_identity: SourceIdentity = field(init=False)
    page_index: int = field(init=False)

    def __post_init__(self):
        if not isinstance(self.source, OriginalPixelSource) or not isinstance(self.scope, AnalysisScope):
            raise TypeError("An original source and explicit AnalysisScope are required")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("Request parameters require a mapping")
        if any(not isinstance(value, str) or not value for value in
               (self.analysis_id, self.model_id, self.model_version)):
            raise ValueError("Request and model identifiers are required")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("Request timestamps must include a timezone")
        if (self.scope == AnalysisScope.ROI) != (self.roi is not None):
            raise ValueError("ROI scope requires a region; full image scope forbids a region")
        if self.roi is not None:
            if not isinstance(self.roi, Region):
                raise TypeError("ROI must be an immutable Region")
            self.roi.validate(self.source)
        object.__setattr__(self, "parameters", freeze(self.parameters))
        object.__setattr__(self, "source_identity", self.source.identity)
        object.__setattr__(self, "page_index", self.source.page_index)


@dataclass(frozen=True)
class AnalysisError:
    code: str
    message: str
    detail: str = ""
    recoverable: bool = True

    def __post_init__(self):
        if any(not isinstance(v, str) for v in (self.code, self.message, self.detail)):
            raise TypeError("Error fields must be strings")
        if type(self.recoverable) is not bool:
            raise TypeError("recoverable must be a boolean")


class AnalysisException(Exception):
    def __init__(self, error: AnalysisError):
        super().__init__(error.detail or error.message)
        self.error = error


class GeometryKind(str, Enum):
    POINT = "POINT"
    BOUNDING_BOX = "BOUNDING_BOX"
    POLYGON = "POLYGON"
    MASK = "MASK"


class CoordinateSpace(str, Enum):
    INPUT_LOCAL = "INPUT_LOCAL"
    ORIGINAL = "ORIGINAL"


@dataclass(frozen=True)
class Geometry:
    kind: GeometryKind
    points: tuple = ()
    bbox: tuple | None = None  # x, y, width, height; half-open pixel extent
    mask_reference: str | None = None  # external resource, no raw tensor in UI contracts
    mask_encoding: str | None = None
    coordinate_space: CoordinateSpace = CoordinateSpace.INPUT_LOCAL

    def __post_init__(self):
        if not isinstance(self.kind, GeometryKind) or not isinstance(self.coordinate_space, CoordinateSpace):
            raise TypeError("Geometry kind and coordinate space must be explicit")
        points = tuple(tuple(point) for point in self.points)
        bbox = tuple(self.bbox) if self.bbox is not None else None
        values = [value for point in points for value in point] + list(bbox or ())
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("Geometry requires finite pixel coordinates")
        if any(len(point) != 2 for point in points):
            raise ValueError("Points require x and y")
        if bbox is not None and (len(bbox) != 4 or bbox[2] <= 0 or bbox[3] <= 0):
            raise ValueError("Bounding extent requires positive width and height")
        if self.kind == GeometryKind.POINT and (len(points) != 1 or bbox is not None):
            raise ValueError("POINT requires exactly one point")
        if self.kind == GeometryKind.POLYGON and (len(points) < 3 or bbox is not None):
            raise ValueError("POLYGON requires at least three points")
        if self.kind in (GeometryKind.BOUNDING_BOX, GeometryKind.MASK) and (bbox is None or points):
            raise ValueError("Box and mask geometries require an extent")
        if self.kind == GeometryKind.MASK:
            if not self.mask_reference or not self.mask_encoding:
                raise ValueError("MASK requires a reference and encoding")
        elif self.mask_reference is not None or self.mask_encoding is not None:
            raise ValueError("Only MASK can refer to mask data")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "bbox", bbox)


@dataclass(frozen=True)
class Detection:
    id: str
    class_id: str | int | None
    class_name: str | None
    confidence: float | None
    geometry: Geometry
    metadata: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id or not isinstance(self.geometry, Geometry):
            raise ValueError("Detection id and geometry are required")
        if self.class_id is not None and type(self.class_id) not in (int, str):
            raise TypeError("Class id must be a string, integer or absent")
        if self.class_name is not None and not isinstance(self.class_name, str):
            raise TypeError("Class name must be a string or absent")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("Detection metadata requires a mapping")
        if self.confidence is not None and (not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("Confidence must be absent or between zero and one")
        object.__setattr__(self, "metadata", freeze(self.metadata))


@dataclass(frozen=True)
class AdapterOutput:
    detections: tuple[Detection, ...] = ()
    summary: Mapping = field(default_factory=dict)
    preprocessing: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if any(not isinstance(d, Detection) for d in self.detections):
            raise TypeError("Adapter output requires immutable detections")
        if not isinstance(self.summary, Mapping) or not isinstance(self.preprocessing, Mapping):
            raise TypeError("Output summary and preprocessing require mappings")
        object.__setattr__(self, "detections", tuple(self.detections))
        object.__setattr__(self, "summary", freeze(self.summary))
        object.__setattr__(self, "preprocessing", freeze(self.preprocessing))


@dataclass(frozen=True)
class AnalysisResult:
    request: AnalysisRequest
    status: AnalysisState
    started_at: datetime
    completed_at: datetime
    duration: float  # monotonic wall seconds, including source read
    detections: tuple[Detection, ...] = ()
    summary: Mapping = field(default_factory=dict)
    preprocessing: Mapping = field(default_factory=dict)
    error: AnalysisError | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self):
        if not isinstance(self.request, AnalysisRequest) or not isinstance(self.status, AnalysisState):
            raise TypeError("Result requires an immutable request and formal state")
        if self.status not in (AnalysisState.COMPLETED, AnalysisState.FAILED, AnalysisState.CANCELED):
            raise ValueError("Results require a terminal state")
        if not math.isfinite(self.duration) or self.duration < 0:
            raise ValueError("Result duration must be finite and nonnegative")
        if self.error is not None and not isinstance(self.error, AnalysisError):
            raise TypeError("Result errors require AnalysisError")
        if not isinstance(self.summary, Mapping) or not isinstance(self.preprocessing, Mapping):
            raise TypeError("Result summary and preprocessing require mappings")
        detections = tuple(self.detections)
        if any(d.geometry.coordinate_space != CoordinateSpace.ORIGINAL for d in detections):
            raise ValueError("Published detections must use original pixel coordinates")
        object.__setattr__(self, "detections", detections)
        object.__setattr__(self, "summary", freeze(self.summary))
        object.__setattr__(self, "preprocessing", freeze(self.preprocessing))

    @property
    def analysis_id(self):
        return self.request.analysis_id

    @property
    def source_identity(self):
        return self.request.source_identity

    @property
    def model_id(self):
        return self.request.model_id

    @property
    def model_version(self):
        return self.request.model_version

    @property
    def scope(self):
        return self.request.scope

    @property
    def roi(self):
        return self.request.roi

    @property
    def parameters(self):
        return self.request.parameters
