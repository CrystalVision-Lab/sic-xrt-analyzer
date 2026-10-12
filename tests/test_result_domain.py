"""Research domain meaning, reference integrity and durable metadata-only storage."""

import hashlib
import json
import shutil
import struct
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
import tifffile
from test_analysis_pipeline import spin
from test_desktop_research import create_jpeg_source as create_source
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import (
    AnalysisError,
    AnalysisRequest,
    AnalysisResult,
    AnalysisScope,
    AnalysisState,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
    utc_now,
)
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results.adapter import import_legacy_result
from sic_xrt_analyzer.results.contracts import (
    AnalysisProject,
    DefectInstance,
    ImageRelationship,
    ImageRole,
    LabelAssessment,
    LinkStatus,
    ObservationLink,
    ReviewEvent,
    ReviewStatus,
    ReviewTarget,
    SpatialCalibration,
)
from sic_xrt_analyzer.results.geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
    GraphEdge,
    GraphNode,
)
from sic_xrt_analyzer.results.persistence import ProjectStore
from sic_xrt_analyzer.results.reviews import ReviewRepository, prediction_snapshot
from sic_xrt_analyzer.results.serialization import dumps, loads
from sic_xrt_analyzer.results.sources import (
    inspect_source,
    relink_source,
    verify_content_hash,
)
from sic_xrt_analyzer.results.validation import new_id

pytest_plugins = ("test_toolbar",)
MANIFEST = {
    "bundle_id": "synthetic-model",
    "model_sha256": "a" * 64,
    "classes": ["BPD", "TED", "TSD"],
    "input": {"shape": ["N", 3, 128, 128], "dtype": "float32"},
    "output": {"meaning": "uncalibrated_class_scores"},
}


