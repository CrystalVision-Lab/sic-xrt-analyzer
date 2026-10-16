"""Source-pixel review areas; navigation never validates a model prediction."""

import hashlib
import json
import math
from collections import Counter, OrderedDict
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot

from sic_xrt_analyzer.analysis.feedback import atomic_json


def make_regions(rows, width, height, edge=512, include_empty=False):
    """Disjoint ownership, with visual padding handled by the viewer, not identity."""
    groups = {}
    for row in rows:
        x, y = row["x"], row["y"]
        if not (
            math.isfinite(x) and math.isfinite(y) and 0 <= x < width and 0 <= y < height
        ):
            continue
        key = (int(y) // edge, int(x) // edge)
        groups.setdefault(key, []).append(row)
    if include_empty:
        for y in range(math.ceil(height / edge)):
            for x in range(math.ceil(width / edge)):
                groups.setdefault((y, x), [])
    return [
        {
            "id": f"{edge}:{y}:{x}",
            "rect": [
                x * edge,
                y * edge,
                min(edge, width - x * edge),
                min(edge, height - y * edge),
            ],
            "rows": points,
            "counts": dict(Counter(p["type"] for p in points)),
            "priority": sum(p.get("low_score", False) for p in points),
            "label": f"열 {x + 1} · 행 {y + 1}",
        }
        for (y, x), points in sorted(groups.items())
    ]


class RegionReview(QObject):
    changed = Signal()
    focusRequested = Signal(float, float, float, float)

    def __init__(self, research):
        super().__init__(research)
        self.research = research
        self.enabled = False  # Activated when the result review panel is opened.
        self.mode = "AREA"
        self.edge = 512
        self.current = ""
        self.session = ""
        self.groups = []
        self.full_groups = {}
        self.checked = set()
        self.records = {}
        self.opened = set()
        self.error = ""
        self.records_invalid = False
        settings = research.bridge._settings
        base = (
            Path(settings.fileName()).parent
            if settings.format() == QSettings.IniFormat
            else Path(
                QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            )
        )
        self.root = base / "area-review"
        self.path = None
        self.signature = None
        from .latest_reader import LatestReader

        self.thumbnails = LatestReader(self)
        self.thumbnails.ready.connect(self._thumbnails_ready)
        self.thumb_key = None
        self.thumb_revision = 0
        self.thumbnail_error = ""
        self.thumb_urls = {}
        self.thumb_cache = OrderedDict()
        self.presentation = "DISTRIBUTION"
        self.compare_page = 0
        self.last_selected_id = ""
        research.changed.connect(self.refresh)

    def refresh(self):
        r = self.research
        identity = str(r.result_identity or "")
        source = r.display_result.request.source if r.display_result else None
        extent = r.display_result.source_identity if r.display_result else None
        if identity != self.session:
            self.session = identity
            self.current = ""
            self.compare_page = 0
            self.checked.clear()
            self.opened.clear()
            self.records = {}
            self.error = ""
            self.records_invalid = False
            self.signature = None
            self.thumb_key = None
            self.thumb_urls = {}
            self.thumbnail_error = ""
            self.thumb_cache.clear()
            self.thumbnails.invalidate()
            research_provider = self.research.bridge.provider
            research_provider.region_images = {}
            self.path = None
            if identity:
                self.path = self.root / (
                    hashlib.sha256(identity.encode()).hexdigest() + ".json"
                )
                try:
                    if self.path.exists():
                        value = json.loads(self.path.read_text(encoding="utf-8"))
                        if not isinstance(value, dict) or any(
                            v not in ("CONFIRMED", "HOLD", "NEEDS_CHANGE", "UNREVIEWED")
                            for v in value.values()
                        ):
                            raise ValueError("Invalid review records")
                        self.records = value
                except (OSError, ValueError):
                    self.records_invalid = True
                    self.error = "검토 기록을 읽지 못했습니다. 기존 파일은 보존됩니다."
        signature = (
            identity,
            self.edge,
            self.mode,
            r.kind_filter,
            r.low_only,
            r.query,
            len(r.rows),
            source.identity if source else None,
        )
        if self.signature != signature:
            self.compare_page = 0
            self.signature = signature
            self.full_groups = (
                {
                    g["id"]: g["rows"]
                    for g in make_regions(
                        r.rows, extent.width, extent.height, self.edge
                    )
                }
                if extent
                else {}
            )
            self.groups = (
                make_regions(
                    r.filtered,
                    extent.width,
                    extent.height,
                    self.edge,
                    self.mode == "SCAN",
                )
                if extent
                else []
            )
            if self.mode == "PRIORITY":
                self.groups.sort(key=lambda g: (-g["priority"], g["id"]))
            elif self.mode == "SAMPLE":
                # Deterministic spatial spread. No group is silently dropped.
                self.groups.sort(
                    key=lambda g: hashlib.sha256(
                        (identity + g["id"]).encode()
                    ).hexdigest()
                )
            if self.current not in {g["id"] for g in self.groups}:
                self.current = self.groups[0]["id"] if self.groups else ""
        selected = next((p for p in r.rows if p["id"] == r.selected_id), None)
        if self.presentation == "COMPARE" and r.selected_id != self.last_selected_id:
            self._align_comparison_selection()
        self.last_selected_id = r.selected_id
        if selected:
            key = f"{self.edge}:{int(selected['y']) // self.edge}:{int(selected['x']) // self.edge}"
            if key in {g["id"] for g in self.groups}:
                self.current = key
                self.opened.add(key)
        self._prepare_thumbnails()
        self.changed.emit()

    def _prepare_thumbnails(self):
        if self.research.display_result is None:
            return
        group = next((g for g in self.groups if g["id"] == self.current), None)
        comparing = self.presentation == "COMPARE"
        rows = (
            self.research.filtered[
                self.compare_page * 24 : (self.compare_page + 1) * 24
            ]
            if comparing
            else (group or {}).get("rows", [])[:512]
        )
        key = (
            self.session,
            self.presentation,
            self.compare_page if comparing else self.current,
            tuple(p["id"] for p in rows),
        )
        if not rows or key == self.thumb_key or not self.research.pixels_available:
            return
        self.thumb_key = key
        self.thumbnail_error = ""
        self.thumb_urls = {}
        if key in self.thumb_cache:
            self._thumbnails_ready((key, self.thumb_cache[key]), "")
            return
        source = self.research.display_result.request.source
        rect = group["rect"] if group else None

        def read():
            import numpy as np
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage

            # Comparison reads bounded equal-scale patches, never a bounding box
            # spanning unrelated candidates across a multi-gigapixel source.
            if comparing:
                images = {}
                for row in rows:
                    w, h = (
                        min(128, source.metadata.width),
                        min(128, source.metadata.height),
                    )
                    x = max(0, min(round(row["x"]) - 64, source.metadata.width - w))
                    y = max(0, min(round(row["y"]) - 64, source.metadata.height - h))
                    pixels = np.ascontiguousarray(source.read_region(x, y, w, h))
                    if (
                        pixels.dtype == np.uint8
                        and pixels.ndim == 3
                        and pixels.shape[2] == 3
                    ):
                        images[row["id"]] = QImage(
                            pixels.data, w, h, pixels.strides[0], QImage.Format_RGB888
                        ).copy()
                source.validate_identity()
                return key, images
            x, y, w, h = rect
            left, top = max(0, x - 64), max(0, y - 64)
            right, bottom = (
                min(source.metadata.width, x + w + 64),
                min(source.metadata.height, y + h + 64),
            )
            pixels = source.read_region(left, top, right - left, bottom - top)
            if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
                return key, {}
            images = {}
            for row in rows:
                cx, cy = int(row["x"]) - left, int(row["y"]) - top
                patch = np.ascontiguousarray(
                    pixels[max(0, cy - 64) : cy + 64, max(0, cx - 64) : cx + 64]
                )
                ph, pw = patch.shape[:2]
                if ph and pw:
                    images[row["id"]] = (
                        QImage(
                            patch.data, pw, ph, patch.strides[0], QImage.Format_RGB888
                        )
                        .copy()
                        .scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
            source.validate_identity()
            return key, images

        self.thumbnails.submit(read)

    def _thumbnails_ready(self, value, error):
        if error:
            self.thumbnail_error = "미리보기를 읽지 못했습니다. 원본 연결을 확인하세요."
            self.changed.emit()
            return
        if not value or value[0] != self.thumb_key:
            return
        key, images = value
        self.thumb_cache[key] = images
        self.thumb_cache.move_to_end(key)
        while len(self.thumb_cache) > 8:
            self.thumb_cache.popitem(last=False)
        self.research.bridge.provider.region_images = images
        self.thumb_revision += 1
        self.thumb_urls = {
            ident: f"image://tiff/region-{ident}?{self.thumb_revision}"
            for ident in images
        }
        self.changed.emit()

    def shutdown(self):
        self.thumbnails.shutdown()
        self.thumb_cache.clear()

    @Slot(bool)
    def activate(self, value):
        self.enabled = value
        self.changed.emit()

    @Slot(str)
    def setPresentation(self, value):
        if value not in ("DISTRIBUTION", "AREA", "COMPARE", "IMAGE"):
            return
        self.presentation = value
        if value == "COMPARE":
            self._align_comparison_selection()
        self._prepare_thumbnails()
        self.changed.emit()

    def _align_comparison_selection(self):
        index = next(
            (
                i
                for i, p in enumerate(self.research.filtered)
                if p["id"] == self.research.selected_id
            ),
            -1,
        )
        if index >= 0:
            self.compare_page = index // 24

    @Slot(int)
    def setComparePage(self, page):
        self.compare_page = max(
            0, min(page, max(0, (len(self.research.filtered) - 1) // 24))
        )
        self._prepare_thumbnails()
        self.changed.emit()

    @Slot(str)
    def selectArea(self, ident):
        reviews = getattr(self.research.bridge, "review_controller", None)
        if reviews and reviews.pending:
            self.error = "작성 중인 검수를 먼저 기록하거나 취소하세요."
            self.changed.emit()
            return
        group = next((g for g in self.groups if g["id"] == ident), None)
        if not group:
            return
        self.current = ident
        self.opened.add(ident)
        if group["rows"]:
            self.research.selectCandidate(group["rows"][0]["id"])
        else:
            self.research._clear_selection()
            self.research.changed.emit()
            self.focusRequested.emit(*group["rect"])
        self.changed.emit()

    @Slot()
    def nextUnreviewed(self):
        index = next(
            (i for i, g in enumerate(self.groups) if g["id"] == self.current), -1
        )
        ordered = self.groups[index + 1 :] + self.groups[: index + 1]
        group = next(
            (
                g
                for g in ordered
                if any(self.records.get(p["id"]) != "CONFIRMED" for p in g["rows"])
            ),
            None,
        )
        if group:
            self.selectArea(group["id"])

    @Slot(str)
    def setMode(self, mode):
        if mode in ("AREA", "PRIORITY", "SAMPLE", "SCAN"):
            self.mode = mode
            self.refresh()

    @Slot(int)
    def setEdge(self, edge):
        if edge in (256, 512, 1024):
            self.edge = edge
            self.refresh()

    @Slot(int)
    def stepArea(self, delta):
        if not self.groups:
            return
        index = next(
            (i for i, g in enumerate(self.groups) if g["id"] == self.current), -1
        )
        group = self.groups[max(0, min(len(self.groups) - 1, index + delta))]
        self.selectArea(group["id"])

    @Slot(int)
    def stepCandidate(self, delta):
        rows = self.state["rows"]
        if rows:
            index = next(
                (i for i, p in enumerate(rows) if p["id"] == self.research.selected_id),
                -1,
            )
            self.research.selectCandidate(
                rows[max(0, min(len(rows) - 1, index + delta))]["id"]
            )

    @Slot(bool)
    def checkArea(self, value):
        group = next((g for g in self.groups if g["id"] == self.current), {})
        ids = {p["id"] for p in group.get("rows", [])}
        self.checked.update(ids) if value else self.checked.difference_update(ids)
        self.changed.emit()

    @Slot(str, bool)
    def check(self, ident, value):
        if ident in {p["id"] for p in self.research.rows}:
            self.checked.add(ident) if value else self.checked.discard(ident)
            self.changed.emit()

    @Slot()
    def clearChecked(self):
        self.checked.clear()
        self.changed.emit()

    @Slot(str)
    def mark(self, status):
        if (
            status not in ("CONFIRMED", "HOLD", "NEEDS_CHANGE", "UNREVIEWED")
            or not self.path
            or self.records_invalid
        ):
            return
        ids = self.checked or (
            {self.research.selected_id} if self.research.selected_id else set()
        )
        updated = dict(self.records)
        updated.update({ident: status for ident in ids})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, updated)
            self.records = updated
            self.checked.clear()
            self.error = ""
        except OSError:
            self.error = "검토 기록 저장 실패"
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        group = next((g for g in self.groups if g["id"] == self.current), {})
        rows = group.get("rows", [])
        return {
            "thumbnailError": self.thumbnail_error,
            "presentation": self.presentation,
            "session": self.session,
            "current": self.current,
            "areaReviewed": sum(self.records.get(p["id"]) == "CONFIRMED" for p in rows),
            "mapCells": [
                {
                    "id": g["id"],
                    "rect": g["rect"],
                    "count": len(g["rows"]),
                    "label": g["label"],
                    "counts": g["counts"],
                }
                for g in self.groups
            ],
            "comparePage": self.compare_page,
            "comparePages": max(1, (len(self.research.filtered) + 23) // 24),
            "compareRows": [
                {
                    **p,
                    "thumbnail": self.thumb_urls.get(p["id"], ""),
                    "checked": p["id"] in self.checked,
                    "review": self.records.get(p["id"], "UNREVIEWED"),
                }
                for p in self.research.filtered[
                    self.compare_page * 24 : (self.compare_page + 1) * 24
                ]
            ],
            "enabled": self.enabled,
            "mode": self.mode,
            "edge": self.edge,
            "key": self.session + ":" + self.current,
            "rect": group.get("rect", []),
            "label": group.get("label", "영역을 선택하세요"),
            "index": next(
                (i for i, g in enumerate(self.groups) if g["id"] == self.current), -1
            ),
            "candidateIndex": next(
                (i for i, p in enumerate(rows) if p["id"] == self.research.selected_id),
                -1,
            ),
            "total": len(self.groups),
            "counts": group.get("counts", {}),
            "allChecked": bool(rows) and all(p["id"] in self.checked for p in rows),
            "opened": len(self.opened),
            "checked": sorted(self.checked),
            "error": self.error,
            "reviewed": sum(v == "CONFIRMED" for v in self.records.values()),
            "coverage": [
                {
                    "rect": g["rect"],
                    "checked": bool(g["rows"])
                    and all(
                        self.records.get(p["id"]) == "CONFIRMED"
                        for p in self.full_groups.get(g["id"], [])
                    ),
                }
                for g in self.groups
                if g["id"] in self.opened
            ],
            "rows": [
                {
                    **p,
                    "thumbnail": self.thumb_urls.get(p["id"], ""),
                    "thumbnailOmitted": i >= 512,
                    "checked": p["id"] in self.checked,
                    "review": self.records.get(p["id"], "UNREVIEWED"),
                }
                for i, p in enumerate(rows)
            ],
        }
