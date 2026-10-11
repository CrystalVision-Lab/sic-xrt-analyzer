"""Resident all-page browsing, prioritized raw reads, and replaceable latest requests."""
import math
from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack


@dataclass(frozen=True)
class _Request:
    serial: int
    path: str
    page: int
    window: tuple | None
    opening: bool = False
    automatic: bool = False
    closing: bool = False
    prefetch: bool = False
    browse: bool = False
    epoch: int = 0


class _Signals(QObject):
    done = Signal(object, object, str)


class _Reader:
    def __init__(self, preload_enabled):
        self.stack = None
        self.preload_enabled = preload_enabled

    def read(self, request, token):
        if token.is_set():
            return None
        if request.closing:
            self.close()
            return None
        if request.opening or self.stack is None or self.stack.path != request.path:
            self.close()
            self.stack = TiffStack(request.path, browse_enabled=self.preload_enabled)
        if request.browse:
            self.stack.prepare_browse(request.page, request.window, canceled=token.is_set)
            return None
        return self.stack.frame(request.page, request.window, automatic=request.automatic, canceled=token.is_set)

    def close(self):
        if self.stack:
            self.stack.close()
            self.stack = None


class _Task(QRunnable):
    def __init__(self, reader, request):
        super().__init__()
        self.reader, self.request = reader, request
        self.token = Event()
        self.signals = _Signals()

    def run(self):
        frame, error = None, ""
        try:
            frame = self.reader.read(self.request, self.token)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        self.signals.done.emit(self.request, frame, error)


