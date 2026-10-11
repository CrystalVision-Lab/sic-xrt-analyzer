"""Viewport-sized painting from prepared levels, without an overview fallback."""
import math

from PySide6.QtCore import Property, QRectF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtQml import qmlRegisterType
from PySide6.QtQuick import QQuickPaintedItem

from sic_xrt_analyzer.imaging.original_source import SourceError
from sic_xrt_analyzer.imaging.tiff_stack import render_samples


class PreparedView(QQuickPaintedItem):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = None
        self._transform = [0., 0., 1.]
        self._revision = 0
        self.setOpaquePainting(False)

    @Property('QVariant', notify=changed)
    def bridge(self):
        return self._bridge

    @bridge.setter
    def bridge(self, value):
        self._bridge = value
        self.update()

    @Property('QVariantList', notify=changed)
    def viewTransform(self):
        return self._transform

    @viewTransform.setter
    def viewTransform(self, value):
        self._transform = value
        self.update()

    @Property(int, notify=changed)
    def revision(self):
        return self._revision

    @revision.setter
    def revision(self, value):
        self._revision = value
        self.update()

    def paint(self, painter):
        frame = self._bridge.stack_viewer.frame if self._bridge else None
        pyramid = getattr(frame.source, 'display_pyramid', None) if frame else None
        if pyramid is None or pyramid.closed:
            return
        try:
            frame.source.validate_identity()
        except SourceError as exc:
            self._bridge.stack_viewer.error = str(exc)
            self._bridge.stack_viewer.changed.emit()
            return
        ox, oy, scale = self._transform
        if scale <= 0:
            return
        meta = frame.source.metadata
        x, y = max(0, math.floor(-ox / scale)), max(0, math.floor(-oy / scale))
        right = min(meta.width, math.ceil((self.width() - ox) / scale))
        bottom = min(meta.height, math.ceil((self.height() - oy) / scale))
        if right <= x or bottom <= y:
            return
        ratio = self.window().devicePixelRatio() if self.window() else 1
        pixels, left, top, factor = pyramid.region(scale * ratio, x, y, right - x, bottom - y)
        preview = render_samples(pixels, frame.source, frame.low, frame.high, getattr(pyramid, 'invert', False))
        # Smooth reduction; exact nearest-neighbour source pixels at 100% and up.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, scale * ratio < 1)
        painter.drawImage(QRectF(ox + left * scale, oy + top * scale,
                                pixels.shape[1] * factor * scale, pixels.shape[0] * factor * scale), preview.image)


qmlRegisterType(PreparedView, 'XrtViewer', 1, 0, 'PreparedView')
