"""Synthetic topology / evidence grouping; these are not real BPD accuracy metrics."""

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.analysis.bpd_samples import SYNTHETIC_CASES, synthetic_sample
from sic_xrt_analyzer.analysis.bpd_structure import StructureSettings, detect_structures
from sic_xrt_analyzer.analysis.contracts import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisScope,
    AnalysisState,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
    Region,
    utc_now,
)
from sic_xrt_analyzer.analysis.skeleton_graph import trace_skeleton
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore, import_legacy_result
from sic_xrt_analyzer.results.bpd_experiment import (
    attach_experiment,
    comparison_image,
    load_experiment_bundle,
    save_experiment_bundle,
)
from sic_xrt_analyzer.results.contracts import (
    LinkStatus,
    ReviewEvent,
    ReviewStatus,
    ReviewTarget,
)
from sic_xrt_analyzer.results.geometry import DefectGeometryKind, GeometrySource
from sic_xrt_analyzer.results.reviews import ReviewRepository, prediction_snapshot
from sic_xrt_analyzer.results.serialization import dumps
from sic_xrt_analyzer.results.validation import new_id


def settings(method="sato", polarity="bright", **overrides):
    data = {
        "method": method,
        "polarity": polarity,
        "scales": (1, 2),
        "low_threshold": 0.10,
        "high_threshold": 0.25,
        "contrast_floor": 0.005,
        "background_sigma": 8,
        "min_area": 12,
        "min_length_px": 20,
        "max_width_px": 12,
        "min_aspect": 3,
        "link_distance_px": 4,
    }
    return StructureSettings(**{**data, **overrides})


def source_for(
    tmp_path,
    name="straight",
    *,
    dtype="uint8",
    rgb=False,
    polarity="bright",
    offset=(0, 0),
):
    sample = synthetic_sample(name, dtype=dtype, rgb=rgb, polarity=polarity)
    x, y = offset
    image = np.full(
        (160 + y + 10, 160 + x + 10) + sample.shape[2:],
        120 * (257 if dtype == "uint16" else 1),
        sample.dtype,
    )
    image[y : y + 160, x : x + 160] = sample
    path = tmp_path / (name + dtype + polarity + ".tif")
    tifffile.imwrite(path, image, photometric="rgb" if rgb else "minisblack")
    return OriginalImageSource(path), Region(x, y, 160, 160)


def legacy_project(source, points):
    request = AnalysisRequest(
        source, AnalysisScope.FULL_IMAGE, "synthetic-classifier", "test-v1"
    )
    rows = tuple(
        Detection(
            str(i),
            ("BPD", "TED", "TSD").index(label),
            label,
            0.9123456789012345,
            Geometry(
                GeometryKind.POINT, ((x, y),), coordinate_space=CoordinateSpace.ORIGINAL
            ),
            {
                "point_id": f"point-{i}",
                "scores": [0.9123456789012345, 0.05, 0.0376543210987655],
                "low_score": False,
            },
        )
        for i, (x, y, label) in enumerate(points)
    )
    now = utc_now()
    result = AnalysisResult(
        request, AnalysisState.COMPLETED, now, now + timedelta(seconds=1), 1.0, rows
    )
    return import_legacy_result(AnalysisProject("Synthetic structure QA"), result)


@pytest.mark.parametrize("name", SYNTHETIC_CASES)
def test_twelve_synthetic_cases_image_topology_and_original_integrity(tmp_path, name):
    source, roi = source_for(tmp_path, name)
    before = hashlib.sha256(Path(source.path).read_bytes()).hexdigest()
    e = detect_structures(source, roi, settings())
    expected = (
        0
        if name in ("empty", "point_noise")
        else 2
        if name in ("separated", "parallel")
        else 1
    )
    assert len(e.proposals) == expected
    if name in ("y", "t"):
        assert len(e.proposals[0].topology.nodes) == 4
        assert len(e.proposals[0].topology.paths) == 3
        assert sorted(e.proposals[0].topology.degrees) == [1, 1, 1, 3]
        assert len(e.proposals[0].topology.junction_clusters) == 1
    if name == "cross":
        assert sorted(e.proposals[0].topology.degrees) == [1, 1, 1, 1, 4]
        assert "CROSSING_OR_CONTACT_AMBIGUOUS" in e.proposals[0].flags
    if name == "boundary":
        assert "TRUNCATED_AT_IMAGE_BOUNDARY" in e.proposals[0].flags
    if name == "short_branch":
        assert "SHORT_BRANCH_REQUIRES_REVIEW" in e.proposals[0].flags
        assert not e.proposals[0].removed_paths
    assert not e.original.flags.writeable
    assert hashlib.sha256(Path(source.path).read_bytes()).hexdigest() == before
    assert e.source_identity == source.identity.__dict__


