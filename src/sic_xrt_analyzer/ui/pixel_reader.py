"""Debounced exact pixels for sampled 2D images; never report display-grid samples."""
from PySide6.QtCore import QObject, QTimer, Signal

from .latest_reader import LatestReader


class PixelReader(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._read)
        self.requested = self.tile = self.failed_key = None
        self.error = ''
        self.revision = 0

    def value(self, source, x, y):
        if not 0 <= x < source.metadata.width or not 0 <= y < source.metadata.height:
            return ''
        identity = source.identity
        if self.tile is not None:
            key, left, top, pixels = self.tile
            if key == identity and left <= x < left + pixels.shape[1] and top <= y < top + pixels.shape[0]:
                value = pixels[y - top, x - left]
                return ', '.join(str(v.item()) for v in value) if pixels.ndim == 3 else str(value.item())
        key = (identity, x, y)
        if key != self.failed_key and (self.requested is None or key != self.requested[0]):
            self.reader.invalidate()
            self.requested = (key, source)
            self.timer.start()
        return ''

    def _read(self):
        if self.requested is None:
            return
        key, source = self.requested
        identity, x, y = key
        left, top = x // 128 * 128, y // 128 * 128
        width, height = min(128, source.metadata.width - left), min(128, source.metadata.height - top)
        self.reader.submit(lambda: (identity, left, top, source.read_region(left, top, width, height)))

    def _ready(self, value, error):
        self.error = error
        if error:
            self.failed_key = self.requested[0] if self.requested else None
        else:
            self.tile = value
            self.failed_key = None
        self.revision += 1
        self.changed.emit()

    def clear(self):
        self.timer.stop()
        self.reader.invalidate()
        self.requested = self.tile = self.failed_key = None
        self.error = ''
        self.revision += 1

    def shutdown(self):
        self.clear()
        self.reader.shutdown()
