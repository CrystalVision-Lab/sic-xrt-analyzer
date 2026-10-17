"""Page-track review: run the #181 engine on the selected ROI volume and record corrections.

Pages are section-scan order ("페이지"), not verified physical Z. AUTO tracks are
proposals; manual corrections are append-only events saved with the 3D session.
"""

import math
from threading import Event
from uuid import uuid4

import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QImage

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.stack3d import assets
from sic_xrt_analyzer.stack3d.scene import rgba
from sic_xrt_analyzer.stack3d.tracking import (
    TrackSettings,
    nearest_detection,
    track_from_seed,
    track_stack,
)
from sic_xrt_analyzer.stack3d.tracking.review import ReviewState
from sic_xrt_analyzer.stack3d.tracking.views import (
    centroid_path,
    filmstrip,
    kymographs,
    outline,
)

from .latest_reader import LatestReader

SELECTED_RGB = (99, 216, 208)  # filled: selected track
OTHER_RGB = (255, 196, 0)  # outline only: other detections (shape differs, not only hue)
SORTS = ("review", "length", "start")
SEED_BOX = 256
KYMO_RADIUS = 40


def _overlay(selected, other):
    h, w = selected.shape
    a = np.zeros((h, w, 4), np.uint8)
    a[other] = (*OTHER_RGB, 230)
    a[selected] = (*SELECTED_RGB, 150)
    return QImage(a.data, w, h, a.strides[0], QImage.Format_RGBA8888).copy()