@pytest.mark.parametrize("method", ("local_contrast", "sato", "frangi"))
@pytest.mark.parametrize("polarity", ("bright", "dark"))
def test_bright_dark_methods_use_original_evidence(tmp_path, method, polarity):
    source, roi = source_for(tmp_path, "straight", polarity=polarity)
    e = detect_structures(source, roi, settings(method, polarity))
    assert len(e.proposals) == 1 and e.proposals[0].polarity == polarity
    assert e.preprocessing["gap_closing"] is False


@pytest.mark.parametrize(
    "dtype,rgb", (("uint8", True), ("uint16", False), ("uint16", True))
)
def test_explicit_rgb_and_uint16_preprocessing_no_model_prediction(
    tmp_path, dtype, rgb
):
    source, roi = source_for(tmp_path, "y", dtype=dtype, rgb=rgb)
    e = detect_structures(source, roi, settings())
    a = attach_experiment(AnalysisProject("ROI only"), e)
    assert e.original.dtype.name == dtype
    assert e.preprocessing["divisor"] == (65535 if dtype == "uint16" else 255)
    assert len(a.project.defect_instances) == 1
    assert (
        not a.project.predictions
        and not a.project.observations
        and not a.project.analysis_runs
    )
    assert a.project.defect_instances[0].class_label is None
    assert not a.project.defect_instances[0].assessment.ground_truth_eligible


def test_original_roi_offset_and_geometry_mask_roundtrip(tmp_path):
    source, roi = source_for(tmp_path, "y", offset=(70, 60))
    e = detect_structures(source, roi, settings())
    a = attach_experiment(AnalysisProject("Offset"), e)
    primary = a.project.geometries[0]
    assert primary.kind == DefectGeometryKind.BRANCHED_GRAPH
    assert primary.geometry_source == GeometrySource.RULE_BASED
    assert all(
        roi.x <= x < roi.x + roi.width and roi.y <= y < roi.y + roi.height
        for x, y in primary.all_points()
    )
    assert len(primary.nodes) == 4 and len(primary.edges) == 3
    mask = a.project.geometries[1]
    assert mask.kind == DefectGeometryKind.MASK_REFERENCE
    target = tmp_path / "bundle"
    save_experiment_bundle(target, a, comparison_image(e, AnalysisProject("View"), a))
    loaded, manifest = load_experiment_bundle(target)
    assert (
        loaded == a.project and ProjectStore().load(target / "project.json") == loaded
    )
    assert manifest["algorithm_version"] == "0.1.0"
    assert manifest["source_identity"] == e.source_identity
    assert manifest["roi"] == roi.__dict__
    assert (
        ProjectStore()
        .resolve_asset(target / "project.json", mask.mask_reference)
        .is_file()
    )
    assert attach_experiment(a.project, e).project is a.project
    with pytest.raises(FileExistsError):
        save_experiment_bundle(target, a, b"x")


