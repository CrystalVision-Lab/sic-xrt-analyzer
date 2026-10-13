"""Independent source-coordinate annotations; never modify inference input."""

from collections import OrderedDict
from uuid import uuid4

from PySide6.QtCore import Property, QObject, Signal, Slot


class DisplayLayers(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.cache = OrderedDict()
        bridge.pipeline.changed.connect(self.changed)

    def _rows(self):
        source = self.bridge.original_source
        if source is None:
            return []
        key = source.identity
        self.cache.setdefault(key, [])
        self.cache.move_to_end(key)
        while len(self.cache) > 8:
            self.cache.popitem(last=False)
        return self.cache[key]

    @Property("QVariantList", notify=changed)
    def rows(self):
        return self._rows()

    @Slot(int, int, int, int)
    def add(self, x, y, width, height):
        source = self.bridge.original_source
        if source is None:
            return
        source.validate_region(x, y, width, height)
        rows = self._rows()
        if len(rows) >= 1000:
            return
        rows.append(
            {
                "id": str(uuid4()),
                "name": "ROI " + str(len(rows) + 1),
                "visible": True,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }
        )
        self.changed.emit()

    @Slot()
    def addSelected(self):
        source = self.bridge.original_source
        record = self.bridge.roi_manager.selected_record(self.bridge.stack_viewer.frame)
        if source is None or record is None or len(self._rows()) >= 1000:
            return
        row = next(
            (
                r
                for r in self.bridge.roiState["items"]
                if r["id"] == record.id and r["active"]
            ),
            None,
        )
        if row is None:
            return
        from copy import deepcopy

        rows = self._rows()
        rows.append(
            {
                "id": str(uuid4()),
                "name": "ROI " + str(len(rows) + 1),
                "visible": True,
                "x": row["bbox"][0],
                "y": row["bbox"][1],
                "width": row["bbox"][2],
                "height": row["bbox"][3],
                "kind": row["kind"],
                "paths": deepcopy(row["paths"]),
            }
        )
        self.changed.emit()

    @Slot(str, bool)
    def toggle(self, ident, visible):
        for row in self._rows():
            if row["id"] == ident:
                row["visible"] = visible
        self.changed.emit()

    @Slot(str)
    def remove(self, ident):
        rows = self._rows()
        rows[:] = [row for row in rows if row["id"] != ident]
        self.changed.emit()
