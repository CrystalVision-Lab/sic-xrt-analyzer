"""OriginalImageSource ROI reads only, preserving original pixel/page mapping."""

import math
import time
from dataclasses import dataclass

import numpy as np
import tifffile

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource, SourceError

RAW_BUDGET = 64 * 1024**2
SCRATCH_BUDGET = 16 * 1024**2
MAX_PAGES = 4096


def integers(values, name):
    if any(type(v) is not int for v in values):
        raise ValueError(name + " must contain integers")


def plan(source, roi, first, last, step=1, xy_step=1):
    integers([*roi, first, last, step, xy_step], "Volume selection")
    source.validate_region(*roi)
    m = source.metadata
    if m.format != "TIFF" or m.channels != 1 or m.dtype != "uint16":
        raise SourceError("UNSUPPORTED_VOLUME", "3D 입력은 uint16 단일 채널 TIFF입니다")
    if not 0 <= first <= last < m.page_count or step < 1 or not 1 <= xy_step <= 64:
        raise ValueError("원본 Page Range / sampling step 오류")
    pages = tuple(range(first, last + 1, step))
    if len(pages) > MAX_PAGES:
        raise ValueError("최대 4096 선택 페이지입니다")
    _x, _y, w, h = roi
    if w * 2 > SCRATCH_BUDGET:
        raise ValueError("ROI row exceeds bounded scratch budget")
    shape = (len(pages), math.ceil(h / xy_step), math.ceil(w / xy_step))
    size = math.prod(shape) * 2
    if size > RAW_BUDGET:
        raise ValueError(
            f"Volume {size / 1024**2:.2f} MiB > 64 MiB: ROI/페이지를 줄이거나 명시적 샘플링을 지정하세요"
        )
    return {
        "roi": list(roi),
        "page_indices": list(pages),
        "xy_step": xy_step,
        "shape": list(shape),
        "raw_bytes": size,
        "original_shape": [m.page_count, m.height, m.width],
        "page_range": [first, last, step],
        "axis_order": "K_Y_X",
        "pixel_mapping": "x=roi.x+ix*xy_step;y=roi.y+iy*xy_step;k=page_indices[ik]",
    }


@dataclass(frozen=True)
class Volume:
    pixels: np.ndarray
    selection: dict
    source_identity: object
    byte_order: str
    seconds: float

    def original(self, k, y, x):
        integers([k, y, x], "Volume cursor")
        if any(v < 0 or v >= n for v, n in zip((k, y, x), self.pixels.shape)):
            raise ValueError("Volume cursor outside selected grid")
        r = self.selection["roi"]
        s = self.selection["xy_step"]
        return (
            r[0] + x * s,
            r[1] + y * s,
            self.selection["page_indices"][k],
            int(self.pixels[k, y, x]),
        )


