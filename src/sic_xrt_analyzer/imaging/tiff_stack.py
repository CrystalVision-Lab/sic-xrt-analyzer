"""Read-only page cache and display windows. No spatial interpretation of frame order."""
import math
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtGui import QImage

from .original_source import OriginalImageSource
from .tiff_pages import page_layout
from .tiff_preview import MAX_PREVIEW_EDGE, TiffPreview


def auto_window(pixels):
    if pixels.dtype == np.uint8:
        return 0.0, 255.0
    if pixels.dtype == np.bool_:
        return 0.0, 1.0
    sample = pixels[::max(1, pixels.shape[0] // 512), ::max(1, pixels.shape[1] // 512)]
    finite = sample[np.isfinite(sample)]
    if not finite.size:
        raise ValueError("표시할 수 있는 유효한 픽셀이 없습니다")
    low, high = (float(v) for v in np.percentile(finite, (1, 99)))
    if high <= low:
        low, high = (0.0, max(1.0, high)) if high >= 0 else (low, 0.0)
    return low, high


def imagej_window(metadata):
    ranges = metadata.get("Ranges", metadata.get("ranges"))
    candidates = [(metadata.get("min"), metadata.get("max"))]
    if ranges is not None:
        try:
            flat = np.asarray(ranges).ravel()
            if flat.size >= 2:
                candidates.append((flat[0], flat[1]))
        except (TypeError, ValueError):
            pass  # Malformed optional display metadata does not prevent page reading.
    for low, high in candidates:
        try:
            low, high = float(low), float(high)
        except (TypeError, ValueError):
            continue
        if math.isfinite(low) and math.isfinite(high) and low < high:
            return low, high
    return None


def render_page(pixels, source, low, high):
    """Convert only display samples. The cached raw ndarray remains immutable."""
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ValueError("표시 최솟값은 최댓값보다 작아야 합니다")
    m = source.metadata
    step = max(1, math.ceil(max(m.width, m.height) / MAX_PREVIEW_EDGE))
    values = pixels[::step, ::step].astype(np.float64)
    finite = np.isfinite(values)
    with np.errstate(invalid="ignore", over="ignore"):
        values -= low
        values *= 255.0 / (high - low)
        np.clip(values, 0, 255, out=values)
        values[~finite] = 0
        display = np.ascontiguousarray(values.astype(np.uint8))
    with tifffile.TiffFile(source.path) as tif:
        page, _, _ = page_layout(tif, source.page_index)
        invert = page.photometric == tifffile.PHOTOMETRIC.MINISWHITE
    if invert:
        display = np.ascontiguousarray(255 - display)
    fmt = (QImage.Format_Grayscale8 if display.ndim == 2 else
           QImage.Format_RGB888 if display.shape[-1] == 3 else QImage.Format_RGBA8888)
    if display.ndim == 3 and display.shape[-1] == 4:
        # Alpha is coverage, not intensity: do not window it with grayscale levels.
        alpha = pixels[::step, ::step, 3]
        if alpha.dtype.kind in "ui":
            display[..., 3] = (alpha.astype(np.float64) * (255 / np.iinfo(alpha.dtype).max)).astype(np.uint8)
    image = QImage(display.data, display.shape[1], display.shape[0], display.strides[0], fmt).copy()
    if image.isNull():
        raise ValueError("페이지 미리보기를 만들 수 없습니다")
    return TiffPreview(image, m.width, m.height, m.bit_depth, m.page_count, step > 1)


@dataclass(frozen=True)
class StackFrame:
    source: OriginalImageSource
    preview: TiffPreview
    pixels: np.ndarray
    low: float
    high: float
    default_low: float
    default_high: float
    range_min: float
    range_max: float
    imagej_frames: int | None
    imagej_slices: int | None
    range_origin: str


class TiffStack:
    """Worker-owned cache, bounded by both page count and raw bytes; no prefetch."""

    def __init__(self, path, *, max_cache_bytes=96 * 1024**2, max_cache_pages=3):
        if max_cache_bytes <= 0 or max_cache_pages < 1:
            raise ValueError("Cache limits must be positive")
        self.path = str(Path(path).resolve(strict=True))
        self.first_source = OriginalImageSource(self.path)
        self.page_count = self.first_source.metadata.page_count
        self.max_cache_bytes, self.max_cache_pages = max_cache_bytes, max_cache_pages
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.decode_count = 0
        with tifffile.TiffFile(self.path) as tif:
            metadata = tif.imagej_metadata or {}
            # Preserve acquisition labels. Never use frames/slices as calibrated spatial Z.
            self.imagej_frames = metadata.get("frames")
            self.imagej_slices = metadata.get("slices")
            self.initial_window = imagej_window(metadata)
        self.default_window = None
        self.range_origin = "ImageJ" if self.initial_window else "첫 페이지 자동 범위"
        self.closed = False

    def read_page(self, index):
        if self.closed:
            raise ValueError("TIFF stack is closed")
        self.first_source.validate_identity()
        source = OriginalImageSource(self.path, index)
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index], source
        pixels = source.read_full()  # One page only; source has read/decode limits.
        pixels.setflags(write=False)
        self.decode_count += 1
        if pixels.nbytes <= self.max_cache_bytes:
            while self.cache and (len(self.cache) >= self.max_cache_pages or
                                  self.cache_bytes + pixels.nbytes > self.max_cache_bytes):
                _, old = self.cache.popitem(last=False)
                self.cache_bytes -= old.nbytes
            self.cache[index] = pixels
            self.cache_bytes += pixels.nbytes
        return pixels, source

    def frame(self, index, window=None, *, automatic=False, canceled=lambda: False):
        pixels, source = self.read_page(index)
        if canceled():
            return None
        if self.default_window is None:
            if self.initial_window is not None:
                self.default_window = self.initial_window
            else:
                # Reopening an old file after a failed file switch may first request a middle page.
                # Keep the fallback range anchored to page one, regardless of request order.
                first_pixels = pixels if index == 0 else self.read_page(0)[0]
                self.default_window = auto_window(first_pixels)
        low, high = auto_window(pixels) if automatic else (window or self.default_window)
        preview = render_page(pixels, source, low, high)
        source.validate_identity()
        if canceled():
            return None
        if pixels.dtype.kind in "ui":
            info = np.iinfo(pixels.dtype)
            range_min, range_max = float(info.min), float(info.max)
        elif pixels.dtype == np.bool_:
            range_min, range_max = 0.0, 1.0
        else:
            sample = pixels[::max(1, pixels.shape[0] // 512), ::max(1, pixels.shape[1] // 512)]
            finite = sample[np.isfinite(sample)]
            range_min, range_max = float(finite.min()), float(finite.max())
        range_min, range_max = min(range_min, low), max(range_max, high)
        if range_max <= range_min:
            range_max = range_min + 1
        return StackFrame(source, preview, pixels, low, high, *self.default_window,
                          range_min, range_max, self.imagej_frames, self.imagej_slices, self.range_origin)

    def close(self):
        self.cache.clear()
        self.cache_bytes = 0
        self.closed = True
