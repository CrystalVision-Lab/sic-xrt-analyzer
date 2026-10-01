"""Decode the first TIFF page into an 8-bit image for the QML viewer."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtGui import QImage

MAX_PREVIEW_EDGE = 4096


@dataclass(frozen=True)
class TiffPreview:
    image: QImage
    width: int
    height: int
    bit_depth: int
    page_count: int
    sampled: bool


def _to_byte_range(pixels: np.ndarray) -> np.ndarray:
    """Map non-8-bit values to a display range without modifying source data."""
    if pixels.dtype == np.uint8:
        return np.ascontiguousarray(pixels)
    if pixels.dtype == np.bool_:
        return np.ascontiguousarray(pixels.astype(np.uint8) * 255)

    values = pixels.astype(np.float64)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("표시할 수 있는 유효한 픽셀이 없습니다")
    sample = values[finite]
    if sample.size > 1_000_000:
        sample = sample[:: max(1, sample.size // 1_000_000)]
    low, high = np.percentile(sample, (1, 99))
    if high <= low:
        return np.full(pixels.shape, 255 if high > 0 else 0, dtype=np.uint8)
    normalized = np.clip((values - low) * (255 / (high - low)), 0, 255)
    normalized[~finite] = 0
    return np.ascontiguousarray(normalized.astype(np.uint8))


def load_tiff_preview(path: str | Path) -> TiffPreview:
    """Load page one of a grayscale, RGB, or RGBA TIFF for display."""
    with tifffile.TiffFile(path) as tiff:
        if not tiff.pages:
            raise ValueError("이미지 페이지가 없습니다")
        page = tiff.pages[0]
        photometric = page.photometric
        bit_depth = page.bitspersample
        pixels = page.asarray()
        page_count = len(tiff.pages)

    if pixels.dtype.kind not in "buif":
        raise ValueError("지원하지 않는 픽셀 형식입니다")
    if pixels.ndim == 2:
        if photometric not in (
            tifffile.PHOTOMETRIC.MINISBLACK,
            tifffile.PHOTOMETRIC.MINISWHITE,
        ):
            raise ValueError("지원하지 않는 회색조 색상 형식입니다")
        image_format = QImage.Format_Grayscale8
        height, width = pixels.shape
    elif pixels.ndim == 3 and pixels.shape[2] in (3, 4):
        if photometric != tifffile.PHOTOMETRIC.RGB:
            raise ValueError("지원하지 않는 컬러 색상 형식입니다")
        image_format = (
            QImage.Format_RGB888 if pixels.shape[2] == 3 else QImage.Format_RGBA8888
        )
        height, width = pixels.shape[:2]
    else:
        raise ValueError("2차원 회색조 또는 RGB/RGBA TIFF만 지원합니다")
    if not width or not height:
        raise ValueError("이미지 크기가 올바르지 않습니다")

    step = max(1, (max(width, height) + MAX_PREVIEW_EDGE - 1) // MAX_PREVIEW_EDGE)
    display = _to_byte_range(pixels[::step, ::step])
    if photometric == tifffile.PHOTOMETRIC.MINISWHITE:
        display = np.ascontiguousarray(255 - display)
    preview_height, preview_width = display.shape[:2]
    image = QImage(
        display.data, preview_width, preview_height, display.strides[0], image_format
    ).copy()
    if image.isNull():
        raise ValueError("이미지 미리보기를 만들 수 없습니다")
    return TiffPreview(
        image=image,
        width=width,
        height=height,
        bit_depth=int(bit_depth),
        page_count=page_count,
        sampled=step > 1,
    )
