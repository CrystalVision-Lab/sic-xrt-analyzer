"""Folder image contact sheet in a circular, explicitly relative layout."""

import math

import numpy as np
from PIL import Image
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QImage

from .latest_reader import LatestReader
from .research_controller import local_path


class FolderMap(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.epoch = 0
        self.rows = []
        self.busy = False
        self.error = ""
        self.path = ""
        self.revision = 0

    @Slot(str)
    def open(self, folder):
        self.epoch += 1
        epoch = self.epoch
        path = local_path(folder)
        self.busy = True
        self.error = ""
        self.path = str(path)
        self.rows = []
        self.bridge.provider.folder_images = {}

        def load():
            from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

            files = sorted(
                p
                for p in path.rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and p.suffix.lower() in (".jpg", ".jpeg", ".tif", ".tiff")
            )
            if len(files) > 500:
                raise ValueError("한 폴더에서 최대 500개 이미지를 표시합니다.")
            rows = []
            images = {}
            errors = []
            for file in files:
                if epoch != self.epoch:
                    raise InterruptedError("이전 폴더 읽기 취소")
                try:
                    if file.suffix.lower() in (".tif", ".tiff"):
                        source = OriginalImageSource(file)
                        if source.metadata.page_count > 1:
                            continue
                        a = source.read_sampled(320)
                        if a.dtype != np.uint8:
                            lo, hi = np.percentile(a, [1, 99])
                            a = np.clip(
                                (a.astype(float) - lo) * 255 / max(hi - lo, 1), 0, 255
                            ).astype("uint8")
                        image = Image.fromarray(a).convert("RGB")
                    else:
                        with Image.open(file) as original:
                            original.draft("RGB", (320, 320))
                            original.thumbnail((320, 320))
                            image = original.convert("RGB")
                    image.thumbnail((320, 320))
                    raw = image.tobytes()
                    ident = str(len(rows))
                    images[ident] = QImage(
                        raw,
                        image.width,
                        image.height,
                        image.width * 3,
                        QImage.Format_RGB888,
                    ).copy()
                    rows.append(
                        {"id": ident, "name": file.name, "path": str(file.resolve())}
                    )
                except (ValueError, OSError) as exc:
                    errors.append(file.name + ": " + str(exc))
            if not rows:
                raise ValueError("열 수 있는 단일 페이지 이미지가 없습니다.")
            radius = max(1, math.ceil(math.sqrt(len(rows) / math.pi)))
            while True:
                cells = [
                    (x, y)
                    for y in range(-radius, radius + 1)
                    for x in range(-radius, radius + 1)
                    if x * x + y * y <= radius * radius
                ]
                if len(cells) >= len(rows):
                    break
                radius += 1
            for row, (x, y) in zip(rows, cells):
                row.update(x=x, y=y)
            return rows, images, radius, errors

        self.reader.submit(load)
        self.changed.emit()

    def shutdown(self):
        self.epoch += 1
        self.reader.shutdown()

    def _ready(self, value, error):
        self.busy = False
        self.error = error or ""
        if not error:
            self.rows, images, self.radius, errors = value
            self.bridge.provider.folder_images = images
            self.revision += 1
            self.error = " · ".join(errors[:3])
        self.changed.emit()

    @Slot(str)
    def openImage(self, ident):
        row = next((r for r in self.rows if r["id"] == ident), None)
        if row:
            self.bridge.projects.manualImageRequested()
            self.bridge.requestImage(self.bridge.localUrl(row["path"]))

    @Property("QVariantMap", notify=changed)
    def state(self):
        return {
            "rows": self.rows,
            "busy": self.busy,
            "error": self.error,
            "path": self.path,
            "revision": self.revision,
            "radius": getattr(self, "radius", 1),
        }
