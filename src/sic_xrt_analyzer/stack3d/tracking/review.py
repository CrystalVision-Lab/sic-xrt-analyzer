"""Append-only manual corrections replayed on an AUTO page-track result.

Events reference detection ids, so they stay meaningful as ground-truth links
independent of display track ids. Pages are scan order, not physical depth.
"""

from dataclasses import dataclass, field

REVIEW = "xrt_page_track_review/v1"
ACTIONS = ("ACCEPT_LINK", "SPLIT", "MERGE", "REJECT_TRACK")
EVENT_KEYS = {
    "revision", "action", "track_id", "other_track_id", "source_detection",
    "target_detection", "page_index", "reviewer", "status", "method", "created_at",
}

# Per-page timeline states. Colours live in QML; marker glyphs are shape cues.
MARKERS = {
    "start": "▶", "linked": "●", "low": "!", "accepted": "✓", "manual": "+",
    "gap": "–", "outside": "",
}
LABELS = {
    "start": "시작", "linked": "링크", "low": "저신뢰 링크", "accepted": "수락한 링크",
    "manual": "수동 링크", "gap": "공백", "outside": "",
}


@dataclass
class ReviewTrack:
    id: str
    detection_ids: list
    status: str = "PROPOSED"  # PROPOSED | REJECTED
    source: str = "AUTO"  # AUTO | MANUAL (edited)
    accepted: set = field(default_factory=set)  # target ids of accepted incoming links
    manual: set = field(default_factory=set)  # target ids joined by MERGE


