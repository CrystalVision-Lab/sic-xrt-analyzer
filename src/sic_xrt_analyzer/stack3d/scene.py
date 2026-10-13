"""Bounded display-only RGBA slices; source Volume remains unmodified uint16."""

import math
import time
from itertools import pairwise

import numpy as np
from PySide6.QtGui import QImage

from .assets import active_points
from .volume import world_mapping, world_point

MAX_EDGE = 512
MAX_TEXTURE_BYTES = 16 * 1024**2


def rgba(samples, low, high):
    if not 0 <= low < high <= 65535:
        raise ValueError("Display window range invalid")
    h, w = samples.shape
    step = max(1, math.ceil(max(h, w) / MAX_EDGE))
    scaled = np.clip(
        (samples[::step, ::step].astype(np.float32) - low) * (255 / (high - low)),
        0,
        255,
    ).astype(np.uint8)
    a = np.empty((*scaled.shape, 4), np.uint8)
    a[:, :, :3] = scaled[:, :, None]
    a[:, :, 3] = 255
    im = QImage(
        a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format_RGBA8888
    ).copy()
    return im, step


def prepare(
    volume,
    cursor,
    window,
    tracks,
    *,
    calibration=None,
    plane_limit=12,
    cancelled=lambda: False,
):
    ts = time.perf_counter()
    k, y, x = cursor
    pixels = volume.pixels
    volume.original(k, y, x)
    if not 1 <= plane_limit <= 12:
        raise ValueError("Plane budget")
    mapping = world_mapping(volume, calibration)
    pages = volume.selection["page_indices"]
    r = volume.selection["roi"]
    indices = sorted(
        {int(i) for i in np.linspace(0, len(pages) - 1, min(plane_limit, len(pages)))}
    )
    if k not in indices:
        if len(indices) >= plane_limit:
            indices.pop(min(range(len(indices)), key=lambda i: abs(indices[i] - k)))
        indices.append(k)
        indices.sort()
    images = {}
    planes = []
    for i in indices:
        if cancelled():
            raise InterruptedError("3D display preparation cancelled")
        image, step = rgba(pixels[i], *window)
        key = f"plane-{i}"
        images[key] = image
        planes.append(
            {
                "key": key,
                "ik": i,
                "page": pages[i],
                "z": mapping["zs"][i],
                "selected": i == k,
                "display_step": step,
            }
        )
    for name, a in [
        ("xy", pixels[k]),
        ("xp", pixels[:, y, :]),
        ("yp", pixels[:, :, x]),
    ]:
        if cancelled():
            raise InterruptedError("Orthogonal display cancelled")
        images[name], _ = rgba(a, *window)
    if sum(i.sizeInBytes() for i in images.values()) > MAX_TEXTURE_BYTES:
        raise ValueError("3D texture image budget exceeded")
    markers = []
    segments = []
    skipped = 0
    for t in tracks:
        events, _ = active_points(t)
        locations = []
        for page, e in sorted(events.items()):
            g = e["geometry"]
            c = g["coordinates"]
            cx, cy = (
                c
                if g["type"] == "POINT"
                else (c[0] + (c[2] - 1) / 2, c[1] + (c[3] - 1) / 2)
            )
            if (
                page not in pages
                or not r[0] <= cx < r[0] + r[2]
                or not r[1] <= cy < r[1] + r[3]
            ):
                skipped += 1
                continue
            point = world_point(volume, mapping, cx, cy, page)
            markers.append(
                {
                    "position": point,
                    "track_id": t["track_id"],
                    "page": page,
                    "status": e["status"],
                }
            )
            locations.append((page, point, e))
        for (pa, a, ea), (pb, b, eb) in pairwise(locations):
            gap = pb - pa > 1
            count = 5 if gap else 1
            for n in range(count):
                start = n / count
                end = (n + 0.5) / count if gap else 1
                segments.extend(
                    [
                        (np.array(a) + (np.array(b) - a) * start).tolist(),
                        (np.array(a) + (np.array(b) - a) * end).tolist(),
                    ]
                )
    omitted = max(0, len(markers) - 1000)
    markers = markers[:1000]
    segments = segments[:10000]
    return {
        "images": images,
        "planes": planes,
        "markers": markers,
        "segments": segments,
        "mapping": mapping,
        "size": [float(r[2] * mapping["sx"]), float(r[3] * mapping["sy"])],
        "selected_world": world_point(volume, mapping, *volume.original(k, y, x)[:3]),
        "omitted_track_points": omitted,
        "outside_or_unsampled_track_points": skipped,
        "texture_bytes": sum(i.sizeInBytes() for i in images.values()),
        "prepare_ms": (time.perf_counter() - ts) * 1000,
    }