class TrackReviewController(QObject):
    changed = Signal()
    tracksChanged = Signal()
    viewsChanged = Signal()
    _progress = Signal(int, object, object, str)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.stack = bridge.stack3d_controller
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self._progress.connect(self._on_progress)
        self.token = Event()
        self.epoch = 0
        self.rev = 0
        self.busy = False
        self.progress = [0, 0, ""]
        self.error = ""
        self.message = ""
        self.reviewer = ""
        self.sort_key = "review"
        self.hide_short = True
        self.overlay = True
        self.pending_seed = None
        self._seen = None
        self.replay = None
        self.reset()
        self.stack.changed.connect(self._stack_changed)
        self.stack.renderChanged.connect(self._stack_changed)

    # Lifecycle ------------------------------------------------------------------
    def reset(self):
        self.cancel(False)
        self.result = None
        self.replay = None
        self.review = None
        self.events = []
        self.saved_count = 0
        self.meta = None
        self.selection = None
        self.selected = ""
        self.merge_target = ""
        self.pending_seed = None
        self._tracks = []
        self._film = []
        self._timeline = []
        self._kymo = {}
        self._page_url = ""
        self._drop_images()
        self.tracksChanged.emit()
        self.viewsChanged.emit()
        self.changed.emit()

    def _drop_images(self):
        images = self.bridge.provider.stack3d_images
        self.bridge.provider.stack3d_images = {
            k: v for k, v in images.items() if not k.startswith("review-")
        }

    @property
    def pending(self):
        return len(self.events) > self.saved_count

    def _volume(self):
        v = self.stack.volume
        if v is None:
            return None
        sel = v.selection
        if sel["xy_step"] != 1 or sel["page_range"][2] != 1:
            return None
        return v

    @property
    def stale(self):
        v = self.stack.volume
        return self.result is not None and (
            v is None or assets.review_selection(v.selection) != self.selection
        )

    def _origin(self):
        return tuple(self.selection["roi"][:2]), self.selection["page_range"][0]

    # Running ------------------------------------------------------------------------
    @Slot()
    def run(self, seed=None):
        if self.busy:
            return
        if self.pending:
            self._fail("보정 기록을 먼저 저장하거나 되돌리세요")
            return
        v = self._volume()
        if v is None:
            self._fail(
                "스택 추적은 XY 샘플링 1·페이지 간격 1인 Volume이 필요합니다"
                if self.stack.volume is not None
                else "먼저 ROI Volume을 준비하세요"
            )
            return
        sel = assets.review_selection(v.selection)
        origin, first = tuple(sel["roi"][:2]), sel["page_range"][0]
        pixels = v.pixels
        self.token = Event()
        token = self.token
        self.epoch += 1
        epoch = self.epoch
        self.busy = True
        self.error = ""
        self.progress = [0, len(pixels), "페이지별 결함 검출"]
        report = lambda d, t, label: self._progress.emit(epoch, d, t, label)

        def work():
            result = track_stack(pixels, TrackSettings(), origin=origin, first_page=first,
                                 cancelled=token.is_set, progress=report)
            seeded = None
            if seed is not None:
                try:
                    seeded = track_from_seed(pixels, *seed, origin=origin, first_page=first,
                                             radius=8.0, result=result).track
                except ValueError:
                    seeded = None
            return epoch, v, sel, result, seeded

        self.reader.submit(work)
        self.changed.emit()

    def _on_progress(self, epoch, done, total, label):
        if epoch == self.epoch and self.busy:
            self.progress = [done, total, label]
            self.changed.emit()

    @Slot()
    def cancel(self, announce=True):
        self.token.set()
        self.epoch += 1
        self.reader.invalidate()
        was = self.busy
        self.busy = False
        if announce and was:
            self.message = "스택 추적 취소 · 원본 변경 없음"
            self.changed.emit()

    def openingFile(self, path):
        source = self.stack.source
        if self.busy and (not source or str(path) != source.source_reference):
            self.cancel()

    def _ready(self, value, error):
        if not self.busy:
            return
        self.busy = False
        if error or value is None:
            self._fail(error or "스택 추적 실패")
            return
        epoch, volume, sel, result, seeded = value
        if epoch != self.epoch or volume is not self.stack.volume:
            self.changed.emit()
            return
        self.result = result
        self.selection = sel
        self.events = []
        self.saved_count = 0
        self.meta = {"review_id": str(uuid4()), "created_at": utc_now().isoformat(),
                     "creator": None}
        self.replay = ReviewState(result)
        self.merge_target = ""
        long_tracks = sum(1 for t in result.tracks if len(t.pages) >= 3)
        self.message = f"트랙 {len(result.tracks)}개 (3페이지 이상 {long_tracks}개) · 자동 제안"
        if self.pending_seed is not None and seeded is None:
            self.message += " · 선택 위치 근처 트랙 없음"
        self.pending_seed = None
        self.selected = seeded.id if seeded else ""
        self._refresh_tracks()
        if not self.selected and self._tracks:
            self.selected = self._tracks[0]["id"]
        self._select_page_in_span()
        self._render()

    def _fail(self, text):
        self.pending_seed = None
        self.error = text
        self.changed.emit()

    # Seed entry from the 2D viewer -----------------------------------------------
    @Slot(float, float, result=bool)
    def startFromViewer(self, x, y):
        source = self.bridge.original_source
        if source is None or source.metadata.page_count < 2 or source.metadata.channels != 1:
            self._fail("여러 페이지 흑백 TIFF를 열어주세요")
            return False
        w, h = source.metadata.width, source.metadata.height
        if not (0 <= x < w and 0 <= y < h):
            return False
        x, y, page = int(x), int(y), source.page_index
        bw, bh = min(SEED_BOX, w), min(SEED_BOX, h)
        x0 = min(max(0, x - bw // 2), w - bw)
        y0 = min(max(0, y - bh // 2), h - bh)
        # Reuse an existing run on the same selection instead of recomputing.
        v = self.stack.volume
        if (
            self.result is not None
            and not self.stale
            and v is not None
            and v.selection["roi"] == [x0, y0, bw, bh]
        ):
            self._pick(page, x, y)
            return True
        if self.pending:
            self._fail("보정 기록을 먼저 저장하거나 되돌리세요")
            return False
        self._seen = self.stack.volume_revision
        # openViewerSelection may switch Source (which resets this review) first.
        if not self.stack.openViewerSelection(x0, y0, bw, bh, focus=(page, y, x)):
            self._fail(self.stack.error or "ROI Volume을 열 수 없습니다")
            return False
        self.pending_seed = (page, x, y)
        self.message = "ROI Volume 준비 후 스택 추적을 실행합니다"
        self.changed.emit()
        return True

    def _stack_changed(self):
        if self.pending_seed is not None and not self.stack.busy and self.stack.error:
            self._fail(self.stack.error)
        if (
            self.pending_seed is not None
            and not self.busy
            and not self.stack.busy
            and self.stack.volume is not None
            and self.stack.volume_revision != self._seen
        ):
            if self.result is not None and not self.stale:
                seed, self.pending_seed = self.pending_seed, None
                self._pick(*seed)  # restored review already covers this ROI
            else:
                self.run(self.pending_seed)
            return
        key = (
            self.stack.volume_revision,
            tuple(self.stack.window),
            self.stack.cursor[0] if self.stack.volume is not None else -1,
        )
        if key != getattr(self, "_view_key", None):
            full = key[:2] != getattr(self, "_view_key", (None, None, None))[:2]
            self._view_key = key
            if self.result is not None:
                self._render(full=full)
            else:
                self.changed.emit()

    # Table ----------------------------------------------------------------------
    def _refresh_tracks(self):
        if self.result is None:
            self._tracks = []
        else:
            rows = [self.replay.summary(t) for t in self.replay.tracks.values()]
            if self.hide_short:
                rows = [r for r in rows if r["detections"] >= 3 or r["id"] == self.selected]
            key = {
                "review": lambda r: (r["status"] == "REJECTED", not r["review"],
                                     r["minConfidence"], -r["detections"], r["first"]),
                "length": lambda r: (r["status"] == "REJECTED", -r["detections"], r["first"]),
                "start": lambda r: (r["first"], r["id"]),
            }[self.sort_key]
            self._tracks = sorted(rows, key=key)
        self.tracksChanged.emit()

    @Slot(str)
    def setSort(self, key):
        if key in SORTS:
            self.sort_key = key
            self._refresh_tracks()
            self.changed.emit()

    @Slot(bool)
    def setHideShort(self, value):
        self.hide_short = bool(value)
        self._refresh_tracks()
        self.changed.emit()

    @Slot(bool)
    def setOverlay(self, value):
        self.overlay = bool(value)
        self._render()

    @Slot(str)
    def setReviewer(self, name):
        self.reviewer = name.strip()[:120]
        self.changed.emit()

    @Slot(str)
    def selectTrack(self, tid):
        if self.result is None or tid not in self.replay.tracks:
            return
        self.selected = tid
        if self.merge_target == tid:
            self.merge_target = ""
        self._select_page_in_span()
        self._render()

    @Slot(int)
    def selectRelative(self, delta):
        ids = [r["id"] for r in self._tracks]
        if not ids:
            return
        i = ids.index(self.selected) if self.selected in ids else -1
        self.selectTrack(ids[min(max(0, i + delta), len(ids) - 1)])

    @Slot(str)
    def setMergeTarget(self, tid):
        if self.result is not None and tid in self.replay.tracks and tid != self.selected:
            self.merge_target = tid
            self.changed.emit()

    def _track(self):
        return self.replay.tracks.get(self.selected) if self.result is not None else None

    def merge_candidates(self, t):
        """Partner tracks: SPLIT/MERGE candidates first, then nearby continuations."""
        if t is None or t.status == "REJECTED":
            return []
        out = []
        for lk in self.replay.track_candidates(t):
            for d in (lk.source_id, lk.target_id):
                o = self.replay.owner(d)
                if o is not None and o is not t and o.status != "REJECTED" and o.id not in out:
                    out.append(o.id)
        s = self.replay.settings
        first, last = t.detection_ids[0], t.detection_ids[-1]
        near = []
        for o in self.replay.tracks.values():
            if o is t or o.status == "REJECTED" or o.id in out:
                continue
            for a, b in ((last, o.detection_ids[0]), (o.detection_ids[-1], first)):
                gap = self.replay.page(b) - self.replay.page(a)
                if 1 <= gap <= s.max_gap + 1:
                    da = self.result.detection(a).centroid
                    db = self.result.detection(b).centroid
                    dist = math.hypot(db[0] - da[0], db[1] - da[1])
                    if dist <= 2 * s.gate_px:
                        near.append((dist, o.id))
        out += [i for _, i in sorted(near)]
        return out[:8]

    # Page navigation ------------------------------------------------------------
    def _page(self):
        return self.stack.cursor[0] if self.stack.volume is not None else 0

    def _select_page_in_span(self):
        t = self._track()
        if t is None or self.stale:
            return
        first = self._origin()[1]
        pages = [self.replay.page(d) for d in t.detection_ids]
        current = first + self._page()
        if not pages[0] <= current <= pages[-1]:
            target = pages[0] if current < pages[0] else pages[-1]
            self.setPage(target - first)
        else:
            self.setPage(current - first)

    @Slot(int)
    def setPage(self, k):
        v = self.stack.volume
        if v is None:
            return
        k = max(0, min(len(v.pixels) - 1, int(k)))
        t = self._track()
        if t is None or self.stale:
            self.stack.setPage(k)
            return
        (ox, oy), first = self._origin()
        x, y = centroid_path(self.result, t.detection_ids, [first + k])[0]
        self.stack.focus(k, round(float(y)) - oy, round(float(x)) - ox)

    @Slot(int)
    def stepPage(self, delta):
        self.setPage(self._page() + delta)

    @Slot(int)
    def jumpToPage(self, page):
        if self.selection is not None:
            self.setPage(page - self._origin()[1])

    @Slot(float, float, bool)
    def pickXY(self, u, v, as_merge_target=False):
        vol = self.stack.volume
        if self.result is None or self.stale or vol is None or not (0 <= u < 1 and 0 <= v < 1):
            return
        (ox, oy), first = self._origin()
        h, w = vol.pixels.shape[1:]
        self._pick(first + self._page(), ox + u * w, oy + v * h, as_merge_target)

    def _pick(self, page, x, y, as_merge_target=False):
        d = nearest_detection(self.result, page, x, y, radius=8.0)
        o = self.replay.owner(d.id) if d else None
        if o is None:
            self.message = "선택 위치 근처에 트랙이 없습니다"
            self.changed.emit()
            return
        if as_merge_target:
            self.setMergeTarget(o.id)
        else:
            self.selectTrack(o.id)

    # Corrections ------------------------------------------------------------------
    def _append(self, event, select=None):
        if not self.reviewer:
            self._fail("검토자 ID를 입력하세요")
            return False
        event["reviewer"] = self.reviewer
        event["revision"] = len(self.events) + 1
        try:
            state = ReviewState(self.result, [*self.events, event])
        except ValueError as e:
            self._fail(str(e))
            return False
        self.events.append(event)
        self.replay = state
        self.error = ""
        if select is not None:
            self.selected = select
        if self.merge_target not in state.tracks or self.merge_target == self.selected:
            self.merge_target = ""
        self._refresh_tracks()
        self._render()
        return True

    def _guard(self):
        t = self._track()
        if t is None or self.busy:
            self._fail("트랙을 선택하세요")
            return None
        if t.status == "REJECTED":
            self._fail("거부한 트랙입니다")
            return None
        return t

    def _detection_at_page(self, t):
        page = self._origin()[1] + self._page()
        return next((d for d in t.detection_ids if self.replay.page(d) == page), None)

    @Slot()
    def acceptLink(self):
        t = self._guard()
        if t is None:
            return
        d = self._detection_at_page(t)
        if d is None or d == t.detection_ids[0]:
            self._fail("현재 페이지로 들어오는 링크가 없습니다")
            return
        src = t.detection_ids[t.detection_ids.index(d) - 1]
        self._append(assets.review_event("ACCEPT_LINK", t.id, self.reviewer or "-",
                                         source_detection=src, target_detection=d,
                                         page=self.replay.page(d)))

    @Slot()
    def splitAtPage(self):
        t = self._guard()
        if t is None:
            return
        page = self._origin()[1] + self._page()
        d = next((x for x in t.detection_ids if self.replay.page(x) >= page), None)
        if d is None or d == t.detection_ids[0]:
            self._fail("트랙의 첫 페이지 이후에서 분할하세요")
            return
        src = t.detection_ids[t.detection_ids.index(d) - 1]
        new_id = f"{t.id}.{len(self.events) + 1}"
        self._append(assets.review_event("SPLIT", t.id, self.reviewer or "-", other=new_id,
                                         source_detection=src, target_detection=d,
                                         page=self.replay.page(d)))

    @Slot()
    def mergeWithTarget(self):
        t = self._guard()
        if t is None:
            return
        tid = self.merge_target or next(iter(self.merge_candidates(t)), "")
        o = self.replay.tracks.get(tid)
        if o is None or o is t or o.status == "REJECTED":
            self._fail("병합할 트랙을 고르세요 (Ctrl+클릭)")
            return
        t_last = self.replay.page(t.detection_ids[-1])
        o_last = self.replay.page(o.detection_ids[-1])
        after_t = [d for d in o.detection_ids if self.replay.page(d) > t_last]
        after_o = [d for d in t.detection_ids if self.replay.page(d) > o_last]
        if after_t and self.replay.page(o.detection_ids[0]) >= self.replay.page(t.detection_ids[0]):
            up, down, dst = t, o, after_t[0]
        elif after_o and self.replay.page(t.detection_ids[0]) >= self.replay.page(o.detection_ids[0]):
            up, down, dst = o, t, after_o[0]
        elif after_t:
            up, down, dst = t, o, after_t[0]
        else:
            self._fail("이어지는 페이지가 없어 병합할 수 없습니다")
            return
        self._append(assets.review_event("MERGE", up.id, self.reviewer or "-", other=down.id,
                                         source_detection=up.detection_ids[-1],
                                         target_detection=dst, page=self.replay.page(dst)),
                     select=up.id)

    @Slot()
    def rejectTrack(self):
        t = self._guard()
        if t is None:
            return
        ids = [r["id"] for r in self._tracks]
        i = ids.index(t.id) if t.id in ids else -1
        following = next((x for x in ids[i + 1:] if self.replay.tracks[x].status != "REJECTED"), t.id)
        if self._append(assets.review_event("REJECT_TRACK", t.id, self.reviewer or "-")):
            self.selectTrack(following)

    @Slot()
    def undo(self):
        if self.pending and not self.busy:
            self.events.pop()
            self.replay = ReviewState(self.result, self.events)
            if self.selected not in self.replay.tracks:
                self.selected = next(iter(self.replay.tracks), "")
            self._refresh_tracks()
            self._render()

    @Slot()
    def discardEvents(self):
        while self.pending:
            self.events.pop()
        if self.result is not None:
            self.replay = ReviewState(self.result, self.events)
            if self.selected not in self.replay.tracks:
                self.selected = next(iter(self.replay.tracks), "")
            self._refresh_tracks()
            self._render()

    # Persistence hooks used by Stack3DController.save / restore ----------------------
    def snapshot(self):
        if self.result is None:
            return None
        return {
            "result": self.result.to_dict(),
            "meta": dict(self.meta),
            "events": [dict(e) for e in self.events],
            "selection": dict(self.selection),
        }

    def mark_saved(self, review):
        self.saved_count = len(review["events"])
        self.meta = {k: review[k] for k in ("review_id", "created_at", "creator")}
        self.changed.emit()

    def restore(self, bundle):
        self.reset()
        if not bundle:
            return
        review, result, state = bundle
        self.result = result
        self.replay = state
        self.events = [dict(e) for e in review["events"]]
        self.saved_count = len(self.events)
        self.meta = {k: review[k] for k in ("review_id", "created_at", "creator")}
        self.selection = dict(review["selection"])
        self.message = f"저장된 스택 추적 복원 · 보정 {len(self.events)}건"
        self._refresh_tracks()
        self.selected = self._tracks[0]["id"] if self._tracks else ""
        self._render()

    # Views --------------------------------------------------------------------------
    def _render(self, full=True):
        t = self._track()
        v = self.stack.volume
        if t is None or self.stale or v is None:
            self._film, self._timeline, self._kymo, self._page_url = [], [], {}, ""
            self._drop_images()
            self.viewsChanged.emit()
            self.changed.emit()
            return
        (ox, oy), first = self._origin()
        low, high = self.stack.window
        page_count = len(v.pixels)
        self.rev += 1
        images = {}
        key = f"review-{self.rev}"
        if full:
            film = []
            for p, box, crop, mask in filmstrip(v.pixels, (ox, oy), first, self.result,
                                                t.detection_ids):
                im, _ = rgba(crop, low, high)
                images[f"{key}-f{p}"] = im
                if mask.any():
                    images[f"{key}-o{p}"] = _overlay(mask, np.zeros_like(mask))
                film.append({"page": p, "k": p - first, "box": list(box),
                             "url": f"image://tiff/stack3d-{key}-f{p}",
                             "overlay": f"image://tiff/stack3d-{key}-o{p}" if mask.any() else ""})
            xp, yp = kymographs(v.pixels, (ox, oy), first, self.result, t.detection_ids,
                                KYMO_RADIUS)
            images[f"{key}-xp"], _ = rgba(xp, low, high)
            images[f"{key}-yp"], _ = rgba(yp, low, high)
            pages = [self.replay.page(d) for d in t.detection_ids]
            self._kymo = {
                "xp": f"image://tiff/stack3d-{key}-xp",
                "yp": f"image://tiff/stack3d-{key}-yp",
                "radius": KYMO_RADIUS,
                "pages": page_count,
                "first": pages[0] - first,
                "last": pages[-1] - first,
                "detected": [p - first for p in pages],
            }
            self._film = film
            self._timeline = self.replay.timeline(t, [first + k for k in range(page_count)])
        else:
            keep = {k: im for k, im in self.bridge.provider.stack3d_images.items()
                    if k.startswith("review-") and not k.endswith("-page")}
            images.update(keep)
        page = self._page()
        if self.overlay:
            mine = np.zeros(v.pixels.shape[1:], bool)
            others = np.zeros_like(mine)
            for d in self.result.detections:
                if d.page != first + page:
                    continue
                target = mine if d.id in t.detection_ids else others
                target[d.points[:, 1] - oy, d.points[:, 0] - ox] = True
            images[f"{key}-page"] = _overlay(mine, outline(others) & ~mine)
            self._page_url = f"image://tiff/stack3d-{key}-page"
        else:
            self._page_url = ""
        self._drop_images()
        self.bridge.provider.stack3d_images = {**self.bridge.provider.stack3d_images, **images}
        if full:
            self.viewsChanged.emit()
        self.changed.emit()

    # QML properties -----------------------------------------------------------------
    @Property("QVariantList", notify=tracksChanged)
    def tracks(self):
        return self._tracks

    @Property("QVariantList", notify=viewsChanged)
    def filmstrip(self):
        return self._film

    @Property("QVariantList", notify=viewsChanged)
    def timeline(self):
        return self._timeline

    @Property("QVariantMap", notify=viewsChanged)
    def kymograph(self):
        return self._kymo

    @Property("QVariantMap", notify=changed)
    def state(self):
        t = self._track()
        v = self.stack.volume
        first = self._origin()[1] if self.selection else (
            v.selection["page_range"][0] if v is not None else 0)
        summary = self.replay.summary(t) if t is not None else {}
        return {
            "busy": self.busy,
            "progress": self.progress,
            "error": self.error,
            "message": self.message,
            "ready": self.result is not None,
            "stale": self.stale,
            "volumeReady": v is not None,
            "trackCount": len(self.replay.tracks) if self.result is not None else 0,
            "selected": self.selected,
            "track": summary,
            "page": self._page(),
            "pageNumber": first + self._page() + 1,
            "pageCount": len(v.pixels) if v is not None else 0,
            "firstPage": first,
            "pageOverlay": self._page_url,
            "sort": self.sort_key,
            "hideShort": self.hide_short,
            "overlay": self.overlay,
            "reviewer": self.reviewer,
            "mergeTarget": self.merge_target,
            "mergeCandidates": self.merge_candidates(t) if t is not None else [],
            "events": len(self.events),
            "pending": len(self.events) - self.saved_count,
            "lastEvent": self.events[-1]["action"] if self.events else "",
        }

    def shutdown(self):
        self.cancel(False)
        self.reader.shutdown()
