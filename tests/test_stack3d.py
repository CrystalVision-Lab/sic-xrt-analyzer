"""Numeric oracle, bounded reads, physical gates and immutable manual track sessions."""

import copy
import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource, SourceError
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.contracts import SpatialCalibration, VerificationStatus
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source, publish_dependencies
from sic_xrt_analyzer.stack3d import assets
from sic_xrt_analyzer.stack3d.scene import prepare
from sic_xrt_analyzer.stack3d.volume import (
    extract,
    physical_calibration,
    plan,
    world_mapping,
    world_point,
)

KINDS = [
    "moving-point",
    "line",
    "curve",
    "branch",
    "gap",
    "nearby",
    "noise",
    "low-contrast",
    "empty",
    "single",
    "missing",
    "unequal-spacing",
    "high-uint16",
    "big-endian",
]


def synthetic(kind):
    v = np.full((8, 40, 48), 20000, dtype=np.uint16)
    for k in range(8):
        v[k, 10 + k, 12 + k] = 65000
        v[k, 15, 8:30] = 60000
        v[k, 20:30, 18] = 61000
    if kind == "curve":
        for k in range(8):
            v[k, 8 + k, 20 + (k * k) % 12] = 64000
    if kind == "branch":
        v[:, 22, 18:32] = 63000
    if kind == "gap":
        v[3:5] = 20000
    if kind == "nearby":
        v[:, 15, 31] = 60000
    if kind == "noise":
        v = np.random.default_rng(118).integers(0, 65536, v.shape, dtype=np.uint16)
    if kind == "low-contrast":
        v = np.where(v > 20000, 20100, 20000).astype(np.uint16)
    if kind == "empty":
        v[:] = 0
    if kind == "single":
        v = v[:1]
    if kind == "missing":
        v = v[[0, 1, 4, 5, 7]]
    if kind == "high-uint16":
        v[0, 0, 0] = 65535
    return v


@pytest.fixture
def study(tmp_path):
    path = tmp_path / "original.tif"
    tifffile.imwrite(
        path,
        synthetic("branch"),
        imagej=True,
        metadata={"axes": "TYX"},
        photometric="minisblack",
    )
    reader = OriginalImageSource(path)
    p, s = add_source(AnalysisProject("QA indexed stack"), reader)
    s = verify_content_hash(s)
    p = p.evolve(image_sources=(s,))
    return p, s, reader, tmp_path / "project.json"


def session(p, s, reader):
    return {
        "schema": assets.SESSION,
        "project_id": p.project_id,
        "source_id": s.source_id,
        "source_sha256": s.content_hash.value,
        "stack_page_count": s.page_count,
        "original_shape": [s.page_count, s.height, s.width],
        "dtype": "uint16",
        "byte_order": "<",
        "selection": plan(reader, [3, 4, 32, 28], 0, s.page_count - 1),
        "coordinate_mode": "INDEXED",
        "calibration": None,
        "settings": {
            "cursor": [0, 0, 0],
            "window": [0, 65535],
            "camera": [-25, 35, 0, 0, 650],
            "plane_limit": 12,
        },
        "tracks": [],
        "revision": 1,
        "session_id": str(uuid4()),
        "revision_id": str(uuid4()),
        "parent_reference": None,
        "created_at": utc_now().isoformat(),
        "editor_id": "QA",
    }


@pytest.mark.parametrize("kind", KINDS)
def test_synthetic_numeric_oracle_and_axis_mapping(tmp_path, kind):
    v = synthetic(kind)
    path = tmp_path / (kind + ".tif")
    tifffile.imwrite(
        path,
        v,
        photometric="minisblack",
        byteorder=">" if kind == "big-endian" else "<",
    )
    reader = OriginalImageSource(path)
    sel = plan(reader, [3, 4, 32, 28], 0, len(v) - 1, 2, 3)
    volume = extract(reader, sel)
    with tifffile.TiffFile(path) as tif:
        for ik, k in enumerate(sel["page_indices"]):
            assert np.array_equal(
                volume.pixels[ik], tif.pages[k].asarray()[4:32:3, 3:35:3]
            )
    assert volume.pixels.dtype == np.uint16 and not volume.pixels.flags.writeable
    x, y, k, value = volume.original(0, 2, 3)
    assert (x, y, k) == (12, 10, 0) and value == int(v[k, y, x])
    assert volume.byte_order == (">" if kind == "big-endian" else "<")
    assert physical_calibration(None, len(v)) is None


