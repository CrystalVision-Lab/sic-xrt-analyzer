"""Bounded original-pixel viewport rendering over the registered preview poses."""

import math
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.imaging.prepared_image import PreparedPixels

MAX_PIXELS = 4_194_304


class NativeViewport:
    """Owned by one worker; disk-backed JPEG decode and bounded output LRU."""

    def __init__(self):
        self.sources = OrderedDict()
        self.outputs = OrderedDict()
        self.group = None
        self.decodes = 0
        self.hits = 0

    def close(self):
        for source, prepared in self.sources.values():
            if prepared:
                prepared.close()
        self.sources.clear()
        self.outputs.clear()

    def render(self, group, rows, transforms, rect, density, cancelled=lambda: False):
        if group != self.group:
            self.close()
            self.group = group
        x, y, w, h = rect
        density = min(
            density, math.sqrt(MAX_PIXELS / max(1, w * h)), 4096 / w, 4096 / h
        )
        ow, oh = max(1, math.ceil(w * density)), max(1, math.ceil(h * density))
        key = (tuple(rect), density)
        if key in self.outputs:
            for source, _ in self.sources.values():
                source.validate_identity()
            self.hits += 1
            self.outputs.move_to_end(key)
            return self.outputs[key], density
        canvas = np.zeros((oh, ow, 4), np.uint8)
        priority = np.full((oh, ow), -1, np.float32)
        view = np.array(
            [[density, 0, -x * density], [0, density, -y * density], [0, 0, 1.0]]
        )
        # Large overview first; higher resolution captures replace its pixels.
        ordered = sorted(rows, key=lambda r: r["width"] * r["height"], reverse=True)
        for row in ordered:
            if cancelled():
                raise InterruptedError("원본 표시 취소")
            if row["id"] not in transforms:
                continue
            matrix = (
                np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]])
                @ np.asarray(transforms[row["id"]], float)
                @ np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
                @ np.diag(
                    [
                        row["preview_width"] / row["width"],
                        row["preview_height"] / row["height"],
                        1.0,
                    ]
                )
            )
            corners = np.array(
                [[x, y, 1], [x + w, y, 1], [x, y + h, 1], [x + w, y + h, 1.0]]
            ).T
            uv = np.linalg.inv(matrix) @ corners
            uv = uv[:2] / uv[2:]
            left, top = np.maximum(0, np.floor(uv.min(1)) - 2).astype(int)
            right, bottom = np.minimum(
                [row["width"], row["height"]], np.ceil(uv.max(1)) + 3
            ).astype(int)
            if right <= left or bottom <= top:
                continue
            preview_density = density * math.sqrt(
                abs(np.linalg.det(np.asarray(transforms[row["id"]])[:2, :2]))
            )
            if preview_density <= 1:
                continue
            left, top, right, bottom = map(int, (left, top, right, bottom))
            path = row["path"]
            if path not in self.sources:
                source = (
                    JpegImageSource(path)
                    if Path(path).suffix.lower() in (".jpg", ".jpeg")
                    else OriginalImageSource(path)
                )
                prepared = None
                required = source.metadata.width * source.metadata.height * 3
                while self.sources and (
                    len(self.sources) >= 2
                    or sum(
                        s.metadata.width * s.metadata.height * 3
                        for s, p in self.sources.values()
                        if p
                    )
                    + required
                    > 1536 * 1024**2
                ):
                    _, (_, old) = self.sources.popitem(last=False)
                    if old:
                        old.close()
                if Path(path).suffix.lower() in (".jpg", ".jpeg"):
                    prepared = PreparedPixels()
                    if not prepared.jpeg(source, cancelled, lambda *a: None):
                        raise InterruptedError("원본 준비 취소")
                    self.decodes += 1
                self.sources[path] = (source, prepared)
                while len(self.sources) > 2:
                    _, (_, old) = self.sources.popitem(last=False)
                    if old:
                        old.close()
            self.sources.move_to_end(path)
            source, prepared = self.sources[path]
            source.validate_identity()
            step = max(
                1, math.ceil(math.sqrt((right - left) * (bottom - top) / MAX_PIXELS))
            )
            if prepared:
                a = np.asarray(prepared.pixels[top:bottom:step, left:right:step]).copy()
            elif (right - left) * (bottom - top) * np.dtype(
                source.metadata.dtype
            ).itemsize <= 64 * 1024**2:
                a = source.read_region(left, top, right - left, bottom - top)[
                    ::step, ::step
                ]
            else:
                # Overview only. The native ROI path is used once the view fits its budget.
                a = source.read_sampled(2048)
                step_x, step_y = row["width"] / a.shape[1], row["height"] / a.shape[0]
                left = top = 0
                step = None
            if a.dtype != np.uint8:
                lo, hi = row.get("display_range", (0, np.iinfo(a.dtype).max))
                a = np.clip(
                    (a.astype(np.float32) - lo) * 255 / max(hi - lo, 1), 0, 255
                ).astype(np.uint8)
            if a.ndim == 2:
                a = cv2.cvtColor(a, cv2.COLOR_GRAY2RGB)
            a = a[:, :, :3]
            sampling = np.array(
                [
                    [step if step else step_x, 0, left],
                    [0, step if step else step_y, top],
                    [0, 0, 1.0],
                ]
            )
            warp = (
                np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
                @ view
                @ matrix
                @ sampling
                @ np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]])
            )
            # One original capture per output pixel: no averaging of shifted defects.
            rgba = cv2.cvtColor(a, cv2.COLOR_RGB2RGBA)
            native_density = density * math.sqrt(abs(np.linalg.det(matrix[:2, :2])))
            method = cv2.INTER_NEAREST if native_density >= 1 else cv2.INTER_LINEAR
            rendered = cv2.warpPerspective(rgba, warp, (ow, oh), flags=method)
            valid = rendered[:, :, 3] > 0
            # Prefer interiors within one capture; details supersede overview layers.
            yy, xx = np.indices(a.shape[:2], dtype=np.float32)
            weight = np.minimum.reduce(
                [xx + 1, yy + 1, a.shape[1] - xx, a.shape[0] - yy]
            )
            weight /= max(a.shape[:2])
            weight = cv2.warpPerspective(weight, warp, (ow, oh))
            score = weight + 2 * ordered.index(row)
            choose = valid & (score > priority)
            canvas[choose] = rendered[choose]
            priority[choose] = score[choose]
            source.validate_identity()
        if cancelled():
            raise InterruptedError("원본 표시 취소")
        self.outputs[key] = canvas
        while sum(a.nbytes for a in self.outputs.values()) > 64 * 1024**2:
            self.outputs.popitem(last=False)
        return canvas, density
