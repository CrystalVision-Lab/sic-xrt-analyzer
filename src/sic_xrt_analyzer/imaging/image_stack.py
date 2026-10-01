"""Bounded 2D display alongside the existing original TIFF stack contract."""
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

from .display_pyramid import DisplayPyramid
from .original_source import (
    OriginalImageSource,
    OriginalMetadata,
    SourceError,
    SourceIdentity,
)
from .prepared_image import PreparedPixels, warm_tiff
from .tiff_stack import (
    StackFrame,
    TiffStack,
    auto_window,
    imagej_window,
    render_samples,
)


def image_array(image):
    """Owned, tightly packed RGB bytes; Qt row padding never becomes a pixel."""
    image = image.convertToFormat(QImage.Format_RGB888)
    array = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    result = array[:, :image.width() * 3].reshape(image.height(), image.width(), 3).copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True, init=False)
class JpegImageSource:
    path: str
    page_index: int
    metadata: OriginalMetadata
    identity: SourceIdentity
    max_read_bytes: int = 128 * 1024**2
    prepared: object = None

    def __init__(self, path):
        canonical = str(Path(path).resolve(strict=True))
        stat = Path(canonical).stat()
        reader = QImageReader(canonical)
        if not reader.canRead() or bytes(reader.format()).lower() not in (b'jpeg', b'jpg'):
            raise SourceError("UNSUPPORTED_FORMAT", "JPEG 형식을 읽을 수 없습니다. 파일 형식 또는 손상을 확인하세요")
        size = reader.size()
        if size.width() <= 0 or size.height() <= 0 or not reader.supportsOption(QImageIOHandler.ScaledSize):
            raise SourceError("UNSUPPORTED_FORMAT", "JPEG 크기 또는 축소 디코더를 확인하세요")
        meta = OriginalMetadata(size.width(), size.height(), 'uint8', 8, 3, stat.st_size, stat.st_mtime_ns, 1, 'JPEG')
        for key, value in {'path': canonical, 'page_index': 0, 'metadata': meta,
                           'identity': SourceIdentity(canonical, stat.st_size, stat.st_mtime_ns, 0, meta.width, meta.height)}.items():
            object.__setattr__(self, key, value)
        self.validate_identity()

    validate_identity = OriginalImageSource.validate_identity
    validate_region = OriginalImageSource.validate_region

    def _reader(self):
        self.validate_identity()
        reader = QImageReader(self.path)
        # Encoded pixel coordinates are also the coordinates in imported ImageJ ROIs.
        reader.setAutoTransform(False)
        return reader

    def _decode(self, reader):
        image = reader.read()
        if image.isNull():
            raise SourceError("SOURCE_READ_FAILED", "JPEG 읽기 실패: " + reader.errorString())
        self.validate_identity()
        return image_array(image)

    def read_sampled(self, max_edge=2048):
        if type(max_edge) is not int or not 1 <= max_edge <= 4096:
            raise SourceError('INVALID_INPUT', 'Preview edge must be between 1 and 4096')
        reader = self._reader()
        edge = min(max_edge, max(self.metadata.width, self.metadata.height))
        reader.setScaledSize(QSize(self.metadata.width, self.metadata.height).scaled(QSize(edge, edge), Qt.KeepAspectRatio))
        return self._decode(reader)

    def read_region(self, x, y, width, height):
        self.validate_region(x, y, width, height)
        if width * height * 4 > self.max_read_bytes:
            raise SourceError("READ_LIMIT_EXCEEDED", "Requested JPEG region exceeds the read budget")
        if self.prepared is not None:
            return self.prepared.region(self, x, y, width, height)
        reader = self._reader()
        if not reader.supportsOption(QImageIOHandler.ClipRect):
            raise SourceError("UNSUPPORTED_FORMAT", "JPEG 부분 읽기 디코더가 없습니다")
        reader.setClipRect(QRect(x, y, width, height))
        pixels = self._decode(reader)
        if pixels.shape[:2] != (height, width):
            raise SourceError("SOURCE_READ_FAILED", "JPEG 부분 읽기 크기가 일치하지 않습니다")
        return pixels

    def read_full(self):
        return self.read_region(0, 0, self.metadata.width, self.metadata.height)


