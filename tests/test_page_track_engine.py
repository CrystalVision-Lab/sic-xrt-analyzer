"""Synthetic page-track engine evidence (#181); not a real-data accuracy claim."""

import json

import numpy as np
import pytest

from sic_xrt_analyzer.stack3d.tracking import (
    TrackResult,
    TrackSettings,
    detect_page,
    track_from_seed,
    track_stack,
)
from sic_xrt_analyzer.stack3d.tracking.benchmark import run_benchmark, scenarios

# Thresholds are deliberately below the current scores (see
# docs/result/XRT-TRACK-181-ENGINE.md) so tuning noise does not flip them.
MIN_RECALL = 0.8
MIN_PURITY = 0.9
MIN_GAIN_OVER_OLD = 0.25
MIN_LINK_PRECISION = 0.8
MIN_LINK_RECALL = 0.85
KNOWN_LIMITS = {"texture_snr2"}  # both engines fail; documented limit
MUST_BEAT_OLD = {"gap", "crossing", "texture", "dense"}


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    return {r["name"]: r for r in run_benchmark(tmp_path_factory.mktemp("bench"))}


def _line_volume(pages=8, x=30, gain=None):
    rng = np.random.default_rng(0)
    v = 60000 + rng.normal(0, 200, (pages, 96, 96))
    v[:, 20:76, x:x + 3] -= 9000
    if gain is not None:
        v *= np.asarray(gain)[:, None, None]
    return np.clip(v, 0, 65535).astype(np.uint16)


def test_detection_is_independent_of_crop_and_gain():
    v = _line_volume()
    full = [d for d in detect_page(v[3], 3) if d.kind == "SEGMENT"]
    crop = [d for d in detect_page(v[3, 10:90, 5:70], 3, origin=(5, 10)) if d.kind == "SEGMENT"]
    dim = [d for d in detect_page((v[3] * 0.4).astype(np.uint16), 3) if d.kind == "SEGMENT"]
    assert len(full) == len(crop) == len(dim) == 1
    for other in (crop[0], dim[0]):
        assert np.allclose(full[0].centroid, other.centroid, atol=1.0)
        assert abs(full[0].contrast_z - other.contrast_z) / full[0].contrast_z < 0.2


def test_result_json_round_trip_keeps_auto_proposed_status():
    result = track_stack(_line_volume(), origin=(100, 200), first_page=10)
    text = json.dumps(result.to_dict())
    back = TrackResult.from_dict(json.loads(text))
    assert back.to_dict() == result.to_dict()
    assert all(t.status == "PROPOSED" and t.source == "AUTO" for t in back.tracks)
    assert {d.page for d in back.detections} <= set(range(10, 18))
    with pytest.raises(ValueError):
        TrackResult.from_dict({**result.to_dict(), "schema": "other/v9"})


def test_seed_returns_whole_track_in_original_coordinates():
    seed = track_from_seed(_line_volume(), 13, 131, 250, origin=(100, 200), first_page=10)
    assert seed.track.pages == tuple(range(10, 18))
    assert seed.detection.page == 13
    with pytest.raises(ValueError):
        track_from_seed(_line_volume(), 13, 180, 220, origin=(100, 200), first_page=10,
                        result=seed.result)


def test_cancel_and_settings_validation():
    with pytest.raises(InterruptedError):
        track_stack(_line_volume(), cancelled=lambda: True)
    with pytest.raises(ValueError):
        TrackSettings(polarity="GREY")
    with pytest.raises(ValueError):
        TrackSettings(low_z=6, high_z=5)


def test_gap_pages_are_bridged_with_gap_links():
    v = _line_volume(pages=10)
    v[4:7] = _line_volume(pages=10, x=80)[4:7]  # line absent, unrelated one present
    seed = track_from_seed(v, 1, 31, 40)
    assert seed.track.pages == (0, 1, 2, 3, 7, 8, 9)
    gap = [link for link in seed.result.links
           if link.kind == "GAP" and link.target_id in seed.track.detection_ids]
    assert len(gap) == 1 and gap[0].confidence < 1


def test_benchmark_scenarios_are_deterministic():
    a, b = scenarios(), scenarios()
    assert [s.name for s in a] == [s.name for s in b]
    assert all(np.array_equal(x.volume, y.volume) for x, y in zip(a, b))


def test_new_engine_meets_floor_and_beats_old_baseline(rows):
    for name, r in rows.items():
        if name in KNOWN_LIMITS:
            continue
        new, glob = r["new"], r["global"]
        assert new["page_recall"] >= MIN_RECALL, name
        assert new["purity"] >= MIN_PURITY, name
        assert glob["link_precision"] >= MIN_LINK_PRECISION, name
        assert glob["link_recall"] >= MIN_LINK_RECALL, name
        if r["category"] in MUST_BEAT_OLD:
            assert new["page_recall"] >= r["old"]["page_recall"] + MIN_GAIN_OVER_OLD, name


def test_branching_is_proposed_as_split_candidate(rows):
    assert rows["branching"]["global"]["split_merge_candidates"] >= 1
