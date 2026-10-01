"""Viewer-owned temporary JPEG decode cache; originals are always read-only."""
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

import imagecodecs
import numpy as np
import tifffile

from .original_source import SourceError


class PreparedPixels:
    def __init__(self):
        self.directory = None
        self.pixels = None
        self.lock = RLock()

    def jpeg(self, source, canceled, progress):
        meta = source.metadata
        size = meta.width * meta.height * 3
        self.directory = TemporaryDirectory(prefix='sic-xrt-viewer-')
        try:
            if size > 2 * 1024**3 or shutil.disk_usage(self.directory.name).free < size + 64 * 1024**2:
                raise SourceError('READ_LIMIT_EXCEEDED', '정밀 표시 임시 캐시 공간이 부족하거나 2 GiB 한도를 넘습니다')
            progress(0, 1, '원본 해상도 JPEG 디코딩 중…')
            target = Path(self.directory.name) / 'decoded.rgb'
            output = encoded = None
            try:
                output = np.memmap(target, dtype='uint8', mode='w+', shape=(meta.height, meta.width, 3))
                encoded = np.memmap(source.path, dtype='uint8', mode='r')
                # libjpeg writes scanlines directly to the mapped destination.
                # No full decoded RAM ndarray or encoded bytes copy is made.
                imagecodecs.jpeg8_decode(encoded, outcolorspace='RGB', out=output)
                output.flush()
            finally:
                if encoded is not None:
                    encoded._mmap.close()
                if output is not None:
                    output._mmap.close()
            source.validate_identity()
            if canceled():
                self.close()
                return False
            self.pixels = np.memmap(target, dtype='uint8', mode='r', shape=(meta.height, meta.width, 3))
            progress(1, 1, '정밀 표시 준비 완료')
            return True
        except Exception:
            self.close()
            raise

    def region(self, source, x, y, width, height):
        with self.lock:
            if self.pixels is None:
                raise SourceError('SOURCE_READ_FAILED', '정밀 캐시가 닫혔습니다. 파일을 다시 여세요')
            source.validate_identity()
            result = self.pixels[y:y + height, x:x + width].copy()
            result.setflags(write=False)
            source.validate_identity()
            return result

    def close(self):
        with self.lock:
            if self.pixels is not None:
                self.pixels._mmap.close()
                self.pixels = None
            if self.directory:
                self.directory.cleanup()
                self.directory = None


def warm_tiff(source, canceled, progress):
    """Touch each mapped OS page in bounded row bands before showing the viewer."""
    source.validate_identity()
    mapped = tifffile.memmap(source.path, page=source.page_index, mode='r')
    try:
        total = source.metadata.height
        for top in range(0, total, 128):
            if canceled():
                return False
            # Touching one byte per 4 KiB causes the complete page to be paged in.
            band = mapped[top:top + 128].view(np.uint8).reshape(-1)
            int(band[::4096].sum(dtype=np.uint64))
            progress(min(total, top + 128), total, '원본 TIFF 정밀 표시 준비 중…')
        source.validate_identity()
        return True
    finally:
        mapped._mmap.close()
