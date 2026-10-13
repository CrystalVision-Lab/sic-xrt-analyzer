"""Coordinate integrity, evidence gates, immutable maps and unmerged observation totals."""

import copy
import hashlib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image
from test_result_domain import MANIFEST, legacy

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.adapter import import_legacy_result
from sic_xrt_analyzer.results.contracts import DefectInstance, VerificationStatus
from sic_xrt_analyzer.results.geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
    GraphEdge,
    GraphNode,
)
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import publish_dependencies
from sic_xrt_analyzer.wafer_map import assets
from sic_xrt_analyzer.wafer_map.mapping import (
    calibration,
    compose,
    footprint,
    inverse,
    layout,
    matrix,
    points,
)
from sic_xrt_analyzer.wafer_map.scene import Scene, paths


@pytest.fixture
def study(tmp_path):
    image = np.random.default_rng(116).integers(0, 255, (512, 640, 3), dtype=np.uint8)
    path = tmp_path / "original.jpg"
    Image.fromarray(image).save(path)
    s = JpegImageSource(path)
    p = import_legacy_result(
        AnalysisProject("QA Map"), legacy(s, count=2946), model_manifest=MANIFEST
    )
    record = verify_content_hash(p.image_sources[0])
    p = p.evolve(image_sources=(record,))
    a = assets.blank(p)
    a["runs"][record.source_id] = p.analysis_runs[0].run_id
    a["placements"] = [placement(record)]
    a["revision"] = 1
    a["editor"] = "QA"
    return p, a, record, tmp_path / "project.json"


def placement(s, m=None, group="relative"):
    return {
        "placement_id": str(uuid4()),
        "source_id": s.source_id,
        "source_sha256": s.content_hash.value,
        "size": [s.width, s.height],
        "group_id": group,
        "matrix": m or layout(0, 0, 0, 1, 1),
        "status": "UNVERIFIED",
        "evidence": {"origin": "synthetic"},
        "created_at": utc_now().isoformat(),
        "editor": "QA",
    }


def physical_group():
    return {
        "id": "physical",
        "label": "QA synthetic wafer",
        "mode": "PHYSICAL",
        "wafer_id": "QA-WAFER",
        "coordinate_system": "QA-XY",
        "unit": "mm",
        "origin": "synthetic measured origin",
        "axes": "X_RIGHT_Y_DOWN",
        "evidence": "QA-only independent synthetic geometry",
        "geometry": None,
    }


def evidence(m, size):
    w, h = size
    a = [[10, 10], [w - 11, 10], [10, h - 11], [w - 11, h - 11]]
    return {
        "source": "QA known transform",
        "reviewer": "QA-only",
        "pixel_spacing": np.linalg.norm(np.asarray(m)[:2, :2], axis=0).tolist(),
        "landmarks": [
            {"image": p, "map": q} for p, q in zip(a, points(m, a), strict=True)
        ],
        "tolerance": 0.005,
        "registration_reference": None,
        "same_target_evidence": "",
    }


@pytest.mark.parametrize(
    "m,axes",
    [
        (layout(30, -20, 0, 1, 1), "X_RIGHT_Y_DOWN"),
        (layout(30, 20, 45, 1, 1), "X_RIGHT_Y_DOWN"),
        (layout(3, 2, 0, 0.002, 0.002), "X_RIGHT_Y_DOWN"),
        (layout(3, 2, 20, 0.002, 0.003), "X_RIGHT_Y_DOWN"),
        ([[0.002, 0.001, 4], [0, 0.003, 8], [0, 0, 1]], "X_RIGHT_Y_DOWN"),
        (layout(2, 5, 40, 0.003, 0.001, "X_RIGHT_Y_UP"), "X_RIGHT_Y_UP"),
    ],
)
def test_known_transforms_roundtrip_and_rotated_footprint(m, axes):
    matrix(m, axes)
    p = [[0, 0], [639, 511], [0, 511], [639, 0], [230, 140]]
    assert np.max(np.abs(np.array(points(inverse(m), points(m, p))) - p)) < 1e-9
    border = footprint(m, 640, 512)
    assert len(border) == 4
    assert np.allclose(border[0], points(m, [[-0.5, -0.5]])[0])


