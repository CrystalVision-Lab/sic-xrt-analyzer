import hashlib

import numpy as np
import pytest
import tifffile
from PIL import Image

from sic_xrt_analyzer.wafer_map.native_view import NativeViewport


def row(path, w, h):
    return {
        "id": "0",
        "path": str(path),
        "width": w,
        "height": h,
        "preview_width": w // 4,
        "preview_height": h // 4,
    }


@pytest.mark.parametrize("zoom", [1, 2, 4])
def test_original_crop_exact_at_native_zoom(tmp_path, zoom):
    a = np.random.default_rng(135).integers(0, 256, (256, 256, 3), np.uint8)
    p = tmp_path / "original.tif"
    tifffile.imwrite(p, a, photometric="rgb")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    renderer = NativeViewport()
    result, _ = renderer.render(
        1, [row(p, 256, 256)], {"0": np.eye(3)}, [10, 12, 8, 6], 4 * zoom
    )
    assert np.array_equal(
        result[:, :, :3], np.repeat(np.repeat(a[48:72, 40:72], zoom, 0), zoom, 1)
    )
    assert (result[:, :, 3] == 255).all()
    assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
    renderer.close()


def test_jpeg_prepared_cache_reused_and_stale_original_rejected(tmp_path):
    p = tmp_path / "source.jpg"
    Image.fromarray(
        np.random.default_rng(135).integers(0, 256, (128, 128, 3), np.uint8)
    ).save(p)
    renderer = NativeViewport()
    rows = [row(p, 128, 128)]
    try:
        for rect in ([0, 0, 8, 8], [4, 4, 8, 8], [0, 0, 8, 8]):
            renderer.render(1, rows, {"0": np.eye(3)}, rect, 4)
        assert renderer.decodes == 1 and renderer.hits == 1
        with p.open("ab") as f:
            f.write(b"changed")
        with pytest.raises(ValueError):
            renderer.render(1, rows, {"0": np.eye(3)}, [0, 0, 8, 8], 4)
    finally:
        renderer.close()


def test_viewport_budget_cancel_and_overview_does_not_decode(tmp_path):
    p = tmp_path / "source.jpg"
    Image.new("RGB", (128, 128)).save(p)
    renderer = NativeViewport()
    rows = [row(p, 128, 128)]
    result, _ = renderer.render(1, rows, {"0": np.eye(3)}, [0, 0, 32, 32], 1)
    assert renderer.decodes == 0 and not result.any()
    with pytest.raises(InterruptedError):
        renderer.render(1, rows, {"0": np.eye(3)}, [0, 0, 8, 8], 4, lambda: True)
    renderer.close()


def test_rotated_capture_keeps_original_pixel_centers(tmp_path):
    a = np.random.default_rng(135).integers(0, 256, (64, 64, 3), np.uint8)
    p = tmp_path / "rotated.tif"
    tifffile.imwrite(p, a, photometric="rgb")
    renderer = NativeViewport()
    matrix = np.array([[0, -1, 15], [1, 0, 0], [0, 0, 1.0]])
    result, _ = renderer.render(1, [row(p, 64, 64)], {"0": matrix}, [0, 0, 16, 16], 4)
    assert np.array_equal(result[:, :, :3], np.rot90(a, k=-1))
    assert (result[:, :, 3] == 255).all()
    renderer.close()


def test_overlap_uses_capture_pixels_without_double_exposure(tmp_path):
    rows = []
    transforms = {}
    for n, color in enumerate([(100, 120, 140), (140, 100, 120)]):
        p = tmp_path / f"{n}.tif"
        tifffile.imwrite(p, np.full((64, 64, 3), color, np.uint8), photometric="rgb")
        r = row(p, 64, 64)
        r["id"] = str(n)
        rows.append(r)
        transforms[str(n)] = np.eye(3)
    renderer = NativeViewport()
    result, _ = renderer.render(1, rows, transforms, [0, 0, 16, 16], 4)
    assert np.array_equal(
        np.unique(result[:, :, :3].reshape(-1, 3), axis=0), [[140, 100, 120]]
    )
    renderer.close()