class StackController(QObject):
    changed = Signal()
    frameReady = Signal(object, bool)
    failed = Signal(str, bool)

    def __init__(self, parent=None, *, prefetch_enabled=True, preload_enabled=True):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._reader = _Reader(preload_enabled)
        self._task = self._pending = None
        self._serial = 0
        self.frame = None
        self.requested_page = 0
        self.window = None
        self.error = ""
        self.busy = False
        self._closed = False
        self._epoch = 0
        self._preload_enabled = preload_enabled
        self.preload_error = ""
        self.detail_busy = False
        self.scrubbing = False
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(80)
        self._detail_timer.timeout.connect(self._detail)
        self._prefetch_enabled = prefetch_enabled
        self._neighbors = []
        self._direction = 1
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(30)
        self._prefetch_timer.timeout.connect(self._prefetch)

    def _submit(self, path, page, window, *, opening=False, automatic=False, detail=False):
        if self._closed:
            return
        self._prefetch_timer.stop()
        self._detail_timer.stop()
        self._neighbors.clear()
        self._serial += 1
        self.requested_page = page
        self.error, self.busy, self.detail_busy = "", not detail, detail
        self._pending = _Request(self._serial, path, page, window, opening, automatic,
                                 epoch=self._epoch)
        if self._task:
            self._task.token.set()
        else:
            self._launch()
        self.changed.emit()

    def _launch(self):
        request, self._pending = self._pending, None
        self._task = _Task(self._reader, request)
        self._task.signals.done.connect(self._done)
        self._pool.start(self._task)

    def open(self, path):
        self._epoch += 1
        self.preload_error = ""
        self.scrubbing = False
        self.window = None
        self._submit(path, 0, None, opening=True)

    def page(self, index):
        if self._closed or self.frame is None or type(index) is not int or not 0 <= index < self.frame.source.metadata.page_count:
            return False
        if index != self.requested_page:
            self._direction = 1 if index > self.requested_page else -1
        stack = self._reader.stack
        cached = None
        if stack is not None and stack.path == self.frame.source.path:
            try:
                cached = None if self.scrubbing else stack.cached_frame(index, self.window)
                if cached is None and self.window is not None:
                    cached = stack.browse_frame(index, self.frame, self.window, validate=not self.scrubbing)
            except (OSError, ValueError):
                pass  # Worker reports source errors through the normal error signal.
        if cached is not None:
            # Publish on this GUI event, including while a canceled prefetch finishes.
            self._serial += 1
            self._detail_timer.stop()
            self._pending = None
            if self._task and not self._task.request.browse:
                self._task.token.set()
            self.requested_page = index
            self.error, self.busy, self.detail_busy = "", False, cached.pixels is None
            self._publish(cached, False)
            if cached.pixels is None and not self.scrubbing:
                self._detail_timer.start()
            self.changed.emit()
            return True
        self._submit(self.frame.source.path, index, self.window)
        return True

    def begin_scrub(self):
        self.scrubbing = True
        self._detail_timer.stop()
        self._serial += 1
        self._pending = None
        self.busy = False
        if self._task and not self._task.request.browse:
            self._task.token.set()

    def end_scrub(self):
        if not self.scrubbing:
            return
        self.scrubbing = False
        if self.frame is not None and (self.frame.pixels is None or self.frame.source.page_index != self.requested_page):
            self._detail()

    def _detail(self):
        if not self._closed and not self.scrubbing and self.frame is not None:
            self._submit(self.frame.source.path, self.requested_page, self.window, detail=True)

    @property
    def preload_state(self):
        stack = self._reader.stack
        if stack is None or stack.browse is None or self.frame is None or stack.path != self.frame.source.path:
            return {"prepared": 0, "total": 0, "ready": False, "bytes": 0}
        count = len(stack.browse.indices)
        return {"prepared": count, "total": stack.page_count, "ready": count == stack.page_count,
                "bytes": stack.browse.bytes}

    def retry_preload(self):
        self.preload_error = ""
        if self._preload_enabled and not self._closed:
            self._prefetch_timer.start(0)
        self.changed.emit()

    def _publish(self, frame, opening):
        self.frame = frame
        self.window = (frame.low, frame.high)
        self.frameReady.emit(frame, opening)
        stack = self._reader.stack
        capacity = 0 if stack is None or frame.pixels is None else min(stack.max_cache_pages,
                                              stack.max_cache_bytes // frame.pixels.nbytes,
                                              stack.max_display_bytes // frame.preview.image.sizeInBytes())
        # Do not prefetch pages that would evict the displayed page from a tiny cache.
        self._neighbors = [frame.source.page_index + self._direction,
                           frame.source.page_index - self._direction][:max(0, capacity - 1)]
        if (self._prefetch_enabled or self._preload_enabled) and not self._closed:
            self._prefetch_timer.start()

    def _prefetch(self):
        if self._closed or self.busy or self.frame is None or self._task or self._pending:
            return
        if self._preload_enabled:
            stack = self._reader.stack
            if self.preload_error or stack is None or stack.path != self.frame.source.path or stack.browse is None:
                return
            prepared = stack.browse.indices
            for index in range(stack.page_count):
                if index not in prepared:
                    self._pending = _Request(self._serial, stack.path, index, self.window, prefetch=True,
                                             browse=True, epoch=self._epoch)
                    self._launch()
                    return
            return
        while self._neighbors:
            index = self._neighbors.pop(0)
            if not 0 <= index < self.frame.source.metadata.page_count:
                continue
            stack = self._reader.stack
            if stack is None or stack.path != self.frame.source.path:
                return
            try:
                if stack.cached_frame(index, self.window) is not None:
                    continue
            except (OSError, ValueError):
                return
            self._pending = _Request(self._serial, stack.path, index, self.window, prefetch=True)
            self._launch()
            return

    def display_range(self, low, high, *, automatic=False):
        if self.frame is None:
            return False
        if not automatic and (not math.isfinite(low) or not math.isfinite(high) or low >= high):
            self.error = "표시 최솟값은 최댓값보다 작아야 합니다"
            self.changed.emit()
            return False
        if not automatic:
            self.window = (low, high)
        self._submit(self.frame.source.path, self.requested_page, self.window, automatic=automatic)
        return True

    @Slot(object, object, str)
    def _done(self, request, frame, error):
        canceled = self._task.token.is_set()
        self._task = None
        if request.browse and not canceled and request.epoch == self._epoch and not self._closed:
            if error:
                self.preload_error = error
            self.changed.emit()
        if not request.prefetch and request.serial == self._serial and not self._closed:
            self.busy = self.detail_busy = False
            if error:
                self.error = error
                if self.frame is not None:
                    self.requested_page = self.frame.source.page_index
                    self.window = (self.frame.low, self.frame.high)
                self.failed.emit(error, request.opening)
            elif frame is not None:
                self._publish(frame, request.opening)
            self.changed.emit()
        if self._pending is not None:
            self._launch()
        elif (self._preload_enabled or (self._neighbors and self._prefetch_enabled)) and not self._closed:
            self._prefetch_timer.start(0 if self._preload_enabled else 30)

    def pixel_value(self, x, y):
        if self.frame is None or self.frame.pixels is None:
            return ""
        pixels = self.frame.pixels
        if not 0 <= x < pixels.shape[1] or not 0 <= y < pixels.shape[0]:
            return ""
        value = pixels[y, x]
        if pixels.ndim == 3:
            return ", ".join(str(v.item()) for v in value)
        return str(value.item())

    def clear(self):
        self._epoch += 1
        self._detail_timer.stop()
        self.scrubbing = False
        self.detail_busy = False
        self.preload_error = ""
        self._prefetch_timer.stop()
        self._neighbors.clear()
        self._serial += 1
        self.frame = self.window = self._pending = None
        self.busy, self.error = False, ""
        if self._task:
            self._task.token.set()
            # Queue cache cleanup after the active reader releases the file.
            self._pending = _Request(self._serial, "", 0, None, closing=True)
        else:
            self._reader.close()
        self.changed.emit()

    def shutdown(self):
        self._closed = True
        self._prefetch_timer.stop()
        self._detail_timer.stop()
        self._neighbors.clear()
        self._pending = None
        if self._task:
            self._task.token.set()
        self._pool.waitForDone()
        self._reader.close()
        self.frame = None
