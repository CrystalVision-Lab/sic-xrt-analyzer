"""Read-only original grid and disk-backed, area-averaged display levels."""
import math
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

import numpy as np
import tifffile

from .tiff_pages import page_layout


class DisplayPyramid:
    def __init__(self, source, pixels=None):
        self.source = source
        self.directory = TemporaryDirectory(prefix='sic-xrt-pyramid-')
        self.lock = RLock()
        self.closed = False
        self.native_copy = False
        self.owns_base = source.metadata.format == 'TIFF'
        if self.owns_base:
            try:
                with tifffile.TiffFile(source.path) as tif:
                    _, _, virtual = page_layout(tif, source.page_index)
                if virtual:
                    meta = source.metadata
                    base = tifffile.memmap(source.path, mode='r').reshape((meta.page_count, meta.height, meta.width) + (() if meta.channels == 1 else (meta.channels,)))[source.page_index]
                else:
                    base = tifffile.memmap(source.path, page=source.page_index, mode='r')
            except ValueError:
                if pixels is None:
                    self.directory.cleanup()
                    raise
                path = Path(self.directory.name) / 'native.npy'
                self.native_copy = True
                base = np.lib.format.open_memmap(path, mode='w+', dtype=pixels.dtype, shape=pixels.shape)
                for y in range(0, pixels.shape[0], 64):
                    base[y:y + 64] = pixels[y:y + 64]
                base.flush(); base._mmap.close()
                base = np.load(path, mmap_mode='r')
        else:
            base = pixels
        self.levels = [base]

    def prepare(self, canceled=lambda: False, progress=lambda *args: None):
        with self.lock:
            if self.closed:
                return False
            return self._prepare(canceled, progress)

    def _prepare(self, canceled, progress):
        total = max(0, math.ceil(math.log2(max(self.levels[0].shape[:2]) / 512)))
        estimate = sum(math.ceil(self.levels[0].nbytes / 4**i) for i in range(1, total + 1))
        if shutil.disk_usage(self.directory.name).free < estimate + 64 * 1024**2:
            raise ValueError('표시 계층 준비를 위한 임시 디스크 공간이 부족합니다')
        for number in range(total):
            if canceled():
                return False
            previous = self.levels[-1]
            h, w = previous.shape[:2]
            shape = ((h + 1) // 2, (w + 1) // 2) + previous.shape[2:]
            path = Path(self.directory.name) / f'{number + 1}.npy'
            output = np.lib.format.open_memmap(path, mode='w+', dtype=previous.dtype, shape=shape)
            try:
                for y in range(0, h, 64):
                    if canceled():
                        return False
                    block = previous[y:min(h, y + 64)].astype(np.float32)
                    if block.shape[0] % 2:
                        block = np.concatenate((block, block[-1:]), axis=0)
                    if w % 2:
                        block = np.concatenate((block, block[:, -1:]), axis=1)
                    reduced = (block[::2, ::2] + block[1::2, ::2] + block[::2, 1::2] + block[1::2, 1::2]) * 0.25
                    if previous.dtype.kind in 'ui':
                        reduced = np.rint(reduced)
                    output[y // 2:y // 2 + reduced.shape[0]] = reduced
                output.flush()
            finally:
                output._mmap.close()
            self.levels.append(np.load(path, mmap_mode='r'))
            progress(number + 1, total, '선명한 확대·축소 표시 준비 중…')
        self.source.validate_identity()
        return True

    @property
    def cache_bytes(self):
        return sum(level.nbytes for level in self.levels[0 if self.native_copy else 1:])

    def region(self, scale, x, y, width, height):
        """Select a level with at least one sample per physical screen pixel."""
        with self.lock:
            if self.closed:
                raise ValueError('Display cache is closed')
            level = min(len(self.levels) - 1, max(0, math.floor(math.log2(1 / max(scale, 1e-9)))))
            factor = 2**level
            pixels = self.levels[level]
            left, top = max(0, math.floor(x / factor)), max(0, math.floor(y / factor))
            right = min(pixels.shape[1], math.ceil((x + width) / factor))
            bottom = min(pixels.shape[0], math.ceil((y + height) / factor))
            return pixels[top:bottom, left:right].copy(), left * factor, top * factor, factor

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for pixels in self.levels[0 if self.owns_base else 1:]:
                pixels._mmap.close()
            self.levels.clear()
            self.directory.cleanup()


class DisplayGroup:
    """Disk display levels shared by all page sources and retained by the active viewer."""
    def __init__(self):
        self.pages = {}
        self.lock = RLock()
        self.closed = False
        self.max_cache_bytes = 4 * 1024**3

    @property
    def cache_bytes(self):
        with self.lock:
            return sum(p.cache_bytes for p in self.pages.values())

    def install(self, index, pyramid):
        with self.lock:
            if self.closed:
                return False
            if self.cache_bytes + pyramid.cache_bytes > self.max_cache_bytes:
                raise ValueError('전체 정밀 표시 캐시가 4GiB 한도를 초과합니다')
            self.pages[index] = pyramid
            return True

    def close(self):
        with self.lock:
            self.closed = True
            pages = list(self.pages.values())
            self.pages.clear()
        for pyramid in pages:
            pyramid.close()