def legacy(source, count=3, *, counts=None, status=AnalysisState.COMPLETED):
    request = AnalysisRequest(
        source,
        AnalysisScope.FULL_IMAGE,
        "synthetic-model",
        "a" * 64,
        parameters={
            "point_mode": "contrast_proposals",
            "proposal_threshold": 12.0,
            "score_threshold": 0.6,
            "max_candidates": 3000,
        },
    )
    labels = (
        [label for label, n in counts.items() for _ in range(n)]
        if counts
        else ["BPD", "TED", "TSD"] * (count // 3 + 1)
    )
    rows = []
    for i, label in enumerate(labels[:count]):
        index = ("BPD", "TED", "TSD").index(label)
        scores = [0.0362938344478607] * 3
        scores[index] = 0.9274123311042786
        rows.append(
            Detection(
                f"candidate_{i:06d}",
                index,
                label,
                scores[index],
                Geometry(
                    GeometryKind.POINT,
                    (
                        (
                            i % source.metadata.width,
                            (i // source.metadata.width) % source.metadata.height,
                        ),
                    ),
                    coordinate_space=CoordinateSpace.ORIGINAL,
                ),
                {
                    "point_id": f"point_{i}",
                    "scores": scores,
                    "low_score": False,
                    "human_verified": False,
                },
            )
        )
    started = utc_now()
    return AnalysisResult(
        request,
        status,
        started,
        started + timedelta(seconds=1),
        1.0,
        tuple(rows),
        {
            "point_mode": "contrast_proposals",
            "model_sha256": "a" * 64,
            "counts": dict(Counter(d.class_name for d in rows)),
        },
        {"patch_size": 128, "batch_size": 32},
        AnalysisError("TEST", "synthetic failure")
        if status == AnalysisState.FAILED
        else None,
    )


@pytest.fixture
def domain(tmp_path):
    path = tmp_path / "original.tif"
    tifffile.imwrite(
        path,
        np.arange(3 * 64 * 96, dtype=np.uint16).reshape(3, 64, 96),
        photometric="minisblack",
    )
    source = OriginalImageSource(path)
    result = legacy(source)
    return (
        import_legacy_result(
            AnalysisProject("Synthetic research"), result, model_manifest=MANIFEST
        ),
        result,
        path,
    )


def review(
    project,
    *,
    reviewer="alice",
    status=ReviewStatus.CONFIRMED,
    revision=1,
    parents=(),
    target_type=ReviewTarget.OBSERVATION,
    target_id=None,
    **changes,
):
    target_id = target_id or project.observations[0].observation_id
    snapshot, run_id = prediction_snapshot(project, target_type, target_id)
    return ReviewEvent(
        new_id(),
        target_type,
        target_id,
        reviewer,
        status,
        snapshot,
        utc_now(),
        revision,
        source_run_id=run_id,
        parent_review_ids=parents,
        **changes,
    )


def shape(project, kind, **fields):
    return DefectGeometry(
        new_id(),
        project.image_sources[0].source_id,
        0,
        kind,
        GeometrySource.HUMAN,
        **fields,
    )


def graph_fields():
    return {
        "nodes": (
            GraphNode("center", 20, 20),
            GraphNode("a", 10, 10),
            GraphNode("b", 30, 10),
            GraphNode("c", 20, 30),
        ),
        "edges": (
            GraphEdge("e1", "center", "a", ((20, 20), (14, 17), (10, 10))),
            GraphEdge("e2", "center", "b"),
            GraphEdge("e3", "center", "c"),
        ),
    }


def test_multiple_sources_three_runs_and_idempotent_read_only_adapter(
    domain, tmp_path, monkeypatch
):
    p, result, path = domain
    before = path.read_bytes()
    legacy_before = repr(result)
    monkeypatch.setattr(
        OriginalImageSource,
        "read_full",
        lambda *_: pytest.fail("No inference/source pixel reads in adapter"),
    )
    assert import_legacy_result(p, result, model_manifest=MANIFEST) is p
    p = import_legacy_result(p, legacy(result.request.source), model_manifest=MANIFEST)
    p = import_legacy_result(
        p, legacy(OriginalImageSource(path, 2)), model_manifest=MANIFEST
    )
    other = tmp_path / "after.tif"
    shutil.copyfile(path, other)
    p = import_legacy_result(
        p, legacy(OriginalImageSource(other)), model_manifest=MANIFEST
    )
    assert (
        len(p.image_sources) == 2
        and len(p.analysis_runs) == 4
        and len(p.observations) == 12
    )
    assert (
        len({r.run_id for r in p.analysis_runs}) == 4
        and not p.defect_instances
        and not p.review_events
    )
    assert (
        p.image_sources[0].content_hash is None
        and p.image_sources[0].calibration.spatial_axis_type == "UNKNOWN"
    )
    assert p.image_sources[0].wafer_placement.coordinate_system == "UNKNOWN"
    assert path.read_bytes() == before and repr(result) == legacy_before
    assert loads(dumps(p)) == p
    changed = replace(
        result,
        detections=(replace(result.detections[0], confidence=0.8),)
        + result.detections[1:],
    )
    with pytest.raises(ValueError, match="Repeated"):
        import_legacy_result(p, changed, model_manifest=MANIFEST)


def test_2946_synthetic_candidates_preserve_counts_ids_coordinates_and_score_bits(
    domain,
):
    p, result, _ = domain
    result = legacy(
        result.request.source, 2946, counts={"BPD": 245, "TED": 1398, "TSD": 1303}
    )
    p = import_legacy_result(
        AnalysisProject("Synthetic count fixture"), result, model_manifest=MANIFEST
    )
    loaded = loads(dumps(p))
    assert Counter(o.assigned_class for o in loaded.observations) == {
        "BPD": 245,
        "TED": 1398,
        "TSD": 1303,
    }
    assert len(loaded.observations) == 2946 and not loaded.defect_instances
    for original, observation in zip(
        result.detections, loaded.observations, strict=True
    ):
        assert (
            observation.source_candidate_id == original.id
            and observation.point_id == original.metadata["point_id"]
        )
        assert (observation.x, observation.y) == original.geometry.points[0]
        assert observation.source_class_id == original.class_id
        assert observation.metadata == original.metadata
        assert tuple(struct.pack("!d", v) for v in observation.raw_scores) == tuple(
            struct.pack("!d", v) for v in original.metadata["scores"]
        )
    assert loaded.model_provenance[0].model_version == result.model_version
    assert loaded.model_provenance[0].training_dataset_version is None


@pytest.mark.parametrize(
    "status", [AnalysisState.COMPLETED, AnalysisState.FAILED, AnalysisState.CANCELED]
)
def test_terminal_runs_without_candidates_keep_actual_status_timestamps_error(
    domain, status
):
    _, result, _ = domain
    result = legacy(result.request.source, 0, status=status)
    p = import_legacy_result(AnalysisProject("Terminal"), result)
    r = loads(dumps(p)).analysis_runs[0]
    assert (
        r.run_status == status
        and r.started_at == result.started_at
        and r.completed_at == result.completed_at
    )
    assert r.duration == result.duration and r.result_id == result.analysis_id
    assert not p.observations and (r.error is not None) == (
        status == AnalysisState.FAILED
    )


@pytest.mark.parametrize(
    "kind,fields",
    [
        (DefectGeometryKind.POINT, {"points": ((10, 20),)}),
        (DefectGeometryKind.BOUNDING_BOX, {"bbox": (10, 20, 10, 10)}),
        (DefectGeometryKind.POLYLINE, {"points": ((10, 20), (20, 30), (40, 25))}),
        (DefectGeometryKind.POLYGON, {"points": ((10, 20), (20, 30), (40, 20))}),
        (
            DefectGeometryKind.MASK_REFERENCE,
            {
                "bbox": (10, 20, 10, 10),
                "mask_reference": "geometry/references/mask.tif",
                "mask_encoding": "tiff",
            },
        ),
        (DefectGeometryKind.BRANCHED_GRAPH, graph_fields()),
    ],
)
def test_all_geometry_shapes_multi_observation_instance_and_roundtrip(
    domain, kind, fields
):
    p, _, _ = domain
    g = shape(p, kind, **fields)
    instance = DefectInstance(
        new_id(),
        g.source_id,
        g.geometry_id,
        tuple(ObservationLink(o.observation_id) for o in p.observations),
        "BPD",
    )
    p = p.evolve(geometries=p.geometries + (g,), defect_instances=(instance,))
    q = loads(dumps(p))
    assert q == p and len(q.defect_instances[0].linked_observations) == 3
    assert not instance.assessment.ground_truth_eligible
    if kind == DefectGeometryKind.BRANCHED_GRAPH:
        assert len(q.geometries[-1].edges) == 3 and len(q.geometries[-1].nodes) == 4
    event = review(
        p, target_type=ReviewTarget.DEFECT_INSTANCE, target_id=instance.instance_id
    )
    assert len(ReviewRepository().append(p, event).review_events) == 1


@pytest.mark.parametrize(
    "kind,fields",
    [
        (DefectGeometryKind.POINT, {"points": ((96, 10),)}),
        (DefectGeometryKind.POINT, {"points": ((float("nan"), 10),)}),
        (DefectGeometryKind.BOUNDING_BOX, {"bbox": (10, 10, 0, 2)}),
        (DefectGeometryKind.BOUNDING_BOX, {"bbox": (90, 10, 20, 2)}),
        (DefectGeometryKind.POLYLINE, {"points": ((1, 2),)}),
        (DefectGeometryKind.POLYGON, {"points": ((1, 1), (2, 2), (3, 3))}),
        (
            DefectGeometryKind.MASK_REFERENCE,
            {
                "bbox": (1, 1, 2, 2),
                "mask_reference": "../mask",
                "mask_encoding": "tiff",
            },
        ),
        (
            DefectGeometryKind.MASK_REFERENCE,
            {
                "bbox": (1, 1, 2, 2),
                "mask_reference": "C:/mask",
                "mask_encoding": "tiff",
            },
        ),
        (
            DefectGeometryKind.MASK_REFERENCE,
            {
                "bbox": (1, 1, 2, 2),
                "mask_reference": "geometry\\mask",
                "mask_encoding": "tiff",
            },
        ),
        (
            DefectGeometryKind.BRANCHED_GRAPH,
            {
                "nodes": (GraphNode("a", 1, 1), GraphNode("b", 2, 2)),
                "edges": (GraphEdge("e", "a", "missing"),),
            },
        ),
        (
            DefectGeometryKind.BRANCHED_GRAPH,
            {
                "nodes": (
                    GraphNode("a", 1, 1),
                    GraphNode("b", 2, 2),
                    GraphNode("c", 3, 3),
                ),
                "edges": (GraphEdge("e", "a", "b"),),
            },
        ),
    ],
)
def test_invalid_geometry_and_coordinates_rejected(domain, kind, fields):
    p, _, _ = domain
    with pytest.raises((ValueError, TypeError)):
        g = shape(p, kind, **fields)
        p.evolve(geometries=p.geometries + (g,))


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "global_duplicate",
        "bad_geometry",
        "bad_run",
        "bad_prediction",
        "bad_page",
        "bad_identity",
        "bad_model",
        "bad_parent",
    ],
)
def test_project_reference_and_identity_integrity(domain, mutation):
    p, _, _ = domain
    with pytest.raises(ValueError):
        if mutation == "duplicate":
            p.evolve(observations=p.observations + (p.observations[0],))
        elif mutation == "global_duplicate":
            p.evolve(
                image_sources=(replace(p.image_sources[0], source_id=p.project_id),)
            )
        elif mutation == "bad_geometry":
            p.evolve(
                observations=(replace(p.observations[0], geometry_id="missing"),)
                + p.observations[1:]
            )
        elif mutation == "bad_run":
            p.evolve(
                observations=(replace(p.observations[0], run_id="missing"),)
                + p.observations[1:]
            )
        elif mutation == "bad_prediction":
            p.evolve(
                predictions=(replace(p.predictions[0], raw_scores=(0.1, 0.2, 0.7)),)
                + p.predictions[1:]
            )
        elif mutation == "bad_page":
            p.evolve(analysis_runs=(replace(p.analysis_runs[0], page_index=3),))
        elif mutation == "bad_identity":
            p.evolve(
                analysis_runs=(
                    replace(
                        p.analysis_runs[0],
                        source_identity={
                            **p.analysis_runs[0].source_identity,
                            "width": 999,
                        },
                    ),
                )
            )
        elif mutation == "bad_model":
            p.evolve(
                analysis_runs=(replace(p.analysis_runs[0], model_version="other"),)
            )
        else:
            ReviewRepository().append(p, review(p, revision=2, parents=("missing",)))