def test_returned_volume_budget_and_explicit_sampling():
    class Header:
        metadata = type(
            "M",
            (),
            {
                "format": "TIFF",
                "channels": 1,
                "dtype": "uint16",
                "page_count": 158,
                "width": 3072,
                "height": 3012,
            },
        )()

        def validate_region(self, *_):
            pass

    s = Header()
    assert plan(s, [1200, 1000, 256, 256], 0, 157)["raw_bytes"] == 20709376
    with pytest.raises(ValueError, match="64 MiB"):
        plan(s, [0, 0, 512, 512], 0, 157)
    sampled = plan(s, [0, 0, 512, 512], 0, 157, 1, 2)
    assert sampled["shape"] == [158, 256, 256]
    assert plan(s, [0, 0, 256, 256], 0, 157, 7)["page_indices"][-1] == 154


@pytest.mark.parametrize(
    "roi,first,last,step,xy",
    [
        ([-1, 0, 20, 20], 0, 7, 1, 1),
        ([30, 30, 32, 28], 0, 7, 1, 1),
        ([0, 0, 0, 20], 0, 7, 1, 1),
        ([0, 0, 20, 20], 7, 0, 1, 1),
        ([0, 0, 20, 20], 0, 9, 1, 1),
        ([0, 0, 20, 20], 0, 7, 0, 1),
        ([0, 0, 20, 20], 0, 7, 1, 0),
        ([0, 0, 20, 20], 0, 7, 1, 1.5),
    ],
)
def test_invalid_selection(study, roi, first, last, step, xy):
    with pytest.raises(ValueError):
        plan(study[2], roi, first, last, step, xy)


def test_cancel_timeout_change_and_corrupt(study, tmp_path):
    _p, _s, reader, _ = study
    sel = plan(reader, [0, 0, 20, 20], 0, 7)
    with pytest.raises(InterruptedError):
        extract(reader, sel, cancelled=lambda: True)
    with pytest.raises(TimeoutError):
        extract(reader, sel, timeout=-1)
    reader.path and Path(reader.path).write_bytes(Path(reader.path).read_bytes() + b"x")
    with pytest.raises(SourceError, match="changed"):
        extract(reader, sel)
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"II*" + b"broken")
    with pytest.raises(tifffile.TiffFileError):
        OriginalImageSource(bad)


def test_reader_decode_limit_preserved(tmp_path):
    a = np.zeros((256, 256), np.uint16)
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(path, a, compression="deflate")
    s = OriginalImageSource(path, max_decode_bytes=1024)
    with pytest.raises(SourceError, match="decode budget"):
        extract(s, plan(s, [0, 0, 8, 8], 0, 0))


def test_source_axes_never_from_imagej_and_physical_gate(study):
    _p, s, reader, _ = study
    assert s.acquisition_metadata["imagej_metadata"]["frames"] == 8
    assert physical_calibration(s, s.page_count) is None
    c = SpatialCalibration(
        "SPATIAL_Z",
        tuple(range(8)),
        0.2,
        0.3,
        0.7,
        "um",
        "X_RIGHT_Y_DOWN_Z_FORWARD",
        "synthetic independent device",
        VerificationStatus.VERIFIED,
    )
    verified = replace(s, calibration=c)
    proof = physical_calibration(verified, 8)
    assert proof["page_depths"][7] == pytest.approx(4.9)
    for field, value in [
        ("orientation", "unknown"),
        ("acquisition_order", ()),
        ("unit", "px"),
        ("spacing_z", None),
    ]:
        assert (
            physical_calibration(
                replace(s, calibration=replace(c, **{field: value})), 8
            )
            is None
        )
    volume = extract(reader, plan(reader, [0, 0, 20, 20], 0, 7))
    m = world_mapping(volume)
    assert world_point(volume, m, 0, 0, 0)[2] == -80
    physical = world_mapping(volume, proof)
    assert physical["mode"] == "PHYSICAL"


