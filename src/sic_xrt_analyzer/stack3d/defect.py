"""Seed-connected dark observations. Display masks/meshes never replace source pixels."""

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes
from skimage.segmentation import watershed

from .continuity import continue_line, line_shape, translated_reference

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
    observations: tuple = ()
    junction_pages: tuple = ()


def dark_mask(pixels, sensitivity=1.0, min_contrast=0.0, *, contrast_field=False):
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
    return (mask, level, background - g) if contrast_field else (mask, level)


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


def isolate_component(mask, anchor, excluded=()):
    """Split narrow contacts using distance basins; never add foreground pixels.

    A basin is an observation proposal, not proof of physical defect identity.
    Explicit negative points create competing markers in the same dark component.
    """
    ay, ax = anchor
    if not mask[ay, ax]:
        return mask & False
    labels, _ = ndi.label(mask, np.ones((3, 3), bool))
    component = labels == labels[ay, ax]
    if not excluded:
        line, resolved = continue_line(component, anchor)
        if resolved:
            return line
    distance = ndi.distance_transform_edt(component)
    # One marker per thick interior, not per local width maximum. A curved
    # line's slowly varying width must not create dozens of tiny basins.
    # Thin necks between genuinely thicker lobes still produce separate cores.
    core = component & (distance >= max(1.0, float(distance.max()) * 0.45))
    markers, _ = ndi.label(core, np.ones((3, 3), bool))
    peaks = core
    # Connect the click to its nearest interior peak without making every click
    # on a component boundary a separate, arbitrarily tiny basin.
    yy, xx = np.nonzero(peaks & component)
    if len(xx):
        nearest = np.argmin((yy - ay) ** 2 + (xx - ax) ** 2)
        chosen = int(markers[yy[nearest], xx[nearest]])
    else:
        chosen = 1
        markers[ay, ax] = chosen
    label = int(markers.max()) + 1
    for ey, ex in excluded:
        if 0 <= ey < mask.shape[0] and 0 <= ex < mask.shape[1] and component[ey, ex]:
            markers[ey, ex] = label
            label += 1
    if markers.max() <= 1:
        return component
    basins = watershed(-distance, markers, mask=component, connectivity=np.ones((3, 3)))
    return (basins == chosen) & component