@pytest.mark.parametrize(
    "bad",
    [
        [[0, 0, 0], [0, 0, 0], [0, 0, 1]],
        [[1, 0, 0], [0, 1, 0], [0.001, 0, 1]],
        [[1, 0, 0], [0, -1, 0], [0, 0, 1]],
        [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]],
        [[1e-12, 0, 0], [0, 1, 0], [0, 0, 1]],
    ],
)
def test_bad_transforms(bad):
    with pytest.raises(ValueError):
        matrix(bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "px"),
        ("origin", ""),
        ("wafer_id", ""),
        ("evidence", ""),
        ("axes", "UNKNOWN"),
    ],
)
def test_missing_physical_coordinate_evidence(study, field, value):
    p, a, _s, _ = study
    g = physical_group()
    g[field] = value
    a["groups"].append(g)
    a["selected_group"] = "physical"
    with pytest.raises(ValueError):
        assets.validate(a, p)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "reviewer",
        "collinear",
        "outside",
        "duplicates",
        "spacing",
        "error",
        "tolerance",
    ],
)
def test_physical_control_point_gate(study, change):
    _p, _a, s, _ = study
    m = layout(2, 3, 15, 0.01, 0.012)
    e = evidence(m, [s.width, s.height])
    g = physical_group()
    if change in ("source", "reviewer"):
        e[change] = ""
    if change == "collinear":
        e["landmarks"] = [
            {"image": [x, x], "map": points(m, [[x, x]])[0]} for x in (10, 20, 30)
        ]
    if change == "outside":
        e["landmarks"][0]["image"] = [-1, 0]
    if change == "duplicates":
        e["landmarks"][1] = e["landmarks"][0]
    if change == "spacing":
        e["pixel_spacing"] = [1, 1]
    if change == "error":
        e["landmarks"][0]["map"][0] += 1
    if change == "tolerance":
        e["tolerance"] = 1e9
    with pytest.raises(ValueError):
        calibration(m, [s.width, s.height], g, e)


def test_physical_asset_and_relative_never_auto_verified(study):
    p, a, s, path = study
    g = physical_group()
    a["groups"].append(g)
    m = layout(2, 3, 25, 0.01, 0.012)
    row = placement(s, m, "physical")
    row["evidence"] = evidence(m, row["size"])
    row["status"] = "VERIFIED"
    a["placements"] = [row]
    q = assets.append(p, a, path)
    ProjectStore().save(path, q)
    assert ProjectStore().load(path) == q
    assert (
        q.image_sources[0].wafer_placement.calibration_status
        == VerificationStatus.VERIFIED
    )
    assert p.image_sources[0].calibration == q.image_sources[0].calibration
    a["placements"][0]["group_id"] = "relative"
    with pytest.raises(ValueError):
        assets.validate(a, p)


def test_history_atomic_revision_save_as_and_missing_source(study, tmp_path):
    p, a, s, path = study
    sha = hashlib.sha256(Path(s.source_reference).read_bytes()).hexdigest()
    q = assets.append(p, a, path)
    ProjectStore().save(path, q)
    b = copy.deepcopy(a)
    b.update(
        revision=2,
        revision_id=str(uuid4()),
        parent_reference=assets.reference(a),
        created_at=(utc_now() + timedelta(seconds=1)).isoformat(),
    )
    b["placements"][0]["matrix"] = layout(50, 30, 35, 0.5, 0.8)
    r = assets.append(q, b, path)
    ProjectStore().save(path, r, expected_revision=q.revision)
    assert len(assets.chain(path, assets.reference(b), r)) == 2
    assert len(assets.chain(path, assets.reference(a), r)) == 1
    with pytest.raises(ValueError):
        ProjectStore().save(path, q, expected_revision=r.revision)
    new = tmp_path / "save-as" / "project.json"
    publish_dependencies(new, r, [], path)
    ProjectStore().save(new, r)
    assert ProjectStore().load(new) == r
    assert hashlib.sha256(Path(s.source_reference).read_bytes()).hexdigest() == sha
    Path(s.source_reference).unlink()
    assert ProjectStore().load(new) == r
    for table in (
        "analysis_runs",
        "observations",
        "predictions",
        "geometries",
        "review_events",
        "defect_instances",
        "model_provenance",
        "image_relationships",
    ):
        assert getattr(r, table) == getattr(p, table)


