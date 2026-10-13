"""Cancellable seed-connected surface reconstruction for the normal 3D workspace."""

from threading import Event

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.stack3d.defect import trace

from .latest_reader import LatestReader
from .stack3d_geometry import register_types


class Defect3DController(QObject):
    changed = Signal()
    meshChanged = Signal()
    _progress = Signal(int, int, int, str)

    def __init__(self, bridge):
        super().__init__(bridge)
        register_types()
        self.bridge = bridge
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
    def start(self, x, y, page=None):
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
        self.token = Event()
        token = self.token
        epoch = self.epoch
        self.path = source.path
        self.busy = True
        self.error = ""
        self.mesh = None
        self.progress = [0, source.metadata.page_count, "선택 결함 확인"]
        seed = (int(x), int(y), source.page_index)
        sensitivity = self.sensitivity
        self.meshChanged.emit()
        self.changed.emit()
        self.reader.submit(
            lambda: trace(
                source,
                seed,
                sensitivity=sensitivity,
                cancelled=token.is_set,
                progress=lambda d, t, l: self._progress.emit(epoch, d, t, l),
            )
        )
        return True

    @Slot(float)
    def reconstruct(self, sensitivity):
        if self.busy:
            return
        seed = self.mesh.seed if self.mesh else None
        if seed and self.bridge.original_source:
            self.sensitivity = max(0.4, min(2.5, float(sensitivity)))
            self.start(seed[0], seed[1], seed[2])

    @Slot()
    def cancel(self):
        self.epoch += 1
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
            if m and any(reason == "AMBIGUOUS_MERGE" for _, reason in m.stops)
            else "",
        }

    def shutdown(self):
        self.cancel()
        self.reader.shutdown()
        self.mesh = None
        self.meshChanged.emit()