@pytest.mark.parametrize("status", list(ReviewStatus))
def test_review_status_keeps_original_predictions_and_never_auto_ground_truth(
    domain, status
):
    p, _, _ = domain
    before = (p.observations, p.predictions)
    event = review(
        p,
        status=status,
        **({"corrected_class": "TSD"} if status == ReviewStatus.CORRECTED else {}),
    )
    repo = ReviewRepository()
    q = repo.append(p, event)
    assert q.observations == before[0] and q.predictions == before[1]
    assert repo.current(q, event.target_type, event.target_id).status == status
    assert not repo.current(
        q, event.target_type, event.target_id
    ).assessment.ground_truth_eligible
    assert loads(dumps(q)).review_events == (event,)
    assert repo.append(q, event) is q
    with pytest.raises(ValueError, match="Duplicate"):
        repo.append(q, replace(event, comment="changed"))


def test_review_history_fork_different_reviewers_and_explicit_merge(domain):
    p, _, _ = domain
    repo = ReviewRepository()
    a = review(p)
    p = repo.append(p, a)
    b = review(
        p,
        status=ReviewStatus.CORRECTED,
        corrected_class="TSD",
        revision=2,
        parents=(a.review_id,),
    )
    p = repo.append(p, b)
    c = review(p, status=ReviewStatus.UNCERTAIN, revision=2, parents=(a.review_id,))
    p = repo.append(p, c)
    state = repo.current(p, a.target_type, a.target_id)
    assert (
        state.conflict
        and state.status == ReviewStatus.NEEDS_REVIEW
        and len(state.tips_by_reviewer["alice"]) == 2
    )
    merged = review(
        p,
        status=ReviewStatus.NEEDS_REVIEW,
        revision=3,
        parents=(b.review_id, c.review_id),
    )
    p = repo.append(p, merged)
    assert not repo.current(p, a.target_type, a.target_id).conflict
    other = review(p, reviewer="bob", status=ReviewStatus.REJECTED)
    p = repo.append(p, other)
    assert repo.current(p, a.target_type, a.target_id).conflict
    assert len(repo.history(p, a.target_type, a.target_id)) == 5
    assert p.predictions[0].assigned_class == "BPD"


