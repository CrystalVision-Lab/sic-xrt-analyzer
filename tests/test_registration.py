from pathlib import Path

"""Known transforms, invalid evidence, immutable assets and original viewport samples."""

import hashlib
from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.registration import assets
from sic_xrt_analyzer.registration.comparison import ComparisonSession
from sic_xrt_analyzer.registration.engine import (
    VERSION,
    estimate,
    fit_landmarks,
    inverse_transform,
    pixel_mapping,
    transform_bounds,
    transform_points,
    validate_transform,
)
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source


def texture(size=512):
    rng = np.random.default_rng(114)
    image = np.zeros((size, size, 3), np.uint8) + 35
    for _ in range(250):
        xy = tuple(rng.integers(10, size - 10, 2).tolist())
        cv2.circle(
            image,
            xy,
            int(rng.integers(2, 8)),
            tuple(rng.integers(70, 250, 3).tolist()),
            -1,
        )
    return image


@pytest.fixture
def pair(tmp_path):
    before = texture()
    m = np.eye(3)
    m[:2, 2] = [13, -7]
    after = cv2.warpAffine(before, m[:2], (512, 512))
    a = tmp_path / "before.jpg"
    b = tmp_path / "after.jpg"
    Image.fromarray(before).save(a, quality=98)
    Image.fromarray(after).save(b, quality=98)
    p = AnalysisProject("정합 실험")
    p, sa = add_source(p, JpegImageSource(a))
    p, sb = add_source(p, JpegImageSource(b))
    sa, sb = verify_content_hash(sa), verify_content_hash(sb)
    p = p.evolve(image_sources=(sa, sb))
    return p, sa, sb, m


@pytest.mark.parametrize(
    "model,m",
    [
        ("translation", [[1, 0, 32], [0, 1, 0], [0, 0, 1]]),
        ("translation", [[1, 0, 0], [0, 1, 21], [0, 0, 1]]),
        ("rigid", [[0.995, -0.0998749, 30], [0.0998749, 0.995, 15], [0, 0, 1]]),
        ("similarity", [[1.1, 0, 3], [0, 1.1, 5], [0, 0, 1]]),
        ("affine", [[1.1, 0.08, 5], [-0.03, 0.9, 20], [0, 0, 1]]),
    ],
)
def test_manual_known_models(model, m):
    m = np.array(m, float)
    if model == "rigid":
        m[:2, :2] /= np.linalg.norm(m[:2, 0])
    p = np.array([[20, 20], [230, 25], [40, 200], [210, 210], [140, 90]], float)
    q = transform_points(m, p)
    result = fit_landmarks(p, q, (512, 512), (600, 550), model)
    assert result["status"] == "NEEDS_REVIEW"
    assert (
        np.max(np.linalg.norm(transform_points(result["matrix"], p) - q, axis=1)) < 1e-6
    )
    assert np.allclose(transform_points(inverse_transform(result["matrix"]), q), p)
    assert len(transform_bounds(m, (0, 0, 100, 50))) == 4


@pytest.mark.parametrize("method", ["sift", "orb", "phase", "ecc"])
def test_known_image_translation(method):
    a = texture()
    m = np.array([[1, 0, 13], [0, 1, -7], [0, 0, 1]], float)
    b = cv2.warpAffine(a, m[:2], (512, 512))
    r = estimate(a, b, (512, 512), (512, 512), method=method, model="translation")
    assert r["status"] == "NEEDS_REVIEW", r
    assert np.max(np.abs(np.array(r["matrix"])[:2, 2] - m[:2, 2])) < 1
    again = estimate(a, b, (512, 512), (512, 512), method=method, model="translation")
    assert np.allclose(r["matrix"], again["matrix"], atol=0.1)


