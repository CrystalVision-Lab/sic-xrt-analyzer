"""Persistent lossless source levels. No image decoding on a prepared map pan."""
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import imagecodecs
import numpy as np
import tifffile


class PixelCache:
    VERSION = 1

    def __init__(self, source, root=None, cancelled=lambda: False):
        self.source = source
        self.levels = []
        self.created = False
        root = Path(root or os.environ.get("SIC_XRT_WAFER_CACHE") or
                    Path(tempfile.gettempdir()) / "sic-xrt-wafer-levels-v1")
        root.mkdir(parents=True, exist_ok=True)
        identity = [self.VERSION, source.path, source.identity.file_size,
                    source.identity.mtime_ns, source.page_index]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        self.path = root / key
        source.validate_identity()
        if not (self.path / "ready.json").is_file():
            self._build(root, identity, cancelled)
        info = json.loads((self.path / "ready.json").read_text())
        if info["identity"] != identity:
            raise ValueError("원본 캐시 정보가 일치하지 않습니다")
        try:
            for number in range(info["levels"]):
                self.levels.append(np.load(self.path / f"{number}.npy", mmap_mode="r"))
            source.validate_identity()
        except Exception:
            self.close()
            raise

    def _build(self, root, identity, cancelled):
        meta = self.source.metadata
        channels = meta.channels
        shape = (meta.height, meta.width) + (() if channels == 1 else (channels,))
        size = math.prod(shape) * np.dtype(meta.dtype).itemsize
        # The budget is disk space, not resident RAM. Do not silently reduce resolution.
        if size * 4 / 3 > 16 * 1024**3 or shutil.disk_usage(root).free < size * 3 + 64 * 1024**2:
            raise ValueError("원본 해상도 캐시 공간이 부족합니다. 디스크 공간을 확보하세요.")
        with tempfile.TemporaryDirectory(prefix="building-", dir=root) as scratch:
            directory = Path(scratch)
            output = np.lib.format.open_memmap(directory / "0.npy", mode="w+", dtype=meta.dtype, shape=shape)
            mapped = encoded = None
            try:
                if cancelled():
                    raise InterruptedError("원본 준비 취소")
                if meta.format == "JPEG":
                    encoded = np.memmap(self.source.path, dtype=np.uint8, mode="r")
                    imagecodecs.jpeg8_decode(encoded, outcolorspace="RGB", out=output)
                else:
                    with tifffile.TiffFile(self.source.path) as tif:
                        mapped = tif.pages[self.source.page_index].asarray(out="memmap")
                    for y in range(0, meta.height, 128):
                        if cancelled():
                            raise InterruptedError("원본 준비 취소")
                        output[y:y+128] = mapped[y:y+128]
                output.flush()
            finally:
                output._mmap.close()
                if encoded is not None:
                    encoded._mmap.close()
                if isinstance(mapped, np.memmap):
                    # tifffile owns its temporary backing file.
                    mapped._mmap.close()
            number = 0
            while max(shape[:2]) > 256:
                if cancelled():
                    raise InterruptedError("표시 계층 준비 취소")
                previous = np.load(directory / f"{number}.npy", mmap_mode="r")
                h, w = shape[:2]
                shape = ((h+1)//2, (w+1)//2) + shape[2:]
                number += 1
                reduced = np.lib.format.open_memmap(directory / f"{number}.npy", mode="w+", dtype=meta.dtype, shape=shape)
                try:
                    for y in range(0, h, 64):
                        if cancelled():
                            raise InterruptedError("표시 계층 준비 취소")
                        block = previous[y:y+64].astype(np.float32)
                        if block.shape[0] % 2:
                            block = np.concatenate((block, block[-1:]), axis=0)
                        if w % 2:
                            block = np.concatenate((block, block[:, -1:]), axis=1)
                        a = (block[::2, ::2] + block[1::2, ::2] + block[::2, 1::2] + block[1::2, 1::2]) * .25
                        if np.dtype(meta.dtype).kind in "ui":
                            a = np.rint(a)
                        reduced[y//2:y//2+a.shape[0]] = a
                    reduced.flush()
                finally:
                    reduced._mmap.close()
                    previous._mmap.close()
            self.source.validate_identity()
            if cancelled():
                raise InterruptedError("원본 준비 취소")
            (directory / "ready.json").write_text(json.dumps({"identity": identity, "levels": number+1}))
            try:
                directory.rename(self.path)
            except FileExistsError:
                # Another app window prepared the same immutable source.
                pass
        self.created = True

    def region(self, left, top, right, bottom, density):
        level = min(len(self.levels)-1, max(0, math.floor(math.log2(1/max(density, 1e-9)))))
        step = 2**level
        left, top = max(0, left//step), max(0, top//step)
        right, bottom = math.ceil(right/step), math.ceil(bottom/step)
        return self.levels[level][top:bottom, left:right].copy(), left*step, top*step, step

    def close(self):
        for pixels in self.levels:
            pixels._mmap.close()
        self.levels.clear()