def test_existing_predictions_reviews_untouched_and_same_line_links(tmp_path):
    source, roi = source_for(tmp_path)
    project = legacy_project(
        source,
        [
            (30, 80, "BPD"),
            (80, 80, "BPD"),
            (130, 80, "BPD"),
            (80, 100, "BPD"),
            (100, 80, "TED"),
        ],
    )
    o = project.observations[0]
    snap, run = prediction_snapshot(project, ReviewTarget.OBSERVATION, o.observation_id)
    review = ReviewEvent(
        new_id(),
        ReviewTarget.OBSERVATION,
        o.observation_id,
        "synthetic-reviewer",
        ReviewStatus.UNCERTAIN,
        snap,
        utc_now(),
        1,
        run,
    )
    project = ReviewRepository().append(project, review)
    before = dumps(project)
    e = detect_structures(source, roi, settings())
    a = attach_experiment(project, e, run_id=run)
    instance = a.project.defect_instances[0]
    assert [l.observation_id for l in instance.linked_observations] == [
        o.observation_id for o in project.observations[:3]
    ]
    assert all(l.status == LinkStatus.PROPOSED for l in instance.linked_observations)
    assert a.project.observations == project.observations
    assert a.project.predictions == project.predictions
    assert a.project.analysis_runs == project.analysis_runs
    assert a.project.review_events == project.review_events
    assert dumps(project) == before
    store = ProjectStore()
    target = tmp_path / "project.json"
    store.save(target, project)
    store.save(target, a.project, expected_revision=project.revision)
    assert store.load(target) == a.project


@pytest.mark.parametrize(
    "name,points",
    [
        (
            "parallel",
            [
                (40, 65, "BPD"),
                (110, 65, "BPD"),
                (40, 85, "BPD"),
                (110, 85, "BPD"),
                (80, 75, "BPD"),
            ],
        ),
        (
            "separated",
            [
                (30, 40, "BPD"),
                (60, 40, "BPD"),
                (100, 110, "BPD"),
                (130, 110, "BPD"),
                (80, 75, "BPD"),
            ],
        ),
    ],
)
def test_separate_image_regions_nearby_parallel_not_distance_grouped(
    tmp_path, name, points
):
    source, roi = source_for(tmp_path, name)
    p = legacy_project(source, points)
    a = attach_experiment(
        p, detect_structures(source, roi, settings()), run_id=p.analysis_runs[0].run_id
    )
    links = [
        {l.observation_id for l in i.linked_observations}
        for i in a.project.defect_instances
    ]
    assert (
        len(links) == 2
        and all(len(ids) == 2 for ids in links)
        and not links[0] & links[1]
    )
    assert p.observations[-1].observation_id not in set.union(*links)
    assert len(a.project.observations) == 5


@pytest.mark.parametrize(
    "name,points",
    [
        ("y", [(55, 50, "BPD"), (105, 50, "BPD"), (80, 120, "BPD")]),
        (
            "cross",
            [(40, 40, "BPD"), (120, 120, "BPD"), (120, 40, "BPD"), (80, 80, "BPD")],
        ),
    ],
)
def test_y_group_and_crossing_ambiguity_never_confirmed(tmp_path, name, points):
    source, roi = source_for(tmp_path, name)
    p = legacy_project(source, points)
    a = attach_experiment(
        p, detect_structures(source, roi, settings()), run_id=p.analysis_runs[0].run_id
    )
    instance = a.project.defect_instances[0]
    assert len(instance.linked_observations) == len(points)
    expected = LinkStatus.AMBIGUOUS if name == "cross" else LinkStatus.PROPOSED
    assert all(link.status == expected for link in instance.linked_observations)
    assert instance.class_label is None and not a.project.review_events
    assert not instance.assessment.ground_truth_eligible


def test_pruning_opt_in_keeps_before_geometry_and_border_is_not_extrapolated(tmp_path):
    source, roi = source_for(tmp_path, "short_branch")
    unpruned = detect_structures(source, roi, settings())
    pruned = detect_structures(source, roi, settings(prune_length_px=15))
    assert len(unpruned.proposals[0].topology.paths) == 3
    assert pruned.proposals[0].removed_paths
    assert len(pruned.proposals[0].before_pruning.paths) == 3
    assert "PRUNED_REVIEW_REQUIRED" in pruned.proposals[0].flags
    a = attach_experiment(AnalysisProject("Pruning"), pruned)
    assert (
        a.manifest["proposals"][0]["before_pruning"]["coordinate_space"] == "ORIGINAL"
    )
    assert a.manifest["proposals"][0]["removed_paths"]


