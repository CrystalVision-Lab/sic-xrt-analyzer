import hashlib
import time
from pathlib import Path

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.stack3d.defect import dark_mask, trace


@pytest.fixture
def connected(tmp_path):
    a = np.full((15, 80, 90), 60000, np.uint16)
    for z in range(3, 12):
        y, x = np.ogrid[:80, :90]
        a[z][(x - (38 + z // 4)) ** 2 + (y - 40) ** 2 < 36] = 5000
        a[z, 15:19, 60:65] = 3000
    p = tmp_path / "connected.tif"
    tifffile.imwrite(p, a, photometric="minisblack")
    return OriginalImageSource(p, 7), a


def test_seed_connected_closed_surface_preserves_original(connected):
    source, a = connected
    before = hashlib.sha256(Path(source.path).read_bytes()).hexdigest()
    m = trace(source, (39, 40, 7))
    assert [s.page for s in m.sections] == list(range(3, 12))
    assert m.voxels == int(np.count_nonzero(a[:, 25:55, 25:55] == 5000))
    assert m.bounds[0] > 25 and m.bounds[3] < 55 and m.xy_step == 1
    edges = np.sort(
        np.concatenate([m.faces[:, [0, 1]], m.faces[:, [1, 2]], m.faces[:, [2, 0]]]),
        axis=1,
    )
    assert (np.unique(edges, axis=0, return_counts=True)[1] == 2).all()
    assert np.isfinite(m.vertices).all() and len(m.faces) > 100
    assert not m.vertices.flags.writeable
    assert hashlib.sha256(Path(source.path).read_bytes()).hexdigest() == before
    assert np.array_equal(source.read_full(), a[7])


def test_empty_page_stops_no_nearest_jump_or_gap_fill(connected):
    source, a = connected
    a[6] = 60000
    tifffile.imwrite(source.path, a, photometric="minisblack")
    s = OriginalImageSource(source.path, 7)
    m = trace(s, (39, 40, 7))
    assert min(r.page for r in m.sections) == 7
    assert all(r.x < 55 and r.y > 25 for r in m.sections)


def test_gradient_is_not_a_dark_component():
    a = np.tile(np.linspace(20000, 65000, 256, dtype=np.uint16), (256, 1))
    a[120:135, 120:135] = 1000
    mask, _ = dark_mask(a)
    assert mask[122:133, 122:133].all()
    assert mask[10:100, 20:230].sum() == 0


def test_cancel_and_display_budget_do_not_mutate_masks(connected, monkeypatch):
    import sic_xrt_analyzer.stack3d.defect as mod

    source, a = connected
    with pytest.raises(InterruptedError):
        trace(source, (39, 40, 7), cancelled=lambda: True)
    monkeypatch.setattr(mod, "MAX_DENSE", 100)
    m = trace(source, (39, 40, 7))
    assert m.xy_step > 1
    assert m.voxels == int(np.count_nonzero(a[:, 25:55, 25:55] == 5000))


def test_controller_latest_source_and_cancel(connected, bridge_factory, qt_app):
    s, _ = connected
    b = bridge_factory()
    b.original_source = s
    c = b.defect3d
    assert c.start(39, 40)
    until = time.monotonic() + 20
    while c.busy:
        assert time.monotonic() < until
        qt_app.processEvents()
        time.sleep(0.005)
    assert c.state["ready"] and not c.error and c.state["pages"] == 9
    b.original_source = OriginalImageSource(s.path, 2)
    c.reconstruct(1.0)
    while c.busy:
        assert time.monotonic() < until
        qt_app.processEvents()
        time.sleep(0.005)
    assert c.mesh.seed[2] == 7 and c.state["pages"] == 9
    c.start(39, 40)
    c.cancel()
    b.original_source = None
    c.bindSource()
    while c.reader.task:
        assert time.monotonic() < until
        qt_app.processEvents()
        time.sleep(0.005)
    assert c.mesh is None and not c.busy


def test_sudden_large_merge_is_reported_not_silently_followed(tmp_path):
    a = np.full((5, 96, 96), 60000, np.uint16)
    a[2, 44:50, 44:50] = 1000
    a[3, 44:49, 20:80] = 1000
    a[3, 20:80, 44:49] = 1000
    p = tmp_path / "merge.tif"
    tifffile.imwrite(p, a, photometric="minisblack")
    mesh = trace(OriginalImageSource(p, 2), (46, 46, 2))
    assert [s.page for s in mesh.sections] == [2]
    assert (3, "AMBIGUOUS_MERGE") in mesh.stops


def test_touching_blob_is_split_without_fabricated_pixels(tmp_path):
    from sic_xrt_analyzer.stack3d.defect import isolate_component

    yy, xx = np.ogrid[:80, :100]
    mask = ((xx - 30) ** 2 + (yy - 40) ** 2 < 100) | (
        (xx - 65) ** 2 + (yy - 40) ** 2 < 144
    )
    mask[39:42, 30:66] = True
    selected = isolate_component(mask, (40, 30))
    assert selected[40, 30] and not selected[40, 65]
    assert np.all(~selected | mask)
    assert selected.sum() < mask.sum() * 0.6


def test_observations_are_real_masks_in_forward_then_backward_order(connected):
    source, a = connected
    frames = []
    mesh = trace(
        source,
        (39, 40, 7),
        observe=lambda p, raw, s, r: frames.append((p, raw.shape, s, r)),
    )
    assert [p for p, _, _, _ in frames] == [7, 8, 9, 10, 11, 12, 6, 5, 4, 3, 2]
    assert [p for p, _, _ in mesh.observations] == [p for p, _, _, _ in frames]
    for p, _, s, r in frames:
        if r == "ACCEPTED":
            assert (
                a[p, s.y : s.y + s.height, s.x : s.x + s.width][s.mask()] == 5000
            ).all()


def test_visual_backpressure_pause_fast_finish_and_replay(
    connected, bridge_factory, qt_app
):
    source, _ = connected
    b = bridge_factory()
    b.original_source = source
    c = b.defect3d

    def wait(pred):
        until = time.monotonic() + 20
        while not pred():
            assert time.monotonic() < until, c.error
            qt_app.processEvents()
            time.sleep(0.005)

    assert c.startVisual(39, 40)
    c.paused = True
    wait(lambda: c.frame_revision == 1)
    for _ in range(20):
        qt_app.processEvents()
        time.sleep(0.01)
    assert c.frame_revision == 1 and c.busy and not c.ack.is_set()
    assert not b.provider.stack3d_images["trace-full"].isNull()
    c.fastFinish()
    wait(lambda: not c.busy)
    assert c.mesh and len(c.mesh.sections) == 9
    c.replay()
    wait(lambda: c.replay_index >= 1)
    c.cancel()
    assert not c.replaying and not c.timer.isActive()
    assert c.ack.is_set()


def test_ambiguous_split_is_not_unioned(tmp_path):
    a = np.full((4, 80, 80), 60000, np.uint16)
    a[1, 35:45, 30:50] = 1000
    a[2, 35:45, 30:38] = 1000
    a[2, 35:45, 42:50] = 1000
    p = tmp_path / "split.tif"
    tifffile.imwrite(p, a, photometric="minisblack")
    mesh = trace(OriginalImageSource(p, 1), (34, 40, 1))
    assert [s.page for s in mesh.sections] == [1]
    assert (2, "AMBIGUOUS_BRANCH") in mesh.stops


def test_exclusion_marker_removes_only_foreground_basin():
    from sic_xrt_analyzer.stack3d.defect import isolate_component

    mask = np.zeros((40, 100), bool)
    mask[15:25, 10:90] = True
    selected = isolate_component(mask, (20, 20), [(20, 80)])
    assert selected[20, 20] and not selected[20, 80]
    assert selected.sum() < mask.sum() and np.all(~selected | mask)


def test_curved_variable_width_line_is_one_observation():
    from sic_xrt_analyzer.stack3d.defect import isolate_component
    yy,xx=np.ogrid[:160,:200]
    center=45+35*np.sin(np.arange(200)/32)
    thickness=3+(np.sin(np.arange(200)/13)+1)*1.5
    mask=(np.abs(yy-center[None,:])<=thickness[None,:]) & (xx>15)&(xx<180)
    selected=isolate_component(mask,(int(center[45]),45))
    assert selected.sum()/mask.sum()>.95
    assert np.all(~selected|mask)


def test_explicit_reconnect_after_skipped_page_adds_no_gap_voxels(connected):
    source,a=connected
    a[8]=60000
    tifffile.imwrite(source.path,a,photometric="minisblack")
    s=OriginalImageSource(source.path,7)
    mesh=trace(s,(39,40,7),anchors={9:(40,40)},skipped={8})
    assert 8 not in {p.page for p in mesh.sections}
    assert 9 in {p.page for p in mesh.sections}
    assert (8,"USER_SKIPPED") in mesh.stops
    for section in mesh.sections:
        assert (a[section.page,section.y:section.y+section.height,section.x:section.x+section.width][section.mask()]==5000).all()