@pytest.mark.parametrize(
    "change",
    [
        "rotation",
        "scale",
        "affine",
        "resolution",
        "brightness",
        "contrast",
        "noise",
        "overlap",
    ],
)
def test_sift_structural_changes(change):
    a = texture()
    m = np.eye(3)
    size = (512, 512)
    if change == "rotation":
        m[:2] = cv2.getRotationMatrix2D((256, 256), 8, 1)
    if change == "scale":
        m[:2] = cv2.getRotationMatrix2D((256, 256), 0, 1.12)
    if change == "affine":
        m[:2] = [[1, 0.08, -10], [-0.03, 1, 12]]
    if change == "resolution":
        m[:2, :2] *= 1.5
        size = (768, 768)
    if change == "overlap":
        m[:2, 2] = [160, 30]
    b = cv2.warpAffine(a, m[:2], size)
    if change == "brightness":
        b = np.clip(b.astype(float) + 30, 0, 255).astype(np.uint8)
    if change == "contrast":
        b = np.clip(b.astype(float) * 0.7 + 20, 0, 255).astype(np.uint8)
    if change == "noise":
        b = np.clip(
            b.astype(float) + np.random.default_rng(7).normal(0, 8, b.shape), 0, 255
        ).astype(np.uint8)
    r = estimate(
        a,
        b,
        (512, 512),
        size,
        method="sift",
        model="affine" if change == "affine" else "auto",
    )
    assert r["status"] == "NEEDS_REVIEW"
    grid = np.array([[200, 100], [350, 200], [200, 350]])
    error = np.linalg.norm(
        transform_points(r["matrix"], grid) - transform_points(m, grid), axis=1
    )
    assert error.max() < 2, error


def test_anisotropic_resize_centres():
    m = pixel_mapping(123, 89, 1001, 777)
    assert np.allclose(
        transform_points(m, [[0, 0], [122, 88]]),
        [
            [1001 / 123 / 2 - 0.5, 777 / 89 / 2 - 0.5],
            [(122.5) * 1001 / 123 - 0.5, (88.5) * 777 / 89 - 0.5],
        ],
    )


@pytest.mark.parametrize(
    "points,kind",
    [
        ([[1, 1]], "affine"),
        ([[1, 1], [1, 1]], "similarity"),
        ([[0, 0], [10, 10], [20, 20.00001]], "affine"),
        ([[-1, 1]], "translation"),
    ],
)
def test_degenerate_landmarks_rejected(points, kind):
    with pytest.raises(ValueError):
        fit_landmarks(points, points, (512, 512), (512, 512), kind)


def test_bad_matches_rejected():
    a = np.random.default_rng(1).uniform(10, 500, (60, 2))
    b = np.random.default_rng(2).uniform(10, 500, (60, 2))
    r = fit_landmarks(a, b, (512, 512), (512, 512), robust=True)
    assert r["status"] == "REJECTED"
    with pytest.raises(ValueError):
        estimate(
            np.zeros((128, 128, 3), np.uint8),
            np.zeros((128, 128, 3), np.uint8),
            (128, 128),
            (128, 128),
        )
    with pytest.raises(InterruptedError):
        estimate(texture(), texture(), (512, 512), (512, 512), cancelled=lambda: True)


@pytest.mark.parametrize(
    "matrix",
    [
        np.zeros((3, 3)),
        [[1, 0, 0], [0, 1, 0], [0, 0.001, 1]],
        [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]],
        [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
    ],
)
def test_invalid_transform(matrix):
    with pytest.raises(ValueError):
        validate_transform(matrix)


def asset_for(pair):
    p, a, b, m = pair
    xy = [[20, 20], [450, 30], [30, 460], [450, 450]]
    result = fit_landmarks(
        xy, transform_points(m, xy), (512, 512), (512, 512), "translation"
    )
    result.update(algorithm="manual", algorithm_version=VERSION, timings={})
    return assets.make_asset(p, a, b, result)


def test_atomic_asset_history_reopen_and_save_as(pair, tmp_path):
    p, *_ = pair
    path = tmp_path / "project.json"
    ProjectStore().save(path, p)
    estimated = asset_for(pair)
    assets.publish(path, estimated)
    new = assets.append(p, estimated)
    ProjectStore().save(path, new, expected_revision=p.revision)
    approved = assets.approve(estimated, "local-researcher")
    assets.publish(path, approved)
    latest = assets.append(new, approved)
    ProjectStore().save(path, latest, expected_revision=new.revision)
    assert ProjectStore().load(path) == latest
    assert (
        len(latest.image_relationships) == 2 and estimated["status"] == "NEEDS_REVIEW"
    )
    assert latest.image_relationships[0].verification_status.value == "UNVERIFIED"
    assert latest.image_relationships[1].verification_status.value == "VERIFIED"
    assert latest.image_relationships[1].match_quality is None
    copy = tmp_path / "copy" / "project.json"
    assets.copy_assets(path, copy, latest)
    ProjectStore().save(copy, latest)
    assert ProjectStore().load(copy) == latest
    with pytest.raises(ValueError):
        ProjectStore().save(
            path, latest.evolve(project_name="conflict"), expected_revision=1
        )
    with pytest.raises(ValueError):
        ProjectStore().save(
            path,
            latest.evolve(image_relationships=()),
            expected_revision=latest.revision,
        )


