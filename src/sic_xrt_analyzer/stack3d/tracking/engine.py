"""Public entry points: whole-volume tracking and seed lookup."""

from dataclasses import dataclass

import numpy as np

from .detection import detect_page
from .linking import link
from .model import Detection, Track, TrackResult, TrackSettings


@dataclass(frozen=True)
class SeedTrack:
    result: TrackResult
    detection: Detection
    track: Track


def _volume(volume):
    v = np.asarray(volume)
    if v.ndim != 3 or v.shape[0] < 1 or v.dtype.kind not in "uif":
        raise ValueError("페이지 x 높이 x 너비 숫자형 볼륨이 필요합니다")
    return v


def track_stack(volume, settings=None, *, origin=(0, 0), first_page=0,
                cancelled=None, progress=None):
    """Detect every page independently, then link globally. Pages are scan order."""
    v = _volume(volume)
    settings = settings or TrackSettings()
    cancelled = cancelled or (lambda: False)
    progress = progress or (lambda *a: None)
    detections = []
    for k in range(v.shape[0]):
        if cancelled():
            raise InterruptedError("결함 추적 취소")
        detections += detect_page(v[k], first_page + k, settings, origin)
        progress(k + 1, v.shape[0], "페이지별 결함 검출")
    tracks, links = link(detections, settings, cancelled, progress)
    return TrackResult(
        tuple(int(n) for n in v.shape), tuple(int(n) for n in origin), int(first_page),
        settings, tuple(sorted(detections, key=lambda d: (d.page, d.id))),
        tuple(links), tuple(tracks),
    )


def nearest_detection(result, page, x, y, radius=6.0):
    best = None
    for d in result.detections:
        if d.page != page:
            continue
        dist = float(np.min(np.hypot(d.points[:, 0] - x, d.points[:, 1] - y)))
        if dist <= radius and (best is None or dist < best[0]):
            best = (dist, d)
    return best[1] if best else None


def track_from_seed(volume, page, x, y, settings=None, *, origin=(0, 0), first_page=0,
                    radius=6.0, cancelled=None, progress=None, result=None):
    """Return the track holding the detection nearest (x, y) on page (absolute coords)."""
    if result is None:
        result = track_stack(volume, settings, origin=origin, first_page=first_page,
                             cancelled=cancelled, progress=progress)
    detection = nearest_detection(result, page, x, y, radius)
    if detection is None:
        raise ValueError("선택 위치 근처에서 결함 후보를 찾지 못했습니다")
    return SeedTrack(result, detection, result.track_of(detection.id))
