"""Qt background orchestration with cooperative cancellation and generation guards."""
import logging
from dataclasses import replace
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from sic_xrt_analyzer.imaging.original_source import SourceError

from .contracts import (
    AdapterOutput,
    AnalysisError,
    AnalysisException,
    AnalysisRequest,
    AnalysisResult,
    AnalysisState,
    CoordinateSpace,
    GeometryKind,
    utc_now,
)
from .model_adapter import CancellationToken, ModelAdapter

log = logging.getLogger(__name__)


def original_detections(output, request, contract):
    if not isinstance(output, AdapterOutput):
        raise TypeError("Adapter must return AdapterOutput")
    detections = []
    ids = set()
    for detection in output.detections:
        geometry = detection.geometry
        if detection.id in ids:
            raise ValueError("Detection ids must be unique within a result")
        ids.add(detection.id)
        if geometry.kind not in contract.geometry_kinds or geometry.coordinate_space != contract.coordinate_space:
            raise ValueError("Adapter output violates its geometry contract")
        dx = dy = 0
        if geometry.coordinate_space == CoordinateSpace.INPUT_LOCAL and request.roi:
            dx, dy = request.roi.x, request.roi.y
        points = tuple((x + dx, y + dy) for x, y in geometry.points)
        bbox = geometry.bbox
        if bbox is not None:
            x, y, w, h = bbox
            bbox = (x + dx, y + dy, w, h)
        translated = replace(geometry, points=points, bbox=bbox, coordinate_space=CoordinateSpace.ORIGINAL)
        # Extents use half-open edges; point samples cannot equal width/height.
        meta = request.source.metadata
        if any(x < 0 or y < 0 or x > meta.width or y > meta.height for x, y in points):
            raise ValueError("Geometry lies outside the original page")
        if translated.kind == GeometryKind.POINT and any(x >= meta.width or y >= meta.height for x, y in points):
            raise ValueError("Point lies outside original sample coordinates")
        if bbox and (bbox[0] < 0 or bbox[1] < 0 or bbox[0] + bbox[2] > meta.width or bbox[1] + bbox[3] > meta.height):
            raise ValueError("Geometry extent lies outside the original page")
        # Local output must also stay inside the submitted crop, not merely the full page.
        if geometry.coordinate_space == CoordinateSpace.INPUT_LOCAL and request.roi:
            roi = request.roi
            if any(x < 0 or y < 0 or x > roi.width or y > roi.height for x, y in geometry.points):
                raise ValueError("Local geometry lies outside the input crop")
            if geometry.kind == GeometryKind.POINT and any(x >= roi.width or y >= roi.height for x, y in geometry.points):
                raise ValueError("Local point lies outside the input crop")
            if geometry.bbox and (geometry.bbox[0] < 0 or geometry.bbox[1] < 0 or
                                  geometry.bbox[0] + geometry.bbox[2] > roi.width or
                                  geometry.bbox[1] + geometry.bbox[3] > roi.height):
                raise ValueError("Local extent lies outside the input crop")
        detections.append(replace(detection, geometry=translated))
    return tuple(detections)


class _Signals(QObject):
    finished = Signal(int, object)


class _Task(QRunnable):
    def __init__(self, generation, request, adapter, token):
        super().__init__()
        self.generation, self.request, self.adapter, self.token = generation, request, adapter, token
        self.signals = _Signals()

    def run(self):
        request = self.request
        started_at, tick = utc_now(), monotonic()
        output, detections, error = AdapterOutput(), (), None
        state = AnalysisState.COMPLETED
        try:
            self.token.check()
            self.adapter.input_contract.validate(request)
            request.source.validate_identity()
            if request.roi:
                r = request.roi
                image = request.source.read_region(r.x, r.y, r.width, r.height)
            else:
                image = request.source.read_full()
            self.token.check()
            output = self.adapter.analyze(image, request, self.token)
            self.token.check()
            request.source.validate_identity()
            detections = original_detections(output, request, self.adapter.output_contract)
        except AnalysisException as exc:
            error = exc.error
            state = AnalysisState.CANCELED if error.code == "CANCELED" else AnalysisState.FAILED
            log.warning("Analysis %s: %s (%s)", request.analysis_id, error.code, error.detail)
        except SourceError as exc:
            error = AnalysisError(exc.code, "원본 이미지를 읽을 수 없습니다. 파일과 분석 범위를 확인하세요", str(exc))
            state = AnalysisState.FAILED
            log.exception("Original source read failed for %s", request.analysis_id)
        except Exception as exc:
            error = AnalysisError("INFERENCE_FAILED", "분석에 실패했습니다. 진단 로그를 확인하세요", str(exc))
            state = AnalysisState.FAILED
            log.exception("Analysis failed for %s", request.analysis_id)
        result = AnalysisResult(request, state, started_at, utc_now(), monotonic() - tick,
                                detections if state == AnalysisState.COMPLETED else (),
                                output.summary if state == AnalysisState.COMPLETED else {},
                                output.preprocessing if state == AnalysisState.COMPLETED else {}, error)
        self.signals.finished.emit(self.generation, result)


