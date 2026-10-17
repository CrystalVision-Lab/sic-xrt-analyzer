"""One bounded Volume, latest-request workers and source-scoped manual research sessions."""

import copy
import math
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import tifffile
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.imaging.tiff_stack import imagej_window
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.sources import inspect_source, verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source
from sic_xrt_analyzer.stack3d import assets
from sic_xrt_analyzer.stack3d.scene import prepare
from sic_xrt_analyzer.stack3d.volume import extract, physical_calibration, plan

from .latest_reader import LatestReader


class Stack3DController(QObject):
    changed = Signal()
    renderChanged = Signal()
    cameraReset = Signal()
    workspaceRequested = Signal(int)
    focusRequested = Signal(float, float)
    sourceRequested = Signal(str)
    _progress = Signal(int, object, object, str)

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
        self.job = ""
        self.error = ""
        self.message = "TIFF 원본과 제한 ROI를 선택하세요"
        self.project = None
        self.selected = ""
        self.source = None
        self.sources = []
        self._records = {}
        self.volume = None
        self.raw_reader = None
        self.frame = {}
        self.volume_revision = 0
        self.render_revision = 0
        self.roi = [0, 0, 256, 256]
        self.page_range = [0, 0, 1]
        self.xy_step = 1
        self.cursor = [0, 0, 0]
        self.window = [0, 65535]
        self.window_explicit = False
        self.camera = [-25, 35, 0, 0, 650]
        self.physical = False
        self.tracks = []
        self.track_id = ""
        self.undo_stack = []
        self.saved_tracks = []
        self.session = None
        self.ref = None
        self.dirty = False
        self.progress = [0, 0, ""]
        self.hover_text = ""
        self.pending_navigation = None
        self.pending_viewer_selection = None
        self._navigation_clear = False
        self.focus_attempts = 0
        self.active = False
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.timeout.connect(self._focus)
        self._progress.connect(self._on_progress)
        self.projects.changed.connect(self._project_changed)
        bridge.imageOpened.connect(self._image_opened)
        bridge.pageChanged.connect(self._page_changed)

    @Slot(int, object, object, str)
    def _on_progress(self, epoch, done, total, label):
        if epoch == self.epoch and self.busy:
            self.progress = [done, total, label]
            self.changed.emit()

    def _start(self, job, work, publish):
        self.cancel(False)
        self.token = Event()
        token = self.token
        self.epoch += 1
        epoch = self.epoch
        self.callback = (self.projects.project, publish)
        self.job = job
        self.busy = True
        self.error = ""
        self.reader.submit(
            lambda: work(
                token.is_set, lambda d, t, l: self._progress.emit(epoch, d, t, l)
            )
        )
        self.changed.emit()

    def _ready(self, value, error):
        callback = self.callback
        self.callback = None
        self.busy = False
        self.job = ""
        if not callback or callback[0] is not self.projects.project:
            return
        if error:
            self.error = error
            self.release()
            self.message = "작업 실패 · 입력을 확인하고 재시도하세요"
        else:
            try:
                callback[1](value)
            except (ValueError, OSError, KeyError, TypeError) as e:
                self.error = str(e)
        self.changed.emit()
        pending = self.pending_viewer_selection
        self.pending_viewer_selection = None
        if pending and not error and pending[0] == self.epoch:
            current = self.bridge.original_source
            if current and current.path == pending[1]:
                self.openViewerSelection(*pending[2])

    @Slot()
    def cancel(self, announce=True):
        self.pending_viewer_selection = None
        self.token.set()
        self.epoch += 1
        self.reader.invalidate()
        self.callback = None
        self.busy = False
        self.job = ""
        if announce:
            self.cursor = list(self.frame.get("cursor", self.cursor))
            self.window = list(self.frame.get("window", self.window))
            self.message = "작업 취소 · 원본 변경 없음"
            self.changed.emit()

    def release(self):
        self.volume = None
        self.raw_reader = None
        self.frame = {}
        self.hover_text = ""
        self.bridge.provider.stack3d_images = {k: v for k, v in self.bridge.provider.stack3d_images.items() if k.startswith("review-")}
        self.renderChanged.emit()
        self.changed.emit()

    def _review(self):
        return getattr(self.bridge, "track_review", None)

    def resetProject(self):
        self.focus_timer.stop()
        if self._review():
            self._review().reset()
        self.pending_navigation = None
        self.cancel(False)
        self.release()
        self.project = None
        self.source = None
        self.selected = ""
        self.session = None
        self.ref = None
        self.tracks = []
        self.saved_tracks = []
        self.track_id = ""
        self.undo_stack = []
        self.dirty = False

    def _refresh_sources(self):
        self._records = {
            s.source_id: s
            for s in (self.project.image_sources if self.project else ())
            if s.acquisition_metadata.get("format") == "TIFF"
        }
        current = self.bridge.original_source
        if (
            current
            and current.metadata.format == "TIFF"
            and current.path != self.bridge._working_path
        ):
            record = next(
                (
                    s
                    for s in self._records.values()
                    if s.file_identity.canonical_path == current.path
                ),
                None,
            )
            if record is None:
                _p, record = add_source(
                    AnalysisProject("Temporary current TIFF"),
                    OriginalImageSource(current.path),
                )
                self._records["CURRENT"] = record
        self.sources = [
            {
                "id": sid,
                "name": s.display_name,
                "width": s.width,
                "height": s.height,
                "pages": s.page_count,
                "dtype": s.dtype,
                "status": inspect_source(s).status,
                "path": s.source_reference,
            }
            for sid, s in self._records.items()
        ]

    def _project_changed(self):
        p = self.projects.project
        if p is self.project:
            return
        old_id = self.project.project_id if self.project else None
        if self.callback:
            old_source = (
                next(
                    (
                        s
                        for s in self.project.image_sources
                        if s.source_id == self.selected
                    ),
                    None,
                )
                if self.project
                else None
            )
            new_source = (
                next((s for s in p.image_sources if s.source_id == self.selected), None)
                if p
                else None
            )
            compatible = bool(
                p
                and p.project_id == old_id
                and old_source
                and new_source
                and old_source.file_identity == new_source.file_identity
                and old_source.calibration == new_source.calibration
                and old_source.acquisition_metadata.get(assets.KEY)
                == new_source.acquisition_metadata.get(assets.KEY)
                and (
                    not old_source.content_hash
                    or not new_source.content_hash
                    or old_source.content_hash.value == new_source.content_hash.value
                )
            )
            if self.job != "save" and compatible:
                self.callback = (p, self.callback[1])
            else:
                self.cancel(False)
        self.project = p
        self._refresh_sources()
        if not p or p.project_id != old_id:
            self.cancel(False)
            self.release()
            self.tracks = []
            self.saved_tracks = []
            self.ref = None
            self.session = None
            self.dirty = False
            refs = assets.sessions(p) if p else {}
            sid = (
                max(
                    refs,
                    key=lambda i: assets.read(self.projects.path, refs[i])[
                        "created_at"
                    ],
                )
                if refs
                else next(iter(self._records), "")
            )
            self.selectSource(sid)
        elif self.selected not in self._records:
            self.selectSource(next(iter(self._records), ""))
        else:
            updated = self._records[self.selected]
            if self.raw_reader and (
                self.raw_reader.identity.canonical_path,
                self.raw_reader.identity.file_size,
                self.raw_reader.identity.mtime_ns,
            ) != (
                updated.file_identity.canonical_path,
                updated.file_identity.file_size,
                updated.file_identity.mtime_ns,
            ):
                self.cancel(False)
                self.release()
            self.source = updated
            self.changed.emit()

    @Slot(bool)
    def setActive(self, value):
        self.active = value
        if value:
            self._refresh_sources()
            if self.selected not in self._records:
                self.selectSource(next(iter(self._records), ""))
            self.changed.emit()

    def openingFile(self, path):
        if not path and self._navigation_clear and self.pending_navigation:
            self._navigation_clear = False
            return
        if self.source and str(Path(path).resolve()) != str(
            Path(self.source.source_reference).resolve()
        ):
            self.cancel(False)
            self.release()
            self.pending_navigation = None
            self.focus_timer.stop()

    def _image_opened(self, result):
        if not result.get("ok"):
            return
        self._refresh_sources()
        if self.pending_navigation:
            self.focus_timer.start(0)
        elif self.source and result["path"] != self.source.source_reference:
            self.cancel(False)
            self.release()
            if self.selected == "CURRENT":
                self.selectSource(
                    "CURRENT"
                    if "CURRENT" in self._records
                    else next(iter(self._records), "")
                )
        self.changed.emit()

    def _page_changed(self, result):
        if result.get("ok") and self.pending_navigation:
            self.focus_timer.start(0)

    @property
    def manual_pending(self):
        review = self._review()
        return self.tracks != self.saved_tracks or bool(review and review.pending)

    @Slot(str)
    def selectSource(self, sid):
        if sid != self.selected and self.manual_pending:
            self.error = "수동 Track 초안을 먼저 저장하거나 초안 취소하세요"
            self.changed.emit()
            return
        if self.job == "save":
            return
        self.cancel(False)
        self.release()
        self.selected = sid
        self.source = self._records.get(sid)
        self.tracks = []
        self.saved_tracks = []
        self.session = None
        self.ref = None
        self.track_id = ""
        self.undo_stack = []
        self.dirty = False
        self.error = ""
        if self._review():
            self._review().reset()
        s = self.source
        if not s:
            self.changed.emit()
            return
        self.roi = [
            max(0, s.width // 2 - 128),
            max(0, s.height // 2 - 128),
            min(256, s.width),
            min(256, s.height),
        ]
        self.page_range = [0, s.page_count - 1, 1]
        self.xy_step = 1
        self.cursor = [0, 0, 0]
        self.physical = False
        self.window = [0, 65535]
        self.window_explicit = False
        ref = s.acquisition_metadata.get(assets.KEY)
        if ref and self.projects.path:

            def work(_cancelled, _progress):
                rows = assets.chain(self.projects.path, ref, self.project)
                head = rows[0][1]
                bundle = None
                if head.get(assets.REVIEW_KEY):
                    review = assets.read(self.projects.path, head[assets.REVIEW_KEY])
                    bundle = (review, *assets.load_result(self.projects.path, review, head))
                return rows, bundle

            def publish(value):
                rows, bundle = value
                a = rows[0][1]
                if self._review():
                    self._review().restore(bundle)
                self.session = copy.deepcopy(a)
                self.ref = ref
                self.tracks = copy.deepcopy(rows[0][2])
                self.saved_tracks = copy.deepcopy(self.tracks)
                self.roi = a["selection"]["roi"]
                self.page_range = a["selection"]["page_range"]
                self.xy_step = a["selection"]["xy_step"]
                self.cursor = a["settings"]["cursor"]
                self.window = a["settings"]["window"]
                self.window_explicit = True
                self.camera = a["settings"]["camera"]
                self.physical = a["coordinate_mode"] == "PHYSICAL"
                self.track_id = self.tracks[0]["track_id"] if self.tracks else ""
                self.message = "세션·수동 기록 복원 · Volume은 원본 확인 후 생성"
                self.cameraReset.emit()

            self._start("restore", work, publish)
        self.changed.emit()

    @Slot(int, int, int, int, result=bool)
    def openViewerSelection(self, x, y, width, height, focus=None):
        self._refresh_sources()
        original = self.bridge.original_source
        if original is None or original.metadata.page_count < 2:
            return False
        sid = next((ident for ident,record in self._records.items()
                    if record.source_reference == original.path), "")
        if not sid:
            return False
        if sid != self.selected:
            self.selectSource(sid)
        if self.busy:
            if self.job == "restore":
                self.pending_viewer_selection = (self.epoch, original.path, (x,y,width,height,focus))
                return True
            return False
        # Explicit display sampling keeps original XY/page mappings intact.
        # Never interpret ImageJ frames as physical Z distances.
        stride = max(1, math.ceil(math.sqrt(width*height*original.metadata.page_count*2/(64*1024**2))))
        if self.configure(x,y,width,height,0,original.metadata.page_count-1,1,stride):
            if focus is not None:
                page, source_y, source_x = focus
                self.cursor = [page, (source_y-y)//stride, (source_x-x)//stride]
            self.generate()
            return True
        return False

    @Slot(float, float, float, float, float, float, float, float, result=bool)
    def configure(self, x, y, w, h, first, last, page_step, xy_step):
        try:
            if not self.source:
                raise ValueError("TIFF 원본을 선택하세요")
            values = [x, y, w, h, first, last, page_step, xy_step]
            if any(
                type(v) not in (int, float)
                or not math.isfinite(v)
                or not float(v).is_integer()
                for v in values
            ):
                raise ValueError("ROI/Page/sampling 입력은 정수여야 합니다")
            x, y, w, h, first, last, page_step, xy_step = map(int, values)
            reader = OriginalImageSource(self.source.source_reference)
            selection = plan(reader, [x, y, w, h], first, last, page_step, xy_step)
            if self.volume is not None and selection != self.volume.selection:
                self.cancel(False)
                self.release()
                self.message = "선택 변경 · 새 Volume을 생성하세요"
            self.roi = [x, y, w, h]
            self.page_range = [first, last, page_step]
            self.xy_step = xy_step
            self.dirty = True
            self.error = ""
            self.changed.emit()
            return True
        except (ValueError, OSError) as e:
            self.error = str(e)
            self.changed.emit()
            return False

    @Slot(int, int, int, int)
    def useViewerRoi(self, x, y, w, h):
        current = self.bridge.original_source
        if (
            not self.source
            or not current
            or current.path != self.source.source_reference
        ):
            self.error = "현재 2D TIFF와 선택 3D Source가 다릅니다"
            self.changed.emit()
            return
        self.configure(x, y, w, h, *self.page_range, self.xy_step)

    @Slot()
    def useImportedRectangle(self):
        try:
            record = self.bridge.roi_manager.selected_record(
                self.bridge.stack_viewer.frame
            )
            if (
                record.tool not in ("Rectangle", "rectangle")
                or record.page_index is None
                or len(record.paths) != 1
            ):
                raise ValueError(
                    "명시적 사각형·페이지 ROI만 전달합니다. Polygon/복합 ROI의 bbox를 Mask로 취급하지 않습니다."
                )
            self.useViewerRoi(*map(int, record.bbox))
        except ValueError as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(bool)
    def setPhysical(self, value):
        proof = (
            physical_calibration(self.source, self.source.page_count)
            if self.source
            else None
        )
        if value and not proof:
            self.error = "Physical 3D 미준비: 독립 검증된 원본 공간축·방향·XY/Z 간격·순서·단위가 필요합니다"
            self.changed.emit()
            return
        self.physical = value
        self.dirty = True
        if self.volume:
            self.requestSlices()
        self.changed.emit()

    @Slot()
    def generate(self):
        if not self.source or self.job == "save":
            return
        s = self.source
        roi = list(self.roi)
        r = list(self.page_range)
        step = self.xy_step
        cursor = list(self.cursor)
        window = list(self.window)
        tracks = copy.deepcopy(self.tracks)
        physical = self.physical
        window_explicit = self.window_explicit
        self.cancel(False)
        self.release()
        self.progress = [0, 0, "원본 확인"]
        self.changed.emit()

        def work(cancelled, progress):
            verified = verify_content_hash(
                s,
                cancelled=cancelled,
                progress=lambda d, t: progress(d, t, "SHA 원본 확인"),
            )
            reader = OriginalImageSource(verified.source_reference)
            selection = plan(reader, roi, *r, step)
            volume = extract(reader, selection, cancelled=cancelled, progress=progress)
            c = [min(max(0, i), n - 1) for i, n in zip(cursor, volume.pixels.shape)]
            proof = (
                physical_calibration(verified, verified.page_count)
                if physical
                else None
            )
            if physical and not proof:
                raise ValueError("Physical calibration is no longer complete")
            chosen_window = window
            if not window_explicit:
                with tifffile.TiffFile(reader.path) as tif:
                    initial = imagej_window(tif.imagej_metadata or {})
                if initial and 0 <= initial[0] < initial[1] <= 65535:
                    chosen_window = list(initial)
            frame = prepare(
                volume, c, chosen_window, tracks, calibration=proof, cancelled=cancelled
            )
            reader.validate_identity()
            return volume, reader, verified, c, frame

        def publish(value):
            self.volume, self.raw_reader, verified, self.cursor, frame = value
            latest = (
                next(
                    (
                        s
                        for s in self.project.image_sources
                        if s.source_id == verified.source_id
                    ),
                    verified,
                )
                if self.project
                else verified
            )
            self.source = replace(latest, content_hash=verified.content_hash)
            self.volume_revision += 1
            self.window = list(frame["window"])
            self._publish_frame(frame)
            self.message = "Volume 준비 완료 · uint16 원본 유지"
            self.dirty = True

        self._start("extract", work, publish)

    def _publish_frame(self, frame):
        self.render_revision += 1
        urls = {
            k: f"image://tiff/stack3d-{self.render_revision}-{k}"
            for k in frame["images"]
        }
        self.bridge.provider.stack3d_images = {
            **{k: v for k, v in self.bridge.provider.stack3d_images.items() if k.startswith("review-")},
            **{f"{self.render_revision}-{k}": im for k, im in frame["images"].items()},
        }
        self.frame = {**{k: v for k, v in frame.items() if k != "images"}, "urls": urls}
        for p in self.frame["planes"]:
            p["url"] = urls[p["key"]]
            p["volume_revision"] = self.volume_revision
        self.renderChanged.emit()

    def requestSlices(self):
        if self.volume is None or self.job == "save":
            return
        volume = self.volume
        reader = self.raw_reader
        cursor = list(self.cursor)
        window = list(self.window)
        tracks = copy.deepcopy(self.tracks)
        proof = (
            physical_calibration(self.source, self.source.page_count)
            if self.physical
            else None
        )

        def work(cancelled, _progress):
            reader.validate_identity()
            frame = prepare(
                volume, cursor, window, tracks, calibration=proof, cancelled=cancelled
            )
            reader.validate_identity()
            return frame

        self._start("slices", work, self._publish_frame)

    @Slot(int)
    def setPage(self, index):
        if self.volume is None or not 0 <= index < len(self.volume.pixels):
            return
        self.cursor[0] = index
        self.dirty = True
        self.requestSlices()

    @Slot(int, int, int)
    def focus(self, k, y, x):
        """Move page and XY cursor together (volume indices)."""
        if self.volume is None:
            return
        nk, ny, nx = self.volume.pixels.shape
        self.cursor = [min(max(0, k), nk - 1), min(max(0, y), ny - 1), min(max(0, x), nx - 1)]
        self.dirty = True
        self.requestSlices()
        self.changed.emit()

    @Slot(int, int)
    def setXY(self, x, y):
        if self.volume is None:
            return
        try:
            self.volume.original(self.cursor[0], y, x)
        except ValueError:
            return
        self.cursor[1:] = [y, x]
        self.dirty = True
        self.requestSlices()

    @Slot(str, float, float, result=str)
    def hover(self, kind, u, v):
        if self.volume is None or not 0 <= u < 1 or not 0 <= v < 1:
            return ""
        k, y, x = self.cursor
        nk, ny, nx = self.volume.pixels.shape
        if kind.startswith("plane:"):
            k = int(kind.split(":")[1])
            if not 0 <= k < nk:
                return ""
            x, y = int(u * nx), int(v * ny)
        elif kind == "xy":
            x, y = int(u * nx), int(v * ny)
        elif kind == "xp":
            x, k = int(u * nx), int(v * nk)
        elif kind == "yp":
            y, k = int(u * ny), int(v * nk)
        else:
            return ""
        try:
            self.raw_reader.validate_identity()
            ox, oy, page, value = self.volume.original(k, y, x)
            return f"X {ox} · Y {oy} · Page {page + 1} · uint16 {value}"
        except (ValueError, OSError):
            return "원본 변경 · 다시 여세요"

    @Slot(int, float, float, int)
    def pickPlane(self, index, u, v, epoch):
        if (
            self.volume is not None
            and epoch == self.volume_revision
            and 0 <= index < len(self.volume.pixels)
        ):
            self.cursor[0] = index
            self.pick("xy", u, v)

    @Slot(str, float, float)
    def pick(self, kind, u, v):
        if self.volume is None or not 0 <= u < 1 or not 0 <= v < 1:
            return
        k, y, x = self.cursor
        nk, ny, nx = self.volume.pixels.shape
        if kind == "xy":
            x, y = int(u * nx), int(v * ny)
        elif kind == "xp":
            x, k = int(u * nx), int(v * nk)
        elif kind == "yp":
            y, k = int(u * ny), int(v * nk)
        else:
            return
        self.cursor = [k, y, x]
        self.dirty = True
        self.requestSlices()

    @Slot(float, float, float, float, float)
    def setCamera(self, rx, ry, px, py, distance):
        values = [rx, ry, px, py, distance]
        if (
            all(math.isfinite(v) for v in values)
            and 200 <= distance <= 3000
            and max(abs(v) for v in values[:4]) <= 10000
        ):
            self.camera = values
            self.dirty = True
            self.changed.emit()

    @Slot()
    def resetView(self):
        self.camera = [-25, 35, 0, 0, 650]
        self.cameraReset.emit()
        self.dirty = True
        self.changed.emit()

    @Slot(float, float)
    def setWindow(self, low, high):
        if (
            not math.isfinite(low)
            or not math.isfinite(high)
            or not 0 <= low < high <= 65535
        ):
            self.error = "0≤표시 최소<최대≤65535"
            self.changed.emit()
            return
        self.window = [low, high]
        self.window_explicit = True
        self.dirty = True
        if self.volume:
            self.requestSlices()
        self.changed.emit()

    def _remember(self):
        self.undo_stack.append((copy.deepcopy(self.tracks), self.track_id))
        self.undo_stack = self.undo_stack[-32:]
        self.dirty = True

    @Slot(str, str)
    def newTrack(self, name, reviewer):
        try:
            if not self.project or self.selected == "CURRENT" or self.volume is None:
                raise ValueError("프로젝트에 TIFF를 등록·저장하고 Volume을 생성하세요")
            if len(self.tracks) >= 100:
                raise ValueError("Track 100개 예산")
            track = assets.new_track(
                self.source, name, reviewer, self.project.project_id
            )
            self._remember()
            self.tracks.append(track)
            self.track_id = track["track_id"]
            self.changed.emit()
        except ValueError as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(str)
    def selectTrack(self, tid):
        if any(t["track_id"] == tid for t in self.tracks):
            self.track_id = tid
            self.changed.emit()

    @Slot(str, str, str)
    def record(self, kind, reviewer, status):
        try:
            if self.volume is None:
                raise ValueError("원본 Volume 필요")
            self.raw_reader.validate_identity()
            track = next(t for t in self.tracks if t["track_id"] == self.track_id)
            if assets.active_points(track)[1]:
                raise ValueError("Track 중단 상태 · 재개한 뒤 기록하세요")
            x, y, page, _ = self.volume.original(*self.cursor)
            geometry = (
                {"type": "POINT", "coordinates": [x, y]}
                if kind == "POINT"
                else {
                    "type": "RECTANGLE",
                    "coordinates": list(self.volume.selection["roi"]),
                }
                if kind == "RECTANGLE"
                else None
            )
            if geometry is None:
                raise ValueError("Point 또는 명시적 사각형만 지원")
            candidate = copy.deepcopy(track)
            assets.event(candidate, "UPSERT", page, geometry, reviewer, status)
            p = self.project.evolve(
                image_sources=tuple(
                    self.source if s.source_id == self.source.source_id else s
                    for s in self.project.image_sources
                )
            )
            assets.validate_track(candidate, p)
            self._remember()
            self.tracks[self.tracks.index(track)] = candidate
            self.requestSlices()
        except (ValueError, OSError, StopIteration) as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(str, str)
    def trackAction(self, action, reviewer):
        try:
            track = next(t for t in self.tracks if t["track_id"] == self.track_id)
            page = (
                self.volume.original(*self.cursor)[2]
                if action == "REMOVE" and self.volume
                else None
            )
            candidate = copy.deepcopy(track)
            assets.event(candidate, action, page, None, reviewer)
            p = self.project.evolve(
                image_sources=tuple(
                    self.source if s.source_id == self.source.source_id else s
                    for s in self.project.image_sources
                )
            )
            assets.validate_track(candidate, p)
            self._remember()
            self.tracks[self.tracks.index(track)] = candidate
            if self.volume:
                self.requestSlices()
            self.changed.emit()
        except (ValueError, OSError, StopIteration) as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(int)
    def goTrackPage(self, page):
        if self.volume and page in self.volume.selection["page_indices"]:
            self.setPage(self.volume.selection["page_indices"].index(page))
        else:
            self.message = "이 페이지는 선택 Volume에 없습니다. Page Range를 명시적으로 바꾸어 생성하세요"
            self.changed.emit()

    @Slot()
    def undo(self):
        if self.undo_stack and self.job != "save":
            self.tracks, self.track_id = self.undo_stack.pop()
            if self.volume:
                self.requestSlices()
            self.changed.emit()

    @Slot()
    def discardTracks(self):
        if self.job == "save":
            return
        self.tracks = copy.deepcopy(self.saved_tracks)
        self.undo_stack = []
        self.track_id = self.tracks[0]["track_id"] if self.tracks else ""
        self.dirty = False
        if self.volume:
            self.requestSlices()
        self.changed.emit()

    @Slot(str)
    def save(self, editor):
        if self.busy or self.volume is None:
            return
        if not self.project or not self.projects.path or self.selected == "CURRENT":
            self.error = "프로젝트에 현재 TIFF를 등록하고 디스크에 저장하세요"
            self.changed.emit()
            return
        if self.projects.busy or self.projects._analysis_busy():
            self.error = "다른 프로젝트 작업을 완료하세요"
            self.changed.emit()
            return
        if not editor.strip():
            self.error = "편집자 ID 필요"
            self.changed.emit()
            return
        p = self.project
        s = self.source
        path = self.projects.path
        tracks = copy.deepcopy(self.tracks)
        selection = copy.deepcopy(self.volume.selection)
        byte_order = self.volume.byte_order
        settings = {
            "cursor": list(self.cursor),
            "window": list(self.window),
            "camera": list(self.camera),
            "plane_limit": 12,
        }
        physical = self.physical
        previous = self.ref
        old = self.session
        expected = (
            self.projects.saved_snapshot.revision
            if self.projects.saved_snapshot
            else None
        )
        review = self._review().snapshot() if self._review() else None
        if review and review["selection"] != assets.review_selection(selection):
            self.error = "스택 추적 결과의 선택 영역과 Volume이 다릅니다 · 다시 실행하거나 선택을 되돌리세요"
            self.changed.emit()
            return

        def work(cancelled, progress):
            verified = verify_content_hash(
                s,
                cancelled=cancelled,
                progress=lambda d, t: progress(d, t, "저장 전 원본 SHA"),
            )
            q = p.evolve(
                image_sources=tuple(
                    verified if r.source_id == s.source_id else r
                    for r in p.image_sources
                )
            )
            refs = []
            for t in tracks:
                assets.validate_track(t, q)
                refs.append(assets.publish(path, t))
            a = {
                "schema": assets.SESSION,
                "project_id": q.project_id,
                "source_id": s.source_id,
                "source_sha256": verified.content_hash.value,
                "stack_page_count": s.page_count,
                "original_shape": selection["original_shape"],
                "dtype": "uint16",
                "byte_order": byte_order,
                "selection": selection,
                "coordinate_mode": "PHYSICAL" if physical else "INDEXED",
                "calibration": physical_calibration(verified, s.page_count)
                if physical
                else None,
                "settings": settings,
                "tracks": refs,
                "revision": old["revision"] + 1 if old else 1,
                "session_id": old["session_id"] if old else str(uuid4()),
                "revision_id": str(uuid4()),
                "parent_reference": previous,
                "created_at": utc_now().isoformat(),
                "editor_id": editor.strip(),
                assets.REVIEW_KEY: None,
            }
            saved_review = None
            if review:
                result_ref = assets.publish(path, review["result"], compact=True)
                meta = review["meta"]
                saved_review = assets.new_review(
                    verified, q.project_id, result_ref, selection,
                    meta["creator"] or editor.strip(),
                )
                saved_review.update(
                    review_id=meta["review_id"],
                    created_at=meta["created_at"],
                    events=review["events"],
                    revision=len(review["events"]),
                )
                assets.validate_review(saved_review, q, a)
                a[assets.REVIEW_KEY] = assets.publish(path, saved_review)
            a["schema"] = assets.SESSION_V2
            assets.validate_session(a, q)
            if cancelled():
                raise InterruptedError("3D 저장 취소")
            ref = assets.publish(path, a)
            q = assets.attach(q, s.source_id, ref)
            ProjectStore().save(path, q, expected_revision=expected)
            return q, a, ref, verified, saved_review

        def publish(value):
            q, a, ref, verified, saved_review = value
            if saved_review and self._review():
                self._review().mark_saved(saved_review)
            self.project = q
            self.projects.project = self.projects.saved_snapshot = q
            self.projects.dirty = False
            self.ref = ref
            self.session = a
            self.source = verified
            self.saved_tracks = copy.deepcopy(tracks)
            self.undo_stack = []
            self.dirty = False
            self.message = "불변 3D 세션·Track revision 저장 완료"
            self.projects.changed.emit()

        self._start("save", work, publish)

    @Slot()
    def openOriginal(self):
        if self.volume is None or self.source is None or self.projects.busy:
            return
        s = self.source
        position = self.volume.original(*self.cursor)[:3]

        def work(cancelled, progress):
            return verify_content_hash(
                s,
                cancelled=cancelled,
                progress=lambda done, total: progress(
                    done, total, "원본 2D 복귀 전 SHA 검증"
                ),
            )

        def publish(verified):
            self.pending_navigation = (verified, position)
            self.focus_attempts = 0
            current = self.bridge.original_source
            if current and current.path == verified.source_reference:
                self.focus_timer.start(0)
            elif self.selected != "CURRENT":
                self._navigation_clear = True
                self.projects.selectSource(self.selected, "")
            else:
                self.sourceRequested.emit(verified.source_reference)
            self.workspaceRequested.emit(0)

        self._start("navigate", work, publish)

    def _focus(self):
        pending = self.pending_navigation
        if not pending:
            return
        s, (x, y, page) = pending
        current = self.bridge.original_source
        self.focus_attempts += 1
        if self.focus_attempts > 1200:
            self.pending_navigation = None
            self.error = "원본 페이지 준비 시간 초과"
            self.changed.emit()
            return
        if not current or current.path != s.source_reference:
            self.focus_timer.start(100)
            return
        try:
            current.validate_identity()
        except (ValueError, OSError):
            self.pending_navigation = None
            return
        if (current.identity.file_size, current.identity.mtime_ns) != (
            s.file_identity.file_size,
            s.file_identity.mtime_ns,
        ):
            self.pending_navigation = None
            self.error = "원본 identity 변경"
            self.changed.emit()
            return
        if self.bridge.stack_viewer.initial_loading or current.page_index != page:
            stack = self.bridge.stack_viewer
            if not stack.initial_loading and not (
                stack.busy and stack.requested_page == page
            ):
                self.bridge.requestPage(page)
            self.focus_timer.start(100)
            return
        self.pending_navigation = None
        self._navigation_clear = False
        self.focusRequested.emit(float(x), float(y))
        self.changed.emit()

    @Property("QVariantMap", notify=renderChanged)
    def scene(self):
        return self.frame

    @Property("QVariantMap", notify=changed)
    def state(self):
        s = self.source
        selection = None
        estimate_error = ""
        if s:
            try:

                class Header:
                    metadata = type(
                        "M",
                        (),
                        {
                            "format": "TIFF",
                            "channels": s.channels,
                            "dtype": s.dtype,
                            "page_count": s.page_count,
                            "height": s.height,
                            "width": s.width,
                        },
                    )()

                    def validate_region(self, x, y, w, h):
                        if (
                            x < 0
                            or y < 0
                            or w <= 0
                            or h <= 0
                            or x + w > s.width
                            or y + h > s.height
                        ):
                            raise ValueError("ROI 원본 경계 오류")

                selection = plan(Header(), self.roi, *self.page_range, self.xy_step)
            except (ValueError, OSError) as e:
                estimate_error = str(e)
        selected = next(
            (t for t in self.tracks if t["track_id"] == self.track_id), None
        )
        points, paused = assets.active_points(selected) if selected else ({}, False)
        position = (
            self.volume.original(*self.cursor) if self.volume is not None else None
        )
        proof = physical_calibration(s, s.page_count) if s else None
        backend = next(
            (
                str(w.rendererInterface().graphicsApi())
                for w in QGuiApplication.allWindows()
                if hasattr(w, "rendererInterface")
            ),
            "Unknown",
        )
        return {
            "backend": backend,
            "rhi_available": any(
                k in backend for k in ("Direct3D", "OpenGL", "Vulkan", "Metal")
            ),
            "sources": self.sources,
            "selected": self.selected,
            "source": {
                "name": s.display_name,
                "path": s.source_reference,
                "width": s.width,
                "height": s.height,
                "pages": s.page_count,
                "dtype": s.dtype,
                "source_id": s.source_id,
                "sha256": s.content_hash.value if s.content_hash else "",
                "status": next(
                    (r["status"] for r in self.sources if r["id"] == self.selected),
                    "MISSING",
                ),
            }
            if s
            else {},
            "roi": self.roi,
            "page_range": self.page_range,
            "xy_step": self.xy_step,
            "estimate": selection or {},
            "estimate_error": estimate_error,
            "busy": self.busy,
            "job": self.job,
            "error": self.error,
            "message": self.message,
            "progress": self.progress,
            "ready": self.volume is not None,
            "shape": list(self.volume.pixels.shape) if self.volume else [0, 0, 0],
            "volume_revision": self.volume_revision,
            "cursor": self.cursor,
            "position": list(position) if position else [],
            "window": self.window,
            "camera": self.camera,
            "physical_available": proof is not None,
            "physical": self.physical,
            "physical_status": "PHYSICAL_3D_NOT_READY"
            if not proof
            else "EXISTING_SOURCE_CALIBRATION_AVAILABLE",
            "manual_pending": self.manual_pending,
            "tracks": [
                {"id": t["track_id"], "name": t["name"], "revision": t["revision"]}
                for t in self.tracks
            ],
            "track_id": self.track_id,
            "track_points": [
                {
                    "page": k,
                    "status": e["status"],
                    "type": e["geometry"]["type"],
                    "reviewer": e["reviewer"],
                    "coordinates": e["geometry"]["coordinates"],
                }
                for k, e in sorted(points.items())
            ],
            "track_paused": paused,
            "dirty": self.dirty,
            "undo": bool(self.undo_stack),
            "project": bool(self.project),
            "saved": bool(self.session),
            "history_revision": self.session["revision"] if self.session else 0,
            "raw_bytes": self.volume.pixels.nbytes if self.volume else 0,
            "byte_order": self.volume.byte_order if self.volume else "",
            "texture_bytes": self.frame.get("texture_bytes", 0),
            "slice_prepare_ms": self.frame.get("prepare_ms", 0),
        }

    def shutdown(self):
        self.focus_timer.stop()
        self.pending_navigation = None
        self.cancel(False)
        self.reader.shutdown()
        self.release()
