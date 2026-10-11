"""Bounded native display crop for zoomed sampled single images."""
import numpy as np
import tifffile
from PySide6.QtCore import QObject, QTimer, Signal

from sic_xrt_analyzer.imaging.tiff_stack import render_samples

from .latest_reader import LatestReader


class DetailReader(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self._read)
        self.requested = self.result = None
        self.error = ''
        self.busy = False
        self.revision = 0

    def request(self, frame, x, y, width, height):
        source = frame.source
        if width <= 0 or height <= 0 or max(width, height) > 2048:
            self.clear()
            return
        size = width * height * source.metadata.channels * max(4, np.dtype(source.metadata.dtype).itemsize)
        if size > 32 * 1024**2:
            self.clear()
            return
        key = (source.identity, x, y, width, height, frame.low, frame.high)
        if self.requested and self.requested[0] == key:
            return
        self.reader.invalidate()
        self.requested = (key, frame)
        self.result = None
        self.busy, self.error = True, ''
        self.timer.start()
        self.changed.emit()

    def _read(self):
        key, frame = self.requested
        _, x, y, width, height, low, high = key
        source = frame.source
        def read():
            pixels = source.read_region(x, y, width, height)
            invert = False
            if source.metadata.format == 'TIFF':
                with tifffile.TiffFile(source.path) as tif:
                    invert = tif.pages[source.page_index].photometric == tifffile.PHOTOMETRIC.MINISWHITE
            preview = render_samples(pixels, source, low, high, invert)
            source.validate_identity()
            return key, preview.image
        self.reader.submit(read)

    def _ready(self, result, error):
        self.busy, self.error = False, error
        self.result = None if error else result
        self.revision += 1
        self.changed.emit()

    def clear(self):
        if self.requested is None and not self.busy and self.result is None and not self.error:
            return
        self.timer.stop()
        self.reader.invalidate()
        self.requested = self.result = None
        self.busy, self.error = False, ''
        self.revision += 1
        self.changed.emit()

    def shutdown(self):
        self.clear()
        self.reader.shutdown()