def test_malformed_review_and_explicit_geometry_correction(domain):
    p, _, _ = domain
    with pytest.raises(ValueError):
        review(p, status=ReviewStatus.CORRECTED)
    with pytest.raises(ValueError):
        ReviewRepository().append(
            p, replace(review(p), original_prediction={"raw_scores": (1.0,)})
        )
    with pytest.raises(ValueError):
        ReviewRepository().append(p, replace(review(p), target_id="missing"))
    g = shape(p, DefectGeometryKind.POLYGON, points=((2, 2), (6, 2), (4, 8)))
    p = p.evolve(geometries=p.geometries + (g,))
    e = review(
        p, status=ReviewStatus.CORRECTED, corrected_geometry_reference=g.geometry_id
    )
    assert ReviewRepository().append(p, e).geometries[0] == p.geometries[0]
    with pytest.raises(ValueError):
        LabelAssessment(ground_truth_eligible=True)


def test_ambiguous_candidate_links_and_explicit_image_relationships(domain, tmp_path):
    p, _result, path = domain
    geom = p.geometries[0]
    instances = tuple(
        DefectInstance(
            new_id(),
            geom.source_id,
            geom.geometry_id,
            (ObservationLink(p.observations[0].observation_id, LinkStatus.AMBIGUOUS),),
        )
        for _ in range(2)
    )
    other = tmp_path / "before.tif"
    shutil.copyfile(path, other)
    p = import_legacy_result(
        p, legacy(OriginalImageSource(other)), model_manifest=MANIFEST
    )
    relation = ImageRelationship(
        new_id(),
        p.image_sources[0].source_id,
        p.image_sources[1].source_id,
        ImageRole.BEFORE_ANNEALING,
        ImageRole.AFTER_ANNEALING,
    )
    p = p.evolve(defect_instances=instances, image_relationships=(relation,))
    assert loads(dumps(p)) == p and len(p.observations) == 6
    assert (
        p.image_sources[1].role == ImageRole.UNKNOWN
    )  # Filename does not assign a scientific role.
    with pytest.raises(ValueError):
        SpatialCalibration(spacing_z=0.5)


