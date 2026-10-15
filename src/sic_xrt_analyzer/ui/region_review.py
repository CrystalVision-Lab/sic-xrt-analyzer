"""Source-pixel review areas; navigation never validates a model prediction."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QObject, Property, QSettings, QStandardPaths, Signal, Slot

from sic_xrt_analyzer.analysis.feedback import atomic_json


def make_regions(rows, width, height, edge=512, include_empty=False):
    """Disjoint ownership, with visual padding handled by the viewer, not identity."""
    groups = {}
    for row in rows:
        x, y = row["x"], row["y"]
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < width and 0 <= y < height):
            continue
        key = (int(y)//edge, int(x)//edge)
        groups.setdefault(key, []).append(row)
    if include_empty:
        for y in range(math.ceil(height/edge)):
            for x in range(math.ceil(width/edge)):
                groups.setdefault((y,x), [])
    return [{"id":f"{edge}:{y}:{x}", "rect":[x*edge,y*edge,min(edge,width-x*edge),min(edge,height-y*edge)],
             "rows":points, "counts":dict(Counter(p["type"] for p in points)),
             "priority":sum(p.get("low_score",False) for p in points),
             "label":f"열 {x+1} · 행 {y+1}"}
            for (y,x),points in sorted(groups.items())]


class RegionReview(QObject):
    changed = Signal()
    focusRequested = Signal(float,float,float,float)

    def __init__(self, research):
        super().__init__(research)
        self.research = research
        self.enabled = False  # Activated when the result review panel is opened.
        self.mode = "AREA"
        self.edge = 512
        self.current = ""
        self.session = ""
        self.groups = []
        self.checked = set()
        self.records = {}
        self.opened = set()
        self.error = ""
        settings = research.bridge._settings
        base = Path(settings.fileName()).parent if settings.format()==QSettings.IniFormat else Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
        self.root = base / "area-review"
        self.path = None
        self.signature = None
        research.changed.connect(self.refresh)

    def refresh(self):
        r = self.research
        identity = str(r.result_identity or "")
        source = r.display_result.request.source if r.display_result else None
        if identity != self.session:
            self.session = identity
            self.current = ""
            self.checked.clear()
            self.opened.clear()
            self.records = {}
            self.error = ""
            self.signature = None
            self.path = None
            if identity:
                self.path = self.root / (hashlib.sha256(identity.encode()).hexdigest()+".json")
                try:
                    if self.path.exists():
                        value = json.loads(self.path.read_text(encoding="utf-8"))
                        if not isinstance(value,dict) or any(v not in ("CONFIRMED","HOLD","NEEDS_CHANGE","UNREVIEWED") for v in value.values()):
                            raise ValueError("Invalid review records")
                        self.records = value
                except (OSError,ValueError):
                    self.error = "검토 기록을 읽지 못했습니다. 기존 파일은 보존됩니다."
        signature = (identity, self.edge, self.mode, r.kind_filter, r.low_only, r.query, len(r.rows))
        if self.signature != signature:
            self.signature = signature
            self.groups = make_regions(r.filtered, source.metadata.width, source.metadata.height,
                                       self.edge,self.mode=="SCAN") if source else []
            if self.mode == "PRIORITY":
                self.groups.sort(key=lambda g:(-g["priority"],g["id"]))
            elif self.mode == "SAMPLE":
                # Deterministic spatial spread. No group is silently dropped.
                self.groups.sort(key=lambda g:hashlib.sha256((identity+g["id"]).encode()).hexdigest())
            if self.current not in {g["id"] for g in self.groups}:
                self.current = self.groups[0]["id"] if self.groups else ""
        selected = next((p for p in r.rows if p["id"]==r.selected_id),None)
        if selected:
            key = f"{self.edge}:{int(selected['y'])//self.edge}:{int(selected['x'])//self.edge}"
            if key in {g["id"] for g in self.groups}:
                self.current = key
                self.opened.add(key)
        self.changed.emit()

    @Slot(bool)
    def activate(self, value):
        self.enabled = value
        self.changed.emit()

    @Slot(str)
    def setMode(self, mode):
        if mode in ("AREA","PRIORITY","SAMPLE","SCAN"):
            self.mode = mode
            self.refresh()

    @Slot(int)
    def setEdge(self, edge):
        if edge in (256,512,1024):
            self.edge = edge
            self.refresh()

    @Slot(int)
    def stepArea(self, delta):
        if not self.groups:
            return
        index = next((i for i,g in enumerate(self.groups) if g["id"]==self.current),-1)
        group = self.groups[max(0,min(len(self.groups)-1,index+delta))]
        self.current = group["id"]
        self.opened.add(self.current)
        if group["rows"]:
            self.research.selectCandidate(group["rows"][0]["id"])
        else:
            self.research._clear_selection()
            self.research.changed.emit()
            self.focusRequested.emit(*group["rect"])
        self.changed.emit()

    @Slot(int)
    def stepCandidate(self, delta):
        rows = self.state["rows"]
        if rows:
            index = next((i for i,p in enumerate(rows) if p["id"]==self.research.selected_id),-1)
            self.research.selectCandidate(rows[max(0,min(len(rows)-1,index+delta))]["id"])

    @Slot(str,bool)
    def check(self, ident, value):
        if ident in {p["id"] for p in self.research.rows}:
            self.checked.add(ident) if value else self.checked.discard(ident)
            self.changed.emit()

    @Slot(str)
    def mark(self, status):
        if status not in ("CONFIRMED","HOLD","NEEDS_CHANGE","UNREVIEWED") or not self.path or self.error:
            return
        ids = self.checked or ({self.research.selected_id} if self.research.selected_id else set())
        updated = dict(self.records)
        updated.update({ident:status for ident in ids})
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(self.path,updated)
            self.records = updated
            self.checked.clear()
        except OSError:
            self.error = "검토 기록 저장 실패"
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        group = next((g for g in self.groups if g["id"]==self.current),{})
        rows = group.get("rows",[])
        return {"enabled":self.enabled,"mode":self.mode,"edge":self.edge,"key":self.session+":"+self.current,
                "rect":group.get("rect",[]),"label":group.get("label","영역을 선택하세요"),
                "index":next((i for i,g in enumerate(self.groups) if g["id"]==self.current),-1),
                "candidateIndex":next((i for i,p in enumerate(rows) if p["id"]==self.research.selected_id),-1),
                "total":len(self.groups),"counts":group.get("counts",{}),"opened":len(self.opened),
                "checked":sorted(self.checked),"error":self.error,
                "reviewed":sum(v=="CONFIRMED" for v in self.records.values()),
                "rows":[{**p,"checked":p["id"] in self.checked,"review":self.records.get(p["id"],"UNREVIEWED")} for p in rows]}
