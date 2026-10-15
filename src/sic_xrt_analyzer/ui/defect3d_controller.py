"""Cancellable seed-connected surface reconstruction for the normal 3D workspace."""

from threading import Event

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.stack3d.defect import trace

from .latest_reader import LatestReader
from .stack3d_geometry import register_types


class Defect3DController(QObject):
    changed = Signal()
    meshChanged = Signal()
    layersChanged = Signal()
    _frame = Signal(int, object)
    _progress = Signal(int, int, int, str)

    def __init__(self, bridge):
        super().__init__(bridge)
        register_types()
        self.bridge = bridge
        self.layers_data = (None, None)
        self.visual = False
        self.paused = False
        self.phase = 0
        self.frame_revision = 0
        self.frame_page = 0
        self.frame_reason = ""
        self.crop_rect = [0, 0, 1, 1]
        self.ack = Event()
        self.fast = Event()
        self.exclusions = {}
        self.last_seed = None
        self.replay_index = -1
        self.replaying = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance_frame)
        self._frame.connect(self._on_frame)
        self.replay_reader = LatestReader(self)
        self.replay_reader.ready.connect(self._replay_ready)
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.epoch = 0
        self.token = Event()
        self.mesh = None
        self.busy = False
        self.error = ""
        self.progress = [0, 0, ""]
        self.path = ""
        self.sensitivity = 1.0
        self._progress.connect(self._on_progress)
        bridge.imageOpened.connect(self.bindSource)

    @Slot()
    def bindSource(self, *args):
        source = self.bridge.original_source
        stale = (
            self.mesh
            and source
            and (
                self.mesh.source_identity.file_size,
                self.mesh.source_identity.mtime_ns,
            )
            != (source.identity.file_size, source.identity.mtime_ns)
        )
        if source is None or source.path != self.path or stale:
            self.cancel()
            self.mesh = None
            self.exclusions = {}
            self.bridge.provider.stack3d_images = {}
            self.path = source.path if source else ""
            self.meshChanged.emit()
            self.changed.emit()

    def openingFile(self, path):
        if self.path and str(path) != self.path:
            self.cancel()
            self.mesh = None
            self.meshChanged.emit()
            self.changed.emit()

    @Slot(float, float, result=bool)
    def start(self, x, y, page=None, visual=False, keep_exclusions=False):
        source = self.bridge.original_source
        if (
            source is None
            or source.metadata.page_count < 2
            or source.metadata.channels != 1
        ):
            self.error = "여러 페이지 흑백 TIFF를 열어주세요"
            self.changed.emit()
            return False
        if not 0 <= x < source.metadata.width or not 0 <= y < source.metadata.height:
            return False
        if page is not None and source.page_index != page:
            from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

            source = OriginalImageSource(source.path, page)
        self.cancel()
        if not keep_exclusions:
            self.exclusions = {}
        self.visual = visual
        self.paused = False
        self.phase = 0
        self.layers_data = (None, None)
        self.layersChanged.emit()
        self.frame_revision = 0
        self.ack = Event()
        self.fast = Event()
        self.token = Event()
        token = self.token
        epoch = self.epoch
        self.path = source.path
        self.busy = True
        self.error = ""
        self.mesh = None
        self.progress = [0, source.metadata.page_count, "선택 결함 확인"]
        seed = (int(x), int(y), source.page_index)
        self.last_seed = seed
        sensitivity = self.sensitivity
        exclusions = {k: tuple(v) for k, v in self.exclusions.items()}
        ack, fast = self.ack, self.fast
        built = []

        def observe(page, raw, section, reason):
            if token.is_set():
                raise InterruptedError("결함 추적 취소")
            if visual and not fast.is_set():
                from sic_xrt_analyzer.stack3d.presentation import (
                    frame_images,
                    layer_vertices,
                )

                full, crop, rect = frame_images(raw, section, reason == "ACCEPTED")
                packet = {
                    "page": page,
                    "full": full,
                    "crop": crop,
                    "rect": rect,
                    "reason": reason,
                    "built": layer_vertices(built, seed, source.metadata.page_count),
                    "current": layer_vertices(
                        [section] if section and reason == "ACCEPTED" else [],
                        seed,
                        source.metadata.page_count,
                    ),
                }
                ack.clear()
                self._frame.emit(epoch, packet)
                while not ack.wait(0.05):
                    if token.is_set():
                        raise InterruptedError("결함 추적 취소")
            if section and reason == "ACCEPTED":
                built.append(section)

        self.meshChanged.emit()
        self.changed.emit()
        self.reader.submit(
            lambda: trace(
                source,
                seed,
                sensitivity=sensitivity,
                observe=observe,
                exclusions=exclusions,
                cancelled=token.is_set,
                progress=lambda d, t, l: self._progress.emit(epoch, d, t, l),
            )
        )
        return True

    @Slot(float, float, result=bool)
    def startVisual(self, x, y):
        return self.start(x, y, visual=True)

    def _on_frame(self, epoch, packet):
        if epoch != self.epoch or not self.busy or self.fast.is_set():
            return
        self._display_packet(packet)

    def _display_packet(self, packet):
        self.bridge.provider.stack3d_images = {
            "trace-full": packet["full"],
            "trace-crop": packet["crop"],
        }
        self.crop_rect = packet["rect"]
        self.frame_page, self.frame_reason = packet["page"], packet["reason"]
        self.layers_data = (packet["built"], packet["current"])
        self.phase = 0
        self.frame_revision += 1
        self.layersChanged.emit()
        self.changed.emit()
        if not self.paused:
            self.timer.start(300)

    def _advance_frame(self):
        if self.phase == 0:
            self.phase = 1
            self.changed.emit()
            if not self.paused:
                self.timer.start(450)
        elif self.replaying:
            self._next_replay()
        else:
            self.ack.set()

    @Slot()
    def togglePause(self):
        self.paused = not self.paused
        if self.paused:
            self.timer.stop()
        else:
            self.timer.start(1)
        self.changed.emit()

    @Slot()
    def stepFrame(self):
        self.timer.stop()
        self.paused = True
        if self.phase == 0:
            self.phase = 1
        elif self.replaying:
            self._next_replay()
        else:
            self.ack.set()
        self.changed.emit()

    @Slot()
    def fastFinish(self):
        self.timer.stop()
        self.fast.set()
        self.ack.set()
        self.replaying = False
        self.visual = False
        self.changed.emit()

    @Slot(bool)
    def setPresented(self, visible):
        if not visible:
            self.fastFinish()

    @Slot()
    def replay(self):
        if not self.mesh or self.busy:
            return
        self.visual = True
        self.replaying = True
        self.paused = False
        self.replay_index = -1
        self._next_replay()

    def _next_replay(self):
        self.replay_index += 1
        mesh, index, epoch = self.mesh, self.replay_index, self.epoch
        if not mesh or index >= len(mesh.observations):
            self.replaying = False
            self.visual = False
            self.changed.emit()
            return
        from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
        from sic_xrt_analyzer.stack3d.presentation import frame_images, layer_vertices

        source = OriginalImageSource(self.path, mesh.observations[index][0])

        def read():
            raw = source.read_full()
            if (
                source.identity.file_size != mesh.source_identity.file_size
                or source.identity.mtime_ns != mesh.source_identity.mtime_ns
            ):
                raise ValueError("원본이 변경되어 재생할 수 없습니다")
            page, section, reason = mesh.observations[index]
            full, crop, rect = frame_images(raw, section, reason == "ACCEPTED")
            built = [
                s for _, s, r in mesh.observations[:index] if s and r == "ACCEPTED"
            ]
            return epoch, {
                "page": page,
                "full": full,
                "crop": crop,
                "rect": rect,
                "reason": reason,
                "built": layer_vertices(built, mesh.seed, source.metadata.page_count),
                "current": layer_vertices(
                    [section] if section and reason == "ACCEPTED" else [],
                    mesh.seed,
                    source.metadata.page_count,
                ),
            }

        self.replay_reader.submit(read)

    def _replay_ready(self, value, error):
        if error:
            self.error = error
            self.replaying = False
            self.changed.emit()
        elif value and value[0] == self.epoch and self.replaying:
            self._display_packet(value[1])

    @Slot(float, float)
    def exclude(self, x, y):
        seed = self.last_seed
        if not seed:
            return
        page = self.frame_page
        points = self.exclusions.setdefault(page, [])
        if len(points) >= 16:
            return
        points.append((int(x), int(y)))
        self.start(seed[0], seed[1], seed[2], visual=True, keep_exclusions=True)

    @Slot(float)
    def reconstruct(self, sensitivity):
        if self.busy:
            return
        seed = self.mesh.seed if self.mesh else None
        if seed and self.bridge.original_source:
            self.sensitivity = max(0.4, min(2.5, float(sensitivity)))
            self.start(seed[0], seed[1], seed[2], visual=True)

    @Slot()
    def cancel(self):
        self.epoch += 1
        self.timer.stop()
        self.ack.set()
        self.fast.set()
        self.replaying = False
        self.visual = False
        self.frame_revision = 0
        self.layers_data = (None, None)
        self.layersChanged.emit()
        self.replay_reader.invalidate()
        self.token.set()
        self.reader.invalidate()
        self.busy = False
        self.changed.emit()

    def _on_progress(self, epoch, done, total, label):
        if epoch == self.epoch and self.busy:
            self.progress = [done, total, label]
            self.changed.emit()

    def _ready(self, mesh, error):
        self.busy = False
        source = self.bridge.original_source
        if error:
            self.error = error
            self.visual = False
            self.timer.stop()
        elif source and mesh and source.path == self.path:
            try:
                source.validate_identity()
            except ValueError:
                self.error = "원본이 변경되어 다시 선택해야 합니다"
            else:
                if (mesh.source_identity.file_size, mesh.source_identity.mtime_ns) == (
                    source.identity.file_size,
                    source.identity.mtime_ns,
                ):
                    self.mesh = mesh
                    self.visual = False
                    self.meshChanged.emit()
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        m = self.mesh
        backend = next(
            (
                str(w.rendererInterface().graphicsApi())
                for w in QGuiApplication.allWindows()
                if hasattr(w, "rendererInterface")
            ),
            "Unknown",
        )
        return {
            "displayExtent": max(
                m.bounds[3] - m.bounds[0],
                m.bounds[4] - m.bounds[1],
                m.bounds[5] - m.bounds[2],
            )
            * 350
            / max(128, self.bridge.original_source.metadata.page_count)
            if m and self.bridge.original_source
            else 200,
            "visual": self.visual,
            "replaying": self.replaying,
            "paused": self.paused,
            "phase": self.phase,
            "frameRevision": self.frame_revision,
            "framePage": self.frame_page + 1,
            "frameReason": self.frame_reason,
            "cropRect": self.crop_rect,
            "sourceSize": [
                self.bridge.original_source.metadata.width,
                self.bridge.original_source.metadata.height,
            ]
            if self.bridge.original_source
            else [1, 1],
            "backend": backend,
            "rhi_available": any(
                k in backend for k in ("Direct3D", "OpenGL", "Vulkan", "Metal")
            ),
            "ready": m is not None,
            "busy": self.busy,
            "error": self.error,
            "progress": self.progress,
            "pages": len(m.sections) if m else 0,
            "voxels": m.voxels if m else 0,
            "faces": len(m.faces) if m else 0,
            "xyStep": m.xy_step if m else 1,
            "sensitivity": self.sensitivity,
            "seed": list(m.seed) if m else [],
            "warning": "일부 페이지의 연결이 모호해 추적을 멈췄습니다"
            if m
            and any(
                reason in ("AMBIGUOUS_MERGE", "AMBIGUOUS_BRANCH")
                for _, reason in m.stops
            )
            else "",
        }

    def shutdown(self):
        self.cancel()
        self.replay_reader.shutdown()
        self.reader.shutdown()
        self.mesh = None
        self.meshChanged.emit()