@pytest.mark.parametrize(
    "bad",
    [
        "future_major",
        "future_minor",
        "truncated",
        "duplicate_key",
        "missing_id",
        "unknown_field",
        "bool_coordinate",
        "nan",
    ],
)
def test_strict_serialization_errors(domain, bad):
    p, _, _ = domain
    raw = dumps(p)
    data = json.loads(raw)
    if bad == "truncated":
        encoded = raw[:-20]
    elif bad == "duplicate_key":
        encoded = b'{"format":"x","format":"y"}'
    else:
        if bad in ("future_major", "future_minor"):
            data["schema_version"] = "2.0.0" if bad == "future_major" else "1.1.0"
        elif bad == "missing_id":
            del data["project"]["project_id"]
        elif bad == "unknown_field":
            data["project"]["__reduce__"] = "os.system"
        elif bad == "bool_coordinate":
            data["project"]["observations"][0]["x"] = True
        else:
            data["project"]["observations"][0]["x"] = float("nan")
        encoded = json.dumps(data).encode()
    with pytest.raises(ValueError):
        loads(encoded)


def test_project_save_reload_across_process_without_original_or_inference(
    domain, tmp_path
):
    p, _, source = domain
    store = ProjectStore()
    path = tmp_path / "project.json"
    store.save(path, p)
    source.unlink()  # Only this test's generated TIFF.
    loaded = store.load(path)
    assert loaded == p and inspect_source(loaded.image_sources[0]).status == "MISSING"
    code = "from sic_xrt_analyzer.results.persistence import ProjectStore; import sys; p=ProjectStore().load(sys.argv[1]); assert 'onnxruntime' not in sys.modules; print(p.project_id,len(p.observations),p.schema_version)"
    completed = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == f"{p.project_id} 3 1.0.0"


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_failed_atomic_save_preserves_previous_bytes_and_recovers(
    domain, tmp_path, monkeypatch, failure
):
    p, _, _ = domain
    store = ProjectStore()
    path = tmp_path / "project.json"
    store.save(path, p)
    before = path.read_bytes()
    q = ReviewRepository().append(p, review(p))
    with monkeypatch.context() as patch:

        def fail(*_):
            raise OSError("synthetic disk full/locked file")

        patch.setattr("sic_xrt_analyzer.results.persistence.os." + failure, fail)
        with pytest.raises(OSError):
            store.save(path, q, expected_revision=p.revision)
    assert path.read_bytes() == before and store.load(path) == p
    assert not list(tmp_path.glob(".project.json.*.tmp"))
    store.save(path, q, expected_revision=p.revision)
    assert store.load(path) == q


