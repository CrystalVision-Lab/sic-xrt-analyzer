"""Bounded original-pixel viewport rendering over the registered preview poses."""

import math
from collections import OrderedDict
from pathlib import Path
from threading import RLock

import cv2
import numpy as np

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from .pixel_cache import PixelCache

MAX_PIXELS = 4_194_304


class NativeViewport:
    """Owned by one worker; disk-backed JPEG decode and bounded output LRU."""

    def __init__(self):
        self.lock = RLock()
        self.sources = OrderedDict()
        self.cache_root = None
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

    def prepare(self, group, rows, transforms, cancelled=lambda: False, progress=lambda *a: None):
        with self.lock:
            if group != self.group:
                self.close()
                self.group = group
            for i, row in enumerate(rows):
                if cancelled():
                    raise InterruptedError("원본 준비 취소")
                if row["id"] in transforms:
                    self._source(row, cancelled)
                progress(i+1, len(rows), "원본 해상도·확대 단계 준비")

    def _source(self, row, cancelled):
        path = row["path"]
        if path not in self.sources:
            source = JpegImageSource(path) if Path(path).suffix.lower() in (".jpg", ".jpeg") else OriginalImageSource(path)
            prepared = PixelCache(source, self.cache_root, cancelled)
            self.decodes += int(prepared.created)
            self.sources[path] = (source, prepared)
        source, prepared = self.sources[path]
        source.validate_identity()
        return source, prepared

    def render(self, group, rows, transforms, rect, density, cancelled=lambda: False):
        with self.lock:
            return self._render(group, rows, transforms, rect, density, cancelled)

    def renderTiles(self, group, rows, transforms, rect, density, cancelled=lambda: False):
        """Reuse fixed map tiles across overlapping pans at discrete zoom levels."""
        with self.lock:
            x, y, w, h = rect
            requested = min(density, math.sqrt(MAX_PIXELS / max(1, w*h)))
            level = 2 ** math.ceil(math.log2(max(requested, 1e-9)))
            # A discrete level avoids rebuilding tiles on every wheel tick.
            left, top = math.floor(x*level), math.floor(y*level)
            right, bottom = math.ceil((x+w)*level), math.ceil((y+h)*level)
            canvas = np.zeros((bottom-top, right-left, 4), np.uint8)
            for ty in range(top//256, (bottom-1)//256+1):
                for tx in range(left//256, (right-1)//256+1):
                    if cancelled():
                        raise InterruptedError("원본 표시 취소")
                    tile, _ = self._render(group, rows, transforms,
                        [tx*256/level, ty*256/level, 256/level, 256/level], level, cancelled)
                    l, t = max(left,tx*256), max(top,ty*256)
                    r, b = min(right,(tx+1)*256), min(bottom,(ty+1)*256)
                    canvas[t-top:b-top,l-left:r-left] = tile[t-ty*256:b-ty*256,l-tx*256:r-tx*256]
            return canvas, [left/level, top/level, (right-left)/level, (bottom-top)/level]

    def _render(self, group, rows, transforms, rect, density, cancelled):
        if group != self.group:
            self.close()
            self.group = group
        x, y, w, h = rect
        density = min(
            density, math.sqrt(MAX_PIXELS / max(1, w * h)), 4096 / w, 4096 / h
        )
        ow, oh = max(1, math.ceil(w * density)), max(1, math.ceil(h * density))
        signature = tuple((r["path"], str(transforms.get(r["id"])), tuple(r.get("display_range", (0,255)))) for r in rows)
        key = (signature, tuple(rect), density)
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
            source, prepared = self._source(row, cancelled)
            native_density = density * math.sqrt(abs(np.linalg.det(matrix[:2, :2])))
            a, left, top, step = prepared.region(left, top, right, bottom, native_density)
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
                    [step, 0, left],
                    [0, step, top],
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
