"""Viewport-sized painting from prepared levels, without an overview fallback."""
import math

from PySide6.QtCore import Property, QRectF, Signal
from PySide6.QtGui import QImage, QPainter
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
        # One converted viewport with a small pan margin. This owns display
        # bytes only; source pixels, page caches and analysis stay untouched.
        self._display_cache = None
        self._display_cache_limit = 32 * 1024**2
        self.setOpaquePainting(False)

    @Property('QVariant', notify=changed)
    def bridge(self):
        return self._bridge

    @bridge.setter
    def bridge(self, value):
        self._bridge = value
        self._display_cache = None
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
            self._display_cache = None
            return
        try:
            frame.source.validate_identity()
        except SourceError as exc:
            self._display_cache = None
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
        level = min(len(pyramid.levels) - 1, max(0, math.floor(math.log2(1 / max(scale * ratio, 1e-9)))))
        factor = 2**level
        palette = getattr(frame.source, 'display_palette', None)
        key = (pyramid, frame.low, frame.high, getattr(pyramid, 'invert', False),
               None if palette is None else palette.tobytes(), level)
        cached = self._display_cache
        if not (cached is not None and cached[0] == key and
                cached[1] <= x and cached[2] <= y and
                cached[3] >= right and cached[4] >= bottom):
            # 128 physical screen pixels on each side, aligned to the selected
            # existing level. Limit retained QImage bytes even on large screens.
            margin = math.ceil(128 / (scale * ratio))
            left = max(0, (x - margin) // factor * factor)
            top = max(0, (y - margin) // factor * factor)
            end_x = min(meta.width, math.ceil((right + margin) / factor) * factor)
            end_y = min(meta.height, math.ceil((bottom + margin) / factor) * factor)
            # QImage scanlines are padded to multiples of four bytes.
            stride = math.ceil((end_x - left) / factor) * 4
            retain = stride * math.ceil((end_y - top) / factor) <= self._display_cache_limit
            if not retain:
                left, top, end_x, end_y = x, y, right, bottom
            pixels, left, top, factor = pyramid.region(scale * ratio, left, top, end_x - left, end_y - top)
            preview = render_samples(pixels, frame.source, frame.low, frame.high, key[3])
            # QPainter's raster path otherwise converts RGB888/gray for every
            # draw. Convert once, retaining alpha coverage when present.
            fmt = QImage.Format_ARGB32_Premultiplied if preview.image.hasAlphaChannel() else QImage.Format_RGB32
            image = preview.image.convertToFormat(fmt)
            cached = (key, left, top, min(meta.width, left + pixels.shape[1] * factor),
                      min(meta.height, top + pixels.shape[0] * factor), image)
            self._display_cache = cached if retain and image.sizeInBytes() <= self._display_cache_limit else None
        # Smooth reduction; exact nearest-neighbour source pixels at 100% and up.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, scale * ratio < 1)
        image = cached[5]
        painter.drawImage(QRectF(ox + cached[1] * scale, oy + cached[2] * scale,
                                image.width() * factor * scale, image.height() * factor * scale), image)


qmlRegisterType(PreparedView, 'XrtViewer', 1, 0, 'PreparedView')