@pytest.mark.parametrize(
    "bad", ["duplicate", "sha", "source", "project", "group", "unit", "nan"]
)
def test_asset_identity_rejection(study, bad):
    p, a, _s, _ = study
    if bad == "duplicate":
        a["placements"].append(copy.deepcopy(a["placements"][0]))
    if bad == "sha":
        a["placements"][0]["source_sha256"] = "a" * 64
    if bad == "source":
        a["placements"][0]["source_id"] = "other"
    if bad == "project":
        a["project_id"] = "other"
    if bad == "group":
        a["placements"][0]["group_id"] = "unknown"
    if bad == "unit":
        a["groups"][0]["unit"] = "mm"
    if bad == "nan":
        a["placements"][0]["matrix"][0][2] = float("nan")
    with pytest.raises((ValueError, KeyError)):
        assets.validate(a, p)


def test_tamper_and_missing_asset_rejected(study):
    p, a, _s, path = study
    q = assets.append(p, a, path)
    ProjectStore().save(path, q)
    asset = path.parent / assets.reference(a)
    data = asset.read_bytes()
    asset.write_bytes(data + b" ")
    with pytest.raises(ValueError):
        ProjectStore().load(path)
    asset.write_bytes(data)
    asset.unlink()
    with pytest.raises(FileNotFoundError):
        ProjectStore().load(path)


def test_run_selection_culling_cache_and_counts(study):
    p, a, s, _ = study
    reader = JpegImageSource(s.source_reference)
    p = import_legacy_result(
        p, legacy(reader, count=791), model_manifest=MANIFEST, source_id=s.source_id
    )
    a["runs"][s.source_id] = p.analysis_runs[-1].run_id
    scene = Scene()
    frame = scene.render(p, a, [320, 256], 1, 900, 700)
    assert sum(frame["summary"].get(k, 0) for k in ("BPD", "TED", "TSD")) == 791
    assert scene.decode_count == 1
    nextframe = scene.render(p, a, [320, 256], 2, 900, 700)
    assert scene.decode_count == 1 and frame["summary"] == nextframe["summary"]
    offscreen = scene.render(p, a, [100000, 100000], 1, 900, 700)
    assert (
        not offscreen["tiles"]
        and not offscreen["paths"]
        and frame["summary"] == offscreen["summary"]
    )
    a["runs"][s.source_id] = p.analysis_runs[0].run_id
    full = scene.render(p, a, [320, 256], 0.01, 900, 700)
    assert sum(full["summary"].get(k, 0) for k in ("BPD", "TED", "TSD")) == 2946
    assert full["omitted_display_points"] > 0
    assert len(p.analysis_runs) == 2 and scene.decode_count == 1
    Path(s.source_reference).unlink()
    missing = scene.render(p, a, [320, 256], 1, 900, 700)
    assert missing["tiles"][0]["availability"] == "MISSING" and not missing["images"]


def test_graph_edges_and_mask_bounds_are_exact(study):
    p, a, s, _ = study
    g = DefectGeometry(
        str(uuid4()),
        s.source_id,
        0,
        DefectGeometryKind.BRANCHED_GRAPH,
        GeometrySource.HUMAN,
        nodes=(GraphNode("a", 10, 10), GraphNode("b", 20, 10), GraphNode("c", 10, 20)),
        edges=(
            GraphEdge("ab", "a", "b", ((10, 10), (15, 12), (20, 10))),
            GraphEdge("ac", "a", "c"),
        ),
    )
    assert paths(g) == [[(10, 10), (15, 12), (20, 10)], [[10, 10], [10, 20]]]
    i = DefectInstance(
        str(uuid4()),
        s.source_id,
        g.geometry_id,
        class_label="BPD",
        instance_status="HUMAN",
    )
    p = p.evolve(geometries=(*p.geometries, g), defect_instances=(i,))
    f = Scene().render(p, a, [320, 256], 1, 900, 700)
    row = next(r for r in f["paths"] if r["layer"] == "human")
    assert len(row["paths"]) == 2
    assert f["summary"]["human"] == 1


