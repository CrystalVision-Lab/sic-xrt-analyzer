"""Bounded display artifacts derived only from observed source pixels/masks."""

import cv2
import numpy as np
from PySide6.QtGui import QImage

MAX_LAYER_BYTES = 16 * 1024**2


def layer_vertices(sections, seed, pages):
    chunks = []
    count = 0
    scale = 350 / max(128, pages)
    for s in sections:
        mask = s.mask()
        padded = np.pad(mask, ((0, 0), (1, 1))).astype(np.int8)
        yy, starts = np.nonzero(np.diff(padded, axis=1) == 1)
        _, ends = np.nonzero(np.diff(padded, axis=1) == -1)
        # Six vertices per horizontal run, not a separate cube per source pixel.
        count += len(yy) * 6 * 3 * 4
        if count > MAX_LAYER_BYTES:
            raise ValueError("적층 표시 메모리 한도를 넘었습니다")
        x0, x1 = starts + s.x - 0.5, ends + s.x - 0.5
        y0, y1 = yy + s.y - 0.5, yy + s.y + 0.5
        z = np.full(len(yy), s.page, float)
        a = np.stack(
            [
                np.column_stack([x0, y0, z]),
                np.column_stack([x1, y0, z]),
                np.column_stack([x1, y1, z]),
                np.column_stack([x0, y0, z]),
                np.column_stack([x1, y1, z]),
                np.column_stack([x0, y1, z]),
            ],
            axis=1,
        ).reshape(-1, 3)
        a -= np.asarray(seed)
        a[:, 1] *= -1
        chunks.append((a * scale).astype(np.float32))
    return np.concatenate(chunks) if chunks else np.empty((0, 3), np.float32)


def frame_images(raw, section, accepted):
    lo, hi = np.percentile(raw[::8, ::8], [1, 99])
    gray = np.clip(
        (raw.astype(np.float32) - lo) * 255 / max(hi - lo, 1), 0, 255
    ).astype(np.uint8)
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    if section:
        part = color[
            section.y : section.y + section.height,
            section.x : section.x + section.width,
        ]
        mask = section.mask()
        tint = np.array([55, 225, 207] if accepted else [255, 184, 69])
        part[mask] = (part[mask] * 0.35 + tint * 0.65).astype(np.uint8)
        contours, _ = cv2.findContours(
            mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(part, contours, -1, tuple(map(int, tint)), 1)
        left, top = max(0, section.x - 40), max(0, section.y - 40)
        right, bottom = (
            min(raw.shape[1], section.x + section.width + 40),
            min(raw.shape[0], section.y + section.height + 40),
        )
    else:
        left = top = 0
        bottom, right = raw.shape
    crop = color[top:bottom, left:right].copy()

    def image(a):
        factor = min(1.0, 1000 / max(a.shape[:2]))
        if factor < 1:
            a = cv2.resize(a, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        return QImage(
            a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format_RGB888
        ).copy()

    if section:
        cv2.rectangle(
            color,
            (section.x - 4, section.y - 4),
            (section.x + section.width + 4, section.y + section.height + 4),
            (55, 225, 207) if accepted else (255, 184, 69),
            max(2, raw.shape[1] // 600),
        )
    return image(color), image(crop), [left, top, right - left, bottom - top]
