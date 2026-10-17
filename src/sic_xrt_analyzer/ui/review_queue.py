"""Keyboard-first candidate review queue. Every decision is an append-only review_label/v1
event stored locally first and sent to the research server in batches."""

import hashlib
import os
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot
from PySide6.QtGui import QImage

from sic_xrt_analyzer.sync.labels import (
    CLASSES,
    LabelOutbox,
    build_queue,
    crop_rect,
    encode_crop,
    make_label,
    margin,
)

from .latest_reader import LatestReader

PAGE = 24
KINDS = ("uncertain", "class", "random")
DECISION_TEXT = {"BPD": "BPD", "TED": "TED", "TSD": "TSD", "NOT_DEFECT": "결함 아님",
                 "UNSURE": "판단 보류"}


class ReviewQueue(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        settings = bridge._settings
        base = (Path(settings.fileName()).parent if settings.format() == QSettings.IniFormat
                else Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)))
        directory = Path(os.environ.get("SIC_XRT_LABEL_DIR") or base / "labels")
        self.outbox = LabelOutbox(directory / "labels.sqlite3")
        self.session_id = str(uuid4())
        self.active = False
        self.kind, self.cls = "uncertain", "TED"
        self.seed = None
        self.queue = []          # [(candidate_id, rank)]
        self.index = 0
        self.page_images = {}    # candidate_id -> (rect, uint8 RGB crop)
        self.page_number = -1
        self.revision = 0
        self.decisions = {}      # candidate_id -> (event_id, decision)
        self.source_sha = ""
        self.source_key = None
        self.shown_at = time.monotonic()
        self.error = self.message = ""
        self.busy = self.syncing = False
        self.hash_reader = LatestReader(self)
        self.hash_reader.ready.connect(self._hash_ready)
        self.crop_reader = LatestReader(self)
        self.crop_reader.ready.connect(self._crops_ready)
        self.sync_reader = LatestReader(self)
        self.sync_reader.ready.connect(self._sync_ready)
        bridge.research_controller.changed.connect(self._research_changed)

    # ---- inputs -------------------------------------------------------------
    @property
    def research(self):
        return self.bridge.research_controller

    def _rows(self):
        return [r for r in self.research.rows if r.get("type") in CLASSES]

    def _row(self, ident):
        return next((r for r in self.research.rows if r["id"] == ident), None)

    def _settings(self):
        return self.bridge._settings

    @property
    def reviewer(self):
        return str(self._settings().value("review/reviewer", "") or "")

    @property
    def send_crops(self):
        value = self._settings().value("review/sendCrops", False)
        return value is True or str(value).lower() == "true"

    def _research_changed(self):
        # A different image/result invalidates the queue; decisions stay in the outbox.
        source = self.bridge.original_source
        key = (source.path, source.identity.mtime_ns, self.research.result_identity) if source else None
        if self.active and key != self.source_key:
            self.stop()

    # ---- queue lifecycle ----------------------------------------------------
    @Slot(str, str)
    def start(self, kind="uncertain", cls="TED"):
        source = self.bridge.original_source
        research = self.research
        if kind not in KINDS or (kind == "class" and cls not in CLASSES):
            return
        if source is None or not research.rows or not research.pixels_available:
            self.error = "검수할 분석 결과와 원본 이미지가 필요합니다."
            self.changed.emit()
            return
        if getattr(source.metadata, "page_count", 1) != 1:
            self.error = "여러 페이지 TIFF는 후보 검수를 지원하지 않습니다."
            self.changed.emit()
            return
        self.kind, self.cls = kind, cls
        self.active, self.error, self.message = True, "", ""
        self.source_key = (source.path, source.identity.mtime_ns, research.result_identity)
        if self.source_sha and self.source_key[:2] == getattr(self, "_hashed_key", None):
            self._build()
            return
        self.busy = True
        self.message = "원본 SHA-256을 확인하는 중…"
        path, key = source.path, self.source_key[:2]

        def work():
            digest = hashlib.sha256()
            with open(path, "rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024**2), b""):
                    digest.update(block)
            source.validate_identity()
            return key, digest.hexdigest()

        self.hash_reader.submit(work)
        self.changed.emit()

    def _hash_ready(self, value, error):
        self.busy = False
        if error:
            self.active, self.error, self.message = False, error, ""
        else:
            self._hashed_key, self.source_sha = value
            self.message = ""
            self._build()
        self.changed.emit()

    def _build(self):
        self.decisions = self.outbox.current(self.source_sha)
        rows = self._rows()
        seed = int(self.source_sha[:8], 16)
        done = set(self.decisions) if self.kind != "random" else ()
        self.queue = build_queue(rows, self.kind, cls=self.cls, seed=seed, done=done)
        self.seed = seed if self.kind == "random" else None
        self.index = self._next_open(0)
        self.page_number = -1
        self._ensure_page()
        self._show()

    @Slot()
    def stop(self):
        self.active = False
        self.queue, self.page_images, self.page_number = [], {}, -1
        self.crop_reader.invalidate()
        self.bridge.provider.review_images = {}
        self.changed.emit()

    def _next_open(self, start):
        for i in range(start, len(self.queue)):
            if self.queue[i][0] not in self.decisions:
                return i
        return min(start, max(0, len(self.queue) - 1))

    # ---- thumbnails -----------------------------------------------------------
    def _ensure_page(self):
        page = self.index // PAGE
        if page == self.page_number or not self.queue:
            return
        self.page_number = page
        ids = [ident for ident, _rank in self.queue[page * PAGE:(page + 1) * PAGE]]
        source = self.bridge.original_source
        rows = {r["id"]: r for r in self.research.rows}
        meta = source.metadata

        def work():
            import numpy as np

            out = {}
            for ident in ids:
                row = rows.get(ident)
                if row is None:
                    continue
                rect = crop_rect(row["x"], row["y"], meta.width, meta.height)
                pixels = np.ascontiguousarray(source.read_region(*rect))
                if pixels.dtype != np.uint8:
                    raise ValueError("후보 검수는 8비트 원본 패치만 지원합니다.")
                out[ident] = (rect, pixels)
            source.validate_identity()
            return page, out

        self.crop_reader.submit(work)

    def _crops_ready(self, value, error):
        if error:
            self.error = error
        elif self.active and value[0] == self.page_number:
            self.page_images = value[1]
            images = {}
            for ident, (_rect, pixels) in self.page_images.items():
                h, w = pixels.shape[:2]
                fmt = QImage.Format_RGB888 if pixels.ndim == 3 else QImage.Format_Grayscale8
                images[ident] = QImage(pixels.data, w, h, pixels.strides[0], fmt).copy()
            self.bridge.provider.review_images = images
            self.revision += 1
        self.changed.emit()

    # ---- decisions ------------------------------------------------------------
    def _show(self):
        self.shown_at = time.monotonic()
        if self.queue:
            ident = self.queue[self.index][0]
            self.research.focusRequested.emit(*self._xy(ident))
        self.changed.emit()

    def _xy(self, ident):
        row = self._row(ident)
        return (row["x"], row["y"]) if row else (0.0, 0.0)

    def _label(self, ident, decision, mode, parent=None):
        row = self._row(ident)
        source = self.bridge.original_source
        result = self.research.display_result
        if row is None or source is None or result is None:
            raise ValueError("후보 정보를 찾을 수 없습니다.")
        crop = None
        if self.send_crops and ident in self.page_images and decision != "RETRACTED":
            rect, pixels = self.page_images[ident]
            crop = encode_crop(pixels, rect)
        rank = next((r for i, r in self.queue if i == ident), 0)
        scores = [float(s) for s in (row.get("scores") or [])]
        return make_label(
            session_id=self.session_id,
            reviewer=self.reviewer or "익명 연구원",
            source={"sha256": self.source_sha, "width": source.metadata.width,
                    "height": source.metadata.height, "page": int(getattr(source, "page_index", 0))},
            run_id=str(result.analysis_id),
            model=self._model(result),
            candidate={"id": ident, "x": float(row["x"]), "y": float(row["y"]),
                       "predicted": row["type"] if row["type"] in CLASSES else "",
                       "scores": scores if len(scores) == 3 else []},
            decision=decision,
            mode=mode,
            queue={"kind": self.kind, "seed": self.seed, "rank": int(rank)},
            dwell_ms=int((time.monotonic() - self.shown_at) * 1000),
            parent_event_id=parent,
            crop=crop,
        )

    @staticmethod
    def _model(result):
        # AnalysisResult.model_version carries the model file SHA-256 (see result export).
        sha = str(result.model_version or "")
        is_sha = len(sha) == 64 and all(ch in "0123456789abcdef" for ch in sha.lower())
        return {"version": str(result.model_id or "")[:256], "sha256": sha.lower() if is_sha else ""}

    def _record(self, ident, decision, mode):
        previous = self.decisions.get(ident)
        label = self._label(ident, decision, mode, previous[0] if previous else None)
        self.outbox.stage(label)
        self.decisions[ident] = (label["event_id"], decision)
        return label

    @Slot(str)
    def decide(self, decision):
        if not self.active or self.busy or not self.queue or decision not in DECISION_TEXT:
            return
        ident = self.queue[self.index][0]
        try:
            self._record(ident, decision, "key")
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        self.error = ""
        self.message = f"#{self._number(ident)} → {DECISION_TEXT[decision]}"
        self.index = self._next_open(self.index + 1)
        self._ensure_page()
        self._show()

    @Slot()
    def acceptPrediction(self):
        if self.active and self.queue:
            row = self._row(self.queue[self.index][0])
            if row and row["type"] in CLASSES:
                self.decide(row["type"])

    @Slot()
    def acceptPage(self):
        """Accept the model class for every undecided candidate on this gallery page."""
        if not self.active or self.busy or not self.queue:
            return
        page = self.index // PAGE
        count = 0
        try:
            for ident, _rank in self.queue[page * PAGE:(page + 1) * PAGE]:
                row = self._row(ident)
                if ident not in self.decisions and row and row["type"] in CLASSES:
                    self._record(ident, row["type"], "batch_implicit")
                    count += 1
        except (ValueError, OSError) as exc:
            self.error = str(exc)
        self.message = f"이 페이지의 {count}개를 모델 분류대로 확정했습니다."
        self.index = self._next_open(min(len(self.queue) - 1, (page + 1) * PAGE))
        self._ensure_page()
        self._show()

    @Slot()
    def undo(self):
        if not self.active or self.busy:
            return
        last = self.outbox.last_event(self.source_sha, self.session_id)
        if last is None:
            self.message = "되돌릴 판정이 없습니다."
            self.changed.emit()
            return
        ident = last["candidate"]["id"]
        try:
            retraction = self._label(ident, "RETRACTED", "key", last["event_id"])
            self.outbox.stage(retraction)
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        self.decisions = self.outbox.current(self.source_sha)
        position = next((i for i, (c, _r) in enumerate(self.queue) if c == ident), None)
        if position is not None:
            self.index = position
        self.message = f"#{self._number(ident)} 판정을 되돌렸습니다."
        self._ensure_page()
        self._show()

    @Slot(int)
    def move(self, delta):
        if self.active and self.queue:
            self.index = max(0, min(len(self.queue) - 1, self.index + delta))
            self._ensure_page()
            self._show()

    @Slot(int)
    def goTo(self, index):
        if self.active and 0 <= index < len(self.queue):
            self.index = index
            self._ensure_page()
            self._show()

    @Slot(str)
    def setReviewer(self, name):
        self._settings().setValue("review/reviewer", name.strip()[:120])
        self.changed.emit()

    @Slot(bool)
    def setSendCrops(self, value):
        self._settings().setValue("review/sendCrops", bool(value))
        self.changed.emit()

    # ---- server ---------------------------------------------------------------
    @Slot()
    def sync(self):
        sync = getattr(self.bridge, "sync_controller", None)
        endpoint = getattr(sync, "endpoint", "") if sync else ""
        if self.syncing or not endpoint:
            self.error = "" if endpoint else "서버가 등록되지 않았습니다. 판정은 이 PC에 안전하게 보관됩니다."
            self.changed.emit()
            return
        from sic_xrt_analyzer.sync.client import Transport

        try:
            transport = Transport(endpoint, sync.token())
        except Exception:  # noqa: BLE001 -- never surface credential storage details
            self.error = "서버 인증 정보를 읽지 못했습니다. 서버 연결을 다시 등록하세요."
            self.changed.emit()
            return
        self.syncing, self.error = True, ""
        outbox = self.outbox

        def work():
            sent = 0
            while True:
                n = outbox.send(transport)
                sent += n
                if n == 0:
                    return sent

        self.sync_reader.submit(work)
        self.changed.emit()

    def _sync_ready(self, value, error):
        self.syncing = False
        if error:
            self.error = f"전송 실패 ({error}). 판정은 보관되어 있으며 다시 시도할 수 있습니다."
        else:
            self.message = f"서버로 {value}건을 보냈습니다."
        self.changed.emit()

    def shutdown(self):
        for reader in (self.hash_reader, self.crop_reader, self.sync_reader):
            reader.invalidate()

    # ---- QML state ------------------------------------------------------------
    def _number(self, ident):
        row = self._row(ident)
        return row["number"] if row else 0

    def _item(self, position):
        ident, rank = self.queue[position]
        row = self._row(ident) or {}
        decided = self.decisions.get(ident)
        return {
            "id": ident, "position": position, "rank": rank, "number": row.get("number", 0),
            "type": row.get("type", ""), "score": row.get("score", 0),
            "scores": list(row.get("scores") or []),
            "margin": margin(row.get("scores") or []),
            "decision": decided[1] if decided else "",
            "image": (f"image://tiff/review-{ident}?r={self.revision}"
                      if ident in self.page_images else ""),
        }

    @Property("QVariantMap", notify=changed)
    def state(self):
        pending, sent = self.outbox.counts()
        page = self.index // PAGE if self.queue else 0
        items = [self._item(i) for i in range(page * PAGE, min(len(self.queue), (page + 1) * PAGE))]
        reviewed = sum(1 for ident, _r in self.queue if ident in self.decisions)
        tally = {}
        for _event, decision in self.decisions.values():
            tally[decision] = tally.get(decision, 0) + 1
        sync = getattr(self.bridge, "sync_controller", None)
        return {
            "active": self.active, "busy": self.busy, "syncing": self.syncing,
            "kind": self.kind, "cls": self.cls,
            "total": len(self.queue), "reviewed": reviewed, "index": self.index,
            "page": page, "pageCount": (len(self.queue) + PAGE - 1) // PAGE,
            "items": items, "current": self._item(self.index) if self.queue else {},
            "decisions": {ident: d for ident, (_e, d) in self.decisions.items()},
            "tally": tally, "pending": pending, "sent": sent,
            "serverReady": bool(getattr(sync, "endpoint", "")) if sync else False,
            "reviewer": self.reviewer, "sendCrops": self.send_crops,
            "message": self.message, "error": self.error,
        }
