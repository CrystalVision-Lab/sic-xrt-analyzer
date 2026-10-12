"""Read-only JPEG session, disk native cache, bounded viewport warps and LRU."""

import time
from collections import OrderedDict

import cv2
import numpy as np
from PySide6.QtGui import QImage

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.prepared_image import PreparedPixels
from sic_xrt_analyzer.results.sources import verify_content_hash

from .engine import (
    PREVIEW_EDGE,
    check,
    inverse_transform,
    pixel_mapping,
    transform_points,
)


class ComparisonSession:
    def __init__(self, before, after, cancelled=lambda: False):
        self.sources = []
        self.caches = []
        self.previews = []
        self.records = []
        self.frames = OrderedDict()
        self.decode_count = 0
        self.overlay_key = None
        self.overlay_project = None
        self.overlay_rows = []
        started = time.perf_counter()
        try:
            for record in (before, after):
                check(cancelled)
                if record.acquisition_metadata.get("format") != "JPEG":
                    raise ValueError("정합은 JPG 전용입니다")
                verified = verify_content_hash(record, cancelled=cancelled)
                source = JpegImageSource(verified.source_reference)
                native = PreparedPixels()
                self.caches.append(native)
                if not native.jpeg(source, cancelled, lambda *a: None):
                    raise InterruptedError("준비 취소됨")
                object.__setattr__(source, "prepared", native)
                self.sources.append(source)
                self.records.append(verified)
                self.decode_count += 1
                self.previews.append(source.read_sampled(PREVIEW_EDGE))
                self.decode_count += 1
            if self.records[0].content_hash.value == self.records[1].content_hash.value:
                raise ValueError("동일한 JPG 내용입니다")
            check(cancelled)
            self.prepare_ms = (time.perf_counter() - started) * 1000
        except Exception:
            self.close()
            raise

    def __del__(self):
        self.close()

    def validate(self):
        for source in self.sources:
            source.validate_identity()

    def close(self):
        for cache in self.caches:
            cache.close()
        self.sources = []
        self.caches = []
        self.previews = []
        self.frames.clear()

    def overlays(self, project, before_id, after_id, frame, width, height, cancelled):
        key = (id(project), before_id, after_id)
        if self.overlay_project is not project or self.overlay_key != key:
            rows = []

            def add(side, points, kind):
                if not points:
                    return
                xy = np.asarray(points, float)
                lo = xy.min(0)
                hi = xy.max(0)
                rows.append(
                    (side, [list(p) for p in points], kind, lo, hi)
                )

            for side, identifier in (("before", before_id), ("after", after_id)):
                run = next(
                    (
                        r.run_id
                        for r in reversed(project.analysis_runs)
                        if r.source_id == identifier
                    ),
                    None,
                )
                for observation in project.observations:
                    if observation.run_id == run and observation.x is not None:
                        add(
                            side,
                            [(observation.x, observation.y)],
                            observation.assigned_class or "unknown",
                        )
                for g in project.geometries:
                    check(cancelled)
                    if g.source_id != identifier or g.page_index != 0:
                        continue
                    if g.nodes:
                        nodes = {n.node_id: (n.x, n.y) for n in g.nodes}
                        for edge in g.edges:
                            add(
                                side,
                                edge.points
                                or (nodes[edge.start_node], nodes[edge.end_node]),
                                g.kind.value,
                            )
                    elif g.points:
                        points = g.points
                        if g.kind.value == "POLYGON":
                            points = (*points, points[0])
                        add(side, points, g.kind.value)
                    elif g.bbox:
                        x, y, w, h = g.bbox
                        if g.kind.value == "ELLIPSE":
                            points = [
                                (
                                    x + w / 2 + w / 2 * np.cos(t),
                                    y + h / 2 + h / 2 * np.sin(t),
                                )
                                for t in np.linspace(0, 2 * np.pi, 33)
                            ]
                        else:
                            points = [
                                (x, y),
                                (x + w, y),
                                (x + w, y + h),
                                (x, y + h),
                                (x, y),
                            ]
                        add(side, points, g.kind.value)
            check(cancelled)
            self.overlay_rows = rows
            self.overlay_key = key
            self.overlay_project = project
        out = []
        for side, points, kind, lo, hi in self.overlay_rows:
            check(cancelled)
            m = np.array(frame["mapping"][0 if side == "before" else 1])
            corners = (
                np.array([lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]]) @ m[:2, :2].T
                + m[:2, 2]
            )
            ll, hh = corners.min(0), corners.max(0)
            if (
                hh[0] >= -5
                and hh[1] >= -5
                and ll[0] < width + 5
                and ll[1] < height + 5
                and len(points) <= 4096
            ):
                out.append({"side": side, "points": points, "type": kind})
        return out

    def render(self, centre, zoom, width, height, matrix=None, cancelled=lambda: False):
        self.validate()
        check(cancelled)
        width, height = int(width), int(height)
        if not 1 <= width <= 3840 or not 1 <= height <= 2160 or not 0.005 <= zoom <= 8:
            raise ValueError("비교 viewport 예산 초과")
        key = (
            tuple(centre),
            zoom,
            width,
            height,
            tuple(np.asarray(matrix).ravel()) if matrix is not None else None,
        )
        if key in self.frames:
            result = self.frames.pop(key)
            self.frames[key] = result
            return {**result, "cache_hit": True}
        ts = time.perf_counter()
        view = np.array(
            [
                [zoom, 0, width / 2 - centre[0] * zoom],
                [0, zoom, height / 2 - centre[1] * zoom],
                [0, 0, 1.0],
            ]
        )
        images = []
        masks = []
        mappings = []
        levels = []
        for i, source in enumerate(self.sources):
            check(cancelled)
            mapping = view @ (
                np.asarray(matrix) if i == 0 and matrix is not None else np.eye(3)
            )
            mappings.append(mapping.tolist())
            corners = transform_points(
                inverse_transform(mapping),
                [[0, 0], [width, 0], [width, height], [0, height]],
            )
            lo = np.maximum(0, np.floor(corners.min(0) - 2)).astype(int)
            hi = np.minimum(
                [source.metadata.width, source.metadata.height],
                np.ceil(corners.max(0) + 2),
            ).astype(int)
            rw, rh = hi - lo
            if rw <= 0 or rh <= 0:
                images.append(np.zeros((height, width, 3), np.uint8))
                masks.append(np.zeros((height, width), np.uint8))
                levels.append("outside")
                continue
            if rw * rh * 3 <= 24 * 1024**2 and zoom >= 0.3:
                data = source.read_region(int(lo[0]), int(lo[1]), int(rw), int(rh))
                origin = np.eye(3)
                origin[:2, 2] = lo
                warp = mapping @ origin
                levels.append("original_crop")
            else:
                data = self.previews[i]
                warp = mapping @ pixel_mapping(
                    data.shape[1],
                    data.shape[0],
                    source.metadata.width,
                    source.metadata.height,
                )
                levels.append("preview")
            images.append(
                cv2.warpAffine(
                    data,
                    warp[:2],
                    (width, height),
                    flags=cv2.INTER_NEAREST if zoom >= 1 else cv2.INTER_LINEAR,
                )
            )
            masks.append(
                cv2.warpAffine(
                    np.ones(data.shape[:2], np.uint8),
                    warp[:2],
                    (width, height),
                    flags=cv2.INTER_NEAREST,
                )
            )
        check(cancelled)
        valid = (masks[0] > 0) & (masks[1] > 0)
        difference = cv2.absdiff(images[0], images[1])
        difference[~valid] = 0
        rgba = np.dstack((images[0], masks[0] * 255))

        def qimage(rgb):
            h, w, c = rgb.shape
            return QImage(
                rgb.data,
                w,
                h,
                rgb.strides[0],
                QImage.Format_RGBA8888 if c == 4 else QImage.Format_RGB888,
            ).copy()

        result = {
            "before": qimage(rgba),
            "after": qimage(images[1]),
            "difference": qimage(difference),
            "mapping": mappings,
            "levels": levels,
            "render_ms": (time.perf_counter() - ts) * 1000,
            "cache_hit": False,
        }
        self.frames[key] = result
        # At most 3 viewports, additionally <=96MiB total output. Native source remains disk-backed.
        while (
            len(self.frames) > 3
            or sum(
                sum(r[k].sizeInBytes() for k in ("before", "after", "difference"))
                for r in self.frames.values()
            )
            > 96 * 1024**2
        ):
            self.frames.popitem(last=False)
        self.validate()
        return result