def test_failed_registration_is_not_identity(study):
    _p, _a, s, _path = study
    other = replace(s, source_id=str(uuid4()), display_name="different")
    # Deliberately distinct content hashes are required in production assets.
    other = replace(other, content_hash=replace(s.content_hash, value="a" * 64))
    target = placement(other, layout(2, 3, 0, 0.01, 0.01), "physical")
    target["status"] = "VERIFIED"
    g = physical_group()
    r = {"status": "REJECTED", "matrix": None}
    with pytest.raises(ValueError):
        compose(r, target, g, s, other, "QA")
    r = {
        "status": "ACCEPTED",
        "matrix": layout(13, -7, 0, 1, 1),
        "source_id": s.source_id,
        "target_id": other.source_id,
        "source_sha256": s.content_hash.value,
        "target_sha256": other.content_hash.value,
    }
    m = compose(r, target, g, s, other, "QA known target")
    expected = np.asarray(target["matrix"]) @ np.asarray(r["matrix"])
    assert np.allclose(m, expected)
    with pytest.raises(ValueError):
        compose(r, target, g, s, other, "")
    with pytest.raises(ValueError):
        compose({**r, "source_id": other.source_id}, target, g, s, other, "QA")


def test_physical_y_up_screen_roundtrip_and_transformed_graph(study):
    from sic_xrt_analyzer.wafer_map.mapping import view

    p, a, _s, _path = study
    g = physical_group()
    g["axes"] = "X_RIGHT_Y_UP"
    a["groups"].append(g)
    a["selected_group"] = g["id"]
    a["placements"][0].update(
        group_id=g["id"], matrix=layout(1, 2, 25, 0.01, 0.02, g["axes"])
    )
    f = Scene().render(p, a, [3, 4], 20, 900, 700)
    screen = view([3, 4], 20, 900, 700, g["axes"])
    assert points(screen, [[3, 5]])[0][1] < points(screen, [[3, 4]])[0][1]
    expected = screen @ np.asarray(a["placements"][0]["matrix"])
    assert np.allclose(f["tiles"][0]["matrix"], expected)
    pts = [[0, 0], [600, 500], [140, 210]]
    assert np.allclose(points(inverse(expected), points(expected, pts)), pts, atol=1e-9)


def test_corrected_review_conflict_group_totals_and_mask_bounds(study):
    from test_result_domain import review

    from sic_xrt_analyzer.results.contracts import (
        ExistenceDecision,
        GeometryDecision,
        ReviewStatus,
    )

    p, a, s, _path = study
    g = DefectGeometry(
        str(uuid4()),
        s.source_id,
        0,
        DefectGeometryKind.MASK_REFERENCE,
        GeometrySource.HUMAN,
        bbox=(20, 30, 50, 60),
        mask_reference="geometry/references/qa.png",
        mask_encoding="png",
    )
    p = p.evolve(geometries=(*p.geometries, g))
    e = review(
        p,
        status=ReviewStatus.CORRECTED,
        geometry_decision=GeometryDecision.CORRECTED,
        corrected_geometry_reference=g.geometry_id,
        existence=ExistenceDecision.PRESENT,
    )
    fork = review(p, reviewer="qa-other", existence=ExistenceDecision.ABSENT)
    p = replace(p, schema_version="1.1.0").evolve(review_events=(e, fork))
    before = p.geometries
    f = Scene().render(p, a, [320, 256], 1, 900, 700)
    row = next(r for r in f["paths"] if r["layer"] == "reviews" and r["mask_bounds"])
    assert (
        row["target_id"] == p.observations[0].observation_id
        and row["label"] == "CONFLICT"
    )
    assert np.allclose(row["paths"][0], points(f["tiles"][0]["matrix"], paths(g)[0]))
    assert f["review_summary"]["conflicts"] == 1 and p.geometries == before
    a["groups"].append(physical_group())
    a["selected_group"] = "physical"
    empty = Scene().render(p, a, [320, 256], 1, 900, 700)
    assert empty["summary"] == {} and empty["review_summary"] == {}
