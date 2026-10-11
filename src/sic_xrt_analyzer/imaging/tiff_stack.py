"""Read-only page cache and display windows. No spatial interpretation of frame order."""
import math
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

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
    samples = pixels[::step, ::step]
    # Window 65,536 intensity levels once, rather than millions of float pixels.
    # Keep the same float64 arithmetic/truncation as the general display path.
    values = np.arange(65536, dtype=np.float64) if pixels.dtype == np.uint16 else samples.astype(np.float64)
    finite = np.isfinite(values)
    with np.errstate(invalid="ignore", over="ignore"):
        values -= low
        values *= 255.0 / (high - low)
        np.clip(values, 0, 255, out=values)
        values[~finite] = 0
        display = np.ascontiguousarray(values.astype(np.uint8))
    if pixels.dtype == np.uint16:
        display = np.ascontiguousarray(display[samples])
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
    """Worker reads; GUI may retrieve prepared frames under a short cache lock."""

    def __init__(self, path, *, max_cache_bytes=96 * 1024**2, max_cache_pages=3,
                 max_display_bytes=32 * 1024**2):
        if max_cache_bytes <= 0 or max_cache_pages < 1 or max_display_bytes <= 0:
            raise ValueError("Cache limits must be positive")
        self.path = str(Path(path).resolve(strict=True))
        self.first_source = OriginalImageSource(self.path)
        self.page_count = self.first_source.metadata.page_count
        self.max_cache_bytes, self.max_cache_pages = max_cache_bytes, max_cache_pages
        self.cache = OrderedDict()
        self._sources = {}
        self._frames = OrderedDict()
        self._lock = Lock()
        self.max_display_bytes = max_display_bytes
        self.display_bytes = 0
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
        with self._lock:
            if index in self.cache:
                self.cache.move_to_end(index)
                return self.cache[index], self._sources[index]
        source = self.first_source if index == 0 else OriginalImageSource(self.path, index)
        pixels = source.read_full()  # One page only; source has read/decode limits.
        pixels.setflags(write=False)
        self.decode_count += 1
        with self._lock:
            if pixels.nbytes <= self.max_cache_bytes:
                while self.cache and (len(self.cache) >= self.max_cache_pages or
                                      self.cache_bytes + pixels.nbytes > self.max_cache_bytes):
                    old_index, old = self.cache.popitem(last=False)
                    self.cache_bytes -= old.nbytes
                    del self._sources[old_index]
                    self._drop_frame(old_index)
                self.cache[index] = pixels
                self._sources[index] = source
                self.cache_bytes += pixels.nbytes
        return pixels, source

    def _drop_frame(self, index):
        old = self._frames.pop(index, None)
        if old is not None:
            self.display_bytes -= old.preview.image.sizeInBytes()

    def cached_frame(self, index, window):
        """No TIFF decoding or conversion. Validate identity even on a display hit."""
        self.first_source.validate_identity()
        with self._lock:
            frame = self._frames.get(index)
            if self.closed or frame is None or window != (frame.low, frame.high):
                return None
            self._frames.move_to_end(index)
            self.cache.move_to_end(index)
            return frame

    def _cache_frame(self, frame):
        with self._lock:
            index = frame.source.page_index
            size = frame.preview.image.sizeInBytes()
            if self.closed or index not in self.cache or size > self.max_display_bytes:
                return
            self._drop_frame(index)
            while self._frames and self.display_bytes + size > self.max_display_bytes:
                self._drop_frame(next(iter(self._frames)))
            self._frames[index] = frame
            self.display_bytes += size

    def frame(self, index, window=None, *, automatic=False, canceled=lambda: False):
        if not automatic:
            cached = self.cached_frame(index, window or self.default_window)
            if cached is not None:
                return None if canceled() else cached
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
        frame = StackFrame(source, preview, pixels, low, high, *self.default_window,
                           range_min, range_max, self.imagej_frames, self.imagej_slices, self.range_origin)
        self._cache_frame(frame)
        return frame

    def close(self):
        with self._lock:
            self.cache.clear()
            self._sources.clear()
            self._frames.clear()
            self.cache_bytes = self.display_bytes = 0
            self.closed = True
