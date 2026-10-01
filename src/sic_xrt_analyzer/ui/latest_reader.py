"""One worker with a replaceable pending read and stale-result rejection."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    done = Signal(int, object, str)


class _Read(QRunnable):
    def __init__(self, serial, function):
        super().__init__()
        self.serial, self.function = serial, function
        self.signals = _Signals()

    def run(self):
        value, error = None, ''
        try:
            value = self.function()
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        self.signals.done.emit(self.serial, value, error)


class LatestReader(QObject):
    ready = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.serial = 0
        self.task = self.pending = None
        self.closed = False

    def submit(self, function):
        if self.closed:
            return
        self.serial += 1
        self.pending = (self.serial, function)
        if self.task is None:
            self._launch()

    def _launch(self):
        serial, function = self.pending
        self.pending = None
        self.task = _Read(serial, function)
        self.task.signals.done.connect(self._done)
        self.pool.start(self.task)

    @Slot(int, object, str)
    def _done(self, serial, value, error):
        self.task = None
        if not self.closed and serial == self.serial:
            self.ready.emit(value, error)
        if self.pending is not None and not self.closed:
            self._launch()

    def invalidate(self):
        self.serial += 1
        self.pending = None

    def shutdown(self):
        self.closed = True
        self.invalidate()
        self.pool.waitForDone()