def test_missing_tampered_and_wrong_identity(pair, tmp_path):
    p, a, b, _ = pair
    path = tmp_path / "project.json"
    asset = asset_for(pair)
    new = assets.append(p, asset)
    with pytest.raises(FileNotFoundError):
        ProjectStore().save(path, new)
    ref = assets.publish(path, asset)
    ProjectStore().save(path, new)
    original = (path.parent / ref).read_bytes()
    (path.parent / ref).write_bytes(original + b" ")
    with pytest.raises(ValueError):
        ProjectStore().load(path)
    (path.parent / ref).write_bytes(original)
    with pytest.raises(ValueError):
        assets.validate(asset, replace(p, project_id="other"))
    with pytest.raises(ValueError):
        assets.validate({**asset, "source_sha256": "0" * 64}, p)
    with pytest.raises(ValueError):
        assets.validate({**asset, "matrix": [[1, 0, 0], [0, 0, 0], [0, 0, 1]]}, p)
        # Missing originals retain safe metadata; source validation remains a separate operation.
        Path(a.source_reference).unlink()
    Path(b.source_reference).unlink()
    assert ProjectStore().load(path) == new


def test_viewport_original_cache_coordinate_samples(pair):
    _p, a, b, m = pair
    before_sha = hashlib.sha256(Path(a.source_reference).read_bytes()).hexdigest()
    session = ComparisonSession(a, b)
    try:
        for zoom in (1, 2, 4):
            frame = session.render([256, 256], zoom, 128, 128, m)
            assert frame["levels"] == ["original_crop", "original_crop"]
            mapped = transform_points(frame["mapping"][0], [[243, 263]])[0]
            assert np.allclose(mapped, [64, 64])
            centre = frame["before"].pixelColor(64, 64)
            expected = session.sources[0].read_region(243, 263, 1, 1)[0, 0]
            assert np.allclose([centre.red(), centre.green(), centre.blue()], expected)
            assert session.render([256, 256], zoom, 128, 128, m)["cache_hit"]
        for x in range(10):
            session.render([200 + x * 5, 260], 2, 128, 128, m)
        assert len(session.frames) <= 3 and session.decode_count == 4
        with pytest.raises(InterruptedError):
            session.render([256, 256], 1, 128, 128, m, lambda: True)
    finally:
        session.close()
    assert (
        hashlib.sha256(Path(a.source_reference).read_bytes()).hexdigest() == before_sha
    )


def test_fit_view_matrix_is_not_registration_scale(pair):
    _p, a, b, m = pair
    session = ComparisonSession(a, b)
    try:
        frame = session.render([256, 256], 0.065, 128, 128, m)
        assert frame["levels"] == ["preview", "preview"]
        assert np.allclose(
            transform_points(inverse_transform(frame["mapping"][1]), [[64, 64]]),
            [[256, 256]],
        )
    finally:
        session.close()


def test_graph_overlay_culling_does_not_invent_edges(pair):
    from sic_xrt_analyzer.results.geometry import (
        DefectGeometry,
        DefectGeometryKind,
        GraphEdge,
        GraphNode,
    )

    p, a, b, m = pair
    nodes = (
        GraphNode("a", 240, 250),
        GraphNode("b", 260, 250),
        GraphNode("c", 240, 270),
    )
    edges = (GraphEdge("ab", "a", "b"), GraphEdge("ac", "a", "c"))
    geometry = DefectGeometry(
        "graph",
        a.source_id,
        0,
        DefectGeometryKind.BRANCHED_GRAPH,
        nodes=nodes,
        edges=edges,
    )
    p = p.evolve(geometries=(geometry,))
    session = ComparisonSession(a, b)
    try:
        frame = session.render([256, 256], 1, 128, 128, m)
        rows = session.overlays(
            p, a.source_id, b.source_id, frame, 128, 128, lambda: False
        )
        assert len(rows) == 2
        assert rows[0]["points"] == [[240, 250], [260, 250]]
        assert rows[1]["points"] == [[240, 250], [240, 270]]
        assert geometry == p.geometries[0]
        with pytest.raises(InterruptedError):
            session.overlays(p, a.source_id, b.source_id, frame, 128, 128, lambda: True)
        far = session.render([450, 450], 4, 128, 128, m)
        assert (
            session.overlays(p, a.source_id, b.source_id, far, 128, 128, lambda: False)
            == []
        )
    finally:
        session.close()