def test_roi_boundary_distinct_from_original_image_boundary(tmp_path):
    source, roi = source_for(tmp_path, "boundary", offset=(20, 20))
    e = detect_structures(source, roi, settings())
    assert "TRUNCATED_AT_ROI_BOUNDARY" in e.proposals[0].flags
    assert "TRUNCATED_AT_IMAGE_BOUNDARY" not in e.proposals[0].flags


def test_unbroken_pixel_ring_graph_integrity_no_self_or_duplicate_edges(tmp_path):
    import cv2

    skel = np.zeros((40, 40), np.uint8)
    cv2.rectangle(skel, (10, 10), (30, 30), 1, 1)
    t = trace_skeleton(skel.astype(bool))
    assert t.cycle and len(t.nodes) == 3 and len(t.paths) == 3
    assert all(a != b for a, b, _ in t.paths)
    assert len({frozenset((a, b)) for a, b, _ in t.paths}) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("low_threshold", 0),
        ("high_threshold", 2),
        ("scales", ()),
        ("min_area", True),
        ("contrast_floor", float("nan")),
        ("prune_length_px", -1),
        ("polarity", "automatic"),
        ("max_roi_pixels", 100_000_000),
    ],
)
def test_invalid_settings_rejected(field, value):
    with pytest.raises((ValueError, TypeError)):
        settings(**{field: value})


def test_cancel_budget_page_identity_and_source_change(tmp_path, monkeypatch):
    source, roi = source_for(tmp_path)
    with pytest.raises(InterruptedError):
        detect_structures(source, roi, settings(), cancel=lambda: True)
    with pytest.raises(ValueError):
        detect_structures(source, roi, settings(max_roi_pixels=100))
    with pytest.raises(ValueError):
        detect_structures(source, Region(-1, 0, 160, 160), settings())
    e = detect_structures(source, roi, settings())
    a = attach_experiment(AnalysisProject("Source"), e)
    wrong = replace(e, source_identity={**e.source_identity, "file_size": 123})
    with pytest.raises(ValueError):
        attach_experiment(
            a.project, wrong, source_id=a.project.image_sources[0].source_id
        )
    with pytest.raises(ValueError):
        attach_experiment(a.project, e, run_id="absent")
    Path(source.path).write_bytes(b"changed synthetic source")
    with pytest.raises(ValueError):
        detect_structures(source, roi, settings())


def test_failed_bundle_preserves_prior_project_and_cleans_owned_stage(
    tmp_path, monkeypatch
):
    source, roi = source_for(tmp_path)
    p = AnalysisProject("Previous")
    target = tmp_path / "previous.json"
    ProjectStore().save(target, p)
    old = target.read_bytes()
    e = detect_structures(source, roi, settings())
    a = attach_experiment(p, e)
    import sic_xrt_analyzer.results.bpd_experiment as module

    def failed(*args):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(module.os, "rename", failed)
    with pytest.raises(OSError):
        save_experiment_bundle(tmp_path / "failed", a, comparison_image(e, p, a))
    assert target.read_bytes() == old and not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".failed.*"))


@pytest.mark.parametrize(
    "mutation", ("version", "path", "hash", "geometry", "algorithm")
)
def test_bundle_rejects_corruption_unsafe_assets_and_wrong_refs(tmp_path, mutation):
    source, roi = source_for(tmp_path)
    p = AnalysisProject("Corruption")
    e = detect_structures(source, roi, settings())
    a = attach_experiment(p, e)
    out = tmp_path / "bundle"
    save_experiment_bundle(out, a, comparison_image(e, p, a))
    path = out / "experiment.json"
    data = json.loads(path.read_text())
    if mutation == "version":
        data["schema_version"] = "2.0.0"
    elif mutation == "path":
        data["assets"]["../original.tif"] = "a" * 64
    elif mutation == "hash":
        data["assets"]["comparison.png"] = "a" * 64
    elif mutation == "geometry":
        data["proposals"][0]["geometry_id"] = "missing"
    else:
        data["algorithm"] = "arbitrary"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        load_experiment_bundle(out)