def test_storage_revision_foreign_project_and_append_only_history(domain, tmp_path):
    p, _, _ = domain
    store = ProjectStore()
    path = tmp_path / "project.json"
    q = ReviewRepository().append(p, review(p))
    store.save(path, q)
    with pytest.raises(ValueError, match="conflict"):
        store.save(path, q, expected_revision=p.revision)
    with pytest.raises(ValueError):
        store.save(path, AnalysisProject("other"))
    with pytest.raises(ValueError, match="history"):
        store.save(path, q.evolve(review_events=()), expected_revision=q.revision)
    assert store.load(path) == q


def test_source_hash_is_explicit_relink_is_verified_and_runs_keep_old_identity(
    domain, tmp_path, monkeypatch
):
    p, _, source = domain
    record = p.image_sources[0]
    with monkeypatch.context() as patch:
        patch.setattr(
            "sic_xrt_analyzer.results.sources._hash_snapshot",
            lambda *_: pytest.fail("No automatic full source hashing"),
        )
        assert inspect_source(record).status == "METADATA_MATCH"
    moved = tmp_path / "moved.tif"
    shutil.copyfile(source, moved)
    with pytest.raises(ValueError, match="previously"):
        relink_source(record, moved)
    verified = verify_content_hash(record)
    assert (
        verified.content_hash.value == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert inspect_source(verified, reference=moved).status == "IDENTITY_MISMATCH"
    relinked = relink_source(verified, moved)
    assert (
        relinked.source_id == record.source_id
        and inspect_source(relinked, verify_hash=True).status == "HASH_MATCH"
    )
    q = p.evolve(image_sources=(relinked,))
    assert loads(dumps(q)) == q and q.analysis_runs[0].source_identity[
        "canonical_path"
    ] == str(source.resolve())
    wrong = tmp_path / "wrong.tif"
    data = bytearray(source.read_bytes())
    data[-1] ^= 1
    wrong.write_bytes(data)
    with pytest.raises(ValueError, match="hash"):
        relink_source(verified, wrong)
    assert (
        inspect_source(verified, reference=wrong, verify_hash=True).status
        == "IDENTITY_MISMATCH"
    )


def test_original_json_named_tiff_cannot_be_overwritten(domain, tmp_path):
    p, _, source = domain
    target = tmp_path / "original.json"
    shutil.copyfile(source, target)
    record = replace(
        p.image_sources[0],
        source_reference=str(target),
        file_identity=replace(
            p.image_sources[0].file_identity, canonical_path=str(target)
        ),
    )
    p = p.evolve(image_sources=(record,))
    before = target.read_bytes()
    with pytest.raises(ValueError, match="original"):
        ProjectStore().save(target, p)
    assert target.read_bytes() == before


def test_asset_resolution_rejects_traversal_missing_and_symlink_escape(tmp_path):
    project = tmp_path / "project" / "project.json"
    project.parent.mkdir()
    outside = tmp_path / "outside.mask"
    outside.write_bytes(b"fake")
    store = ProjectStore()
    for reference in (
        "../outside.mask",
        "/outside.mask",
        "C:/outside.mask",
        "a\\b.mask",
    ):
        with pytest.raises(ValueError):
            store.resolve_asset(project, reference)
    with pytest.raises(FileNotFoundError):
        store.resolve_asset(project, "geometry/missing.mask")
    link = project.parent / "escape.mask"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating Windows symlinks requires OS permission")
    with pytest.raises(ValueError, match="escapes"):
        store.resolve_asset(project, "escape.mask")


def test_existing_json_csv_export_bytes_unchanged_by_project_adapter_and_reviews(
    workbench, tmp_path
):
    w = workbench
    w.open(create_source(tmp_path).path)
    invoke(w.item("runAction"), "trigger")
    spin(w.app, lambda: w.bridge.analysis["hasResult"])
    result = w.bridge.pipeline.result
    assert w.bridge.research.exportResult(str(tmp_path / "export"))
    original = Path(w.bridge.research.export_path)
    before = {
        name: (original / name).read_bytes()
        for name in ("result.json", "predictions.csv")
    }
    p = import_legacy_result(AnalysisProject("Export regression"), result)
    p = ReviewRepository().append(
        p, review(p, status=ReviewStatus.CORRECTED, corrected_class="TSD")
    )
    store = ProjectStore()
    store.save(tmp_path / "project.json", p)
    assert store.load(tmp_path / "project.json") == p
    assert w.bridge.pipeline.result is result
    assert w.bridge.research.exportResult(str(tmp_path / "export"))
    final = Path(w.bridge.research.export_path)
    assert {name: (final / name).read_bytes() for name in before} == before


@pytest.mark.parametrize(
    "kind,fields",
    [
        (GeometryKind.POINT, {"points": ((10, 20),)}),
        (GeometryKind.BOUNDING_BOX, {"bbox": (10, 20, 10, 10)}),
        (GeometryKind.POLYGON, {"points": ((10, 20), (20, 30), (40, 20))}),
        (
            GeometryKind.MASK,
            {
                "bbox": (10, 20, 10, 10),
                "mask_reference": "geometry/references/legacy-mask.tif",
                "mask_encoding": "tiff",
            },
        ),
    ],
)
def test_legacy_nonpoint_geometry_preserved_without_inventing_center_or_instance(
    domain, kind, fields
):
    _, result, _ = domain
    geometry = Geometry(kind, coordinate_space=CoordinateSpace.ORIGINAL, **fields)
    result = replace(
        result, detections=(replace(result.detections[0], geometry=geometry),)
    )
    p = import_legacy_result(
        AnalysisProject("Legacy shapes"), result, model_manifest=MANIFEST
    )
    assert len(p.observations) == 1 and not p.defect_instances
    o = p.observations[0]
    assert (o.x, o.y) == ((10, 20) if kind == GeometryKind.POINT else (None, None))
    assert (
        p.geometries[0].points == geometry.points
        and p.geometries[0].bbox == geometry.bbox
    )
    assert loads(dumps(p)) == p


def test_project_writer_lock_prevents_concurrent_process_update(domain, tmp_path):
    p, _, _ = domain
    path = tmp_path / "project.json"
    store = ProjectStore()
    store.save(path, p)
    from sic_xrt_analyzer.results.persistence import _write_lock

    child = "from sic_xrt_analyzer.results.persistence import ProjectStore; import sys; s=ProjectStore(); p=s.load(sys.argv[1]); s.save(sys.argv[1],p.evolve(project_name='changed'),expected_revision=p.revision)"
    with _write_lock(path.with_name(path.name + ".lock")):
        completed = subprocess.run(
            [sys.executable, "-c", child, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode != 0 and store.load(path) == p
    q = p.evolve(project_name="changed")
    store.save(path, q, expected_revision=p.revision)
    assert store.load(path) == q
