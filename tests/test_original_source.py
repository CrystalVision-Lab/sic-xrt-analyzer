import os
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource, SourceError
from sic_xrt_analyzer.imaging.tiff_preview import load_tiff_preview


@pytest.mark.parametrize("dtype", ["uint8", "uint16", "float32"])
@pytest.mark.parametrize("compression", [None, "deflate"])
def test_original_metadata_region_and_dtype(tmp_path, dtype, compression):
    pixels = np.arange(80, dtype=dtype).reshape(8, 10)
    if dtype == "float32":
        pixels = pixels / 7 - 20
        pixels[0, 0] = np.nan
    path = tmp_path / "raw.tiff"
    tifffile.imwrite(path, pixels, compression=compression)
    source = OriginalImageSource(path)
    m = source.metadata
    assert (m.width, m.height, m.dtype, m.channels, m.bit_depth) == (10, 8, dtype, 1, pixels.dtype.itemsize * 8)
    assert m.file_size == path.stat().st_size
    assert m.mtime_ns == path.stat().st_mtime_ns and m.format == "TIFF"
    assert source.identity.canonical_path == str(path.resolve())
    np.testing.assert_array_equal(source.read_region(3, 2, 7, 6), pixels[2:8, 3:10])
    np.testing.assert_array_equal(source.read_full(), pixels)
    assert source.read_full().dtype == pixels.dtype
    with pytest.raises(FrozenInstanceError):
        source.page_index = 1


@pytest.mark.parametrize("roi", [(-1, 0, 1, 1), (0, -1, 1, 1), (0, 0, 0, 1),
                                 (0, 0, 1, -1), (9, 0, 2, 1), (0, 7, 1, 2),
                                 (0.0, 0, 1, 1), (True, 0, 1, 1)])
def test_invalid_roi_rejected(tmp_path, roi):
    path = tmp_path / "raw.tif"
    tifffile.imwrite(path, np.zeros((8, 10), np.uint8))
    with pytest.raises(SourceError, match="ROI") as exc:
        OriginalImageSource(path).read_region(*roi)
    assert exc.value.code == "INVALID_ROI"


def test_rgb_miniswhite_and_page_identity(tmp_path):
    path = tmp_path / "pages.tif"
    gray = np.arange(24, dtype=np.uint16).reshape(4, 6)
    rgb = np.arange(72, dtype=np.uint8).reshape(4, 6, 3)
    with tifffile.TiffWriter(path) as writer:
        writer.write(gray, photometric="miniswhite")
        writer.write(rgb, photometric="rgb")
    first, second = OriginalImageSource(path), OriginalImageSource(path, 1)
    assert first.identity != second.identity and second.metadata.channels == 3
    assert first.metadata.page_count == 2
    np.testing.assert_array_equal(first.read_full(), gray)  # No display inversion.
    np.testing.assert_array_equal(second.read_region(1, 1, 3, 2), rgb[1:3, 1:4])
    with pytest.raises(SourceError):
        OriginalImageSource(path, 2)


def test_large_original_is_separate_from_preview(tmp_path, monkeypatch):
    path = tmp_path / "large.tif"
    mapped = tifffile.memmap(path, shape=(6000, 8000), dtype="uint16", photometric="minisblack")
    mapped[:] = 50000
    mapped[1800:1803, 4000:4004] = np.arange(12).reshape(3, 4) + 12345
    mapped.flush()
    mapped._mmap.close()
    source = OriginalImageSource(path, max_read_bytes=1024)
    def forbid_decode(*args, **kwargs):
        raise AssertionError("Memmapped region must not decode the entire page")
    monkeypatch.setattr(tifffile.TiffPage, "asarray", forbid_decode)
    preview = load_tiff_preview(path)
    assert (source.metadata.width, source.metadata.height) == (8000, 6000)
    assert (preview.image.width(), preview.image.height()) == (4000, 3000)
    assert preview.sampled
    raw = source.read_region(4000, 1800, 4, 3)
    np.testing.assert_array_equal(raw, np.arange(12).reshape(3, 4) + 12345)
    assert raw.dtype == np.uint16
    with pytest.raises(SourceError) as exc:
        source.read_full()
    assert exc.value.code == "READ_LIMIT_EXCEEDED"


def test_compressed_decode_budget_and_file_mutation(tmp_path, monkeypatch):
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(path, np.zeros((32, 32), np.uint16), compression="deflate")
    source = OriginalImageSource(path, max_decode_bytes=100)
    def forbid_decode(*args, **kwargs):
        raise AssertionError("Decode budget must be checked before allocating")
    monkeypatch.setattr(tifffile.TiffPage, "asarray", forbid_decode)
    with pytest.raises(SourceError) as exc:
        source.read_region(0, 0, 1, 1)
    assert exc.value.code == "UNSUPPORTED_LARGE_DECODE"
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    with pytest.raises(SourceError) as exc:
        source.read_region(0, 0, 1, 1)
    assert exc.value.code == "SOURCE_CHANGED"


def test_preview_rejects_oversized_compressed_page_before_decode(tmp_path, monkeypatch):
    from sic_xrt_analyzer.imaging import tiff_preview
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(path, np.zeros((32, 32), np.uint16), compression="deflate")
    monkeypatch.setattr(tiff_preview, "MAX_PREVIEW_DECODE_BYTES", 100)
    def forbid_decode(*args, **kwargs):
        raise AssertionError("Oversized compressed preview must not allocate full page")
    monkeypatch.setattr(tifffile.TiffPage, "asarray", forbid_decode)
    with pytest.raises(ValueError, match="디코딩 한도"):
        load_tiff_preview(path)


def test_planar_rgb_is_explicitly_unsupported(tmp_path):
    path = tmp_path / "planar.tif"
    # Last axis is four: shape alone must not misidentify separate planes as RGBA.
    tifffile.imwrite(path, np.zeros((3, 5, 4), np.uint8), photometric="rgb", planarconfig="separate")
    with pytest.raises(SourceError) as exc:
        OriginalImageSource(path)
    assert exc.value.code == "UNSUPPORTED_FORMAT"
    with pytest.raises(ValueError, match="인터리브"):
        load_tiff_preview(path)


def test_decoder_failure_uses_source_error_code(tmp_path, monkeypatch):
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(path, np.zeros((8, 8), np.uint16), compression="deflate")
    source = OriginalImageSource(path)
    def broken_decoder(*args, **kwargs):
        raise RuntimeError("decoder detail")
    monkeypatch.setattr(tifffile.TiffPage, "asarray", broken_decoder)
    with pytest.raises(SourceError, match="decoder detail") as exc:
        source.read_full()
    assert exc.value.code == "SOURCE_READ_FAILED"