class AnalysisPipeline(QObject):
    """GUI-thread controller. Inject an approved adapter explicitly; default is unavailable."""

    changed = Signal()

    def __init__(self, adapter: ModelAdapter | None = None, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.source = None
        self.result = None
        self.error = None
        self.current_roi = None
        self.state = self._rest_state()
        self._generation = 0
        self._active = None
        self._tasks = {}
        self._used_ids = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)  # Never invoke a model instance concurrently.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh_source)
        self._timer.start()

    def _rest_state(self):
        return AnalysisState.READY if self.adapter is not None and self.adapter.available else AnalysisState.UNAVAILABLE

    def invalidate(self):
        self._generation += 1
        if self._active:
            self._active.token.cancel()
        self._active = None
        self.result = self.error = None
        self.state = self._rest_state()
        self.changed.emit()

    def set_source(self, source):
        self.invalidate()
        self.source = source
        self.current_roi = None
        self.changed.emit()

    def set_current_roi(self, roi):
        self.current_roi = roi
        self.changed.emit()

    @property
    def result_roi_mismatch(self):
        return bool(self.result and self.result.roi != self.current_roi)

    def reject(self, error: AnalysisError):
        self.invalidate()
        self.error = error
        self.state = AnalysisState.UNAVAILABLE if error.code == "MODEL_NOT_AVAILABLE" else AnalysisState.FAILED
        self.changed.emit()
        return False

    @Slot()
    def refresh_source(self):
        if self.source is None:
            return
        try:
            self.source.validate_identity()
        except SourceError as exc:
            self.invalidate()
            self.source = None
            self.error = AnalysisError(exc.code, "원본 파일이 변경되었습니다. 파일을 다시 여세요", str(exc))
            self.state = AnalysisState.FAILED
            self.changed.emit()

    def start(self, request: AnalysisRequest):
        self.invalidate()  # New attempts clear preceding results, including invalid attempts.
        self.refresh_source()
        try:
            if self.adapter is None or not self.adapter.available:
                raise AnalysisException(AnalysisError("MODEL_NOT_AVAILABLE", "승인된 모델이 연결되지 않았습니다"))
            if self.source is None or request.source_identity != self.source.identity:
                raise AnalysisException(AnalysisError("INVALID_INPUT", "현재 원본 이미지와 분석 요청이 일치하지 않습니다"))
            if (request.model_id, request.model_version) != (self.adapter.model_id, self.adapter.model_version):
                raise AnalysisException(AnalysisError("INVALID_INPUT", "요청과 모델 버전이 일치하지 않습니다"))
            if request.analysis_id in self._used_ids:
                raise AnalysisException(AnalysisError("INVALID_INPUT", "분석 요청 ID는 재사용할 수 없습니다"))
            self.adapter.input_contract.validate(request)
        except AnalysisException as exc:
            return self.reject(exc.error)
        self._used_ids.add(request.analysis_id)
        task = _Task(self._generation, request, self.adapter, CancellationToken())
        self._tasks[self._generation] = task
        self._active = task
        task.signals.finished.connect(self._finished)
        self.state = AnalysisState.RUNNING
        self.changed.emit()
        self._pool.start(task)
        return True

    @Slot()
    def cancel(self):
        if self._active is None:
            return
        self._active.token.cancel()
        self._generation += 1  # Ignore late results even from noncooperative adapters.
        self._active = None
        self.result = None
        self.error = AnalysisError("CANCELED", "분석이 취소되었습니다")
        self.state = AnalysisState.CANCELED
        self.changed.emit()

    @Slot(int, object)
    def _finished(self, generation, result):
        self._tasks.pop(generation, None)
        if generation != self._generation or self._active is None:
            return
        self.refresh_source()
        if generation != self._generation or self.source is None or result.source_identity != self.source.identity:
            return
        self._active = None
        self.result, self.error, self.state = result, result.error, result.status
        self.changed.emit()

    def shutdown(self):
        self._timer.stop()
        self.invalidate()
        for task in self._tasks.values():
            task.token.cancel()
        self._pool.waitForDone()  # Noncooperative inference may delay normal app shutdown.
