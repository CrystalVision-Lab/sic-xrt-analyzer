"""Authoritative project review UI; no inference, training or legacy feedback writes."""

from dataclasses import replace

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QImage

from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.review_workspace import (
    GeometryDraft,
    add_manual,
    append_review,
)
from sic_xrt_analyzer.results.reviews import ReviewRepository
from sic_xrt_analyzer.results.serialization import plain

from .latest_reader import LatestReader

BADGES = {
    "UNREVIEWED": "미검수",
    "COMPLETE": "완료",
    "CORRECTED": "종류·영역 수정",
    "ABSENT": "결함 아님",
    "UNCERTAIN": "보류",
    "CONFLICT": "충돌",
}


class ReviewController(QObject):
    changed = Signal()
    focusRequested = Signal(float, float, float, float)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.reviewer = str(bridge._settings.value("projectReviewer", ""))
        self.mode = "EXPLORE"
        self.error = ""
        self.message = ""
        self.target_type = ReviewTarget.OBSERVATION
        self.target_id = ""
        self.source_id = self.run_id = ""
        self.existence = self.classification = self.geometry_decision = "NOT_REVIEWED"
        self.comment = ""
        self.pending = False
        self.draft = None
        self.manual = False
        self.tool = "move"
        self.edge_id = ""
        self.dragging = False
        self.filter = "ALL"
        self.compare = "BOTH"
        self.crop = ""
        self.crop_revision = 0
        self.crop_reader = LatestReader(self)
        self.crop_reader.ready.connect(self._crop_ready)
        self.next_after_save = False
        bridge.project_controller.operationFinished.connect(self._saved)
        self.cached = None
        self.rows = []
        self.index = {}
        self.geometries = {}
        self.events = {}
        bridge.project_controller.changed.connect(self._refresh)
        bridge.research_controller.changed.connect(self.changed)
        bridge.imageOpened.connect(self._image_opened)

    @property
    def projects(self):
        return self.bridge.project_controller

    def _refresh(self):
        p = self.projects.project
        if p is not self.cached:
            self.cached = p
            self.rows = []
            self.index = {}
            self.geometries = {}
            self.events = {}
            if p:
                self.geometries = {g.geometry_id: g for g in p.geometries}
                for e in p.review_events:
                    self.events.setdefault((e.target_type, e.target_id), []).append(e)
                runs = {r.run_id: r for r in p.analysis_runs}
                for o in p.observations:
                    self.rows.append(
                        {
                            "id": o.observation_id,
                            "type": "OBSERVATION",
                            "sourceId": runs[o.run_id].source_id,
                            "runId": o.run_id,
                            "candidateId": o.source_candidate_id,
                            "label": o.assigned_class or "UNKNOWN",
                            "geometryId": o.geometry_id,
                            "number": len(self.rows) + 1,
                        }
                    )
                observations = {o.observation_id: o for o in p.observations}
                for i in p.defect_instances:
                    self.rows.append(
                        {
                            "id": i.instance_id,
                            "type": "DEFECT_INSTANCE",
                            "sourceId": i.source_id,
                            "runId": "",
                            "candidateId": "",
                            "label": i.class_label or "UNKNOWN",
                            "geometryId": i.geometry_id,
                            "manual": i.instance_status == "HUMAN",
                            "linkedObservations": [
                                {
                                    "id": observations[ident.observation_id].observation_id,
                                    "candidateId": observations[
                                        ident.observation_id
                                    ].source_candidate_id,
                                    "label": observations[ident.observation_id].assigned_class
                                    or "UNKNOWN",
                                    "runId": observations[ident.observation_id].run_id,
                                }
                                for ident in i.linked_observations
                            ],
                            "number": len(self.rows) + 1,
                        }
                    )
                for row in self.rows:
                    key = (ReviewTarget(row["type"]), row["id"])
                    history = self.events.get(key, [])
                    superseded = {
                        parent for e in history for parent in e.parent_review_ids
                    }
                    tips = [e for e in history if e.review_id not in superseded]
                    meanings = {
                        (
                            e.review_status,
                            e.corrected_class,
                            e.corrected_geometry_reference,
                            e.existence,
                            e.class_decision,
                            e.geometry_decision,
                        )
                        for e in tips
                    }
                    fork = len({e.reviewer_id for e in tips}) < len(tips)
                    event = tips[-1] if tips else None
                    status = (
                        "CONFLICT"
                        if fork or len(meanings) > 1
                        else "UNREVIEWED"
                        if event is None
                        else "ABSENT"
                        if event.existence.value == "ABSENT"
                        or event.review_status.value == "REJECTED"
                        else "UNCERTAIN"
                        if event.review_status.value in ("UNCERTAIN", "NEEDS_REVIEW")
                        or event.existence.value == "UNCERTAIN"
                        or event.geometry_decision.value == "UNCERTAIN"
                        else "CORRECTED"
                        if event.review_status.value == "CORRECTED"
                        else "COMPLETE"
                    )
                    row.update(
                        status=status,
                        badge=BADGES[status],
                        humanClass=event.class_decision.value
                        if event and status != "CONFLICT"
                        else "",
                        conflict=status == "CONFLICT",
                    )
                    self.index[row["id"]] = row
        self.changed.emit()

    def _image_opened(self, result):
        if not self.pending and self.mode != "EXPLORE":
            self.cancel()
        self.changed.emit()

    def context(self):
        p = self.projects.project
        r = self.bridge.research_controller
        if p is None:
            return "", ""
        if r.saved:
            if r.saved.project.project_id != p.project_id:
                return "", ""
            return r.saved.run.source_id, r.saved.run.run_id
        live = r.display_result
        run = next(
            (x for x in p.analysis_runs if live and x.result_id == live.analysis_id),
            None,
        )
        if run:
            return run.source_id, run.run_id
        current = self.bridge.original_source
        source = next(
            (
                s
                for s in p.image_sources
                if current
                and (
                    s.file_identity.canonical_path,
                    s.file_identity.file_size,
                    s.file_identity.mtime_ns,
                )
                == (
                    current.identity.canonical_path,
                    current.identity.file_size,
                    current.identity.mtime_ns,
                )
            ),
            None,
        )
        return (source.source_id, "") if source else ("", "")

    def available(self, source_id, run_id=""):
        if (
            self.projects.busy
            or self.projects.read_only
            or self.bridge.pipeline.state.value == "RUNNING"
        ):
            return False
        p = self.projects.project
        current = self.bridge.original_source
        if p is None or current is None:
            return False
        source = next((s for s in p.image_sources if s.source_id == source_id), None)
        if (
            source is None
            or source.page_count != 1
            or current.metadata.page_count != 1
        ):
            return False
        if (
            current.identity.canonical_path,
            current.identity.file_size,
            current.identity.mtime_ns,
        ) != (
            source.file_identity.canonical_path,
            source.file_identity.file_size,
            source.file_identity.mtime_ns,
        ):
            return False
        status = self.projects.availability.get(source_id)
        if not source.content_hash or not status or status.status != "HASH_MATCH":
            return False
        context_source, context_run = self.context()
        if context_source != source_id or (run_id and context_run != run_id):
            return False
        try:
            current.validate_identity()
        except (ValueError, OSError):
            return False
        return True

    @Slot(str)
    def setReviewer(self, value):
        value = value.strip()
        if not value or len(value) > 120 or any(ord(c) < 32 for c in value):
            self.error = "연구원 ID는 제어문자 없는 1–120자입니다."
        elif self.pending:
            self.error = "작성 중인 검수를 기록하거나 취소한 뒤 연구원을 변경하세요."
        else:
            self.reviewer = value
            self.bridge._settings.setValue("projectReviewer", value)
            self.bridge._settings.sync()
            self.error = ""
        self.changed.emit()

    @Slot(result=bool)
    def enter(self):
        if self.pending:
            self.error = "작성 중인 검수를 먼저 기록하거나 취소하세요."
            self.changed.emit()
            return False
        r = self.bridge.research_controller
        _source, run = self.context()
        ident = ""
        kind = ReviewTarget.OBSERVATION
        if r.selection_kind == "OBSERVATION":
            row = next(
                (
                    o
                    for o in self.rows
                    if o["type"] == "OBSERVATION"
                    and o["candidateId"] == r.selected_id
                    and o["runId"] == run
                ),
                None,
            )
            ident = row["id"] if row else ""
        elif r.selection_kind == "DEFECT_INSTANCE":
            kind = ReviewTarget.DEFECT_INSTANCE
            ident = r.experiments.selected_id
            if not r.experiments.saved_origin and ident not in self.index:
                for prov in (
                    self.projects.project.model_provenance
                    if self.projects.project
                    else []
                ):
                    ident = prov.manifest_snapshot.get("mapping", {}).get(ident, ident)
        if not ident or ident not in self.index:
            self.error = "프로젝트에 분석 또는 실험 근거를 추가하고 대상을 선택하세요."
            self.changed.emit()
            return False
        return self.select(kind.value, ident)

    @Slot(str, str, result=bool)
    def select(self, kind, ident):
        if self.pending:
            self.error = "작성 중인 검수를 먼저 기록하거나 취소하세요."
            self.changed.emit()
            return False
        row = self.index.get(ident)
        if row is None or row["type"] != kind:
            return False
        self.target_type = ReviewTarget(kind)
        self.target_id = ident
        self.source_id, self.run_id = row["sourceId"], row["runId"] or self.context()[1]
        self.mode = "REVIEW"
        self.manual = False
        self.draft = None
        self.error = self.message = self.crop = ""
        self.crop_reader.invalidate()
        self.existence = self.classification = self.geometry_decision = "NOT_REVIEWED"
        self.comment = ""
        own = [
            e
            for e in self.events.get((self.target_type, ident), ())
            if e.reviewer_id == self.reviewer
        ]
        if own:
            e = own[-1]
            self.existence = e.existence.value
            self.classification = e.class_decision.value
            self.geometry_decision = e.geometry_decision.value
            self.comment = e.comment
        if row["sourceId"] != self.context()[0] or (
            row["runId"] and row["runId"] != self.context()[1]
        ):
            self.error = (
                "원본·Run을 프로젝트에서 선택하고 SHA 검증하세요. 이력만 표시합니다."
            )
        else:
            if kind == "OBSERVATION":
                self.bridge.research_controller.selectCandidate(row["candidateId"])
            else:
                g = self.geometries[row["geometryId"]]
                points = g.all_points()
                if self.available(self.source_id, self.run_id):
                    self._crop(g)
                if points:
                    xs, ys = zip(*points)
                    self.focusRequested.emit(
                        min(xs),
                        min(ys),
                        max(max(xs) - min(xs), 1),
                        max(max(ys) - min(ys), 1),
                    )
        self.changed.emit()
        return True

    def _crop(self, geometry):
        source = self.bridge.original_source
        ident = self.target_id
        points = geometry.all_points()
        if not points:
            return
        xs, ys = zip(*points)
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        x = max(0, min(source.metadata.width - 128, int(cx) - 64))
        y = max(0, min(source.metadata.height - 128, int(cy) - 64))
        width = min(128, source.metadata.width - x)
        height = min(128, source.metadata.height - y)

        def read():
            import numpy as np

            pixels = np.ascontiguousarray(source.read_region(x, y, width, height))
            source.validate_identity()
            return (
                ident,
                source.identity,
                QImage(
                    pixels.data, width, height, pixels.strides[0], QImage.Format_RGB888
                ).copy(),
            )

        self.crop_reader.submit(read)

    def _crop_ready(self, value, error):
        if error:
            self.error = error
        elif (
            value
            and value[0] == self.target_id
            and self.bridge.original_source
            and value[1] == self.bridge.original_source.identity
        ):
            self.bridge.provider.project_review_image = value[2]
            self.crop_revision += 1
            self.crop = f"image://tiff/projectreview?r={self.crop_revision}"
        self.changed.emit()

    @Slot()
    def saveAndNext(self):
        if not self.projects.path:
            self.error = "먼저 프로젝트 저장 위치를 지정하세요."
            self.changed.emit()
            return
        if self.pending and not self.commit(False):
            return
        self.next_after_save = True
        self.projects.save("", "")

    def _saved(self, job, ok):
        if job == "save" and ok and not self.projects.dirty:
            self.error = ""
            self.message = "프로젝트 디스크 저장 완료"
            self.changed.emit()
        if job == "save" and self.next_after_save:
            self.next_after_save = False
            if ok and not self.projects.dirty:
                self.step(1)
            else:
                self.error = (
                    "디스크 저장에 실패했습니다. 현재 대상과 미저장 기록을 유지합니다."
                )
                self.changed.emit()

    @Slot(str, str, str, str)
    def decisions(self, existence, classification, geometry, comment):
        if self.mode == "EXPLORE":
            return
        self.existence, self.classification, self.geometry_decision, self.comment = (
            existence,
            classification,
            geometry,
            comment,
        )
        self.pending = True
        self.changed.emit()

    @Slot()
    def edit(self):
        if not self.available(self.source_id, self.run_id):
            self.error = "검증된 2D 원본와 동일 Run을 연결하세요."
            self.changed.emit()
            return
        row = self.index.get(self.target_id)
        if not row:
            return
        original = self.geometries[row["geometryId"]]
        # Continue this reviewer's correction if unambiguous; original remains available in compare.
        tips = ReviewRepository().current(
            self.projects.project, self.target_type, self.target_id
        )
        ids = tips.tips_by_reviewer.get(self.reviewer, ())
        if not tips.conflict and len(ids) == 1:
            event = next(
                e for e in self.projects.project.review_events if e.review_id == ids[0]
            )
            if event.corrected_geometry_reference:
                original = self.geometries[event.corrected_geometry_reference]
        source = next(
            s
            for s in self.projects.project.image_sources
            if s.source_id == self.source_id
        )
        self.draft = GeometryDraft(source, original.page_index, original)
        self.mode = "EDIT"
        self.pending = True
        self.tool = "move"
        self.error = ""
        self.bridge.feedback_controller.setMode("")
        self.changed.emit()

    @Slot(str)
    def addManual(self, kind):
        if self.pending:
            self.error = "작성 중인 검수를 먼저 기록하거나 취소하세요."
            self.changed.emit()
            return
        source, run = self.context()
        if not self.available(source, run):
            self.error = "프로젝트에 등록·SHA 검증된 2D 원본를 여세요."
            self.changed.emit()
            return
        if kind not in ("POINT", "POLYLINE", "POLYGON", "BRANCHED_GRAPH"):
            return
        record = next(
            s for s in self.projects.project.image_sources if s.source_id == source
        )
        self.source_id, self.run_id = source, run
        self.target_id = ""
        self.manual = True
        self.mode = "EDIT"
        self.draft = GeometryDraft(record, kind=kind)
        self.existence = "PRESENT"
        self.classification = "UNKNOWN"
        self.geometry_decision = "ACCEPTED"
        self.comment = ""
        self.pending = True
        self.tool = "add"
        self.error = ""
        self.bridge.feedback_controller.setMode("")
        self.changed.emit()

    @Slot(str)
    def setTool(self, tool):
        if tool in ("move", "add", "edge_vertex", "pan"):
            self.tool = tool
            self.changed.emit()

    def _operate(self, fn):
        if self.draft is None or not self.available(self.source_id, self.run_id):
            return
        try:
            fn()
            self.error = ""
        except (ValueError, StopIteration, IndexError) as exc:
            self.error = str(exc)
        self.changed.emit()

    @Slot(float, float, float)
    def press(self, x, y, radius):
        def act():
            d = self.draft
            if self.tool == "move":
                self.dragging = d.select(x, y, radius)
                if self.dragging:
                    d.gesture = plain(d.data)
                    d.checkpoint()
            elif self.tool == "edge_vertex":
                d.add_edge_vertex(self.edge_id, x, y)
            elif self.tool == "add":
                d.add(x, y)

        self._operate(act)

    @Slot(float, float)
    def drag(self, x, y):
        if self.dragging:
            self._operate(lambda: self.draft.move(x, y, checkpoint=False))

    @Slot(bool)
    def release(self, cancelled=False):
        if (
            self.dragging
            and cancelled
            and self.draft
            and self.draft.gesture is not None
        ):
            self.draft.undo()
        self.dragging = False
        self.changed.emit()

    @Slot()
    def deleteVertex(self):
        self._operate(lambda: self.draft.delete())

    @Slot()
    def undo(self):
        self._operate(lambda: self.draft.undo())

    @Slot()
    def restore(self):
        self._operate(lambda: self.draft.restore())

    @Slot(str, str, bool)
    def edge(self, start, end, delete):
        self._operate(lambda: self.draft.edge(start, end, delete))

    @Slot(str)
    def selectEdge(self, ident):
        self.edge_id = ident
        self.tool = "edge_vertex"
        self.changed.emit()

    @Slot(str)
    def setCompare(self, value):
        if value in ("BOTH", "ORIGINAL", "CORRECTED"):
            self.compare = value
            self.changed.emit()

    @Slot(bool, result=bool)
    def commit(self, next_target=False):
        saving = self.projects.saving()
        if saving:
            # Keep the draft; recording it now could not be merged into the file being written.
            self.error = f"{saving}이 끝난 뒤 기록하세요. 작성 중인 검수는 유지됩니다."
            self.changed.emit()
            return False
        if not self.available(self.source_id, self.run_id):
            self.error = "동일 Run·SHA 검증된 원본 JPG가 필요합니다."
            self.changed.emit()
            return False
        try:
            p = self.projects.project
            g = self.draft.finish() if self.draft else None
            if g is None and self.geometry_decision == "CORRECTED":
                from sic_xrt_analyzer.results.validation import new_id

                history = self.events.get((self.target_type, self.target_id), ())
                prior = next(
                    (
                        e
                        for e in reversed(history)
                        if e.reviewer_id == self.reviewer
                        and e.corrected_geometry_reference
                    ),
                    None,
                )
                if prior is None:
                    raise ValueError("기존 영역 보정 기록이 없습니다.")
                g = replace(
                    self.geometries[prior.corrected_geometry_reference],
                    geometry_id=new_id(),
                )
            if self.manual:
                p, _event, instance = add_manual(
                    p,
                    self.source_id,
                    g,
                    self.reviewer,
                    self.classification,
                    self.comment,
                    self.run_id or None,
                )
                self.target_type = ReviewTarget.DEFECT_INSTANCE
                self.target_id = instance.instance_id
            else:
                p, _event = append_review(
                    p,
                    self.target_type,
                    self.target_id,
                    self.reviewer,
                    self.existence,
                    self.classification,
                    self.geometry_decision,
                    self.comment,
                    g,
                    self.source_id,
                    self.run_id or None,
                )
            self.pending = False
            self.draft = None
            self.mode = "REVIEW"
            self.manual = False
            self.projects._replace(p)
            r = self.bridge.research_controller
            if r.saved:
                r.saved = replace(r.saved, project=p)
            self.error = ""
            self.message = "프로젝트 메모리에 기록됨 · 디스크 저장 필요"
            # Next after append is intentional; disk-save+next is a separate awaited action.
            if next_target:
                self.step(1)
            self.changed.emit()
            return True
        except (ValueError, TypeError, StopIteration, OSError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return False

    @Slot()
    def cancel(self):
        self.pending = False
        self.draft = None
        self.mode = "EXPLORE"
        self.manual = False
        self.dragging = False
        self.target_id = ""
        self.error = self.message = self.crop = ""
        self.crop_reader.invalidate()
        self.changed.emit()

    @Slot(str)
    def setFilter(self, value):
        if value in (
            "ALL",
            "UNREVIEWED",
            "COMPLETE",
            "CORRECTED",
            "ABSENT",
            "UNCERTAIN",
            "CONFLICT",
        ):
            self.filter = value
            self.changed.emit()

    def filtered(self):
        source, run = self.context()
        return [
            r
            for r in self.rows
            if r["sourceId"] == source
            and (not r["runId"] or r["runId"] == run)
            and (self.filter == "ALL" or r["status"] == self.filter)
        ]

    @Slot(int)
    def step(self, delta):
        rows = self.filtered()
        if not rows:
            return
        index = next((i for i, r in enumerate(rows) if r["id"] == self.target_id), -1)
        row = rows[max(0, min(index + delta, len(rows) - 1))]
        self.select(row["type"], row["id"])

    @Property("QVariantMap", notify=changed)
    def state(self):
        row = self.index.get(self.target_id, {})
        history = [
            plain(e) for e in self.events.get((self.target_type, self.target_id), ())
        ]
        original = self.geometries.get(row.get("geometryId"))
        corrected = []
        if row and self.projects.project:
            state = ReviewRepository().current(
                self.projects.project, self.target_type, self.target_id
            )
            for ids in state.tips_by_reviewer.values():
                for ident in ids:
                    e = next(
                        e
                        for e in self.projects.project.review_events
                        if e.review_id == ident
                    )
                    if e.corrected_geometry_reference:
                        corrected.append(
                            plain(self.geometries[e.corrected_geometry_reference])
                        )
        source, run = self.context()
        badges = {
            row["candidateId"]: row["badge"]
            for row in self.rows
            if row["type"] == "OBSERVATION" and row["runId"] == run
        }
        return {
            "mode": self.mode,
            "editing": self.draft is not None,
            "pending": self.pending,
            "reviewer": self.reviewer,
            "error": self.error,
            "message": self.message,
            "selected": row,
            "targetId": self.target_id,
            "sourceId": self.source_id,
            "runId": self.run_id,
            "ready": self.available(self.source_id or source, self.run_id or run),
            "existence": self.existence,
            "classification": self.classification,
            "geometryDecision": self.geometry_decision,
            "comment": self.comment,
            "history": history,
            "original": plain(original) if original else {},
            "corrected": corrected,
            "compare": self.compare,
            "draft": plain(self.draft.data) if self.draft else {},
            "handles": self.draft.handles() if self.draft else [],
            "vertex": (self.draft.selected or "") if self.draft else "",
            "tool": self.tool,
            "edgeId": self.edge_id,
            "manual": self.manual,
            "filter": self.filter,
            "rows": self.filtered()[:100],
            "total": len(self.filtered()),
            "badges": badges,
            "crop": self.crop,
            "legacyEvents": len(self.bridge.feedback_controller.data.get("events", ()))
            if self.bridge.feedback_controller.data
            else 0,
        }
