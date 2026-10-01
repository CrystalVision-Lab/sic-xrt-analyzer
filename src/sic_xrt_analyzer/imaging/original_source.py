"""Header-only TIFF snapshots and bounded reads of unmodified original samples."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile


class SourceError(ValueError):
    """A source cannot be safely read under the current policy."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class SourceIdentity:
    canonical_path: str
    file_size: int
    mtime_ns: int
    page_index: int
    width: int
    height: int


@dataclass(frozen=True)
class OriginalMetadata:
    width: int
    height: int
    dtype: str
    bit_depth: int
    channels: int
    file_size: int
    mtime_ns: int
    page_count: int
    format: str = "TIFF"


@dataclass(frozen=True, init=False)
class OriginalImageSource:
    path: str
    page_index: int
    metadata: OriginalMetadata
    identity: SourceIdentity
    max_read_bytes: int
    max_decode_bytes: int

    def __init__(self, path, page_index=0, *, max_read_bytes=128 * 1024**2,
                 max_decode_bytes=64 * 1024**2):
        if type(page_index) is not int or page_index < 0:
            raise SourceError("INVALID_INPUT", "Page index must be a nonnegative integer")
        if any(type(limit) is not int or limit <= 0 for limit in (max_read_bytes, max_decode_bytes)):
            raise SourceError("INVALID_INPUT", "Read budgets must be positive integers")
        canonical = str(Path(path).resolve(strict=True))
        stat = Path(canonical).stat()
        with tifffile.TiffFile(canonical) as tif:
            if page_index >= len(tif.pages):
                raise SourceError("INVALID_INPUT", "Page index is outside the TIFF")
            page = tif.pages[page_index]
            shape = page.shape
            gray = len(shape) == 2 and page.photometric.name in ("MINISBLACK", "MINISWHITE")
            rgb = (len(shape) == 3 and shape[-1] in (3, 4) and page.photometric.name == "RGB"
                   and page.planarconfig == tifffile.PLANARCONFIG.CONTIG)
            if not (gray or rgb) or np.dtype(page.dtype).kind not in "buif":
                raise SourceError("UNSUPPORTED_FORMAT", "Only numeric grayscale or interleaved RGB/RGBA pages are supported")
            height, width = shape[:2]
            bits = page.bitspersample
            bits = max(bits) if isinstance(bits, tuple) else bits
            meta = OriginalMetadata(width, height, np.dtype(page.dtype).name, int(bits),
                                    1 if gray else shape[-1], stat.st_size, stat.st_mtime_ns,
                                    len(tif.pages))
        identity = SourceIdentity(canonical, stat.st_size, stat.st_mtime_ns, page_index, width, height)
        for name, value in {"path": canonical, "page_index": page_index, "metadata": meta,
                            "identity": identity, "max_read_bytes": max_read_bytes,
                            "max_decode_bytes": max_decode_bytes}.items():
            object.__setattr__(self, name, value)
        self.validate_identity()

    def validate_identity(self):
        try:
            stat = Path(self.path).stat()
        except OSError as exc:
            raise SourceError("SOURCE_CHANGED", "Source is no longer accessible") from exc
        if (stat.st_size, stat.st_mtime_ns) != (self.identity.file_size, self.identity.mtime_ns):
            raise SourceError("SOURCE_CHANGED", "Source size or modification time changed; reopen the file")

    def validate_region(self, x, y, width, height):
        if any(type(value) is not int for value in (x, y, width, height)):
            raise SourceError("INVALID_ROI", "ROI coordinates must be integers")
        if (x < 0 or y < 0 or width <= 0 or height <= 0 or
                x + width > self.metadata.width or y + height > self.metadata.height):
            raise SourceError("INVALID_ROI", "ROI must be nonempty and inside the original page")

    def read_region(self, x: int, y: int, width: int, height: int) -> np.ndarray:
        try:
            return self._read_region(x, y, width, height)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError("SOURCE_READ_FAILED", str(exc)) from exc

    def _read_region(self, x, y, width, height):
        self.validate_region(x, y, width, height)
        self.validate_identity()
        meta = self.metadata
        itemsize = np.dtype(meta.dtype).itemsize
        if width * height * meta.channels * itemsize > self.max_read_bytes:
            raise SourceError("READ_LIMIT_EXCEEDED", "Requested array exceeds the read budget; use smaller regions")
        with tifffile.TiffFile(self.path) as tif:
            page = tif.pages[self.page_index]
            if page.is_memmappable:
                mapped = tifffile.memmap(self.path, page=self.page_index, mode="r")
                try:
                    output = np.array(mapped[y:y + height, x:x + width], copy=True)
                finally:
                    mapped._mmap.close()
            else:
                page_bytes = meta.width * meta.height * meta.channels * itemsize
                if page_bytes > self.max_decode_bytes:
                    raise SourceError("UNSUPPORTED_LARGE_DECODE", "Compressed/nonmappable page exceeds decode budget; region decoder required")
                pixels = page.asarray(maxworkers=1)
                output = np.array(pixels[y:y + height, x:x + width], copy=True)
        self.validate_identity()
        return output

    def read_full(self) -> np.ndarray:
        """Explicit full read, subject to the same allocation and decoding budgets."""
        return self.read_region(0, 0, self.metadata.width, self.metadata.height)