class SampledImageStack:
    """One resident display grid; exact samples remain available via bounded read_region."""
    page_count = 1
    browse = None
    max_cache_pages = 1
    max_cache_bytes = 32 * 1024**2
    max_display_bytes = 32 * 1024**2

    def __init__(self, source):
        self.first_source, self.path = source, source.path
        self.closed = False
        self.samples = None
        self._frame = None
        self.default_window = None
        self.initial_window = None
        self.invert = False
        self.native_ready = False
        self.retain_prepared = False
        if source.metadata.format == 'TIFF':
            with tifffile.TiffFile(source.path) as tif:
                self.initial_window = imagej_window(tif.imagej_metadata or {})
                self.invert = tif.pages[0].photometric == tifffile.PHOTOMETRIC.MINISWHITE

    def prepare_native(self, canceled=lambda: False, progress=lambda *args: None):
        if self.native_ready:
            return True
        source = self.first_source
        if source.metadata.format == 'JPEG':
            # Small JPEG already has its complete native grid in frame.pixels.
            if max(source.metadata.width, source.metadata.height) <= 2048:
                self.native_ready = True
                return True
            cache = PreparedPixels()
            if not cache.jpeg(source, canceled, progress):
                return False
            object.__setattr__(source, 'prepared', cache)
            # Use the same decoded grid for preview and exact pixels.
            step = max(1, math.ceil(max(source.metadata.width, source.metadata.height) / 2048))
            self.samples = cache.pixels[::step, ::step].copy()
            self.samples.setflags(write=False)
        elif not warm_tiff(source, canceled, progress):
            return False
        pyramid = DisplayPyramid(source, source.prepared.pixels if isinstance(source, JpegImageSource) else None)
        object.__setattr__(source, 'display_pyramid', pyramid)
        pyramid.invert = self.invert
        try:
            if not pyramid.prepare(canceled, progress):
                pyramid.close()
                return False
        except Exception:
            pyramid.close()
            raise
        self.native_ready = True
        return True

    def frame(self, index, window=None, *, automatic=False, canceled=lambda: False):
        if self.closed or index != 0:
            raise ValueError("Image is closed or page is out of range")
        self.first_source.validate_identity()
        if self.samples is None:
            meta = self.first_source.metadata
            edge = min(2048, math.isqrt(self.max_cache_bytes // (meta.channels * np.dtype(meta.dtype).itemsize)))
            self.samples = self.first_source.read_sampled(edge)
        if canceled():
            return None
        if self.default_window is None:
            self.default_window = self.initial_window or auto_window(self.samples)
        low, high = auto_window(self.samples) if automatic else (window or self.default_window)
        preview = render_samples(self.samples, self.first_source, low, high, self.invert)
        dtype = self.samples.dtype
        if dtype.kind in 'ui':
            info = np.iinfo(dtype)
            minimum, maximum = float(info.min), float(info.max)
        elif dtype == np.bool_:
            minimum, maximum = 0.0, 1.0
        else:
            finite = self.samples[np.isfinite(self.samples)]
            minimum, maximum = float(finite.min()), float(finite.max())
            if minimum >= maximum:
                maximum = minimum + 1
        raw = self.samples if self.samples.shape[:2] == (self.first_source.metadata.height, self.first_source.metadata.width) else None
        self._frame = StackFrame(self.first_source, preview, raw, low, high, *self.default_window,
                                 min(minimum, low), max(maximum, high), None, None,
                                 'ImageJ' if self.initial_window else '표시 샘플 자동 범위')
        self.first_source.validate_identity()
        return None if canceled() else self._frame

    def cached_frame(self, index, window):
        self.first_source.validate_identity()
        return self._frame if index == 0 and self._frame and window == (self._frame.low, self._frame.high) else None

    def browse_frame(self, *args, **kwargs):
        return None

    def close(self):
        self.closed = True
        self.samples = self._frame = None
        if not self.retain_prepared:
            pyramid = getattr(self.first_source, 'display_pyramid', None)
            if pyramid is not None:
                pyramid.close()
        if not self.retain_prepared and isinstance(self.first_source, JpegImageSource) and self.first_source.prepared is not None:
            self.first_source.prepared.close()


def open_stack(path, *, browse_enabled=False):
    """Dispatch by actual signature, preserving TIFF analysis source semantics."""
    with Path(path).open('rb') as file:
        signature = file.read(4)
    if signature[:2] == b'\xff\xd8':
        return SampledImageStack(JpegImageSource(path))
    if signature not in (b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+'):
        raise SourceError('UNSUPPORTED_FORMAT', '지원하지 않거나 손상된 이미지입니다. TIFF 또는 JPG/JPEG 파일을 선택하세요')
    stack = TiffStack(path, browse_enabled=browse_enabled)
    meta = stack.first_source.metadata
    size = meta.width * meta.height * meta.channels * np.dtype(meta.dtype).itemsize
    if meta.page_count == 1 and size > stack.first_source.max_read_bytes:
        source = stack.first_source
        stack.close()
        return SampledImageStack(source)
    return stack
