"""Imported ROI overlay and bounded editing history scoped to the open image."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from sic_xrt_analyzer.imaging.imagej_roi import (
    MAX_POINTS,
    MAX_ROIS,
    ImportedRoi,
    load_rois,
)
from sic_xrt_analyzer.imaging.roi_edit import geometry

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
        self.undo_stack, self.redo_stack = [], []
        self.vertex = -1
        self.edit_error = ''
        self.modified = set()
        self.gesture = None
        self.saved_records = None

    @property
    def dirty(self):
        return tuple(self.records) != self.saved_records if self.saved_records is not None else bool(self.modified)

    def selected_record(self, frame):
        if self.busy or frame is None:
            raise ValueError('이미지와 ROI가 준비된 뒤 편집하세요')
        record = next((r for r in self.records if r.id == self.selected), None)
        if record is None or record.id in self.hidden or (record.page_index is not None and record.page_index != frame.source.page_index):
            raise ValueError('현재 페이지의 표시된 ROI를 선택하세요')
        if len(record.paths) != 1:
            raise ValueError('복합 경로 ROI 편집은 아직 지원하지 않습니다')
        return record

    def snapshot(self):
        return tuple(self.records), frozenset(self.hidden), self.selected, frozenset(self.modified), self.vertex

    def remember(self, before):
        self.undo_stack.append(before)
        while len(self.undo_stack) > 10 or sum(sum(len(p) for r in s[0] for p in r.paths) for s in self.undo_stack) > MAX_POINTS:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def restore(self, state):
        records, hidden, self.selected, modified, self.vertex = state
        self.records, self.hidden, self.modified = list(records), set(hidden), set(modified)
        self.gesture = None
        self.edit_error = ''
        self.changed.emit()

    def history(self, redo=False):
        source, destination = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
        if not source or self.busy or self.gesture:
            return
        destination.append(self.snapshot())
        self.restore(source.pop())

    def change(self, frame, operation, *, remember=True):
        previous_vertex = self.vertex
        try:
            record = self.selected_record(frame)
            before = self.snapshot()
            updated = geometry(record, operation(record), frame.source.metadata)
            if updated == record:
                return True
            if sum(sum(len(p) for p in r.paths) for r in self.records) - len(record.paths[0]) + len(updated.paths[0]) > MAX_POINTS:
                raise ValueError('ROI 전체 좌표 수 한도 초과')
            if remember:
                self.remember(before)
            self.records = [updated if r.id == record.id else r for r in self.records]
            self.modified.add(record.id)
            self.edit_error = ''
            self.changed.emit()
            return True
        except (ValueError, IndexError, TypeError) as exc:
            self.vertex = previous_vertex
            self.edit_error = str(exc)
            self.changed.emit()
            return False

    def select_vertex(self, index, frame):
        record = self.selected_record(frame)
        if type(index) is not int or not 0 <= index < len(record.paths[0]):
            raise ValueError('점 번호가 범위를 벗어납니다')
        self.vertex = index
        self.changed.emit()

    def move_vertex(self, x, y, frame, *, remember=True):
        def move(record):
            if not 0 <= self.vertex < len(record.paths[0]):
                raise ValueError('수정할 점을 선택하세요')
            points = list(record.paths[0])
            points[self.vertex] = (x, y)
            return [points]
        return self.change(frame, move, remember=remember)

    def add_vertex(self, x, y, frame):
        def add(record):
            points = list(record.paths[0])
            index = len(points) if record.kind == 'point' or self.vertex < 0 else self.vertex + 1
            points.insert(index, (x, y))
            self.vertex = index
            return [points]
        return self.change(frame, add)

    def delete_vertex(self, frame):
        def delete(record):
            points = list(record.paths[0])
            if not 0 <= self.vertex < len(points):
                raise ValueError('삭제할 점을 선택하세요')
            points.pop(self.vertex)
            return [points]
        if self.change(frame, delete):
            self.vertex = min(self.vertex, len(self.selected_record(frame).paths[0]) - 1)
            self.changed.emit()

    def move_roi(self, dx, dy, frame):
        return self.change(frame, lambda record: [[(x + dx, y + dy) for x, y in record.paths[0]]])

    def begin_drag(self, x, y, tolerance, frame):
        try:
            record = self.selected_record(frame)
            distances = [(px - x)**2 + (py - y)**2 for px, py in record.paths[0]]
            index = min(range(len(distances)), key=distances.__getitem__)
            if distances[index] > tolerance**2:
                return False
            self.gesture = self.snapshot()
            self.vertex = index
            self.changed.emit()
            return True
        except ValueError:
            return False

    def finish_drag(self, cancel=False):
        before, self.gesture = self.gesture, None
        if before is not None:
            if cancel:
                self.restore(before)
            elif tuple(self.records) != before[0]:
                self.remember(before)
        self.changed.emit()

    def new_points(self, frame):
        if frame is None or self.busy or len(self.records) >= MAX_ROIS or sum(sum(len(p) for p in r.paths) for r in self.records) >= MAX_POINTS:
            return
        before = self.snapshot()
        x, y = frame.source.metadata.width // 2, frame.source.metadata.height // 2
        record = ImportedRoi(uuid4().hex, '새 점 ROI', 'point', (((x, y),),), '#45c3cf', (x, y, 1, 1), frame.source.page_index if frame.source.metadata.page_count > 1 else None)
        self.remember(before)
        self.records.append(record)
        self.selected, self.vertex = record.id, 0
        self.modified.add(record.id)
        self.changed.emit()

    def rename(self, name, frame):
        record = self.selected_record(frame)
        if not name.strip():
            raise ValueError('ROI 이름을 입력하세요')
        before = self.snapshot()
        self.remember(before)
        self.records = [replace(r, name=name.strip()[:160]) if r.id == record.id else r for r in self.records]
        self.modified.add(record.id)
        self.changed.emit()

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
            before = self.snapshot()
            records, self.errors = result
            existing = {r.id: r for r in self.records}
            existing.update((r.id, r) for r in records)
            if len(existing) > MAX_ROIS or sum(sum(len(p) for p in r.paths) for r in existing.values()) > MAX_POINTS:
                self.errors.append('ROI 목록 개수/좌표 한도 초과: 기존 목록을 유지했습니다')
            else:
                self.remember(before)
                self.records = list(existing.values())
                if records:
                    self.selected = records[0].id
                    self.vertex = 0
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
            result[-1]['modified'] = roi.id in self.modified
        return result

    def invalidate_pending(self):
        self.reader.invalidate()
        self.busy = False

    def clear_list(self):
        self.remember(self.snapshot())
        self.invalidate_pending()
        self.modified.update(r.id for r in self.records)
        self.records.clear()
        self.hidden.clear()
        self.selected = ''
        self.vertex = -1
        self.errors = []
        self.changed.emit()

    def clear(self):
        self.invalidate_pending()
        self.records.clear()
        self.hidden.clear()
        self.selected = ''
        self.errors = []
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.modified.clear()
        self.gesture = None
        self.vertex = -1
        self.edit_error = ''
        self.saved_records = None
        self.changed.emit()

    def shutdown(self):
        self.reader.shutdown()
