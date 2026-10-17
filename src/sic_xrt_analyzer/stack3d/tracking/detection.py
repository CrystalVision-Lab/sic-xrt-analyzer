"""Deterministic per-page detection; never depends on tracking state.

Each page is normalized on its own (fixed-kernel median background, MAD noise),
so gain changes and crop size do not change thresholds in z units.
"""

import math

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.filters import apply_hysteresis_threshold
from skimage.morphology import skeletonize

from sic_xrt_analyzer.analysis.skeleton_graph import prune_spurs, trace_skeleton

from .model import Detection, TrackSettings

EIGHT = np.ones((3, 3), bool)


def _mad_scale(a, floor):
    centred = a - np.median(a)
    return centred, max(1.4826 * float(np.median(np.abs(centred))), floor)


def median_background(page, kernel):
    """Median background with a fixed kernel in source pixels (block-reduced)."""
    g = np.asarray(page, np.float32)
    f = max(1, kernel // 8)
    h, w = g.shape
    ph, pw = -h % f, -w % f
    padded = np.pad(g, ((0, ph), (0, pw)), mode="reflect" if min(h, w) > 1 else "edge")
    blocks = padded.reshape(padded.shape[0] // f, f, padded.shape[1] // f, f).mean((1, 3))
    small = ndi.median_filter(blocks, size=max(3, kernel // f | 1), mode="reflect")
    if f > 1:
        small = ndi.zoom(small, f, order=1, mode="nearest", grid_mode=True)
    return small[:h, :w]


def normalize_page(page, settings):
    """Return (residual, z): signed residual and smoothed noise-normalized z map."""
    g = np.asarray(page)
    if g.ndim != 2 or g.dtype.kind not in "uif" or not np.isfinite(g).all():
        raise ValueError("숫자형 흑백 페이지가 필요합니다")
    g = g.astype(np.float32)
    residual = g - median_background(g, settings.background_px)
    floor = 1e-3 * abs(float(np.median(g))) + 1e-6
    smooth = ndi.gaussian_filter(residual, settings.smooth_sigma)
    smooth, sigma = _mad_scale(smooth, floor)
    return residual, smooth / sigma


def _line_kernels(length, count):
    kernels = []
    half = (length - 1) / 2
    for i in range(count):
        theta = math.pi * i / count
        k = np.zeros((length, length), np.float32)
        for t in np.linspace(-half, half, length * 2):
            x, y = half + t * math.cos(theta), half + t * math.sin(theta)
            k[round(y), round(x)] = 1
        kernels.append(k / k.sum())
    return kernels


def _line_z(z, settings):
    best = np.full(z.shape, -np.inf, np.float32)
    for kernel in _line_kernels(settings.line_length_px | 1, settings.line_orientations):
        r = cv2.filter2D(z, cv2.CV_32F, kernel, borderType=cv2.BORDER_REFLECT)
        r, sigma = _mad_scale(r, 1e-6)
        np.maximum(best, r / sigma, out=best)
    return best


def _blob_z(residual_signed, settings):
    s = settings.blob_sigma
    r = -ndi.gaussian_laplace(residual_signed, s) * s * s
    r, sigma = _mad_scale(r, 1e-6)
    return r / sigma


def _isotropy(signed, sigma):
    """|lambda_min| / |lambda_max| of a positive peak's Hessian; 0 for lines."""
    hxx = ndi.gaussian_filter(signed, sigma, order=(0, 2))
    hyy = ndi.gaussian_filter(signed, sigma, order=(2, 0))
    hxy = ndi.gaussian_filter(signed, sigma, order=(1, 1))
    tr, det = hxx + hyy, hxx * hyy - hxy * hxy
    disc = np.sqrt(np.maximum(tr * tr / 4 - det, 0))
    l1, l2 = tr / 2 - disc, tr / 2 + disc  # l1 <= l2; a peak has both < 0
    return np.where(l2 < 0, np.abs(l2) / np.maximum(np.abs(l1), 1e-12), 0.0)


def _orientation(points):
    if len(points) < 3:
        return 0.0, 1.0
    cov = np.cov(points.T.astype(float))
    w, v = np.linalg.eigh(cov)
    theta = math.atan2(v[1, 1], v[0, 1]) % math.pi
    return theta, max(4 * math.sqrt(max(w[1], 0.0)), 1.0)


def _elongation(points):
    if len(points) < 3:
        return 1.0
    w = np.linalg.eigvalsh(np.cov(points.T.astype(float)))
    return math.sqrt(max(w[1], 1e-6) / max(w[0], 0.08))


def _paths(skeleton):
    """Split a skeleton at junctions into ordered (x, y) point paths."""
    if not skeleton.any():
        return []
    try:
        topology = trace_skeleton(skeleton)
        paths = [np.asarray(p, np.int32) for _, _, p in topology.paths]
        if paths or skeleton.sum() < 2:
            return paths
    except ValueError:
        pass
    degree = ndi.convolve(skeleton.astype(np.uint8), np.ones((3, 3), np.uint8),
                          mode="constant") - skeleton
    parts, _n = ndi.label(skeleton & ~(skeleton & (degree >= 3)), EIGHT)
    out = []
    for i, sl in enumerate(ndi.find_objects(parts), 1):
        yy, xx = np.nonzero(parts[sl] == i)
        out.append(np.c_[xx + sl[1].start, yy + sl[0].start].astype(np.int32))
    return out


def _prune(skeleton, length, border):
    """Drop side spurs caused by a wide mask; protect true image borders."""
    for _ in range(3):
        try:
            topology = trace_skeleton(skeleton)
        except ValueError:
            return skeleton
        pruned, removed = prune_spurs(skeleton, topology, length, boundary_edges=border)
        if not removed:
            break
        skeleton = skeletonize(pruned)
    return skeleton


def _join_collinear(paths, settings):
    """Union collinear pieces split by junctions/spurs (e.g. a line through a crossing)."""
    ends = []
    for p in paths:
        reach = min(len(p) - 1, 6)
        a = p[0] - p[reach] if reach else np.zeros(2)
        b = p[-1] - p[-1 - reach] if reach else np.zeros(2)
        ends.append(((p[0], a), (p[-1], b)))
    parent = list(range(len(paths)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cos_min = math.cos(math.radians(settings.join_angle_deg))
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            for pi, ti in ends[i]:
                for pj, tj in ends[j]:
                    gap = pj - pi
                    dist = float(np.hypot(*gap))
                    if dist > settings.join_gap_px:
                        continue
                    ni, nj = np.linalg.norm(ti), np.linalg.norm(tj)
                    if ni < 2 or nj < 2:
                        continue
                    # Tangents point outward; collinear continuation is anti-parallel.
                    if float(ti @ tj) / (ni * nj) > -cos_min:
                        continue
                    if dist > 1.5 and float(ti @ gap) / (ni * dist) < cos_min * 0.9:
                        continue
                    parent[find(i)] = find(j)
    groups = {}
    for i in range(len(paths)):
        groups.setdefault(find(i), []).append(paths[i])
    return [np.unique(np.concatenate(g), axis=0) for g in groups.values()]


def _detect_polarity(residual, z, settings, polarity, page, origin, start):
    sign = -1.0 if polarity == "DARK" else 1.0
    zp = z * sign
    support = zp > settings.support_z
    mask = apply_hysteresis_threshold(zp, settings.low_z, settings.high_z)
    lz = _line_z(zp, settings)
    mask |= apply_hysteresis_threshold(lz, settings.line_low_z, settings.line_high_z) & support
    bz = _blob_z(residual * sign, settings)
    iso = _isotropy(residual * sign, settings.blob_sigma)
    mask |= apply_hysteresis_threshold(bz, settings.blob_low_z, settings.blob_high_z) & support
    # Trim halos of strong structures so close neighbours stay separate.
    mask &= zp >= settings.relative_floor * ndi.maximum_filter(zp, size=7)
    labels, count = ndi.label(mask, EIGHT)
    if count > 20000:
        raise ValueError("페이지 검출 수가 처리 예산을 초과했습니다")
    ox, oy = origin
    raw = []
    distance = ndi.distance_transform_edt(mask)
    for index, sl in enumerate(ndi.find_objects(labels), 1):
        if sl is None:
            continue
        comp = labels[sl] == index
        area = int(comp.sum())
        if area < settings.min_area_px:
            continue
        yy, xx = np.nonzero(comp)
        pts = np.c_[xx + sl[1].start, yy + sl[0].start]
        extent = max(np.ptp(xx), np.ptp(yy)) + 1
        if extent <= settings.blob_max_extent_px and _elongation(pts) < 2.5:
            raw.append(("BLOB", pts))
            continue
        # Point defects touching a structure: isotropic LoG peaks that are
        # thicker than the structure's typical half-width.
        full = skeletonize(comp)
        half = float(np.percentile(distance[sl][full], 30)) if full.any() else 0.0
        local_d = ndi.maximum_filter(distance[sl] * comp, size=3)
        peaks = comp & (bz[sl] >= settings.blob_high_z) & (local_d >= half + 0.75) & (
            local_d >= settings.blob_core_px) & (iso[sl] >= 0.6) & (
            bz[sl] == ndi.maximum_filter(bz[sl], size=5))
        removed = np.zeros_like(comp)
        yy_, xx_ = np.ogrid[:comp.shape[0], :comp.shape[1]]
        for py, px in zip(*np.nonzero(peaks)):
            radius = local_d[py, px]
            disk = (yy_ - py) ** 2 + (xx_ - px) ** 2
            if removed[py, px]:
                continue
            cy, cx = np.nonzero(comp & (disk <= radius * radius))
            raw.append(("BLOB", np.c_[cx + sl[1].start, cy + sl[0].start]))
            removed |= disk <= (radius + 2) ** 2
        skeleton = full & ~removed
        if skeleton.any():
            border = (sl[1].start == 0, sl[1].stop == mask.shape[1],
                      sl[0].start == 0, sl[0].stop == mask.shape[0])
            skeleton = _prune(skeleton, max(settings.min_segment_px, 2 * half + 4), border)
        pieces = [p for p in _paths(skeleton) if len(p) >= 2]
        for p in _join_collinear(pieces, settings):
            p = p + [sl[1].start, sl[0].start]
            if len(p) < settings.min_segment_px:
                continue
            raw.append(("SEGMENT", p))
    out = []
    for kind, pts in sorted(raw, key=lambda r: (r[1][:, 1].min(), r[1][:, 0].min(), r[0])):
        at = (pts[:, 1], pts[:, 0])
        if kind == "BLOB":
            contrast = float(np.max(zp[at]))
            if contrast < settings.low_z or (
                contrast < settings.high_z and np.max(bz[at]) < settings.blob_high_z
            ):
                continue
        else:
            contrast = float(np.mean(zp[at]))
            if contrast < settings.low_z and np.mean(lz[at]) < settings.line_high_z:
                continue
        theta, length = _orientation(pts)
        if kind == "BLOB":
            theta, length = 0.0, 2 * math.sqrt(len(pts) / math.pi)
        else:
            length = max(length, float(len(pts)))
        shifted = (pts + [ox, oy]).astype(np.int32)
        shifted.setflags(write=False)
        out.append(Detection(
            f"p{page}-d{start + len(out)}", page, kind,
            (float(shifted[:, 0].mean()), float(shifted[:, 1].mean())),
            shifted, theta, length, contrast, polarity,
        ))
    return out


def detect_page(page_pixels, page, settings=None, origin=(0, 0)):
    """Detect BLOB/SEGMENT observations on one page. Coordinates include origin."""
    settings = settings or TrackSettings()
    residual, z = normalize_page(page_pixels, settings)
    polarities = ("DARK", "BRIGHT") if settings.polarity == "BOTH" else (settings.polarity,)
    out = []
    for polarity in polarities:
        out += _detect_polarity(residual, z, settings, polarity, page, origin, len(out))
    return out