def _trace(
    source,
    seed,
    *,
    sensitivity=1.0,
    cancelled=lambda: False,
    progress=lambda *a: None,
    read_page=None,
    observe=lambda *a: None,
    exclusions=None,
    anchors=None,
    skipped=(),
):
    """Follow one seeded observation; refuse ambiguous unions and growth."""
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
    observations = []
    exclusions = exclusions or {}
    anchors = anchors or {}
    skipped = set(skipped)
    for k, point in anchors.items():
        if not 0 <= k < source.metadata.page_count or len(point) != 2:
            raise ValueError("연결 지정 페이지 오류")
        source.validate_region(int(point[0]), int(point[1]), 1, 1)
    if page in skipped:
        raise ValueError("시작 페이지는 건너뛸 수 없습니다")
    last_raw = [None]

    def check():
        if cancelled():
            raise InterruptedError("결함 추적 취소")
        source.validate_identity()

    def read(k, previous=None):
        check()
        explicit = k in anchors
        seed_x, seed_y = anchors.get(k, (x, y))
        if previous is None or explicit:
            cx, cy = seed_x, seed_y
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
        last_raw[0] = raw
        while True:
            check()
            w = min(edge, reader.metadata.width)
            h = min(edge, reader.metadata.height)
            ox = max(0, min(reader.metadata.width - w, cx - w // 2))
            oy = max(0, min(reader.metadata.height - h, cy - h // 2))
            if w * h > MAX_EDGE**2:
                raise ValueError("연결 영역이 읽기 예산보다 큽니다")
            pixels = raw[oy : oy + h, ox : ox + w]
            mask, threshold, contrast = dark_mask(
                pixels, sensitivity, baseline[0], contrast_field=True
            )
            labels, n = ndi.label(mask, np.ones((3, 3), bool))
            if previous is None or explicit:
                sy, sx = int(seed_y) - oy, int(seed_x) - ox
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
                yy, xx = np.nonzero(labels == label)
                nearest = np.argmin((xx - sx) ** 2 + (yy - sy) ** 2)
                sy, sx = int(yy[nearest]), int(xx[nearest])
                if not baseline[0]:
                    baseline[0] = max(threshold, float(contrast[sy, sx]) * 0.3)
                    mask &= contrast > baseline[0]
                selected = isolate_component(
                    mask,
                    (sy, sx),
                    [(ey - oy, ex - ox) for ex, ey in exclusions.get(k, ())],
                )
            else:
                overlap = np.zeros((h, w), bool)
                pm = previous.mask()
                ax = max(ox, previous.x)
                ay = max(oy, previous.y)
                bx = min(ox + w, previous.x + previous.width)
                by = min(oy + h, previous.y + previous.height)
                if bx <= ax or by <= ay:
                    return None, threshold, "NO_CONTACT"
                overlap[ay - oy : by - oy, ax - ox : bx - ox] = pm[
                    ay - previous.y : by - previous.y, ax - previous.x : bx - previous.x
                ]
                contact = ndi.binary_dilation(overlap, np.ones((3, 3), bool))
                connected = np.unique(labels[contact])
                connected = connected[connected > 0]
                if not len(connected):
                    aligned, reason = translated_reference(overlap, labels)
                    if aligned is None:
                        return None, threshold, reason
                    overlap = aligned
                    contact = ndi.binary_dilation(overlap, np.ones((3, 3), bool))
                    connected = np.unique(labels[overlap])
                    connected = connected[connected > 0]
                # Several contacted components are a split, never a license to
                # union independent defects into a plate. Choose only a clear winner.
                counts = np.bincount(labels[overlap].ravel(), minlength=n + 1)
                ranked = sorted(connected, key=lambda j: counts[j], reverse=True)
                if len(ranked) > 1 and counts[ranked[1]] >= max(
                    2, counts[ranked[0]] * 0.45
                ):
                    return None, threshold, "AMBIGUOUS_BRANCH"
                label = int(ranked[0])
                yy, xx = np.nonzero((labels == label) & contact)
                center = np.array(
                    [
                        previous.y + previous.height / 2 - oy,
                        previous.x + previous.width / 2 - ox,
                    ]
                )
                nearest = np.argmin((yy - center[0]) ** 2 + (xx - center[1]) ** 2)
                anchor = (int(yy[nearest]), int(xx[nearest]))
                selected, resolved = continue_line(labels == label, anchor, overlap)
                if exclusions.get(k):
                    resolved = False
                if not resolved:
                    if selected is None and not exclusions.get(k):
                        return _section(k, ox, oy, labels == label), threshold, "AMBIGUOUS_BRANCH"
                    if not exclusions.get(k) and np.count_nonzero(labels == label) > max(
                        previous.count * 4, previous.count + 256
                    ):
                        return _section(k, ox, oy, labels == label), threshold, "AMBIGUOUS_MERGE"
                    selected = isolate_component(
                        mask, anchor,
                        [(ey - oy, ex - ox) for ex, ey in exclusions.get(k, ())],
                    )
            if int(selected.sum()) < 2:
                return None, threshold, "NO_CONTACT"
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
            return _section(k, ox, oy, selected), threshold, "ACCEPTED"

    first, t, _ = read(page)
    if first is None:
        raise ValueError("선택한 검은 성분이 너무 작습니다")
    if first.count > 16384 or (
        max(first.width, first.height) > 256
        and first.count / max(first.width, first.height) > 24
    ):
        raise ValueError(
            "선택 영역이 주변 구조와 연결되어 있습니다. 결함 안쪽을 다시 선택하거나 분할 감도를 조절하세요"
        )
    sections[page] = first
    observations.append((page, first, "ACCEPTED"))
    observe(page, last_raw[0], first, "ACCEPTED")
    thresholds[page] = t
    packed = first.bits.nbytes
    for direction in [1, -1]:
        previous = first
        for k in range(
            page + direction,
            source.metadata.page_count if direction > 0 else -1,
            direction,
        ):
            if k in skipped:
                stops.append((k, "USER_SKIPPED"))
                # No interpolation, synthetic section, or replacement pixel.
                observations.append((k, None, "USER_SKIPPED"))
                continue
            current, t, reason = read(k, previous)
            done += 1
            progress(done, source.metadata.page_count, "앞뒤 결함 연결 확인")
            # Natural length growth is not a merge when a thin, unbranched
            # continuation has comparable width. Do not compare every slice to
            # the often tiny initial tip of the defect.
            line_continuity = False
            if current is not None:
                old_line, old_width = line_shape(previous.mask())
                new_line, new_width = line_shape(current.mask())
                line_continuity = old_line and new_line and new_width <= max(old_width * 2.5, old_width + 4)
            if (
                current is not None
                and not line_continuity
                and k not in anchors
                and (
                    current.count > max(previous.count * 2.5, previous.count + 128)
                )
            ):
                reason = "AMBIGUOUS_MERGE"
            observations.append((k, current, reason))
            observe(k, last_raw[0], current, reason)
            if reason != "ACCEPTED":
                stops.append((k, reason))
                break
            packed += current.bits.nbytes
            if packed > MAX_PACKED:
                raise ValueError("연결된 결함의 마스크 메모리 한도를 초과했습니다")
            sections[k] = current
            thresholds[k] = t
            previous = current
    check()
    ordered = tuple(sections[k] for k in sorted(sections))
    from skimage.morphology import skeletonize

    junction_pages = []
    for section in ordered:
        skeleton = skeletonize(section.mask())
        degree = (
            ndi.convolve(
                skeleton.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant"
            )
            - skeleton
        )
        if np.count_nonzero(skeleton & (degree == 1)) > 2:
            junction_pages.append(section.page)
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
        tuple(observations),
        tuple(junction_pages),
    )


def trace(
    source,
    seed,
    *,
    sensitivity=1.0,
    cancelled=lambda: False,
    progress=lambda *a: None,
    observe=lambda *a: None,
    exclusions=None,
    anchors=None,
    skipped=(),
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
            observe=observe,
            exclusions=exclusions,
            anchors=anchors,
            skipped=skipped,
        )
