"""Model configuration, source-bound CSV input and desktop result export."""
import csv
import hashlib
import os
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.imaging.original_source import SourceError

from .latest_reader import LatestReader


def local_path(value):
    url = QUrl(value)
    return Path(url.toLocalFile() if url.isLocalFile() else value)


class ResearchController(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.loader = LatestReader(self)
        self.loader.ready.connect(self._loaded)
        self.loading = False
        self.error = self.bundle = self.csv_path = self.csv_hash = self.export_path = ""
        self.points = []
        self.point_identity = None
        self.result_identity = None
        self.rows = []
        bridge.pipeline.changed.connect(self._pipeline_changed)

    def load_saved(self):
        path = os.environ.get("SIC_XRT_MODEL_BUNDLE") or self.bridge._settings.value("researchModelBundle", "")
        if not path:
            base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
            candidate = base / "models" / "research"
            path = str(candidate) if (candidate / "manifest.json").is_file() else ""
        if path:
            self.loadModel(str(path))

    @Slot(str)
    def loadModel(self, folder):
        if self.bridge.pipeline.state == AnalysisState.RUNNING:
            self.error = "분석을 취소한 뒤 모델을 변경하세요."
            self.changed.emit()
            return
        path = local_path(folder)
        self.bundle = str(path)
        self.loading, self.error = True, ""
        self.bridge.pipeline.adapter = None
        self.bridge.pipeline.invalidate()
        self.changed.emit()
        def load():
            from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
            return DesktopResearchAdapter(path)
        self.loader.submit(load)

    def _loaded(self, adapter, error):
        self.loading = False
        self.error = "모델을 읽지 못했습니다. manifest.json과 model.onnx가 있는 폴더를 확인하세요." if error else ""
        if not error:
            self.bridge.pipeline.adapter = adapter
            self.bridge._settings.setValue("researchModelBundle", self.bundle)
            self.bridge._settings.sync()
        self.bridge.pipeline.invalidate()
        self.changed.emit()

    def _pipeline_changed(self):
        pipeline = self.bridge.pipeline
        if self.point_identity and (pipeline.source is None or pipeline.source.identity != self.point_identity):
            self.points = []
            self.point_identity = None
            self.csv_path = self.csv_hash = ""
        result = pipeline.result
        result_id = result.analysis_id if result and result.status == AnalysisState.COMPLETED else None
        if result_id != self.result_identity:
            self.result_identity, self.rows, self.export_path = result_id, [], ""
            if result_id:
                for d in result.detections:
                    if not d.geometry.points:
                        continue
                    x, y = d.geometry.points[0]
                    self.rows.append({"id": d.id, "point_id": d.metadata.get("point_id", d.id),
                                      "x": x, "y": y, "type": d.class_name or "unknown",
                                      "score": d.confidence, "low_score": d.metadata.get("low_score", False)})
        self.changed.emit()

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
        result = self.bridge.pipeline.result
        summary = result.summary if result and result.status == AnalysisState.COMPLETED else {}
        return {"loading": self.loading, "error": self.error, "bundle": self.bundle,
                "coordinatesPath": self.csv_path, "coordinatesCount": len(self.points),
                "counts": dict(summary.get("counts", {})), "points": self.rows,
                "displayRows": self.rows[:200], "total": len(self.rows),
                "lowScoreCount": summary.get("low_score_count", 0),
                "limited": summary.get("candidate_limit_reached", False),
                "excluded": sum(summary.get("excluded", {}).values()), "exportPath": self.export_path}

    @Slot(str, result=bool)
    def exportResult(self, folder):
        result = self.bridge.pipeline.result
        try:
            from sic_xrt_analyzer.analysis.research import new_run, write_json
            if result is None or result.status != AnalysisState.COMPLETED:
                raise ValueError("저장할 완료 결과가 없습니다.")
            result.request.source.validate_identity()
            path = new_run(local_path(folder), "desktop_analysis")
            fields = ["id", "point_id", "x", "y", "type", "score", "low_score"]
            with (path / "predictions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
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
                       "predictions": self.rows, "research_only": True, "human_verified": False,
                       "completed_at": result.completed_at.isoformat(), "seconds": result.duration}
            write_json(path / "result.json", payload)
            self.export_path, self.error = str(path), ""
            self.changed.emit()
            return True
        except (OSError, ValueError, SourceError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return False
