import json
from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np
import pytest
from PIL import Image

from sic_xrt_analyzer.analysis.research import (
    FrozenClassifier,
    analyze_image,
    classify_points,
    propose_points,
    read_rgb,
)
from sic_xrt_analyzer.registration.research import (
    fit_registration,
    match_points,
    register_images,
    track_analyses,
    transform_points,
)


class DummyClassifier:
    manifest: ClassVar = {"bundle_id": "test", "model_sha256": "test"}

    def predict(self, patches):
        assert all(p.shape == (128, 128, 3) and p.dtype == np.uint8 for p in patches)
        return np.tile([.1, .8, .1], (len(patches), 1))


def point(name, x, y, label="TED"):
    return {"point_id": name, "x": x, "y": y, "predicted_type": label, "uncertain": False}


def test_classify_coordinates_are_not_shifted_or_padded():
    image = np.zeros((256, 256, 3), np.uint8)
    points = [point("a", 100.2, 100), point("same", 100.1, 100), point("edge", 10, 10),
              point("bad", float("nan"), 100), point("boundary", 192, 192)]
    accepted, rejected = classify_points(image, points, DummyClassifier())
    assert len(accepted) == 2
    assert accepted[0]["x"] == 100.2
    assert accepted[0]["predicted_type"] == "TED"
    assert not accepted[0]["human_verified"]
    assert {p["reason"] for p in rejected} == {
        "duplicate_crop_center", "incomplete_128px_patch", "invalid_coordinate"}


def test_uint16_and_gray_rejected(tmp_path):
    for array in [np.zeros((200, 200, 3), np.uint16), np.zeros((200, 200), np.uint8)]:
        with pytest.raises(ValueError, match="uint8 RGB"):
            classify_points(array, [], DummyClassifier())
    path = tmp_path / "gray.png"
    Image.fromarray(np.zeros((200, 200), np.uint8)).save(path)
    with pytest.raises(ValueError, match="uint8 RGB"):
        read_rgb(path)


def test_no_candidates_on_flat_background_and_candidate_cap():
    blank = np.full((1200, 1200, 3), 90, np.uint8)
    points, capped = propose_points(blank)
    assert points == [] and not capped
    for x in [200, 400, 600, 800, 1024]:
        cv2.circle(blank, (x, 400), 4, (255, 255, 255), -1)
    points, capped = propose_points(blank, max_candidates=3)
    assert len(points) == 3 and capped
    full, capped = propose_points(blank, max_candidates=10)
    assert len(full) == 5 and not capped  # tile seam does not double count


def test_saved_analysis_empty_is_completed_not_defect_free(tmp_path):
    image_path = tmp_path / "flat.png"
    Image.fromarray(np.zeros((256, 256, 3), np.uint8)).save(image_path)
    result = analyze_image(image_path, DummyClassifier(), tmp_path)
    assert result["classified_count"] == 0
    assert result["counts_are"] == "classified_candidate_points_not_verified_defect_totals"
    assert (Path(result["output_dir"]) / "predictions.csv").is_file()
    assert result["human_verified"] is False


def test_bad_bundle_contract_fails_before_runtime(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="계약"):
        FrozenClassifier(tmp_path)


def test_known_transform_fit_rejects_outliers_and_preserves_direction():
    rng = np.random.default_rng(8)
    after = rng.uniform(100, 800, (60, 2))
    matrix = np.array([[.98, -.04, 38], [.04, .98, 20], [0, 0, 1.]])
    before = transform_points(after, matrix)
    before[-10:] = rng.uniform(0, 1000, (10, 2))
    fitted = fit_registration(before, after, (1000, 1000, 3), (1000, 1000, 3),
                              method="test", ransac_px=2)
    assert fitted["status"] == "accepted_tentative"
    assert fitted["inlier_count"] == 50
    assert np.max(np.abs(transform_points(after[:50], fitted["matrix_after_to_before"])
                         - before[:50])) < .001


def test_registration_fails_on_blank_and_localized_points():
    blank = np.zeros((256, 256, 3), np.uint8)
    assert register_images(blank, blank)["status"] == "failed"
    xy = np.random.default_rng(1).uniform(100, 110, (30, 2))
    result = fit_registration(xy, xy, (1000, 1000), (1000, 1000), method="test")
    assert result["status"] == "failed"
    assert "inliers_too_localized" in result["reasons"]


def test_duplicate_feature_orientations_do_not_count_as_independent_support():
    xy = np.repeat([[10, 10], [100, 100], [900, 100], [100, 900]], 5, axis=0)
    result = fit_registration(xy, xy, (1000, 1000), (1000, 1000), method="test")
    assert result["status"] == "failed"
    assert result["unique_correspondence_count"] == 4


def test_sift_recovers_shift_with_different_preview_scales():
    rng = np.random.default_rng(12)
    before = rng.integers(0, 255, (700, 1000, 3), np.uint8)
    before = cv2.GaussianBlur(before, (3, 3), 0)
    # After is a smaller field of view, not merely the same-size image shifted.
    after = before[100:650, 200:950].copy()
    result = register_images(before, after, max_side=800)
    assert result["status"] == "accepted_tentative"
    mapped = transform_points([[0, 0], [400, 300]], result["matrix_after_to_before"])
    np.testing.assert_allclose(mapped, [[200, 100], [600, 400]], atol=2)


def test_ambiguous_pairs_and_overlap_never_become_conversion():
    matrix = np.array([[1, 0, 100], [0, 1, 0], [0, 0, 1]])
    before = [point("outside", 50, 100), point("good", 200, 100, "BPD"),
              point("conflict1", 300, 100), point("conflict2", 310, 100), point("none", 450, 100)]
    after = [point("changed", 100, 100, "TED"), point("ambiguous", 205, 100)]
    rows = match_points(before, after, matrix, (500, 500), (500, 400), radius=15)
    statuses = {r["before_id"]: r["status"] for r in rows if r["before_id"]}
    assert statuses == {"outside": "outside_overlap", "good": "tentative_match",
                        "conflict1": "ambiguous", "conflict2": "ambiguous", "none": "unmatched"}
    assert sum(r["type_change_candidate"] for r in rows) == 1
    assert all(not r["physical_conversion_confirmed"] for r in rows)


def test_failed_registration_saves_no_matches_and_changed_image_rejected(tmp_path):
    path = tmp_path / "flat.png"
    Image.fromarray(np.zeros((256, 256, 3), np.uint8)).save(path)
    a = analyze_image(path, DummyClassifier(), tmp_path)
    b = analyze_image(path, DummyClassifier(), tmp_path)
    result = track_analyses(a, b, tmp_path)
    assert result["status"] == "registration_failed" and result["matches"] == []
    Image.fromarray(np.full((256, 256, 3), 1, np.uint8)).save(path)
    with pytest.raises(ValueError, match="원본 영상"):
        track_analyses(a, b, tmp_path)
