"""Imported ROI overlay state scoped to the currently opened image."""
from PySide6.QtCore import QObject, Signal

from sic_xrt_analyzer.imaging.imagej_roi import MAX_POINTS, MAX_ROIS, load_rois

from .latest_reader import LatestReader


class RoiManager(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.records = []
        self.hidden = set()
        self.selected = ''
        self.busy = False
        self.errors = []

    def load(self, paths, frame):
        self.busy, self.errors = True, []
        self.reader.submit(lambda: load_rois(paths, frame.source.metadata,
                                            frames=frame.imagej_frames or 0, slices=frame.imagej_slices or 0))
        self.changed.emit()

    def _ready(self, result, error):
        self.busy = False
        if error:
            self.errors = [error]
        else:
            records, self.errors = result
            existing = {r.id: r for r in self.records}
            existing.update((r.id, r) for r in records)
            if len(existing) > MAX_ROIS or sum(sum(len(p) for p in r.paths) for r in existing.values()) > MAX_POINTS:
                self.errors.append('ROI 목록 개수/좌표 한도 초과: 기존 목록을 유지했습니다')
            else:
                self.records = list(existing.values())
                if records:
                    self.selected = records[0].id
        self.changed.emit()

    def view(self, frame):
        meta = frame.source.metadata if frame else None
        result = []
        for roi in self.records:
            x, y, w, h = roi.bbox
            active = bool(meta and (roi.page_index is None or roi.page_index == frame.source.page_index)
                          and x + w <= meta.width and y + h <= meta.height)
            result.append({'id': roi.id, 'name': roi.name, 'kind': roi.kind,
                           'paths': [[[x, y] for x, y in path] for path in roi.paths],
                           'color': roi.color, 'bbox': list(roi.bbox), 'page': roi.page_index + 1 if roi.page_index is not None else 0,
                           'visible': roi.id not in self.hidden, 'active': active, 'selected': self.selected == roi.id,
                           'pointCount': sum(len(p) for p in roi.paths)})
        return result

    def invalidate_pending(self):
        self.reader.invalidate()
        self.busy = False

    def clear(self):
        self.invalidate_pending()
        self.records.clear()
        self.hidden.clear()
        self.selected = ''
        self.errors = []
        self.changed.emit()

    def shutdown(self):
        self.reader.shutdown()
