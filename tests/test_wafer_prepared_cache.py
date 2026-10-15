import numpy as np
from PIL import Image

from sic_xrt_analyzer.wafer_map.native_view import NativeViewport


def test_all_sources_prepared_and_reopened_without_decoding(tmp_path):
    rows, transforms = [], {}
    for i in range(4):
        path = tmp_path / f"{i}.jpg"
        Image.new("RGB", (512, 512), (30 * i, 80, 150)).save(path)
        rows.append(
            {
                "id": str(i),
                "path": str(path),
                "width": 512,
                "height": 512,
                "preview_width": 128,
                "preview_height": 128,
            }
        )
        transforms[str(i)] = np.array([[1, 0, 128 * i], [0, 1, 0], [0, 0, 1.0]])
    renderer = NativeViewport()
    renderer.cache_root = tmp_path / "cache"
    renderer.prepare(1, rows, transforms)
    assert renderer.decodes == 4
    for x in (0, 128, 256, 384, 0):
        image, _ = renderer.renderTiles(1, rows, transforms, [x, 0, 128, 128], 4)
        assert image[:, :, 3].all()
    assert renderer.decodes == 4
    renderer.close()
    reopened = NativeViewport()
    reopened.cache_root = tmp_path / "cache"
    reopened.prepare(2, rows, transforms)
    assert reopened.decodes == 0
    reopened.close()


def test_pan_reuses_tiles_and_exact_source_coordinates(tmp_path):
    import tifffile

    pixels = np.random.default_rng(1).integers(0, 256, (512, 512, 3), np.uint8)
    path = tmp_path / "raw.tif"
    tifffile.imwrite(path, pixels, photometric="rgb")
    row = {
        "id": "a",
        "path": str(path),
        "width": 512,
        "height": 512,
        "preview_width": 128,
        "preview_height": 128,
    }
    renderer = NativeViewport()
    renderer.cache_root = tmp_path / "cache"
    renderer.prepare(1, [row], {"a": np.eye(3)})
    for x in (0, 4):
        image, rect = renderer.renderTiles(
            1, [row], {"a": np.eye(3)}, [x, 0, 80, 64], 4
        )
        assert np.array_equal(image[:, :, :3], pixels[:256, x * 4 : x * 4 + 320])
        assert rect == [x, 0, 80, 64]
    assert renderer.hits >= 2
    renderer.close()
