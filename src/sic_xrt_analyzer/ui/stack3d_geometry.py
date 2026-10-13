"""Bounded line vertex data for manual indexed paths in Qt Quick 3D."""

import numpy as np
from PySide6.QtCore import Property, Signal
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


_registered = False


def register_types():
    global _registered
    if not _registered:
        qmlRegisterType(StackTrackLines, "XrtStack3D", 1, 0, "TrackLines")
        _registered = True
