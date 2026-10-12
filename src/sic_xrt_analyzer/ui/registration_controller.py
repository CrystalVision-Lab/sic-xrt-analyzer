"""JPG-only registration controller; one latest worker, immutable evidence, local approval."""

import time
from threading import Event

import cv2
import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot

from sic_xrt_analyzer.registration import assets
from sic_xrt_analyzer.registration.comparison import ComparisonSession
from sic_xrt_analyzer.registration.engine import (
    VERSION,
    estimate,
    fit_landmarks,
    inverse_transform,
    refine,
    transform_points,
)
from sic_xrt_analyzer.results.persistence import ProjectStore
from sic_xrt_analyzer.results.sources import inspect_source, verify_content_hash

from .latest_reader import LatestReader


class RegistrationController(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.projects = bridge.project_controller
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.token = Event()
        self.epoch = 0
        self.callback = None
        self.busy = False
        self.render_busy = False
        self.error = ""
        self.message = "같은 프로젝트의 Before / After JPG를 직접 선택하세요."
        self.before_id = self.after_id = ""
        self.session = None
        self.asset = None
        self.landmarks = []
        self.pending_point = None
        self.source_cache = None
        self.source_rows = []
        self.overlay_cache = None
        self.overlay_rows = []
        self.project_id = ""
        self.latest_id = ""
        self.revision = 0
        self.frame = None
        self.zoom = 0.08
        self.centre = [0.0, 0.0]
        self.width = 800
        self.height = 600
        self.method = "sift"
        self.model = "auto"
        self.job = ""
        self.metrics = {}
        self.projects.changed.connect(self._project_changed)

    def resetProject(self):
        """Explicit manifest activation also resets a reload of the same project ID."""
        self.cancel()
        self.session = None
        self.asset = None
        self.frame = None
        self.before_id = self.after_id = ""
        self.latest_id = ""
        self.landmarks = []
        self.pending_point = None
        self.clear_images()

    def _project_changed(self):
        p = self.projects.project
        identifier = p.project_id if p else ""
        if self.busy and self.callback and self.callback[1] is not p:
            self.cancel()
        if identifier != self.project_id:
            self.cancel()
            self.session = None
            self.asset = None
            self.frame = None
            self.before_id = self.after_id = ""
            self.landmarks = []
            self.pending_point = None
            self.project_id = identifier
            self.latest_id = ""
            self.error = ""
            self.clear_images()
        relations = (
            [
                r
                for r in p.image_relationships
                if r.transform_reference
                and r.transform_reference.startswith(assets.PREFIX)
            ]
            if p
            else []
        )
        if relations and not self.latest_id and not self.busy:
            relation = relations[-1]
            self.latest_id = relation.registration_id
            try:
                self.asset = assets.read(
                    self.projects.path, relation.transform_reference, p
                )
                self.before_id = relation.source_image_id
                self.after_id = relation.target_image_id
                self.landmarks = list(self.asset["landmarks"])
                self.pending_point = None
                if self.session is None:
                    self.prepare()
            except (ValueError, OSError) as exc:
                self.error = str(exc)
        self.changed.emit()

    def clear_images(self):
        self.bridge.provider.registration_images = {}
        self.revision += 1

    def _start(self, job, function, callback):
        self.token.set()
        self.reader.invalidate()
        self.token = Event()
        token = self.token
        self.epoch += 1
        epoch = self.epoch
        project = self.projects.project
        self.busy = job != "render"
        self.render_busy = job == "render"
        self.job = job
        self.error = ""
        self.callback = (epoch, project, callback)

        def work():
            return function(token.is_set)

        self.reader.submit(work)
        self.changed.emit()

    def _ready(self, value, error):
        callback = self.callback
        self.busy = self.render_busy = False
        self.job = ""
        self.callback = None
        if not callback or callback[0] != self.epoch:
            return
        if callback[1] is not self.projects.project:
            self.error = "프로젝트가 변경되어 이전 결과를 폐기했습니다."
            self.changed.emit()
            return
        if error:
            self.error = error
            if self.session is not None:
                try:
                    self.session.validate()
                except (ValueError, OSError):
                    self.session = None
                    self.frame = None
                    self.clear_images()
        else:
            try:
                callback[2](value)
            except (ValueError, OSError) as exc:
                self.error = str(exc)
        self.changed.emit()

    @Slot()
    def cancel(self):
        self.token.set()
        self.reader.invalidate()
        self.epoch += 1
        self.callback = None
        self.busy = self.render_busy = False
        self.job = ""
        self.changed.emit()

    @Slot(str, str)
    def select(self, before_id, after_id):
        self.cancel()
        self.before_id = before_id
        self.after_id = after_id
        self.asset = None
        self.session = None
        self.frame = None
        self.landmarks = []
        self.pending_point = None
        self.error = ""
        self.clear_images()
        self.changed.emit()

    def _pair(self):
        p = self.projects.project
        if not p or self.projects.busy:
            raise ValueError("기존 프로젝트를 열고 프로젝트 작업 완료 후 실행하세요.")
        rows = {s.source_id: s for s in p.image_sources}
        a, b = rows.get(self.before_id), rows.get(self.after_id)
        if a is None or b is None or a.source_id == b.source_id:
            raise ValueError("서로 다른 Before/After JPG를 선택하세요.")
        if any(s.acquisition_metadata.get("format") != "JPEG" for s in (a, b)):
            raise ValueError("TIFF는 정합에 사용할 수 없습니다.")
        return a, b

    @Slot()
    def prepare(self):
        try:
            a, b = self._pair()
        except ValueError as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        self.message = "SHA 검증·비교 영상 준비 중…"
        snapshot = self.projects.project

        def publish(session):
            verified = {s.source_id: s for s in session.records}
            changed = tuple(
                verified.get(s.source_id, s) for s in snapshot.image_sources
            )
            p = (
                snapshot.evolve(image_sources=changed)
                if changed != snapshot.image_sources
                else snapshot
            )
            self.session = session
            self.zoom = min(self.width / b.width, self.height / b.height)
            self.centre = [b.width / 2, b.height / 2]
            self.metrics = {
                "prepare_ms": session.prepare_ms,
                "decode_count": session.decode_count,
            }
            # Keep source hashes, not altered source pixels. No analysis is requested.
            self.projects._replace(p)
            self.message = (
                "SHA 확인 완료 · 정합 전에는 두 화면 좌표가 직접 대응하지 않습니다."
            )
            self.requestFrame(self.width, self.height)

        self._start(
            "prepare", lambda cancelled: ComparisonSession(a, b, cancelled), publish
        )

    @Slot(str, str)
    def run(self, method, model):
        if self.busy or self.projects.busy or self.session is None:
            return
        try:
            self._pair()
        except ValueError as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        self.method, self.model = method, model
        snapshot = self.projects.project
        session = self.session
        landmarks = list(self.landmarks)
        before_id, after_id, path = self.before_id, self.after_id, self.projects.path

        def work(cancelled):
            session.validate()
            sizes = [(s.width, s.height) for s in session.records]
            ts = time.perf_counter()
            try:
                if method == "manual":
                    result = fit_landmarks(
                        [p["before"] for p in landmarks],
                        [p["after"] for p in landmarks],
                        *sizes,
                        model,
                    )
                    result.update(
                        algorithm="manual_landmarks",
                        algorithm_version=VERSION,
                        timings={"transform_ms": (time.perf_counter() - ts) * 1000},
                    )
                else:
                    result = estimate(
                        *session.previews,
                        *sizes,
                        method=method,
                        model=model,
                        cancelled=cancelled,
                    )
                    result = refine(result, *session.sources, cancelled=cancelled)
            except (ValueError, RuntimeError, cv2.error) as exc:
                result = {
                    "matrix": None,
                    "model": model if model != "auto" else "similarity",
                    "landmarks": landmarks if method == "manual" else [],
                    "quality": {"reasons": [str(exc)]},
                    "status": "REJECTED",
                    "algorithm": method,
                    "algorithm_version": VERSION,
                    "timings": {"total_ms": (time.perf_counter() - ts) * 1000},
                }
            session.validate()
            for record in session.records:
                verify_content_hash(record, cancelled=cancelled)
            p = assets.assign_roles(snapshot, before_id, after_id)
            a = assets.make_asset(p, *session.records, result)
            if path:
                assets.publish(path, a)
            return p, a

        def publish(value):
            p, a = value
            self.asset = a
            self.latest_id = a["registration_id"]
            self.landmarks = list(a["landmarks"])
            self.projects._replace(assets.append(p, a))
            self.message = (
                "추정 완료 · 연구원 검토 필요"
                if a["status"] != "REJECTED"
                else "정합 실패 · 근거와 실패 이력을 보존했습니다."
            )
            self.requestFrame(self.width, self.height)

        if not self.projects.path:
            self.error = "정합 자산을 보관할 프로젝트를 먼저 저장하세요."
            self.changed.emit()
            return
        self._start("estimate", work, publish)

    @Slot()
    def beginLandmarks(self):
        if self.busy:
            return
        self.asset = None
        self.landmarks = []
        self.pending_point = None
        self.message = "Before → After 순서로 동일 구조를 직접 클릭하세요. 정합 전 좌표는 각 원본 기준입니다."
        self.requestFrame(self.width, self.height)
        self.changed.emit()

    @Slot(str)
    def selectAttempt(self, identifier):
        if self.busy or self.projects.busy:
            return
        p = self.projects.project
        if not p:
            return
        r = next(
            (r for r in p.image_relationships if r.registration_id == identifier), None
        )
        if not r:
            return
        try:
            a = assets.read(self.projects.path, r.transform_reference, p)
            same = (self.before_id, self.after_id) == (
                r.source_image_id,
                r.target_image_id,
            )
            self.cancel()
            self.asset = a
            self.latest_id = identifier
            self.before_id = r.source_image_id
            self.after_id = r.target_image_id
            self.landmarks = list(a["landmarks"])
            self.pending_point = None
            if same and self.session:
                self.requestFrame(self.width, self.height)
            else:
                self.session = None
                self.frame = None
                self.clear_images()
                self.prepare()
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            self.changed.emit()

    @Slot(str)
    def approveAndSave(self, reviewer):
        if (
            self.busy
            or self.projects.busy
            or not self.asset
            or self.asset["status"] != "NEEDS_REVIEW"
        ):
            return
        if self.bridge.review_controller.pending:
            self.error = "작성 중인 결함 검수를 먼저 기록하거나 취소하세요."
            self.changed.emit()
            return
        snapshot = self.projects.project
        session = self.session
        original = self.asset
        path = self.projects.path
        expected = (
            self.projects.saved_snapshot.revision
            if self.projects.saved_snapshot
            else None
        )

        def work(cancelled):
            if session is None:
                raise ValueError("원본을 다시 연결하고 SHA 검증 후 승인하세요.")
            for source in session.records:
                verify_content_hash(source, cancelled=cancelled)
            a = assets.approve(original, reviewer)
            assets.publish(path, a)
            updated = assets.append(snapshot, a)
            if cancelled():
                raise InterruptedError("승인 저장 취소됨")
            ProjectStore().save(path, updated, expected_revision=expected)
            return updated, a

        def publish(value):
            p, a = value
            self.asset = a
            self.latest_id = a["registration_id"]
            self.projects.project = self.projects.saved_snapshot = p
            self.projects.dirty = False
            self.projects.changed.emit()
            self.message = (
                "로컬 검수 승인·프로젝트 저장 완료 · 공식 과학 검증과 구분됩니다."
            )

        self._start("approve-save", work, publish)

    @Slot(int, int)
    def requestFrame(self, width, height):
        if self.session is None or self.busy:
            return
        self.width = min(3840, max(1, width))
        self.height = min(2160, max(1, height))
        session = self.session
        centre = list(self.centre)
        zoom = self.zoom
        matrix = (
            self.asset["matrix"]
            if self.asset and self.asset["status"] != "REJECTED"
            else None
        )

        project = self.projects.project
        before_id = self.before_id
        after_id = self.after_id

        def work(cancelled):
            frame = session.render(
                centre, zoom, self.width, self.height, matrix, cancelled
            )
            frame["overlays"] = session.overlays(
                project, before_id, after_id, frame, self.width, self.height, cancelled
            )
            return frame

        def publish(frame):
            self.frame = frame
            self.revision += 1
            self.bridge.provider.registration_images = {
                k: frame[k] for k in ("before", "after", "difference")
            }
            self.metrics.update(
                render_ms=frame["render_ms"], cache_hit=frame["cache_hit"]
            )

        self._start(
            "render",
            work,
            publish,
        )

    @Slot()
    def fit(self):
        if not self.session:
            return
        s = self.session.records[1]
        self.zoom = max(
            0.005, min(8, min(self.width / s.width, self.height / s.height))
        )
        self.centre = [s.width / 2, s.height / 2]
        self.requestFrame(self.width, self.height)

    @Slot(float, float, float)
    def zoomAt(self, factor, x, y):
        if not self.session or self.busy:
            return
        old = self.zoom
        new = max(0.005, min(8, old * factor))
        anchor = (
            np.asarray(self.centre)
            + (np.array([x, y]) - np.array([self.width, self.height]) / 2) / old
        )
        self.centre = (
            anchor - (np.array([x, y]) - np.array([self.width, self.height]) / 2) / new
        ).tolist()
        self.zoom = new
        self.requestFrame(self.width, self.height)

    @Slot(float, float)
    def pan(self, dx, dy):
        if not self.session or self.busy:
            return
        self.centre = (
            np.asarray(self.centre) - np.array([dx, dy]) / self.zoom
        ).tolist()
        self.requestFrame(self.width, self.height)

    def position(self, side, x, y):
        if not self.frame:
            return None
        return transform_points(
            inverse_transform(self.frame["mapping"][0 if side == "before" else 1]),
            [[x, y]],
        )[0]

    @Slot(str, float, float)
    def addPoint(self, side, x, y):
        if self.busy or self.render_busy or not self.session:
            return
        if self.asset:
            self.asset = None
            self.frame = None
            self.pending_point = None
            self.landmarks = []
            self.requestFrame(self.width, self.height)
            return
        pos = self.position(side, x, y)
        if pos is None:
            return
        s = self.session.records[0 if side == "before" else 1]
        if not (0 <= pos[0] < s.width and 0 <= pos[1] < s.height):
            return
        if side == "before":
            self.pending_point = pos.tolist()
        elif self.pending_point is not None:
            if len(self.landmarks) >= 64:
                self.error = "수동 대응점은 64쌍까지 지원합니다."
            else:
                self.landmarks.append(
                    {
                        "before": self.pending_point,
                        "after": pos.tolist(),
                        "inlier": True,
                    }
                )
                self.pending_point = None
        self.changed.emit()

    @Slot(int)
    def deletePoint(self, index):
        if 0 <= index < len(self.landmarks):
            self.landmarks.pop(index)
            self.asset = None
            self.requestFrame(self.width, self.height)
            self.changed.emit()

    @Slot(int, str, float, float)
    def editPoint(self, index, side, x, y):
        if (
            self.busy
            or side not in ("before", "after")
            or not 0 <= index < len(self.landmarks)
            or not self.session
        ):
            return
        s = self.session.records[0 if side == "before" else 1]
        if (
            not np.isfinite([x, y]).all()
            or not 0 <= x < s.width
            or not 0 <= y < s.height
        ):
            self.error = "대응점은 원본 범위 안에 있어야 합니다."
        else:
            self.landmarks[index] = {**self.landmarks[index], side: [x, y]}
            self.asset = None
        self.changed.emit()

    @Slot(str, float, float, result=str)
    def cursor(self, side, x, y):
        p = self.position(side, x, y)
        return f"{side} 원본 ({p[0]:.2f}, {p[1]:.2f})" if p is not None else ""

    def shutdown(self):
        self.cancel()
        self.reader.shutdown()
        if self.session:
            self.session.close()
        self.session = None

    @Property("QVariantMap", notify=changed)
    def state(self):
        p = self.projects.project
        if p is not self.source_cache:
            self.source_cache = p
            self.source_rows = []
            if p:
                for source in p.image_sources:
                    if source.acquisition_metadata.get("format") != "JPEG":
                        continue
                    availability = inspect_source(source)
                    self.source_rows.append(
                        {
                            "id": source.source_id,
                            "name": source.display_name,
                            "role": source.role.value,
                            "width": source.width,
                            "height": source.height,
                            "status": availability.status,
                            "sha": bool(source.content_hash),
                            "runs": sum(
                                r.source_id == source.source_id for r in p.analysis_runs
                            ),
                        }
                    )
        rows = self.source_rows
        a = self.asset
        return {
            "sources": rows,
            "beforeId": self.before_id,
            "afterId": self.after_id,
            "busy": self.busy,
            "renderBusy": self.render_busy,
            "job": self.job,
            "error": self.error,
            "message": self.message,
            "ready": self.session is not None,
            "revision": self.revision,
            "zoom": self.zoom,
            "asset": a or {},
            "status": a["status"] if a else "NOT_RUN",
            "landmarks": self.landmarks,
            "pendingPoint": self.pending_point or [],
            "metrics": self.metrics,
            "overlays": self.frame.get("overlays", []) if self.frame else [],
            "levels": self.frame["levels"] if self.frame else [],
            "mapping": self.frame["mapping"] if self.frame else [],
            "history": [
                {"id": r.registration_id, "status": r.verification_status.value}
                for r in p.image_relationships
                if r.transform_reference
                and r.transform_reference.startswith(assets.PREFIX)
            ]
            if p
            else [],
        }
