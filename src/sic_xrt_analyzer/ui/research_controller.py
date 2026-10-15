"""Model configuration, source-bound CSV input and desktop result export."""
import csv
import hashlib
import os
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QImage

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.imaging.original_source import SourceError

from .latest_reader import LatestReader


def local_path(value):
    url = QUrl(value)
    return Path(url.toLocalFile() if url.isLocalFile() else value)


def bundled_model_path():
    """Find local bundles without depending on a particular user's Qt settings."""
    if getattr(sys, "frozen", False):
        roots = [Path(sys.executable).resolve().parent]
    else:
        # Editable installs must also work when launched outside the repository.
        project = Path(__file__).resolve().parents[3]
        roots = ([project] if (project / "pyproject.toml").is_file() else [])
        if Path.cwd() not in roots:
            roots.append(Path.cwd())
    for root in roots:
        for relative in ("models/research", "artifacts/models/research"):
            candidate = root / relative
            if (candidate / "manifest.json").is_file():
                return candidate
    return None


class ResearchController(QObject):
    changed = Signal()
    focusRequested = Signal(float, float)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.saved = None
        self.loader = LatestReader(self)
        self.loader.ready.connect(self._loaded)
        self.loading = False
        self._startup_model = False
        self._startup_attempts = set()
        self.error = self.bundle = self.csv_path = self.csv_hash = self.export_path = ""
        self.points = []
        self.point_identity = None
        self.result_identity = None
        self.live_rows = []
        self.rows = []
        self.filtered = []
        self.kind_filter, self.query, self.low_only = "ALL", "", False
        self.page = 0
        self.selected_id = ""
        self.selection_kind = ""
        self.visited = set()
        self.thumbnail_source = self.thumbnail_error = ""
        self.thumbnail_center = [0.5, 0.5]
        self.thumbnail_revision = 0
        self.thumbnail_loader = LatestReader(self)
        self.thumbnail_loader.ready.connect(self._thumbnail_ready)
        from .experiment_controller import ExperimentController
        self.experiments = ExperimentController(self)
        from .region_review import RegionReview
        self.region_review = RegionReview(self)
        bridge.pipeline.changed.connect(self._pipeline_changed)

    @Property(QObject, constant=True)
    def regions(self):
        return self.region_review

    @property
    def display_result(self):
        return self.saved if self.saved is not None else self.bridge.pipeline.result

    @property
    def pixels_available(self):
        if self.saved is None:
            return self.bridge.pipeline.source is not None
        source = self.saved.source
        return source is not None and self.bridge.original_source is not None and source.identity == self.bridge.original_source.identity

    def show_saved(self, presentation):
        self.saved = presentation
        self.result_identity = None
        self._pipeline_changed()

    @Slot()
    def show_live(self):
        reviews=getattr(self.bridge,"review_controller",None)
        if reviews and reviews.pending:
            reviews.error="작성 중인 검수를 먼저 기록하거나 취소하세요.";reviews.changed.emit();return
        self.saved = None
        self.result_identity = None
        self._pipeline_changed()

    def load_saved(self):
        updates = getattr(self.bridge, "model_update_controller", None)
        path = os.environ.get("SIC_XRT_MODEL_BUNDLE") or (updates.startup_bundle() if updates else None) or self.bridge._settings.value("researchModelBundle", "")
        if not path:
            path = bundled_model_path()
        if path:
            self._startup_model = True
            self.loadModel(str(path))
        else:
            self.error = "사용 가능한 모델이 없습니다. 관리자에게 모델 배포를 요청하세요."
            self.changed.emit()

    @Slot(str)
    def loadModel(self, folder):
        if self.bridge.pipeline.state == AnalysisState.RUNNING:
            self.error = "분석을 취소한 뒤 모델을 변경하세요."
            self.changed.emit()
            return
        updates=getattr(self.bridge,"model_update_controller",None)
        if not self._startup_model and updates and updates.protected():
            self.error="분석·검수·편집을 마치고 프로젝트를 저장한 뒤 모델을 변경하세요."
            self.changed.emit();return
        path = local_path(folder)
        self._pending_bundle = str(path)
        self.loading, self.error = True, ""

        self.changed.emit()
        def load():
            from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
            return DesktopResearchAdapter(path)
        self.loader.submit(load)

    def _loaded(self, adapter, error):
        self.loading = False
        startup = self._startup_model
        if error and self._startup_model:
            self._startup_attempts.add(self._pending_bundle)
            updates=getattr(self.bridge,"model_update_controller",None)
            fallback=updates.startup_fallback(self._pending_bundle) if updates else None
            if not fallback:fallback=bundled_model_path()
            if fallback and str(fallback) not in self._startup_attempts:
                self.loadModel(str(fallback));return
        self._startup_model=False
        self.error = "모델을 읽지 못했습니다. manifest.json과 model.onnx가 있는 폴더를 확인하세요." if error else ""
        if not error:
            self.bundle = self._pending_bundle
            self.bridge.pipeline.adapter = adapter
            self.bridge.pipeline.set_source(self.bridge.pipeline.source)
            if not startup:
                self.bridge._settings.setValue("researchModelBundle", self.bundle)
                self.bridge._settings.sync()
        self.bridge.pipeline.changed.emit()
        self.changed.emit()

    def _pipeline_changed(self):
        pipeline = self.bridge.pipeline
        if self.point_identity and (pipeline.source is None or pipeline.source.identity != self.point_identity):
            self.points = []
            self.point_identity = None
            self.csv_path = self.csv_hash = ""
        if self.saved is not None and pipeline.state == AnalysisState.RUNNING:
            self.saved = None
            self.result_identity = None
        if self.saved is not None and not self.pixels_available:
            self.thumbnail_loader.invalidate()
            self.thumbnail_source = ""
            self.thumbnail_error = "원본 연결·검증이 필요합니다."
        result = self.display_result
        result_id = result.analysis_id if result and result.status == AnalysisState.COMPLETED else None
        if pipeline.state == AnalysisState.RUNNING:
            self.live_rows = [{"id":d.id,"number":i+1,"x":d.geometry.points[0][0],"y":d.geometry.points[0][1],"type":d.class_name,"score":d.confidence,"region":[list(p) for p in d.metadata.get("bpd_region",())]} for i,d in enumerate(pipeline.live_detections)]
        else:
            self.live_rows = []
        if result_id != self.result_identity:
            self.result_identity, self.rows, self.export_path = result_id, [], ""
            self._clear_selection()
            self.visited.clear()
            self.page = 0
            if result_id and self.saved is not None:
                self.rows = self.saved.rows
            elif result_id:
                for d in result.detections:
                    if not d.geometry.points:
                        continue
                    x, y = d.geometry.points[0]
                    scores = d.metadata.get("scores", ())
                    self.rows.append({"id": d.id, "point_id": d.metadata.get("point_id", d.id),
                                      "number": len(self.rows) + 1,
                                      "scores": list(scores) if len(scores) == 3 else [],
                                      "x": x, "y": y, "type": d.class_name or "unknown",
                                      "region": [list(p) for p in d.metadata.get("bpd_region", ())], "regionProvenance": d.metadata.get("region_provenance", ""), "regionClipped": d.metadata.get("region_clipped", False), "regionError": d.metadata.get("region_error", ""),
                                      "score": d.confidence, "low_score": d.metadata.get("low_score", False)})
            self._filter_rows()
        self.changed.emit()

    def _clear_selection(self):
        self.selected_id = ""
        if self.selection_kind == "OBSERVATION":
            self.selection_kind = ""
        self.thumbnail_source = self.thumbnail_error = ""
        self.thumbnail_loader.invalidate()

    def _filter_rows(self):
        query = self.query.casefold().strip()
        self.filtered = [p for p in self.rows
                         if (self.kind_filter == "ALL" or p["type"] == self.kind_filter)
                         and (not self.low_only or p["low_score"])
                         and (not query or query in str(p["number"]) or query in p["id"].casefold()
                              or query in p["point_id"].casefold())]
        if self.selected_id and not any(p["id"] == self.selected_id for p in self.filtered):
            self._clear_selection()
        self.page = min(self.page, max(0, (len(self.filtered) - 1) // 100))

    @Slot(str, bool, str)
    def setFilter(self, kind, low_only, query):
        if kind not in ("ALL", "BPD", "TED", "TSD"):
            return
        self.kind_filter, self.low_only, self.query, self.page = kind, low_only, query, 0
        self._filter_rows()
        if self.selected_id:
            index = next((i for i, row in enumerate(self.filtered) if row["id"] == self.selected_id), -1)
            if index >= 0:
                self.page = index // 100
        self.changed.emit()

    @Slot(int)
    def setResultPage(self, page):
        self.page = max(0, min(page, max(0, (len(self.filtered) - 1) // 100)))
        self.changed.emit()

    @Slot(str)
    def selectCandidate(self, candidate_id):
        reviews=getattr(self.bridge,"review_controller",None)
        if reviews and reviews.pending:
            reviews.error="작성 중인 검수를 먼저 기록하거나 취소하세요.";reviews.changed.emit();return
        row = next((p for p in self.rows if p["id"] == candidate_id), None)
        result = self.display_result
        if row is None or result is None or result.analysis_id != self.result_identity:
            return
        source = result.request.source
        if not self.pixels_available:
            self.experiments.clear_selection()
            self.selection_kind, self.selected_id = "OBSERVATION", candidate_id
            self.thumbnail_source = ""
            self.thumbnail_error = "원본 연결·SHA 검증이 필요합니다. 메타데이터만 표시합니다."
            self.changed.emit()
            return
        try:
            source.validate_identity()
        except SourceError:
            self.bridge.pipeline.refresh_source()
            return
        self.experiments.clear_selection()
        self.selection_kind = "OBSERVATION"
        self.selected_id = candidate_id
        if self.saved is None:
            self.bridge.feedback_controller.select_candidate(row)
        self.visited.add(candidate_id)
        if row in self.filtered:
            self.page = self.filtered.index(row) // 100
        self.thumbnail_source = self.thumbnail_error = ""
        result_id = self.result_identity
        def read():
            import numpy as np
            meta = source.metadata
            w, h = min(128, meta.width), min(128, meta.height)
            x = max(0, min(round(row["x"]) - 64, meta.width - w))
            y = max(0, min(round(row["y"]) - 64, meta.height - h))
            pixels = np.ascontiguousarray(source.read_region(x, y, w, h))
            if pixels.dtype != np.uint8 or pixels.shape != (h, w, 3):
                raise ValueError("이 후보의 원본 패치는 RGB 8비트가 아닙니다.")
            image = QImage(pixels.data, w, h, pixels.strides[0], QImage.Format_RGB888).copy()
            source.validate_identity()
            return result_id, candidate_id, image, [(row["x"] - x + .5) / w, (row["y"] - y + .5) / h]
        self.thumbnail_loader.submit(read)
        self.changed.emit()
        self.focusRequested.emit(row["x"], row["y"])

    def _thumbnail_ready(self, payload, error):
        if not self.selected_id:
            return
        if error:
            self.thumbnail_error = error
        elif payload[0] == self.result_identity and payload[1] == self.selected_id:
            self.bridge.provider.research_image = payload[2]
            self.thumbnail_center = payload[3]
            self.thumbnail_revision += 1
            self.thumbnail_source = f"image://tiff/research?revision={self.thumbnail_revision}"
        self.changed.emit()

    @Slot(int)
    def stepCandidate(self, delta):
        if not self.filtered:
            return
        index = next((i for i, p in enumerate(self.filtered) if p["id"] == self.selected_id), -1)
        index = max(0, min(len(self.filtered) - 1, index + delta))
        self.selectCandidate(self.filtered[index]["id"])

    @Slot(str)
    def setCoordinates(self, filename):
        try:
            from sic_xrt_analyzer.analysis.research import load_points
            if self.bridge.pipeline.state == AnalysisState.RUNNING or self.bridge.pipeline.source is None:
                raise ValueError("분석할 영상을 먼저 열고 분석이 끝난 뒤 좌표를 가져오세요.")
            path = local_path(filename)
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("좌표 CSV는 10 MB 이하여야 합니다.")
            rows = load_points(path)
            if len(rows) > 50000:
                raise ValueError("좌표 CSV는 50,000행 이하여야 합니다.")
            points = []
            import math
            for i, row in enumerate(rows):
                x, y = float(row["x"]), float(row["y"])
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("유효하지 않은 좌표가 있습니다.")
                points.append({"point_id": row.get("point_id", str(i)), "x": x, "y": y})
            self.points, self.csv_path = points, str(path)
            self.csv_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.point_identity = self.bridge.pipeline.source.identity
            self.error = ""
            self.bridge.pipeline.invalidate()
        except (OSError, ValueError, KeyError) as exc:
            self.error = str(exc)
        self.changed.emit()

    def parameters(self, parameters):
        result = dict(parameters)
        if result.get("point_mode") == "provided_coordinates":
            if not self.points or self.point_identity != self.bridge.pipeline.source.identity:
                raise ValueError("현재 영상에 대응하는 좌표 CSV를 먼저 가져오세요.")
            result.update(points=self.points, coordinates_sha256=self.csv_hash, coordinates_path=self.csv_path)
        return result

    @Property("QVariantMap", notify=changed)
    def state(self):
        result = self.display_result
        summary = result.summary if result and result.status == AnalysisState.COMPLETED else {}
        selected_index = next((i for i, p in enumerate(self.filtered) if p["id"] == self.selected_id), -1)
        selected = next((p for p in self.rows if p["id"] == self.selected_id), {})
        selection = {"kind": self.selection_kind, "id": self.selected_id if self.selection_kind == "OBSERVATION" else self.experiments.selected_id,
                     "page_index": self.saved.run.page_index if self.saved is not None else self.bridge.original_source.page_index if self.bridge.original_source else -1,
                     "source_id": self.saved.run.source_id if self.saved is not None else self.bridge.original_source.identity.canonical_path if self.bridge.original_source else "",
                     "origin": "SAVED" if self.saved is not None else "ONNX" if self.selection_kind == "OBSERVATION" else "EXPERIMENT",
                     "run_id": self.saved.run.run_id if self.saved is not None else self.result_identity or "",
                     "project_id": self.saved.project.project_id if self.saved is not None else ""}
        review = self.bridge.feedback_controller.selected() if selected and self.saved is None else {}
        reviewed = bool(selected and review and review["original"].get("candidate_id") == selected["id"] and review["revision"])
        review_status = "검토 이력 · " + review["status"] if reviewed else "사람 검수 미확정"
        if self.saved is not None and selected:
            from sic_xrt_analyzer.results.contracts import ReviewTarget
            from sic_xrt_analyzer.results.reviews import ReviewRepository
            observation = next(o for o in self.saved.project.observations if o.run_id == self.saved.run.run_id and o.source_candidate_id == selected["id"])
            repository = ReviewRepository()
            history = repository.history(self.saved.project, ReviewTarget.OBSERVATION, observation.observation_id)
            if history:
                review_state = repository.current(self.saved.project, ReviewTarget.OBSERVATION, observation.observation_id)
                review_status = "저장된 개별 검수 · " + review_state.status.value + (" · 충돌" if review_state.conflict else "")

        return {"loading": self.loading, "error": self.error, "bundle": self.bundle,
                "coordinatesPath": self.csv_path, "coordinatesCount": len(self.points),
                "counts": dict(summary.get("counts", {})), "points": self.rows if self.pixels_available else [], "livePoints": self.live_rows,
                "savedActive": self.saved is not None, "pixelsAvailable": self.pixels_available,
                "displayRows": [{**p, "viewed": p["id"] in self.visited} for p in self.filtered[self.page*100:(self.page+1)*100]],
                "filteredPoints": self.filtered, "filteredTotal": len(self.filtered),
                "filterKind": self.kind_filter, "filterLow": self.low_only, "query": self.query,
                "page": self.page, "pages": max(1, (len(self.filtered) + 99) // 100),
                "relatedStructures": [{"id": r["id"], "number": r["number"], "ambiguous": r["ambiguous"]} for r in self.experiments.related(selected)],
                "selection": selection, "reviewStatus": review_status,
                "selected": selected, "selectedIndex": selected_index, "viewedCount": len(self.visited),
                "thumbnailSource": self.thumbnail_source, "thumbnailError": self.thumbnail_error,
                "thumbnailCenter": self.thumbnail_center,
                "runInfo": {"analysisId": self.result_identity or "", "source": result.source_identity.canonical_path if summary else "",
                            "page": result.request.page_index + 1 if summary else 0,
                            "model": result.model_id if summary else "", "modelHash": result.model_version if summary else "",
                            "mode": summary.get("point_mode", ""),
                            "seconds": round(result.duration, 2) if summary else 0,
                            "completed": result.completed_at.isoformat() if summary and result.completed_at else "",
                            "origin": "저장된 이력" if self.saved is not None else "현재 분석",
                            "runId": self.saved.run.run_id if self.saved is not None else self.result_identity or ""},
                "total": len(self.rows),
                "lowScoreCount": summary.get("low_score_count", 0),
                "limited": summary.get("candidate_limit_reached", False),
                "exclusionSummary": " · ".join({"incomplete_patch":"가장자리 패치 부족", "outside_scope":"범위 밖", "duplicate_center":"중복 중심", "invalid_coordinate":"좌표 오류"}.get(k,k) + " " + str(v) for k,v in summary.get("excluded",{}).items() if v),
                "excluded": sum(summary.get("excluded", {}).values()), "exportPath": self.export_path}

    @Slot(str, result=bool)
    def exportResult(self, folder):
        result = self.display_result
        try:
            from sic_xrt_analyzer.analysis.research import new_run, write_json
            if result is None or result.status != AnalysisState.COMPLETED:
                raise ValueError("저장할 완료 결과가 없습니다.")
            if not self.pixels_available:
                raise ValueError("기존 CSV/JSON 내보내기는 원본이 연결된 Run에서 사용할 수 있습니다.")
            result.request.source.validate_identity()
            path = new_run(local_path(folder), "desktop_analysis")
            fields = ["id", "point_id", "x", "y", "type", "score", "low_score"]
            with (path / "predictions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.rows)
            def plain(value):
                if hasattr(value, "items"):
                    return {k: plain(v) for k, v in value.items()}
                if isinstance(value, (list, tuple)):
                    return [plain(v) for v in value]
                return value
            payload = {"schema": "xrt_desktop_research", "schema_version": 1,
                       "analysis_id": result.analysis_id, "source": asdict(result.source_identity),
                       "scope": result.scope.value, "roi": asdict(result.roi) if result.roi else None,
                       "model_id": result.model_id, "model_sha256": result.model_version,
                       "summary": plain(result.summary), "parameters": plain(result.parameters),
                       "predictions": [{k:v for k,v in row.items() if k not in ("region","regionProvenance")} for row in self.rows], "research_only": True, "human_verified": False,
                       "completed_at": result.completed_at.isoformat(), "seconds": result.duration}
            write_json(path / "result.json", payload)
            self.export_path, self.error = str(path), ""
            self.changed.emit()
            return True
        except (OSError, ValueError, SourceError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return False