def test_binary_mask_extent_and_samples_are_verified_even_with_updated_asset_hash(
    tmp_path,
):
    from PIL import Image

    source, roi = source_for(tmp_path)
    project = AnalysisProject("Binary mask")
    e = detect_structures(source, roi, settings())
    a = attach_experiment(project, e)
    out = tmp_path / "bundle"
    save_experiment_bundle(out, a, comparison_image(e, project, a))
    manifest_path = out / "experiment.json"
    m = json.loads(manifest_path.read_text())
    ref = a.masks[0][0]
    path = out / ref
    Image.fromarray(np.full(a.masks[0][1].shape, 127, np.uint8)).save(path)
    m["assets"][ref] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="binary samples"):
        load_experiment_bundle(out)


@pytest.mark.parametrize(
    "mutation", ("header", "page", "roi", "classification", "collection")
)
def test_experiment_provenance_fields_are_not_silently_accepted(tmp_path, mutation):
    source, roi = source_for(tmp_path)
    p = AnalysisProject("Provenance")
    e = detect_structures(source, roi, settings())
    a = attach_experiment(p, e)
    out = tmp_path / "bundle"
    save_experiment_bundle(out, a, comparison_image(e, p, a))
    path = out / "experiment.json"
    m = json.loads(path.read_text())
    if mutation == "header":
        m["source_metadata"]["dtype"] = "float32"
    elif mutation == "page":
        m["source_identity"]["page_index"] = 500
    elif mutation == "roi":
        m["roi"]["x"] = -1
    elif mutation == "classification":
        m["proposals"][0]["classification"] = "BPD"
    else:
        m["assets"] = []
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError):
        load_experiment_bundle(out)


def test_only_explicit_roi_is_read_and_global_skeleton_budget_fails_cleanly(
    tmp_path, monkeypatch
):
    source, roi = source_for(tmp_path, "parallel")
    calls = []
    original_read = OriginalImageSource.read_region

    def read(self, *args):
        calls.append(args)
        return original_read(self, *args)

    def full(self):
        raise AssertionError("Full image/stack read forbidden")

    monkeypatch.setattr(OriginalImageSource, "read_region", read)
    monkeypatch.setattr(OriginalImageSource, "read_full", full)
    with pytest.raises(ValueError, match="connectivity budget"):
        detect_structures(source, roi, settings(max_skeleton_pixels=150))
    assert calls == [(roi.x, roi.y, roi.width, roi.height)]


def test_both_polarities_are_kept_separate_and_unsupported_dtype_rejected(tmp_path):
    import cv2

    image = np.full((160, 160), 120, np.uint8)
    cv2.line(image, (20, 50), (140, 50), 220, 5)
    cv2.line(image, (20, 100), (140, 100), 20, 5)
    path = tmp_path / "mixed.tif"
    tifffile.imwrite(path, image, photometric="minisblack")
    e = detect_structures(
        OriginalImageSource(path), Region(0, 0, 160, 160), settings(polarity="both")
    )
    assert len(e.proposals) == 2 and {p.polarity for p in e.proposals} == {
        "bright",
        "dark",
    }
    path = tmp_path / "float.tif"
    tifffile.imwrite(path, image.astype(np.float32), photometric="minisblack")
    with pytest.raises(ValueError, match="uint8/uint16"):
        detect_structures(OriginalImageSource(path), Region(0, 0, 160, 160), settings())


def test_junction_representative_paths_follow_actual_cluster_pixels():
    from itertools import pairwise

    from sic_xrt_analyzer.analysis.skeleton_graph import pixel_neighbors, trace_skeleton

    skeleton = np.zeros((10, 10), bool)
    for x, y in (
        (4, 4),
        (5, 4),
        (4, 5),
        (5, 5),
        (4, 3),
        (4, 2),
        (6, 4),
        (7, 4),
        (5, 6),
        (5, 7),
        (3, 5),
        (2, 5),
    ):
        skeleton[y, x] = True
    topology = trace_skeleton(skeleton)
    neighbors = pixel_neighbors(skeleton)
    assert len(topology.junction_clusters[0]) >= 4
    assert len(topology.paths) == 4
    for _, _, path in topology.paths:
        for p, q in pairwise(path):
            assert q in neighbors[p]
