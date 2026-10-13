"""Optional local, source-bound correction reports. No automatic upload or GT approval."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Property, QObject, QStandardPaths, Signal, Slot

from .latest_reader import LatestReader


class IssueReports(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.busy = False
        self.error = self.saved = ""

    @Slot(str, str)
    def submitSelected(self, reason, note):
        from copy import deepcopy

        record = self.bridge.roi_manager.selected_record(self.bridge.stack_viewer.frame)
        row = next(
            (
                r
                for r in self.bridge.roiState["items"]
                if record and r["id"] == record.id and r["active"]
            ),
            None,
        )
        if row is None:
            self.error = "ROI를 선택하세요."
            self.changed.emit()
            return
        geometry = deepcopy(
            {
                k: row.get(k)
                for k in ("kind", "tool", "paths", "bbox", "page", "name", "text")
            }
        )
        self._submit(reason, note, 0, 0, 0, 0, geometry)

    @Slot(str, str, int, int, int, int)
    def submit(self, reason, note, x, y, width, height):
        geometry = (
            {"kind": "rectangle", "bbox": [x, y, width, height]}
            if width > 0 and height > 0
            else None
        )
        self._submit(reason, note, x, y, width, height, geometry)

    def _submit(self, reason, note, x, y, width, height, geometry):
        research = self.bridge.research_controller
        source = self.bridge.original_source
        row = next((r for r in research.rows if r["id"] == research.selected_id), None)
        if self.busy or source is None or row is None or not research.pixels_available:
            return
        if reason not in (
            "결함 아님",
            "종류가 다름",
            "위치가 다름",
            "영역이 다름",
            "기타",
        ):
            return
        if width > 0 and height > 0:
            try:
                source.validate_region(x, y, width, height)
            except ValueError:
                self.error = "ROI 범위를 확인하세요."
                self.changed.emit()
                return
        from sic_xrt_analyzer.analysis.contracts import utc_now

        record = {
            "created_at": utc_now().isoformat(),
            "schema": "xrt_user_report/v1",
            "report_id": str(uuid4()),
            "reason": reason,
            "comment": note[:2000],
            "candidate": dict(row),
            "run_id": research.result_identity,
            "source": source.identity.__dict__,
            "roi": [x, y, width, height] if width > 0 and height > 0 else None,
            "roi_geometry": geometry,
            "model_version": research.display_result.model_version,
            "approval": "UNVERIFIED",
        }
        directory = Path(
            os.environ.get("SIC_XRT_REPORT_DIR")
            or str(
                Path(
                    QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
                )
                / "reports"
            )
        )
        self.busy, self.error, self.saved = True, "", ""

        def save():
            source.validate_identity()
            digest = hashlib.sha256()
            with open(source.path, "rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024**2), b""):
                    digest.update(block)
            source.validate_identity()
            record["source_sha256"] = digest.hexdigest()
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / (record["report_id"] + ".json")
            with target.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
            return str(target)

        self.reader.submit(save)
        self.changed.emit()

    def _ready(self, value, error):
        self.busy = False
        self.error = error or ""
        self.saved = value if not error else ""
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {"busy": self.busy, "error": self.error, "saved": self.saved}