def extract(
    source, selection, *, cancelled=lambda: False, progress=lambda *_: None, timeout=120
):
    started = time.monotonic()

    def check():
        if cancelled():
            raise InterruptedError("3D Volume 추출 취소")
        if time.monotonic() - started > timeout:
            raise TimeoutError(
                "Volume 120초 정책 시간 초과: ROI/페이지를 줄이고 재시도하세요"
            )
        source.validate_identity()

    check()
    r = selection["roi"]
    pages = selection["page_indices"]
    expected = plan(source, r, *selection["page_range"], selection["xy_step"])
    if expected != selection:
        raise ValueError("Volume selection mapping differs")
    with tifffile.TiffFile(source.path) as tif:
        byte_order = tif.byteorder
    output = np.empty(selection["shape"], dtype=np.uint16)
    x, y, w, h = r
    s = selection["xy_step"]
    rows = max(1, min(128, SCRATCH_BUDGET // (w * 2), source.max_read_bytes // (w * 2)))
    rows = max(s, (rows // s) * s)
    if w * rows * 2 > min(SCRATCH_BUDGET, source.max_read_bytes):
        rows = 1
    for ik, k in enumerate(pages):
        check()
        reader = OriginalImageSource(
            source.path,
            k,
            max_read_bytes=source.max_read_bytes,
            max_decode_bytes=source.max_decode_bytes,
        )
        if reader.metadata != source.metadata:
            raise ValueError("TIFF page metadata changed")
        # For tall ROIs, copy one bounded stripe. Sample grid always starts at original ROI origin.
        if rows == 1:
            for iy in range(output.shape[1]):
                check()
                a = reader.read_region(x, y + iy * s, w, 1)
                output[ik, iy] = a[0, ::s]
        else:
            for dy in range(0, h, rows):
                check()
                a = reader.read_region(x, y + dy, w, min(rows, h - dy))
                oy = dy // s
                sample = a[::s, ::s]
                output[ik, oy : oy + sample.shape[0]] = sample
        progress(ik + 1, len(pages), "원본 ROI 페이지 읽기")
    check()
    output.setflags(write=False)
    return Volume(
        output, selection, source.identity, byte_order, time.monotonic() - started
    )


def physical_calibration(source_record, page_count):
    """Consume explicit pre-existing verified source calibration; never infer from TIFF tags."""
    c = source_record.calibration if source_record else None
    if (
        not c
        or c.calibration_status.value != "VERIFIED"
        or c.spatial_axis_type not in ("SPATIAL_Z", "DEPTH")
    ):
        return None
    if (
        c.unit not in ("um", "mm")
        or not c.calibration_source
        or c.orientation not in ("X_RIGHT_Y_DOWN_Z_FORWARD", "X_RIGHT_Y_DOWN_Z_REVERSE")
        or not c.pixel_spacing_x
        or not c.pixel_spacing_y
        or not c.spacing_z
        or sorted(c.acquisition_order) != list(range(page_count))
    ):
        return None
    depths = [None] * page_count
    sign = -1 if c.orientation.endswith("REVERSE") else 1
    for rank, k in enumerate(c.acquisition_order):
        depths[k] = sign * rank * c.spacing_z
    return {
        "status": "VERIFIED",
        "unit": c.unit,
        "source": c.calibration_source,
        "axis_type": c.spatial_axis_type,
        "orientation": c.orientation,
        "pixel_spacing": [c.pixel_spacing_x, c.pixel_spacing_y],
        "page_depths": depths,
    }


def world_mapping(volume, calibration=None):
    r = volume.selection["roi"]
    pages = volume.selection["page_indices"]
    step = volume.selection["xy_step"]
    ny, nx = volume.pixels.shape[1:]
    centre = [r[0] + (nx - 1) * step / 2, r[1] + (ny - 1) * step / 2]
    if calibration:
        sx, sy = calibration["pixel_spacing"]
        depths = np.asarray(calibration["page_depths"])[pages]
        span = max((r[2] - 1) * sx, (r[3] - 1) * sy, float(np.ptp(depths)), 1e-12)
        scale = 300 / span
        zs = (depths - (depths[0] + depths[-1]) / 2) * scale
        return {
            "centre": centre,
            "sx": sx * scale,
            "sy": sy * scale,
            "zs": zs.tolist(),
            "mode": "PHYSICAL",
            "unit": calibration["unit"],
        }
    scale = 300 / max(r[2], r[3])
    span = max(1, pages[-1] - pages[0])
    return {
        "centre": centre,
        "sx": scale,
        "sy": scale,
        "zs": [(k - (pages[0] + pages[-1]) / 2) * 160 / span for k in pages],
        "mode": "INDEXED",
        "unit": "px / Page Index",
    }


def world_point(volume, mapping, x, y, page):
    pages = volume.selection["page_indices"]
    if page not in pages:
        raise ValueError("Track page not sampled in current volume")
    return [
        (x - mapping["centre"][0]) * mapping["sx"],
        -(y - mapping["centre"][1]) * mapping["sy"],
        mapping["zs"][pages.index(page)],
    ]
