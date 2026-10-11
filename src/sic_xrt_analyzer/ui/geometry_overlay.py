"""Viewport geometry painting and bounded asynchronous binary-mask display cache."""
import hashlib
import math
from itertools import pairwise
from time import perf_counter

from PySide6.QtCore import Property, QPointF, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtQml import qmlRegisterType
from PySide6.QtQuick import QQuickPaintedItem

from .latest_reader import LatestReader


def intersects(a, b):
    return a[0] <= b[0]+b[2] and a[0]+a[2] >= b[0] and a[1] <= b[1]+b[3] and a[1]+a[3] >= b[1]


def path_bounds(path):
    xs, ys = [p[0] for p in path], [p[1] for p in path]
    return [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]


def segment_distance(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0, min(1, ((x-a[0])*dx+(y-a[1])*dy)/length)) if length else 0
    return math.hypot(x-a[0]-t*dx, y-a[1]-t*dy)


def mask_image(mask, crop, mode):
    """Recheck the asset at read time; encoded display bytes never become analysis pixels."""
    import numpy as np
    from PIL import Image
    start = perf_counter()
    with open(mask["path"], "rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != mask["sha256"]:
            raise ValueError("Mask 자산 해시가 변경되었습니다.")
        stream.seek(0)
        with Image.open(stream) as image:
            bx, by, bw, bh = mask["bounds"]
            if image.mode != "L" or image.size != (int(bw), int(bh)):
                raise ValueError("Mask 원본 범위가 변경되었습니다.")
            x, y, w, h = crop
            # One-pixel halo preserves boundaries at viewport crop edges.
            left, top = max(0, x-int(bx)-1), max(0, y-int(by)-1)
            right, bottom = min(int(bw), x-int(bx)+w+1), min(int(bh), y-int(by)+h+1)
            samples = np.asarray(image.crop((left, top, right, bottom))) != 0
    if mode == "boundary":
        padded = np.pad(samples, 1)
        interior = padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
        samples = samples & ~interior
    rgba = np.zeros((*samples.shape, 4), dtype=np.uint8)
    rgba[..., :3] = (181, 147, 248)
    rgba[..., 3] = samples * (160 if mode == "boundary" else 55)
    result = QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.strides[0], QImage.Format_RGBA8888).copy()
    bounds = [int(bx)+left, int(by)+top, right-left, bottom-top]
    # Only display masks may be reduced. Placement still uses the original extent.
    if max(result.width(), result.height()) > 2048:
        result = result.scaled(2048, 2048, Qt.KeepAspectRatio, Qt.FastTransformation)
    return result, bounds, (perf_counter()-start)*1000


def display_property(name, kind, default, notify):
    def get(self):
        return getattr(self, "_"+name, default)
    def set_value(self, value):
        if get(self) == value:
            return
        if name == "rows":
            self.reader.invalidate()
            self.cache.clear()
            self.keys = self.pending = ()
            self.mask_error = ""
        setattr(self, "_"+name, value)
        self.changed.emit()
        self.refresh.start()
        self.update()
    return Property(kind, get, set_value, notify=notify)


