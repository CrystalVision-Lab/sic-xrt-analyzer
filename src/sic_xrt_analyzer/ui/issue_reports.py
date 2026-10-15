"""Optional local, source-bound correction reports. No automatic upload or GT approval."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot

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
        settings=bridge._settings
        base=Path(settings.fileName()).parent if settings.format()==QSettings.IniFormat else Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
        self.directory=Path(os.environ.get("SIC_XRT_REPORT_DIR") or base/"reports")
        from sic_xrt_analyzer.sync.report_queue import ReportQueue
        self.queue=ReportQueue(self.directory/"outbox.sqlite3")
        self.preview=[]
        self.preview_endpoint=""
        self.digest_cache={}
        self.cancel_token=None

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

    def _submit(self, reason, note, x, y, width, height, geometry, *, selected_ids=None, correction="", attach=False):
        research = self.bridge.research_controller
        source = self.bridge.original_source
        row = next((r for r in research.rows if r["id"] == research.selected_id), None)
        if self.busy or source is None or (row is None and reason != "누락 결함" and not selected_ids) or not research.pixels_available:
            return
        from sic_xrt_analyzer.sync.report_queue import REASONS
        if reason not in REASONS:
            return
        rows=[dict(r) for r in research.rows if r["id"] in selected_ids] if selected_ids is not None else ([dict(row)] if row else [])
        if reason=="누락 결함":
            rows=[]
        if len(rows)>500 or (reason=="중복 후보" and len(rows)<2) or (reason=="누락 결함" and (width<=0 or height<=0)):
            self.error="한 번에 500개까지 선택할 수 있습니다. 중복은 2개 이상, 누락은 ROI를 지정하세요."
            self.changed.emit()
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
            "candidate": dict(row) if row else {},
            "candidates": rows,
            "correction": correction,
            "run_id": research.result_identity,
            "source": source.identity.__dict__,
            "roi": [x, y, width, height] if width > 0 and height > 0 else None,
            "roi_geometry": geometry,
            "model_version": research.display_result.model_version,
            "approval": "UNVERIFIED",
        }
        directory = self.directory
        self.busy, self.error, self.saved = True, "", ""

        def save():
            source.validate_identity()
            key=(source.path,source.identity.file_size,source.identity.mtime_ns)
            if key not in self.digest_cache:
                digest = hashlib.sha256()
                with open(source.path, "rb") as stream:
                    for block in iter(lambda: stream.read(4 * 1024**2), b""):
                        digest.update(block)
                source.validate_identity()
                self.digest_cache[key]=digest.hexdigest()
            record["source_sha256"] = self.digest_cache[key]
            crops=[]
            if attach:
                import base64, io
                from PIL import Image
                cx,cy=(x+width/2,y+height/2) if width>0 else (rows[0]["x"],rows[0]["y"])
                for kind,edge in (("detail",128),("context",512)):
                    cw,ch=min(edge,source.metadata.width),min(edge,source.metadata.height)
                    ox=max(0,min(source.metadata.width-cw,int(cx-cw/2)))
                    oy=max(0,min(source.metadata.height-ch,int(cy-ch/2)))
                    pixels=source.read_region(ox,oy,cw,ch)
                    buffer=io.BytesIO()
                    Image.fromarray(pixels).save(buffer,format="PNG")
                    data=buffer.getvalue()
                    crops.append(dict(kind=kind,rect=[ox,oy,cw,ch],png=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest()))
            source.validate_identity()
            packet={k:record[k] for k in ("report_id","created_at","reason","comment","run_id","model_version","approval","correction")}
            packet.update(schema="xrt_correction/v1",candidates=[{k:r[k] for k in ("id","x","y","type","score")} for r in rows],
                source=dict(sha256=record["source_sha256"],width=source.metadata.width,height=source.metadata.height,dtype=source.metadata.dtype,page=source.page_index),
                roi=record["roi"],crops=crops)
            self.queue.stage(packet)
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

    @Slot(str,str,str,bool,int,int,int,int)
    def stageSelection(self,reason,note,correction,attach,x,y,width,height):
        ids=list(self.bridge.research.regions.checked)
        if not ids and self.bridge.research.selected_id:
            ids=[self.bridge.research.selected_id]
        geometry={"kind":"rectangle","bbox":[x,y,width,height]} if width>0 and height>0 else None
        self._submit(reason,note,x,y,width,height,geometry,selected_ids=ids,correction=correction,attach=attach)

    @Slot()
    def resetNotice(self):
        self.saved=self.error=""
        self.changed.emit()

    @Slot(result=bool)
    def prepareSend(self):
        if self.busy:
            return False
        self.preview_endpoint=self.bridge.sync_controller.endpoint
        self.preview=self.queue.pending(self.preview_endpoint) if self.preview_endpoint else []
        self.error="" if self.preview_endpoint else "설정에서 동기화 서버와 기기 인증을 먼저 등록하세요."
        self.changed.emit()
        return bool(self.preview)

    @Slot()
    def sendPrepared(self):
        sync=self.bridge.sync_controller
        if self.busy or not self.preview or sync.endpoint!=self.preview_endpoint:
            return
        from sic_xrt_analyzer.sync.client import Transport
        import threading
        try:
            self.cancel_token=threading.Event()
            transport=Transport(self.preview_endpoint,sync.token(),self.cancel_token)
        except Exception:
            self.error="서버 인증 정보를 확인하세요."
            self.changed.emit()
            return
        rows=list(self.preview)
        self.preview=[]
        self.busy=True
        self.saved=self.error=""
        def send():
            self.queue.send(rows,transport)
            return ""
        self.reader.submit(send)
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        rows=self.queue.rows()
        pending,sent=self.queue.counts()
        return {"busy":self.busy,"error":self.error,"saved":self.saved,
            "pending":pending,"sent":sent,
            "previewEndpoint":self.preview_endpoint,"previewCount":len(self.preview),
            "previewCandidates":sum(len(r["payload"]["candidates"]) for r in self.preview),
            "previewCrops":sum(len(r["payload"]["crops"]) for r in self.preview),
            "previewReasons":list(dict.fromkeys(r["payload"]["reason"] for r in self.preview)),
            "rows":rows}
