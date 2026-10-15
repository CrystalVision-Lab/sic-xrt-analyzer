import cv2
import numpy as np
import pytest

from sic_xrt_analyzer.wafer_map.mosaic import compose


def texture():
    rng = np.random.default_rng(131)
    a = rng.integers(30, 220, (400, 520, 3), np.uint8)
    a = cv2.GaussianBlur(a, (3, 3), 0)
    for _ in range(100):
        x, y = rng.integers([5, 5], [515, 395])
        cv2.circle(a, (int(x), int(y)), int(rng.integers(2, 10)), (20, 20, 20), -1)
    return a


def meta(images, names=None):
    return [
        {
            "name": names[i] if names else str(i) + ".jpg",
            "width": a.shape[1],
            "height": a.shape[0],
        }
        for i, a in enumerate(images)
    ]


def test_overlap_geometry_mosaic_not_arbitrary_grid():
    a = texture()
    images = [
        a[0:260, 0:300],
        a[0:260, 220:520],
        a[140:400, 0:300],
        a[140:400, 220:520],
    ]
    r = compose(images, meta(images))
    assert (
        r["evidence"]["method"] == "SIFT_SIMILARITY_RANSAC"
        and len(r["transforms"]) == 4
    )
    assert abs(r["size"][0] - 520) < 5 and abs(r["size"][1] - 400) < 5
    h0 = r["transforms"][0]
    h1 = r["transforms"][1]
    assert (
        np.linalg.norm((h1 @ np.array([0, 0, 1]) - h0 @ np.array([220, 0, 1]))[:2]) < 2
    )
    assert r["rgba"].shape[2] == 4


def test_provided_composite_verified_not_duplicated():
    a = texture()
    images = [a, a[:200, :260], a[:200, 260:], a[200:, :260], a[200:, 260:]]
    r = compose(images, meta(images))
    assert r["evidence"]["method"] == "PROVIDED_COMPOSITE"
    assert np.array_equal(r["rgba"][:, :, :3], a)
    assert r["size"] == [520, 400] and len(r["transforms"]) == 5


def test_unrelated_solid_images_fail_instead_of_fake_wafer():
    images = [
        np.full((100, 100, 3), 30, np.uint8),
        np.full((100, 100, 3), 190, np.uint8),
    ]
    with pytest.raises(ValueError, match="겹치는"):
        compose(images, meta(images))
    with pytest.raises(InterruptedError):
        compose([texture()], meta([texture()]), cancelled=lambda: True)


def test_numbered_area_composites_make_one_round_wafer():
    import cv2

    rng = np.random.default_rng(131)
    a = cv2.GaussianBlur(
        rng.integers(20, 180, (288, 288, 3), dtype=np.uint8), (19, 19), 0
    )
    y, x = np.ogrid[:288, :288]
    a[(x - 144) ** 2 + (y - 144) ** 2 > 138**2] = 240
    images = [
        a[r * 96 : (r + 1) * 96, c * 96 : (c + 1) * 96]
        for r in range(3)
        for c in range(3)
    ]
    result = compose(
        images, meta(images, [f"After annealing_{i + 1}.jpg" for i in range(9)])
    )
    assert result["evidence"]["method"] == "ACQUISITION_EDGE_ORDER"
    assert result["size"] == [288, 288]
    assert np.array_equal(result["rgba"][:, :, :3], a)
