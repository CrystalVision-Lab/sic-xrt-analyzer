"""Adapters own model loading, preprocessing, inference and inverse transform mapping."""
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Protocol

import numpy as np

from .contracts import (
    AdapterOutput,
    AnalysisError,
    AnalysisException,
    AnalysisRequest,
    AnalysisScope,
    CoordinateSpace,
    GeometryKind,
)


class CancellationToken:
    def __init__(self):
        self._event = Event()

    @property
    def cancel_requested(self):
        return self._event.is_set()

    def cancel(self):
        self._event.set()

    def check(self):
        if self.cancel_requested:
            raise AnalysisException(AnalysisError("CANCELED", "분석이 취소되었습니다"))


class InputCompatibilityReason(str, Enum):
    UNSUPPORTED_DTYPE = "UNSUPPORTED_DTYPE"
    UNSUPPORTED_CHANNEL_COUNT = "UNSUPPORTED_CHANNEL_COUNT"


@dataclass(frozen=True)
class ModelInputContract:
    supported_scopes: tuple[AnalysisScope, ...]
    expected_channels: tuple[int, ...]
    accepted_dtypes: tuple[str, ...]
    input_size_policy: str
    normalization: str
    color_space: str
    bit_depth_policy: str

    def __post_init__(self):
        for name in ("supported_scopes", "expected_channels", "accepted_dtypes"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not self.supported_scopes or any(not isinstance(s, AnalysisScope) for s in self.supported_scopes):
            raise ValueError("Adapter must declare supported scopes")
        if not self.expected_channels or any(type(c) is not int or c <= 0 for c in self.expected_channels):
            raise ValueError("Adapter must declare accepted original channel counts")
        if not self.accepted_dtypes:
            raise ValueError("Adapter must declare accepted original dtypes")
        object.__setattr__(self, "accepted_dtypes", tuple(np.dtype(dtype).name for dtype in self.accepted_dtypes))
        if any(not isinstance(p, str) or not p for p in
               (self.input_size_policy, self.normalization, self.color_space, self.bit_depth_policy)):
            raise ValueError("Adapter must document its preprocessing policies")

    def incompatibility_reasons(self, metadata):
        """The original backend rules, without reading pixels or running inference.

        Color/normalization/size policies document adapter preprocessing; they are
        not additional acceptance rules. Source metadata describes original decoded
        samples, never the display grid or the model's float32 tensor.
        """
        reasons = []
        if metadata.dtype not in self.accepted_dtypes:
            reasons.append(InputCompatibilityReason.UNSUPPORTED_DTYPE)
        if metadata.channels not in self.expected_channels:
            reasons.append(InputCompatibilityReason.UNSUPPORTED_CHANNEL_COUNT)
        return tuple(reasons)

    def validate(self, request: AnalysisRequest):
        if request.scope not in self.supported_scopes:
            raise AnalysisException(AnalysisError("UNSUPPORTED_SCOPE", "모델이 요청한 분석 범위를 지원하지 않습니다"))
        meta = request.source.metadata
        if self.incompatibility_reasons(meta):
            raise AnalysisException(AnalysisError("INVALID_INPUT", "모델이 원본 이미지 형식을 지원하지 않습니다"))


@dataclass(frozen=True)
class ModelOutputContract:
    geometry_kinds: tuple[GeometryKind, ...]
    coordinate_space: CoordinateSpace

    def __post_init__(self):
        object.__setattr__(self, "geometry_kinds", tuple(self.geometry_kinds))
        if not self.geometry_kinds or any(not isinstance(k, GeometryKind) for k in self.geometry_kinds):
            raise ValueError("Adapter must declare geometry kinds")
        if not isinstance(self.coordinate_space, CoordinateSpace):
            raise TypeError("Adapter must declare output coordinate space")


class ModelAdapter(Protocol):
    model_id: str
    model_name: str
    model_version: str
    available: bool
    device: str | None
    input_contract: ModelInputContract
    output_contract: ModelOutputContract

    def analyze(self, image: np.ndarray, request: AnalysisRequest,
                cancellation_token: CancellationToken) -> AdapterOutput:
        """Receive raw original samples; return geometry after undoing model transforms.

        INPUT_LOCAL means pixels of the original input crop, never resized/padded tensor pixels.
        Pipeline adds crop origin and stamps authoritative request/timing on AnalysisResult.
        """
        ...
