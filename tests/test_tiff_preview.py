"""Verify TIFF decoding and the limits of the display preview."""

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.imaging.tiff_preview import load_tiff_preview


def test_grayscale_first_page_and_display_range(tmp_path):
    path = tmp_path / "stack.tif"
    with tifffile.TiffWriter(path) as writer:
        writer.write(np.array([[0, 65535], [32768, 0]], dtype=np.uint16))
        writer.write(np.full((2, 2), 42, dtype=np.uint16))

    preview = load_tiff_preview(path)
    assert (preview.width, preview.height, preview.bit_depth, preview.page_count) == (
        2, 2, 16, 2
    )
    assert preview.image.pixelColor(0, 0).red() == 0
    assert preview.image.pixelColor(1, 0).red() == 255


def test_rgb_and_large_preview(tmp_path):
    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 10, 20]
    path = tmp_path / "rgb.tif"
    tifffile.imwrite(path, rgb, photometric="rgb")
    preview = load_tiff_preview(path)
    assert preview.image.pixelColor(0, 0).getRgb()[:3] == (255, 10, 20)

    large_path = tmp_path / "wide.tif"
    tifffile.imwrite(large_path, np.ones((2, 4097), dtype=np.uint8))
    large = load_tiff_preview(large_path)
    assert large.sampled
    assert large.width == 4097
    assert large.image.width() <= 4096


def test_miniswhite_is_displayed_with_correct_polarity(tmp_path):
    path = tmp_path / "white_zero.tif"
    tifffile.imwrite(
        path, np.array([[0, 255]], dtype=np.uint8), photometric="miniswhite"
    )
    preview = load_tiff_preview(path)
    assert preview.image.pixelColor(0, 0).red() == 255
    assert preview.image.pixelColor(1, 0).red() == 0


def test_lzw_compressed_tiff(tmp_path):
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(path, np.array([[0, 255]], dtype=np.uint8), compression="lzw")
    preview = load_tiff_preview(path)
    assert preview.image.pixelColor(1, 0).red() == 255


def test_unsupported_shape_is_reported(tmp_path):
    path = tmp_path / "many_channels.tif"
    tifffile.imwrite(
        path,
        np.zeros((4, 4, 5), dtype=np.uint8),
        photometric="rgb",
        planarconfig="contig",
    )
    with pytest.raises(ValueError, match="지원하지|회색조"):
        load_tiff_preview(path)