class GeometryOverlay(QQuickPaintedItem):
    changed = Signal()
    rows = display_property('rows', 'QVariantList', [], changed)
    viewTransform = display_property('viewTransform', 'QVariantList', [0., 0., 1.], changed)
    selectedId = display_property('selectedId', str, '', changed)
    maskMode = display_property('maskMode', str, 'off', changed)
    lineWidth = display_property('lineWidth', float, 1.5, changed)
    lines = display_property('lines', bool, True, changed)
    highlight = display_property('highlight', bool, True, changed)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.refresh = QTimer(self)
        self.refresh.setSingleShot(True)
        self.refresh.timeout.connect(self._prepare)
        self.cache, self.keys, self.pending = {}, (), ()
        self.mask_error = ""
        self.metrics = {"paintMs": 0., "paintCount": 0, "visiblePaths": 0, "maskLoadMs": 0., "maskBytes": 0}
        self.visibleChanged.connect(self._visibility)
        self.widthChanged.connect(self._schedule)
        self.heightChanged.connect(self._schedule)

    def _schedule(self):
        self.refresh.start()
        self.update()

    def _visibility(self):
        if not self.isVisible():
            self.reader.invalidate()
            self.cache.clear()
            self.pending = ()
        self._schedule()

    @Property('QVariant', notify=changed)
    def controller(self):
        return getattr(self, '_controller', None)

    @controller.setter
    def controller(self, value):
        self._controller = value
        if value:
            value.mask_readers.append(self.reader)
        self._schedule()

    def view_bounds(self):
        ox, oy, scale = self.viewTransform
        if scale <= 0:
            return [0, 0, 0, 0]
        return [-ox/scale, -oy/scale, self.width()/scale, self.height()/scale]

    def _prepare(self):
        if not self.isVisible() or self.maskMode == 'off':
            self.reader.invalidate()
            self.pending = self.keys = ()
            self.cache.clear()
            return
        bounds = self.view_bounds()
        rows = sorted((r for r in self.rows if intersects(r['mask']['bounds'], bounds)), key=lambda r: r['id'] != self.selectedId)[:8]
        specs = []
        for row in rows:
            bx, by, bw, bh = row['mask']['bounds']
            # Rounded crop includes a small pan margin, clamped to validated bbox.
            x = max(int(bx), math.floor((bounds[0]-32)/128)*128)
            y = max(int(by), math.floor((bounds[1]-32)/128)*128)
            right = min(int(bx+bw), math.ceil((bounds[0]+bounds[2]+32)/128)*128)
            bottom = min(int(by+bh), math.ceil((bounds[1]+bounds[3]+32)/128)*128)
            if right <= x or bottom <= y:
                continue
            crop = (x, y, right-x, bottom-y)
            key = (row['mask']['path'], row['mask']['sha256'], crop, self.maskMode)
            specs.append((key, row['mask'], crop, self.maskMode))
        self.keys = tuple(s[0] for s in specs)
        self.cache = {k: v for k, v in self.cache.items() if k in self.keys}
        missing = tuple(s for s in specs if s[0] not in self.cache)
        if missing == self.pending:
            return
        self.reader.invalidate()
        self.pending = missing
        if missing:
            def read():
                values, budget = [], 32*1024**2
                for key, mask, crop, mode in missing:
                    value = mask_image(mask, crop, mode)
                    size = value[0].sizeInBytes()
                    if size <= budget:
                        values.append((key, value))
                        budget -= size
                return values
            self.reader.submit(read)

    def _ready(self, values, error):
        self.pending = ()
        self.mask_error = error
        if not error:
            budget = 32*1024**2
            for key, value in values:
                if key in self.keys and value[0].sizeInBytes() <= budget:
                    self.cache[key] = value
                    budget -= value[0].sizeInBytes()
            while sum(v[0].sizeInBytes() for v in self.cache.values()) > 32*1024**2:
                self.cache.pop(next(iter(self.cache)))
            self.metrics['maskLoadMs'] = sum(v[2] for _, v in values)
        self.update()
        self.changed.emit()

    @Slot(float, float, float, result=str)
    def hit(self, x, y, tolerance):
        best, limit = '', tolerance
        for row in self.rows:
            if not intersects(row['bounds'], [x-tolerance, y-tolerance, tolerance*2, tolerance*2]):
                continue
            distance = min((segment_distance(x, y, a, b) for path in row['paths'] for a, b in pairwise(path)), default=math.inf)
            if distance < limit:
                best, limit = row['id'], distance
        return best

    @Property('QVariantMap', notify=changed)
    def stats(self):
        return {**self.metrics, 'maskBytes': sum(v[0].sizeInBytes() for v in self.cache.values()), 'maskCount': len(self.cache), 'maskError': self.mask_error}

    def paint(self, painter):
        start = perf_counter()
        if not self.isVisible():
            return
        ox, oy, scale = self.viewTransform
        if scale <= 0:
            return
        bounds = self.view_bounds()
        painter.setClipRect(QRectF(0, 0, self.width(), self.height()))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        for key in self.keys:
            if key in self.cache:
                image, b, _ = self.cache[key]
                painter.drawImage(QRectF(*b), image)
        count = 0
        for row in sorted(self.rows, key=lambda r: r['id'] == self.selectedId):
            if not intersects(row['bounds'], bounds):
                continue
            selected = self.highlight and row['id'] == self.selectedId
            pen = QPen(QColor('#fff04a' if selected else '#b593f8'))
            pen.setWidthF(self.lineWidth + (1.5 if selected else 0))
            pen.setCosmetic(True)
            pen.setStyle(Qt.SolidLine if selected else Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            if self.lines or selected:
                for path in row['paths']:
                    # Bounds intersection retains segments crossing viewport with both endpoints offscreen.
                    if not intersects(path_bounds(path), bounds):
                        continue
                    shape = QPainterPath(QPointF(*path[0]))
                    for point in path[1:]:
                        shape.lineTo(*point)
                    painter.drawPath(shape)
                    count += 1
                pen.setStyle(Qt.SolidLine)
                painter.setPen(pen)
                for node in row['nodes']:
                    radius = (4 if node['degree'] > 2 else 2.5)/scale
                    if node['degree'] > 2:
                        painter.drawRect(QRectF(node['x']-radius, node['y']-radius, radius*2, radius*2))
                    elif node['degree'] == 1:
                        painter.drawEllipse(QPointF(node['x'], node['y']), radius, radius)
        self.metrics.update(paintMs=(perf_counter()-start)*1000, paintCount=self.metrics['paintCount']+1, visiblePaths=count)


qmlRegisterType(GeometryOverlay, 'XrtViewer', 1, 0, 'GeometryOverlay')
