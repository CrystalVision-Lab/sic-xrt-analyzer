"""Read-only review views (filmstrip crops, kymographs) cut from original uint16 pixels.

Coordinates are original page coordinates; the volume is K x Y x X starting at
(origin, first_page) with xy_step 1. No pixel is modified or interpolated.
"""

import numpy as np

FILMSTRIP_MAX = 200


def centroid_path(result, detection_ids, pages):
    """(len(pages), 2) x, y per page: linear between detections, clamped outside."""
    known = sorted((result.detection(d).page, *result.detection(d).centroid) for d in detection_ids)
    kp = np.array([k[0] for k in known], float)
    xs = np.array([k[1] for k in known], float)
    ys = np.array([k[2] for k in known], float)
    p = np.asarray(pages, float)
    return np.stack([np.interp(p, kp, xs), np.interp(p, kp, ys)], axis=1)


def crop_size(result, detection_ids, minimum=48, maximum=96, margin=16):
    extent = 0
    for d in detection_ids:
        pts = result.detection(d).points
        extent = max(extent, int(np.ptp(pts[:, 0])) + 1, int(np.ptp(pts[:, 1])) + 1)
    return int(min(maximum, max(minimum, extent + margin)))


def crop_box(cx, cy, size, shape_yx, origin):
    """Square box (x0, y0, x1, y1) in original coords, clamped inside the volume."""
    h, w = shape_yx
    ox, oy = origin
    size = min(size, w, h)
    x0 = round(float(cx)) - size // 2
    y0 = round(float(cy)) - size // 2
    x0 = min(max(x0, ox), ox + w - size)
    y0 = min(max(y0, oy), oy + h - size)
    return x0, y0, x0 + size, y0 + size


def filmstrip(pixels, origin, first_page, result, detection_ids, size=None):
    """[(page, box, uint16 crop, bool mask)] for every page of the track span."""
    pages = sorted(result.detection(d).page for d in detection_ids)
    span = list(range(pages[0], pages[-1] + 1))[:FILMSTRIP_MAX]
    path = centroid_path(result, detection_ids, span)
    size = size or crop_size(result, detection_ids)
    by_page = {result.detection(d).page: result.detection(d) for d in detection_ids}
    ox, oy = origin
    out = []
    for p, (cx, cy) in zip(span, path):
        x0, y0, x1, y1 = crop_box(cx, cy, size, pixels.shape[1:], origin)
        crop = pixels[p - first_page, y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        mask = np.zeros(crop.shape, bool)
        d = by_page.get(p)
        if d is not None:
            px, py = d.points[:, 0] - x0, d.points[:, 1] - y0
            keep = (px >= 0) & (py >= 0) & (px < crop.shape[1]) & (py < crop.shape[0])
            mask[py[keep], px[keep]] = True
        out.append((p, (x0, y0, x1, y1), crop, mask))
    return out


def kymographs(pixels, origin, first_page, result, detection_ids, radius=40):
    """X-page and Y-page slices through the track centroid path, (K, 2R+1) each.

    Row k is volume page k. Columns outside the volume repeat the edge pixel.
    """
    k_count, h, w = pixels.shape
    pages = [first_page + k for k in range(k_count)]
    path = centroid_path(result, detection_ids, pages)
    ox, oy = origin
    offsets = np.arange(-radius, radius + 1)
    xs = np.clip(np.round(path[:, 0]).astype(int) - ox, 0, w - 1)
    ys = np.clip(np.round(path[:, 1]).astype(int) - oy, 0, h - 1)
    rows = np.arange(k_count)[:, None]
    xp = pixels[rows, ys[:, None], np.clip(xs[:, None] + offsets, 0, w - 1)]
    yp = pixels[rows, np.clip(ys[:, None] + offsets, 0, h - 1), xs[:, None]]
    return xp, yp


def outline(mask):
    """Boundary pixels of a boolean mask (4-neighbour)."""
    m = np.pad(mask, 1)
    inner = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    return mask & ~inner
