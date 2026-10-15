"""Bounded line vertex data for manual indexed paths in Qt Quick 3D."""

import numpy as np
from PySide6.QtCore import Property, QObject, Signal
from PySide6.QtGui import QVector3D
from PySide6.QtQml import qmlRegisterType
from PySide6.QtQuick3D import QQuick3DGeometry


class StackTrackLines(QQuick3DGeometry):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vertices = []

    @Property("QVariantList", notify=changed)
    def vertices(self):
        return self._vertices

    @vertices.setter
    def vertices(self, value):
        a = np.asarray(value, dtype=np.float32)
        if len(value) > 10000 or (
            a.size and (a.ndim != 2 or a.shape[1] != 3 or not np.isfinite(a).all())
        ):
            raise ValueError("Track renderer vertex budget")
        self._vertices = value
        self.clear()
        self.setStride(12)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Lines)
        self.addAttribute(
            QQuick3DGeometry.Attribute.Semantic.PositionSemantic,
            0,
            QQuick3DGeometry.Attribute.ComponentType.F32Type,
        )
        self.setVertexData(a.tobytes())
        if a.size:
            self.setBounds(QVector3D(*a.min(0).tolist()), QVector3D(*a.max(0).tolist()))
        self.update()
        self.changed.emit()


class DefectSurface(QQuick3DGeometry):
    sourceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None

    @Property(QObject, notify=sourceChanged)
    def sourceController(self):
        return self._source

    @sourceController.setter
    def sourceController(self, value):
        if self._source is value:
            return
        if self._source:
            self._source.meshChanged.disconnect(self._refresh)
        self._source = value
        if value:
            value.meshChanged.connect(self._refresh)
        self._refresh()
        self.sourceChanged.emit()

    def _refresh(self):
        self.clear()
        m = self._source.mesh if self._source else None
        if m is None:
            self.update()
            return
        positions = m.vertices[:, [2, 1, 0]].copy()
        positions[:, 1] *= -1
        seed = self._source.last_seed
        if seed:
            positions -= np.array([seed[0], -seed[1], seed[2]])
            positions *= 350 / max(
                128, self._source.bridge.original_source.metadata.page_count
            )
        else:
            positions -= (positions.min(0) + positions.max(0)) / 2
            positions *= 350 / max(1, float(np.ptp(positions, axis=0).max()))
        normals = m.normals[:, [2, 1, 0]].copy()
        normals[:, 1] *= -1
        vertices = np.concatenate([positions, normals], axis=1).astype(np.float32)
        self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        for semantic, offset in [
            (QQuick3DGeometry.Attribute.Semantic.PositionSemantic, 0),
            (QQuick3DGeometry.Attribute.Semantic.NormalSemantic, 12),
        ]:
            self.addAttribute(
                semantic, offset, QQuick3DGeometry.Attribute.ComponentType.F32Type
            )
        self.addAttribute(
            QQuick3DGeometry.Attribute.Semantic.IndexSemantic,
            0,
            QQuick3DGeometry.Attribute.ComponentType.U32Type,
        )
        self.setVertexData(vertices.tobytes())
        self.setIndexData(m.faces.astype(np.uint32).tobytes())
        self.setBounds(
            QVector3D(*positions.min(0).tolist()), QVector3D(*positions.max(0).tolist())
        )
        self.update()


class DefectLayer(QQuick3DGeometry):
    sourceChanged = Signal()
    currentChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._current = False

    @Property(bool, notify=currentChanged)
    def current(self):
        return self._current

    @current.setter
    def current(self, value):
        self._current = value
        self._refresh()
        self.currentChanged.emit()

    @Property(QObject, notify=sourceChanged)
    def sourceController(self):
        return self._source

    @sourceController.setter
    def sourceController(self, value):
        if self._source:
            self._source.layersChanged.disconnect(self._refresh)
        self._source = value
        if value:
            value.layersChanged.connect(self._refresh)
        self._refresh()
        self.sourceChanged.emit()

    def _refresh(self):
        self.clear()
        a = self._source.layers_data[int(self._current)] if self._source else None
        if a is not None and a.size:
            self.setStride(12)
            self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
            self.addAttribute(
                QQuick3DGeometry.Attribute.Semantic.PositionSemantic,
                0,
                QQuick3DGeometry.Attribute.ComponentType.F32Type,
            )
            self.setVertexData(a.tobytes())
            self.setBounds(QVector3D(*a.min(0).tolist()), QVector3D(*a.max(0).tolist()))
        self.update()


_registered = False


def register_types():
    global _registered
    if not _registered:
        qmlRegisterType(StackTrackLines, "XrtStack3D", 1, 0, "TrackLines")
        qmlRegisterType(DefectLayer, "XrtStack3D", 1, 0, "DefectLayer")
        qmlRegisterType(DefectSurface, "XrtStack3D", 1, 0, "DefectSurface")
        _registered = True