def test_track_revisions_gaps_and_bounded_scene(study):
    p, s, reader, _ = study
    t = assets.new_track(s, "manual structure", "QA", p.project_id)
    assets.event(t, "UPSERT", 0, {"type": "POINT", "coordinates": [12, 10]}, "QA")
    assets.event(
        t,
        "UPSERT",
        3,
        {"type": "RECTANGLE", "coordinates": [12, 10, 4, 4]},
        "QA",
        "UNCERTAIN",
    )
    assets.event(t, "PAUSE", None, None, "QA")
    assert assets.active_points(t)[1]
    assets.event(t, "RESUME", None, None, "QA")
    assert not assets.active_points(t)[1]
    assets.validate_track(t, p)
    v = extract(reader, plan(reader, [3, 4, 32, 28], 0, 7))
    f = prepare(v, [0, 2, 3], [19000, 65000], [t], plane_limit=3)
    assert len(f["planes"]) == 3 and len(f["markers"]) == 2 and len(f["segments"]) == 18
    assert f["texture_bytes"] < 16 * 1024**2
    original = t["events"][0].copy()
    assets.event(
        t, "UPSERT", 0, {"type": "POINT", "coordinates": [13, 11]}, "QA", "REVIEWED"
    )
    assets.event(t, "REMOVE", 3, None, "QA")
    assert t["events"][0] == original and set(assets.active_points(t)[0]) == {0}
    assert "BPD" not in str(t) and "CONFIRMED" not in str(t)


def test_session_atomic_save_reopen_save_as_sha_and_science(study, tmp_path):
    p, s, reader, path = study
    a = session(p, s, reader)
    t = assets.new_track(s, "manual", "QA", p.project_id)
    assets.event(t, "UPSERT", 0, {"type": "POINT", "coordinates": [12, 10]}, "QA")
    assets.validate_track(t, p)
    a["tracks"] = [assets.publish(path, t)]
    assets.validate_session(a, p)
    ref = assets.publish(path, a)
    before = hashlib.sha256(Path(reader.path).read_bytes()).hexdigest()
    q = assets.attach(p, s.source_id, ref)
    ProjectStore().save(path, q)
    assert (
        ProjectStore().load(path) == q
        and q.observations == p.observations
        and q.geometries == p.geometries
    )
    assert (
        q.image_sources[0].calibration == s.calibration
        and q.image_sources[0].wafer_placement == s.wafer_placement
    )
    other = tmp_path / "save-as" / "project.json"
    publish_dependencies(other, q, [], path)
    ProjectStore().save(other, q)
    assert ProjectStore().load(other) == q
    Path(reader.path).unlink()
    assert ProjectStore().load(path) == q
    target = path.parent / ref
    data = target.read_bytes()
    target.write_bytes(data + b" ")
    with pytest.raises(ValueError, match="SHA"):
        ProjectStore().load(path)
    assert before == s.content_hash.value


def test_no_history_rewrite_or_wrong_source(study):
    p, s, reader, path = study
    a = session(p, s, reader)
    t = assets.new_track(s, "manual", "QA", p.project_id)
    assets.event(t, "UPSERT", 0, {"type": "POINT", "coordinates": [12, 10]}, "QA")
    a["tracks"] = [assets.publish(path, t)]
    ref = assets.publish(path, a)
    q = assets.attach(p, s.source_id, ref)
    ProjectStore().save(path, q)
    changed = copy.deepcopy(t)
    changed["events"][0]["geometry"]["coordinates"] = [14, 11]
    b = copy.deepcopy(a)
    b.update(
        revision=2,
        parent_reference=ref,
        revision_id=str(uuid4()),
        created_at=utc_now().isoformat(),
    )
    b["tracks"] = [assets.publish(path, changed)]
    newer = assets.attach(q, s.source_id, assets.publish(path, b))
    with pytest.raises(ValueError, match="rewriting"):
        ProjectStore().save(path, newer)
    wrong = copy.deepcopy(a)
    wrong["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA"):
        assets.validate_session(wrong, p)
    drop = q.evolve(
        image_sources=(replace(s, acquisition_metadata={"format": "TIFF"}),)
    )
    with pytest.raises(ValueError, match="delete 3D"):
        ProjectStore().save(path, drop, expected_revision=q.revision)


def test_local_3d_sessions_are_not_in_server_projection(study):
    from sic_xrt_analyzer.sync.protocol import project_projection

    p, s, reader, path = study
    a = session(p, s, reader)
    ref = assets.publish(path, a)
    # Only the contract's known reference is attached; server projection remains unchanged.
    p = assets.attach(p, s.source_id, ref)
    root, entities = project_projection(p)
    import json

    serialized = json.dumps([root, entities])
    assert "stack_3d_session_reference" not in serialized
    assert "assets/stack-3d/" not in serialized