class ReviewState:
    """Tracks after replaying events; raises ValueError on an invalid event."""

    def __init__(self, result, events=()):
        self.result = result
        self.settings = result.settings
        self.links = {(lk.source_id, lk.target_id): lk for lk in result.links
                      if lk.kind in ("CONTINUE", "GAP")}
        self.candidates = [lk for lk in result.links if lk.kind in ("SPLIT", "MERGE")]
        self.tracks = {t.id: ReviewTrack(t.id, list(t.detection_ids)) for t in result.tracks}
        for e in events:
            self.apply(e)

    def page(self, detection_id):
        return self.result.detection(detection_id).page

    def owner(self, detection_id):
        return next((t for t in self.tracks.values() if detection_id in t.detection_ids), None)

    def _track(self, tid):
        t = self.tracks.get(tid)
        if t is None:
            raise ValueError("알 수 없는 트랙입니다")
        if t.status == "REJECTED":
            raise ValueError("거부한 트랙은 보정할 수 없습니다")
        return t

    def _pair(self, t, source, target):
        ids = t.detection_ids
        if target not in ids or ids.index(target) == 0 or ids[ids.index(target) - 1] != source:
            raise ValueError("트랙 안의 연속 링크가 아닙니다")

    def apply(self, e):
        if set(e) != EVENT_KEYS or e["action"] not in ACTIONS:
            raise ValueError("스택 추적 보정 이벤트 형식 오류")
        if e["method"] != "MANUAL" or e["status"] != "REVIEWED":
            raise ValueError("보정 이벤트는 MANUAL/REVIEWED입니다")
        action, src, dst = e["action"], e["source_detection"], e["target_detection"]
        t = self._track(e["track_id"])
        if action == "REJECT_TRACK":
            if src is not None or dst is not None or e["other_track_id"] is not None:
                raise ValueError("트랙 거부 이벤트 형식 오류")
            t.status = "REJECTED"
        elif action == "ACCEPT_LINK":
            self._pair(t, src, dst)
            t.accepted.add(dst)
        elif action == "SPLIT":
            self._pair(t, src, dst)
            new_id = e["other_track_id"]
            if not isinstance(new_id, str) or not new_id or new_id in self.tracks:
                raise ValueError("분할 트랙 ID 오류")
            i = t.detection_ids.index(dst)
            tail = t.detection_ids[i:]
            t.detection_ids = t.detection_ids[:i]
            moved = set(tail)
            self.tracks[new_id] = ReviewTrack(
                new_id, tail, "PROPOSED", "MANUAL",
                {x for x in t.accepted if x in moved} - {dst},
                {x for x in t.manual if x in moved} - {dst},
            )
            t.accepted -= moved
            t.manual -= moved
            t.source = "MANUAL"
        elif action == "MERGE":
            down = self._track(e["other_track_id"])
            if down is t or t.detection_ids[-1] != src or dst not in down.detection_ids:
                raise ValueError("병합은 앞 트랙의 끝에서 뒤 트랙으로 이어야 합니다")
            if self.page(dst) <= self.page(src):
                raise ValueError("병합 링크는 다음 페이지로 이어야 합니다")
            i = down.detection_ids.index(dst)
            tail = down.detection_ids[i:]
            moved = set(tail)
            t.detection_ids += tail
            t.accepted |= {x for x in down.accepted if x in moved} - {dst}
            t.manual |= ({x for x in down.manual if x in moved} - {dst}) | {dst}
            t.source = "MANUAL"
            down.detection_ids = down.detection_ids[:i]
            down.accepted -= moved
            down.manual -= moved
            if not down.detection_ids:
                del self.tracks[down.id]
            else:
                down.source = "MANUAL"
        if e["page_index"] is not None and (dst is None or e["page_index"] != self.page(dst)):
            raise ValueError("보정 이벤트 페이지 불일치")

    # Derived per-track values -------------------------------------------------
    def link_confidence(self, t, target):
        if target in t.accepted or target in t.manual:
            return 1.0
        ids = t.detection_ids
        lk = self.links.get((ids[ids.index(target) - 1], target))
        return lk.confidence if lk else 0.0

    def min_confidence(self, t):
        return min((self.link_confidence(t, d) for d in t.detection_ids[1:]), default=1.0)

    def pending_links(self, t):
        low = self.settings.review_below
        return sum(1 for d in t.detection_ids[1:] if self.link_confidence(t, d) < low)

    def track_candidates(self, t):
        ids = set(t.detection_ids)
        return [lk for lk in self.candidates if lk.source_id in ids or lk.target_id in ids]

    def summary(self, t):
        pages = [self.page(d) for d in t.detection_ids]
        cand = self.track_candidates(t)
        pending = self.pending_links(t)
        return {
            "id": t.id,
            "first": pages[0],
            "last": pages[-1],
            "span": pages[-1] - pages[0] + 1,
            "detections": len(pages),
            "gaps": pages[-1] - pages[0] + 1 - len(pages),
            "minConfidence": round(self.min_confidence(t), 4),
            "pendingLinks": pending,
            "candidates": len(cand),
            "review": t.status != "REJECTED" and (pending > 0 or bool(cand)),
            "status": t.status,
            "source": t.source,
            "kinds": sorted({self.result.detection(d).kind for d in t.detection_ids}),
        }

    def timeline(self, t, pages):
        """One entry per volume page (original indices) for track t."""
        by_page = {self.page(d): d for d in t.detection_ids}
        first, last = min(by_page), max(by_page)
        low = self.settings.review_below
        marks = {}
        for lk in self.track_candidates(t):
            for d in (lk.source_id, lk.target_id):
                if d in by_page.values():
                    marks.setdefault(self.page(d), []).append(lk)
        out = []
        for p in pages:
            d = by_page.get(p)
            conf = None
            if p < first or p > last:
                state = "outside"
            elif d is None:
                state = "gap"
            elif p == first:
                state = "start"
            elif d in t.manual:
                state, conf = "manual", 1.0
            elif d in t.accepted:
                state, conf = "accepted", 1.0
            else:
                conf = self.link_confidence(t, d)
                state = "low" if conf < low else "linked"
            cands = marks.get(p, [])
            kinds = sorted({lk.kind for lk in cands})
            partners = sorted({
                o.id for lk in cands for x in (lk.source_id, lk.target_id)
                if (o := self.owner(x)) is not None and o is not t
            })
            out.append({
                "page": p,
                "state": state,
                "marker": MARKERS[state],
                "label": LABELS[state],
                "confidence": None if conf is None else round(conf, 3),
                "detection": d or "",
                "candidate": "/".join(kinds),
                "candidateMarker": "".join("<" if k == "SPLIT" else ">" for k in kinds),
                "partners": partners,
            })
        return out
