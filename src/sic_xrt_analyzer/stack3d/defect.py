"""Seed-connected dark observations. Display masks/meshes never replace source pixels."""

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

MAX_PACKED = 128 * 1024**2
MAX_DENSE = 32 * 1024**2
MAX_FACES = 400_000
MAX_EDGE = 4096


@dataclass(frozen=True)
class Section:
    page: int
    x: int
    y: int
    width: int
    height: int
    bits: np.ndarray
    count: int

    def mask(self):
        return (
            np.unpackbits(self.bits, count=self.width * self.height)
            .reshape(self.height, self.width)
            .astype(bool)
        )


@dataclass(frozen=True)
class DefectMesh:
    vertices: np.ndarray
    normals: np.ndarray
    faces: np.ndarray
    sections: tuple
    seed: tuple
    bounds: tuple
    xy_step: int
    voxels: int
    source_identity: object
    thresholds: tuple
    stops: tuple = ()


def dark_mask(pixels, sensitivity=1.0, min_contrast=0.0):
    """Robust local dark contrast; no closing/dilation adds foreground voxels."""
    if not 0.4 <= sensitivity <= 2.5:
        raise ValueError("분할 감도 범위 오류")
    a = np.asarray(pixels)
    if a.ndim != 2 or a.dtype.kind not in "uif" or not np.isfinite(a).all():
        raise ValueError("숫자형 흑백 TIFF가 필요합니다")
    g = a.astype(np.float32)
    # Remove a robust linear illumination ramp before morphology; reflected
    # image borders must not become false dark bands.
    sy = max(1, g.shape[0] // 128)
    sx = max(1, g.shape[1] // 128)
    sampled = g[::sy, ::sx]
    dx = float(np.median(np.diff(sampled, axis=1))) / sx
    dy = float(np.median(np.diff(sampled, axis=0))) / sy
    g -= np.arange(g.shape[1], dtype=np.float32)[None, :] * dx
    g -= np.arange(g.shape[0], dtype=np.float32)[:, None] * dy
    kernel = min(65, max(17, min(g.shape) // 4 | 1))
    background = ndi.grey_closing(ndi.grey_opening(g, size=kernel), size=kernel)
    noise = g - ndi.gaussian_filter(g, 1)
    sigma = float(np.median(np.abs(noise - np.median(noise))) * 1.4826)
    span = float(np.percentile(g, 99) - np.percentile(g, 10))
    floor = max(float(np.max(np.abs(g))) * 0.0008, span * 0.025, 1e-5)
    contrast = max(max(5 * sigma, floor) / sensitivity, min_contrast)
    # Black top-hat removes smooth illumination without thresholding the whole background.
    level = contrast
    mask = (background - g) > contrast
    return mask, level


def _section(page, x, y, mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    cropped = mask[top:bottom, left:right]
    bits = np.packbits(cropped)
    bits.setflags(write=False)
    return Section(
        page, x + left, y + top, right - left, bottom - top, bits, int(cropped.sum())
    )


def _trace(
    source,
    seed,
    *,
    sensitivity=1.0,
    cancelled=lambda: False,
    progress=lambda *a: None,
    read_page=None,
):
    """Track strict 26-neighbour pixel contact in adjacent pages, both directions.

    No nearest-component jumps or interpolation across empty pages. Branches in
    the observed connected component are retained; touching defects may merge.
    """
    from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

    if source.metadata.page_count < 2 or source.metadata.channels != 1:
        raise ValueError("여러 페이지 흑백 TIFF를 열어주세요")
    x, y, page = map(int, seed)
    source.validate_region(x, y, 1, 1)
    if not 0 <= page < source.metadata.page_count:
        raise ValueError("페이지 범위 오류")
    identity = source.identity
    sections = {}
    thresholds = {}
    stops = []
    baseline = [0.0]
    done = 0

    def check():
        if cancelled():
            raise InterruptedError("결함 추적 취소")
        source.validate_identity()

    def read(k, previous=None):
        check()
        if previous is None:
            cx, cy = x, y
            edge = 128
        else:
            cx = previous.x + previous.width // 2
            cy = previous.y + previous.height // 2
            edge = max(128, max(previous.width, previous.height) + 64)
        reader = source
        raw = (
            read_page(k)
            if read_page
            else OriginalImageSource(source.path, k).read_full()
        )
        if (reader.metadata.width, reader.metadata.height, reader.metadata.dtype) != (
            source.metadata.width,
            source.metadata.height,
            source.metadata.dtype,
        ):
            raise ValueError("페이지별 원본 크기·dtype가 다릅니다")
        while True:
            check()
            w = min(edge, reader.metadata.width)
            h = min(edge, reader.metadata.height)
            ox = max(0, min(reader.metadata.width - w, cx - w // 2))
            oy = max(0, min(reader.metadata.height - h, cy - h // 2))
            if w * h > MAX_EDGE**2:
                raise ValueError("연결 영역이 읽기 예산보다 큽니다")
            pixels = raw[oy : oy + h, ox : ox + w]
            mask, threshold = dark_mask(pixels, sensitivity, baseline[0] * 0.5)
            labels, n = ndi.label(mask, np.ones((3, 3), bool))
            if previous is None:
                sy, sx = y - oy, x - ox
                label = int(labels[sy, sx])
                if not label:
                    # Screen clicks can be a few source pixels off at Fit.
                    yy, xx = np.nonzero(
                        labels[max(0, sy - 4) : sy + 5, max(0, sx - 4) : sx + 5]
                    )
                    if not len(xx):
                        if edge < 512 and edge < max(
                            reader.metadata.width, reader.metadata.height
                        ):
                            edge *= 2
                            continue
                        raise ValueError("검은 결함 안쪽을 확대해 클릭하세요")
                    xx += max(0, sx - 4)
                    yy += max(0, sy - 4)
                    nearest = np.argmin((xx - sx) ** 2 + (yy - sy) ** 2)
                    label = int(labels[yy[nearest], xx[nearest]])
                selected = labels == label
            else:
                overlap = np.zeros((h, w), bool)
                pm = previous.mask()
                ax = max(ox, previous.x)
                ay = max(oy, previous.y)
                bx = min(ox + w, previous.x + previous.width)
                by = min(oy + h, previous.y + previous.height)
                if bx <= ax or by <= ay:
                    return None, threshold
                overlap[ay - oy : by - oy, ax - ox : bx - ox] = pm[
                    ay - previous.y : by - previous.y, ax - previous.x : bx - previous.x
                ]
                contact = ndi.binary_dilation(overlap, np.ones((3, 3), bool))
                connected = np.unique(labels[contact])
                connected = connected[connected > 0]
                if not len(connected):
                    return None, threshold
                lookup = np.zeros(n + 1, bool)
                lookup[connected] = True
                selected = lookup[labels]
            if int(selected.sum()) < 2:
                return None, threshold
            touches = (
                (ox > 0 and selected[:, 0].any())
                or (oy > 0 and selected[0].any())
                or (ox + w < reader.metadata.width and selected[:, -1].any())
                or (oy + h < reader.metadata.height and selected[-1].any())
            )
            if touches:
                if edge >= MAX_EDGE:
                    raise ValueError("연결 영역이 추적 범위를 초과했습니다")
                edge = min(MAX_EDGE, edge * 2)
                continue
            return _section(k, ox, oy, selected), threshold

    first, t = read(page)
    if first is None:
        raise ValueError("선택한 검은 성분이 너무 작습니다")
    sections[page] = first
    thresholds[page] = t
    baseline[0] = t
    packed = first.bits.nbytes
    for direction in [-1, 1]:
        previous = first
        for k in range(
            page + direction,
            source.metadata.page_count if direction > 0 else -1,
            direction,
        ):
            current, t = read(k, previous)
            done += 1
            progress(done, source.metadata.page_count, "앞뒤 결함 연결 확인")
            if current is None:
                stops.append((k, "NO_CONTACT"))
                break
            if current.count > max(previous.count * 4, previous.count + 256):
                stops.append((k, "AMBIGUOUS_MERGE"))
                break
            packed += current.bits.nbytes
            if packed > MAX_PACKED:
                raise ValueError("연결된 결함의 마스크 메모리 한도를 초과했습니다")
            sections[k] = current
            thresholds[k] = t
            previous = current
    check()
    ordered = tuple(sections[k] for k in sorted(sections))
    x0 = min(s.x for s in ordered)
    y0 = min(s.y for s in ordered)
    x1 = max(s.x + s.width for s in ordered)
    y1 = max(s.y + s.height for s in ordered)
    z0, z1 = ordered[0].page, ordered[-1].page
    depth = z1 - z0 + 1
    step = max(1, math.ceil(math.sqrt((x1 - x0) * (y1 - y0) * (depth + 2) / MAX_DENSE)))
    if (depth + 2) * 9 > MAX_DENSE:
        raise ValueError("연결 결함의 깊이가 표시 메모리 한도를 초과했습니다")
    while (depth + 2) * (math.ceil((y1 - y0) / step) + 2) * (
        math.ceil((x1 - x0) / step) + 2
    ) > MAX_DENSE:
        step += 1
    for _ in range(8):
        check()
        progress(done, source.metadata.page_count, "연결 결함 표면 생성")
        dense = np.zeros(
            (
                depth + 2,
                math.ceil((y1 - y0) / step) + 2,
                math.ceil((x1 - x0) / step) + 2,
            ),
            np.uint8,
        )
        for s in ordered:
            ys, xs = np.nonzero(s.mask())
            dense[
                s.page - z0 + 1,
                (ys + s.y - y0) // step + 1,
                (xs + s.x - x0) // step + 1,
            ] = 1
        vertices, faces, normals, _ = marching_cubes(
            dense, 0.5, spacing=(1.0, float(step), float(step)), allow_degenerate=False
        )
        if len(faces) <= MAX_FACES:
            break
        step *= 2
    else:
        raise ValueError("결함 표면의 삼각형 수가 표시 한도를 초과했습니다")
    vertices -= np.array([1, step, step], np.float32)
    vertices += np.array([z0, y0, x0], np.float32)
    for a in [vertices, faces, normals]:
        a.setflags(write=False)
    check()
    return DefectMesh(
        vertices,
        normals,
        faces,
        ordered,
        (x, y, page),
        (x0, y0, z0, x1, y1, z1 + 1),
        step,
        sum(s.count for s in ordered),
        identity,
        tuple(sorted(thresholds.items())),
        tuple(stops),
    )


def trace(
    source, seed, *, sensitivity=1.0, cancelled=lambda: False, progress=lambda *a: None
):
    import tifffile

    from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
    from sic_xrt_analyzer.imaging.tiff_pages import page_layout

    with tifffile.TiffFile(source.path) as tif:

        def read_page(index):
            source.validate_identity()
            if cancelled():
                raise InterruptedError("결함 추적 취소")
            page, _, virtual = page_layout(tif, index)
            if virtual:
                pixels = OriginalImageSource(source.path, index).read_full()
            else:
                if np.prod(page.shape) * np.dtype(page.dtype).itemsize > 64 * 1024**2:
                    raise ValueError("페이지 디코딩 예산을 초과했습니다")
                pixels = page.asarray(maxworkers=1)
            if (
                pixels.shape != (source.metadata.height, source.metadata.width)
                or pixels.dtype.name != source.metadata.dtype
            ):
                raise ValueError("페이지별 크기·dtype가 다릅니다")
            source.validate_identity()
            return pixels

        return _trace(
            source,
            seed,
            sensitivity=sensitivity,
            cancelled=cancelled,
            progress=progress,
            read_page=read_page,
        )
