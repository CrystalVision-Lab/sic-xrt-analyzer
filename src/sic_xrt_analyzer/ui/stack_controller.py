"""One active read/render and one replaceable latest request; GUI never decodes pixels."""
import math
from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

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


class _Signals(QObject):
    done = Signal(object, object, str)


class _Reader:
    def __init__(self):
        self.stack = None

    def read(self, request, token):
        if token.is_set():
            return None
        if request.closing:
            self.close()
            return None
        if request.opening or self.stack is None or self.stack.path != request.path:
            self.close()
            self.stack = TiffStack(request.path)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._reader = _Reader()
        self._task = self._pending = None
        self._serial = 0
        self.frame = None
        self.requested_page = 0
        self.window = None
        self.error = ""
        self.busy = False
        self._closed = False

    def _submit(self, path, page, window, *, opening=False, automatic=False):
        if self._closed:
            return
        self._serial += 1
        self.requested_page = page
        self.error, self.busy = "", True
        self._pending = _Request(self._serial, path, page, window, opening, automatic)
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
        self.window = None
        self._submit(path, 0, None, opening=True)

    def page(self, index):
        if self.frame is None or type(index) is not int or not 0 <= index < self.frame.source.metadata.page_count:
            return False
        self._submit(self.frame.source.path, index, self.window)
        return True

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
        self._task = None
        if request.serial == self._serial and not self._closed:
            self.busy = False
            if error:
                self.error = error
                if self.frame is not None:
                    self.requested_page = self.frame.source.page_index
                    self.window = (self.frame.low, self.frame.high)
                self.failed.emit(error, request.opening)
            elif frame is not None:
                self.frame = frame
                self.window = (frame.low, frame.high)
                self.frameReady.emit(frame, request.opening)
            self.changed.emit()
        if self._pending is not None:
            self._launch()

    def pixel_value(self, x, y):
        if self.frame is None:
            return ""
        pixels = self.frame.pixels
        if not 0 <= x < pixels.shape[1] or not 0 <= y < pixels.shape[0]:
            return ""
        value = pixels[y, x]
        if pixels.ndim == 3:
            return ", ".join(str(v.item()) for v in value)
        return str(value.item())

    def clear(self):
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
        self._pending = None
        if self._task:
            self._task.token.set()
        self._pool.waitForDone()
        self._reader.close()
        self.frame = None
