"""Lazy per-capture folder mosaics; unrelated images are never put in an invented grid."""

import math
import re
import warnings
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QImage

from .latest_reader import LatestReader
from .research_controller import local_path


class FolderMap(QObject):
    changed = Signal()
    _progress = Signal(int, int, int, str)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.epoch = 0
        self.rows = []
        self.groups = []
        self.current_rows = []
        self.active_group = 0
        self.busy = False
        self.error = ""
        self.scan_errors = []
        self.path = ""
        self.revision = 0
        self.size = [1, 1]
        self.evidence = {}
        self.transforms = {}
        self.progress = [0, 0, ""]
        self._progress.connect(self._on_progress)

    def _on_progress(self, epoch, d, t, label):
        if epoch == self.epoch:
            self.progress = [d, t, label]
            self.changed.emit()

    @Slot(str)
    def open(self, folder):
        self.epoch += 1
        epoch = self.epoch
        path = local_path(folder)
        self.path = str(path)
        self.busy = True
        self.error = ""
        self.rows = []
        self.groups = []
        self.transforms = {}
        self.size = [1, 1]
        self.bridge.provider.folder_images = {}
        self.revision += 1

        def discover():
            from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

            files = sorted(
                p
                for p in path.rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and p.suffix.lower() in (".jpg", ".jpeg", ".tif", ".tiff")
            )
            if len(files) > 500:
                raise ValueError("한 폴더에서 최대 500개 이미지를 표시합니다")
            rows = []
            errors = []
            for n, file in enumerate(files):
                if epoch != self.epoch:
                    raise InterruptedError("폴더 읽기 취소")
                try:
                    if file.suffix.lower() in (".tif", ".tiff"):
                        source = OriginalImageSource(file)
                        if source.metadata.page_count > 1:
                            continue
                        w, h = source.metadata.width, source.metadata.height
                    else:
                        with warnings.catch_warnings():
                            warnings.simplefilter(
                                "ignore", Image.DecompressionBombWarning
                            )
                            with Image.open(file) as im:
                                w, h = im.size
                    rows.append(
                        {
                            "id": str(len(rows)),
                            "name": file.name,
                            "path": str(file.resolve()),
                            "width": w,
                            "height": h,
                            "parent": str(file.parent.relative_to(path)),
                        }
                    )
                except (OSError, ValueError, Image.DecompressionBombError) as e:
                    errors.append(file.name + ": " + str(e))
                self._progress.emit(epoch, n + 1, len(files), "촬영 묶음 확인")
            if not rows:
                raise ValueError("열 수 있는 단일 페이지 이미지가 없습니다")
            buckets = {}
            for row in rows:
                parent = row["parent"]
                same = [r for r in rows if r["parent"] == parent]
                if any(r["name"].rsplit(".", 1)[0].isdigit() for r in same):
                    key = parent
                else:
                    match = re.search(r"(before|after)", row["name"], re.IGNORECASE)
                    key = parent + (" / " + match[0].lower() if match else "")
                buckets.setdefault(key, []).append(row["id"])
            groups = [
                {
                    "id": i,
                    "label": (key if key != "." else path.name)
                    + " · "
                    + str(len(ids))
                    + "장",
                    "members": ids,
                }
                for i, (key, ids) in enumerate(
                    sorted(buckets.items(), key=lambda kv: -len(kv[1]))
                )
            ]
            # Prefer the larger per-area composites for a complete wafer view.
            # Keep stages and magnifications separate; detail groups remain available.
            full = {}
            for row in rows:
                siblings = [
                    r for r in rows if r["parent"] == row["parent"] and r is not row
                ]
                stage = re.search(r"(before|after)", row["name"], re.IGNORECASE)
                zoom = re.search(r"x(\d+)", row["parent"], re.IGNORECASE)
                ordinal = re.search(r"(\d+)$", Path(row["name"]).stem)
                if len(siblings) < 4 or not stage or not zoom or not ordinal:
                    continue
                typical = np.median([r["width"] * r["height"] for r in siblings])
                if row["width"] * row["height"] >= 4 * typical:
                    full.setdefault((stage[0].lower(), zoom[1]), []).append(row)
            complete = []
            for (stage, zoom), members in sorted(full.items()):
                if len({r["parent"] for r in members}) >= 4:
                    label = "전체 웨이퍼 · 어닐링 " + (
                        "후" if stage == "after" else "전"
                    )
                    complete.append(
                        {
                            "label": label
                            + " x"
                            + zoom
                            + " · "
                            + str(len(members))
                            + "장",
                            "members": [r["id"] for r in members],
                        }
                    )
            groups = complete + groups
            for i, group in enumerate(groups):
                group["id"] = i
            return "discover", epoch, rows, groups, errors

        self.reader.submit(discover)
        self.changed.emit()

    @Slot(int)
    def selectGroup(self, index):
        if not 0 <= index < len(self.groups):
            return
        self.epoch += 1
        epoch = self.epoch
        self.reader.invalidate()
        self.active_group = index
        self.busy = True
        self.error = ""
        self.transforms = {}
        ids = set(self.groups[index]["members"])
        rows = [r for r in self.rows if r["id"] in ids]
        self.current_rows = rows
        self.bridge.provider.folder_images = {}
        self.revision += 1

        def build():
            from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
            from sic_xrt_analyzer.wafer_map.mosaic import compose

            images = []
            thumbs = {}
            valid = []
            errors = []
            edge = max(
                320, min(1024, int(math.sqrt(256 * 1024**2 / (3 * max(1, len(rows))))))
            )

            def progress(d, t, label):
                self._progress.emit(epoch, d, t, label)

            for n, row in enumerate(rows):
                if epoch != self.epoch:
                    raise InterruptedError("사진 맞춤 취소")
                file = Path(row["path"])
                try:
                    if file.suffix.lower() in (".tif", ".tiff"):
                        source = OriginalImageSource(file)
                        try:
                            a = source.read_sampled(edge)
                        except ValueError:
                            a = source.read_full()
                            step = max(1, math.ceil(max(a.shape[:2]) / edge))
                            a = a[::step, ::step]
                        if a.dtype != np.uint8:
                            lo, hi = np.percentile(a, [1, 99])
                            a = np.clip(
                                (a.astype(np.float32) - lo) * 255 / max(hi - lo, 1),
                                0,
                                255,
                            ).astype(np.uint8)
                        im = Image.fromarray(a).convert("RGB")
                    else:
                        with warnings.catch_warnings():
                            warnings.simplefilter(
                                "ignore", Image.DecompressionBombWarning
                            )
                            with Image.open(file) as original:
                                original.draft("RGB", (edge, edge))
                                original.thumbnail((edge, edge))
                                im = original.convert("RGB")
                    im.thumbnail((edge, edge))
                    a = np.asarray(im).copy()
                    images.append(a)
                    valid.append(
                        {
                            **row,
                            "preview_width": a.shape[1],
                            "preview_height": a.shape[0],
                        }
                    )
                    thumb = im.copy()
                    thumb.thumbnail((320, 320))
                    raw = thumb.tobytes()
                    thumbs[row["id"]] = QImage(
                        raw,
                        thumb.width,
                        thumb.height,
                        thumb.width * 3,
                        QImage.Format_RGB888,
                    ).copy()
                except (OSError, ValueError, Image.DecompressionBombError) as e:
                    errors.append(row["name"] + ": " + str(e))
                progress(n + 1, len(rows), "원본 미리보기 읽기")
            # Publish available thumbnails even when alignment has no evidence.
            try:
                result = compose(
                    images,
                    valid,
                    cancelled=lambda: epoch != self.epoch,
                    progress=progress,
                )
            except ValueError as e:
                return "mosaic", epoch, None, valid, thumbs, errors + [str(e)]
            return "mosaic", epoch, result, valid, thumbs, errors

        self.reader.submit(build)
        self.changed.emit()

    def _ready(self, value, error):
        self.busy = False
        if error:
            self.error = error
            self.changed.emit()
            return
        if not value or value[1] != self.epoch:
            return
        if value[0] == "discover":
            _, _, self.rows, self.groups, errors = value
            self.scan_errors = errors
            self.selectGroup(0)
            return
        _, _, result, rows, images, errors = value
        if result:
            a = result["rgba"]
            images["mosaic"] = QImage(
                a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format_RGBA8888
            ).copy()
            self.size = result["size"]
            self.evidence = result["evidence"]
            self.transforms = {
                rows[i]["id"]: m.tolist() for i, m in result["transforms"].items()
            }
        else:
            self.evidence = {}
            self.size = [1, 1]
        self.current_rows = rows
        self.bridge.provider.folder_images = images
        self.revision += 1
        self.error = " · ".join((self.scan_errors + errors)[:3])
        self.changed.emit()

    @Slot(float, float)
    def openAt(self, x, y):
        for row in reversed(self.current_rows):
            matrix = self.transforms.get(row["id"])
            if matrix is None:
                continue
            u, v, _ = np.linalg.inv(np.asarray(matrix)) @ np.array([x, y, 1.0])
            # Transforms use registration preview dimensions, not thumbnail sizes.
            if 0 <= u < row["preview_width"] and 0 <= v < row["preview_height"]:
                self.openImage(row["id"])
                return

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
            "groups": [{"id": g["id"], "label": g["label"]} for g in self.groups],
            "group": self.active_group,
            "busy": self.busy,
            "error": self.error,
            "path": self.path,
            "revision": self.revision,
            "radius": 1,
            "size": self.size,
            "ready": "mosaic" in self.bridge.provider.folder_images,
            "count": len(self.current_rows),
            "aligned": len(self.transforms),
            "evidence": self.evidence,
            "progress": self.progress,
        }

    def shutdown(self):
        self.epoch += 1
        self.reader.shutdown()
