"""Page-track review screen (#188) on a synthetic stack; no real XRT data."""

import copy
import time
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source
from sic_xrt_analyzer.stack3d import assets
from sic_xrt_analyzer.stack3d.tracking import track_stack
from sic_xrt_analyzer.stack3d.tracking.review import ReviewState
from sic_xrt_analyzer.stack3d.tracking.views import filmstrip, kymographs
from sic_xrt_analyzer.ui.bridge import FileBridge

PAGES, SIZE = 14, 96


def synthetic_stack():
    """Dark drifting line (pages 0-13), dark dot (2-11), on a bright noisy field."""
    rng = np.random.default_rng(188)
    v = 60000 + rng.normal(0, 250, (PAGES, SIZE, SIZE))
    for k in range(PAGES):
        x = 30 + k // 3
        v[k, 20:70, x:x + 3] -= 9000
        if 2 <= k <= 11:
            yy, xx = np.ogrid[:SIZE, :SIZE]
            v[k][(xx - 70) ** 2 + (yy - 40 - k // 4) ** 2 <= 9] -= 9000
    return np.clip(v, 0, 65535).astype(np.uint16)


def spin(app, predicate, timeout=60):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "worker timeout"
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def screen(qt_app, tmp_path):
    tif = tmp_path / "synthetic.tif"
    tifffile.imwrite(tif, synthetic_stack(), photometric="minisblack")
    p, s = add_source(AnalysisProject("QA page-track review"), OriginalImageSource(tif))
    s = verify_content_hash(s)
    p = p.evolve(image_sources=(s,))
    path = tmp_path / "project.json"
    ProjectStore().save(path, p)
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = FileBridge(parent=engine, settings=QSettings(str(tmp_path / "p.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", bridge.provider)
    bridge.centralSync.dismissSetup()
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    engine.load(QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve())))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    window.findChild(QObject, "uiState").setProperty("workspaceIndex", 3)
    bridge.projects.open(str(path))
    c = bridge.stack3d
    c.setActive(True)
    spin(qt_app, lambda: bridge.projects.project is not None and not bridge.projects.busy and not c.busy)
    yield bridge, c, bridge.trackReview, window, warnings, path
    bridge.waitForLoads()
    window.hide()
    engine.deleteLater()


def volume(app, c):
    assert c.configure(0, 0, SIZE, SIZE, 0, PAGES - 1, 1, 1)
    c.generate()
    spin(app, lambda: not c.busy and c.volume is not None)


def run(app, r):
    r.run()
    spin(app, lambda: not r.busy)
    assert r.result is not None, r.error


def line_track(r):
    return max(r.replay.tracks.values(), key=lambda t: len(t.detection_ids))


def test_views_cut_original_pixels_along_track():
    v = synthetic_stack()
    result = track_stack(v, origin=(0, 0), first_page=0)
    t = max(result.tracks, key=lambda t: len(t.pages))
    assert len(t.pages) >= 12
    film = filmstrip(v, (0, 0), 0, result, t.detection_ids)
    assert [f[0] for f in film] == list(range(t.pages[0], t.pages[-1] + 1))
    for page, (x0, y0, x1, y1), crop, mask in film:
        assert np.array_equal(crop, v[page, y0:y1, x0:x1]) and crop.dtype == np.uint16
        assert mask.shape == crop.shape
    xp, yp = kymographs(v, (0, 0), 0, result, t.detection_ids, radius=10)
    assert xp.shape == yp.shape == (PAGES, 21) and xp.dtype == np.uint16
    # The straightened line stays dark in the centre column on every page.
    assert (xp[:, 10].astype(int) < xp[:, 0].astype(int) - 4000).all()


def test_review_state_replays_events_and_rejects_bad_ones():
    result = track_stack(synthetic_stack())
    t = max(result.tracks, key=lambda t: len(t.pages))
    ids = t.detection_ids

    def ev(action, **kw):
        e = assets.review_event(action, kw.pop("track", t.id), "QA", **kw)
        return e

    events = [ev("SPLIT", other="x1", source_detection=ids[4], target_detection=ids[5],
                 page=result.detection(ids[5]).page)]
    state = ReviewState(result, events)
    assert state.tracks[t.id].detection_ids == list(ids[:5])
    assert state.tracks["x1"].detection_ids == list(ids[5:])
    events.append(ev("MERGE", other="x1", source_detection=ids[4], target_detection=ids[5],
                     page=result.detection(ids[5]).page))
    state = ReviewState(result, events)
    assert state.tracks[t.id].detection_ids == list(ids) and "x1" not in state.tracks
    timeline = state.timeline(state.tracks[t.id], range(PAGES))
    assert timeline[result.detection(ids[5]).page]["state"] == "manual"
    events.append(ev("ACCEPT_LINK", source_detection=ids[1], target_detection=ids[2],
                     page=result.detection(ids[2]).page))
    events.append(ev("REJECT_TRACK"))
    state = ReviewState(result, events)
    assert state.tracks[t.id].status == "REJECTED" and not state.summary(state.tracks[t.id])["review"]
    with pytest.raises(ValueError):
        ReviewState(result, [ev("ACCEPT_LINK", source_detection=ids[1], target_detection=ids[3], page=None)])
    with pytest.raises(ValueError):
        ReviewState(result, [*events, ev("ACCEPT_LINK", source_detection=ids[1], target_detection=ids[2], page=None)])


def test_screen_keyboard_corrections_save_and_reload(screen, qt_app):
    b, c, r, window, warnings, path = screen
    assert window.findChild(QObject, "trackReviewEmpty").property("visible")
    volume(qt_app, c)
    run(qt_app, r)
    assert r.state["trackCount"] >= 2 and r.tracks
    # Low-confidence / review tracks are listed first by default.
    keys = [(row["status"] == "REJECTED", not row["review"], row["minConfidence"]) for row in r.tracks]
    assert keys == sorted(keys)
    t = line_track(r)
    r.selectTrack(t.id)
    span = r.replay.summary(t)["span"]
    assert len(r.filmstrip) == span and len(r.timeline) == PAGES
    images = b.provider.stack3d_images
    xp = images[r.kymograph["xp"].split("stack3d-")[1]]
    assert (xp.width(), xp.height()) == (81, PAGES)
    assert not images[r.filmstrip[0]["url"].split("stack3d-")[1]].isNull()
    assert {i["state"] for i in r.timeline} <= {"start", "linked", "low", "gap", "outside"}
    assert r.state["pageOverlay"]

    # Keyboard flow on the real window.
    window.requestActivate()
    spin(qt_app, lambda: window.isActive(), 10)
    r.setReviewer("QA")
    r.setPage(6)
    spin(qt_app, lambda: not c.busy)
    before = len(r.replay.tracks)
    QTest.keyClick(window, Qt.Key_S)
    qt_app.processEvents()
    assert [e["action"] for e in r.events] == ["SPLIT"], r.error
    assert len(r.replay.tracks) == before + 1
    tail = r.events[-1]["other_track_id"]
    r.setMergeTarget(tail)
    QTest.keyClick(window, Qt.Key_M)
    qt_app.processEvents()
    assert r.events[-1]["action"] == "MERGE" and tail not in r.replay.tracks
    QTest.keyClick(window, Qt.Key_Right)
    spin(qt_app, lambda: not c.busy)
    assert c.cursor[0] == 7
    QTest.keyClick(window, Qt.Key_A)
    qt_app.processEvents()
    assert r.events[-1]["action"] == "ACCEPT_LINK" and r.events[-1]["page_index"] == 7
    timeline = r.timeline
    assert timeline[6]["state"] == "manual" and timeline[7]["state"] == "accepted"
    last = r.tracks[-1]["id"] == t.id
    QTest.keyClick(window, Qt.Key_Up if last else Qt.Key_Down)
    qt_app.processEvents()
    other = r.selected
    assert other != t.id
    QTest.keyClick(window, Qt.Key_R)
    qt_app.processEvents()
    assert r.events[-1]["action"] == "REJECT_TRACK" and r.replay.tracks[other].status == "REJECTED"
    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    qt_app.processEvents()
    assert len(r.events) == 3 and r.replay.tracks[other].status == "PROPOSED"
    assert all(e["method"] == "MANUAL" and e["status"] == "REVIEWED" and e["reviewer"] == "QA" for e in r.events)
    events = copy.deepcopy(r.events)
    merged = list(r.replay.tracks[t.id].detection_ids)

    # Unsaved corrections block a rerun and source switching.
    r.run()
    assert "저장" in r.error and r.result is not None
    assert c.manual_pending
    spin(qt_app, lambda: not c.busy)
    c.save("QA")
    spin(qt_app, lambda: not c.busy)
    assert not r.pending and not c.manual_pending, c.error
    session = assets.read(path, ProjectStore().load(path).image_sources[0].acquisition_metadata[assets.KEY])
    assert session["schema"] == assets.SESSION_V2 and session[assets.REVIEW_KEY]
    stored = assets.read(path, session[assets.REVIEW_KEY])
    assert stored["events"] == events and stored["selection"]["roi"] == [0, 0, SIZE, SIZE]

    # Reopen: events replay on the stored AUTO result; append-only on the next save.
    b.projects.open(str(path))
    spin(qt_app, lambda: not b.projects.busy and not c.busy and r.result is not None)
    assert r.events == events and r.replay.tracks[t.id].detection_ids == merged
    assert r.stale
    volume(qt_app, c)
    assert not r.stale
    r.setReviewer("QA")
    r.selectTrack(t.id)
    r.rejectTrack()
    spin(qt_app, lambda: not c.busy)
    c.save("QA")
    spin(qt_app, lambda: not c.busy)
    assert not c.error and not r.pending, (c.error, r.error)
    rows = assets.chain(path, ProjectStore().load(path).image_sources[0].acquisition_metadata[assets.KEY],
                        ProjectStore().load(path))
    assert len(rows) == 2
    newer = assets.read(path, rows[0][1][assets.REVIEW_KEY])
    assert newer["events"][:3] == events and newer["review_id"] == stored["review_id"]
    assert not warnings, warnings


def test_seed_click_opens_roi_and_selects_track(screen, qt_app):
    b, c, r, _window, warnings, _path = screen
    b.original_source = OriginalImageSource(c.source.source_reference, 5)
    assert r.startFromViewer(31, 45)
    spin(qt_app, lambda: c.volume is not None and not c.busy and not r.busy and r.result is not None)
    t = r.replay.tracks[r.selected]
    assert len(t.detection_ids) >= 12, r.message
    assert c.volume.selection["roi"] == [0, 0, SIZE, SIZE]
    assert not warnings, warnings


def test_cancel_keeps_previous_state(screen, qt_app):
    _b, c, r, _w, _warnings, _path = screen
    volume(qt_app, c)
    r.run()
    r.cancel()
    assert not r.busy and r.result is None
    spin(qt_app, lambda: r.reader.task is None)
    assert r.result is None


def test_old_v1_session_and_review_history_rules(screen, qt_app, tmp_path):
    _b, c, r, _w, _warnings, path = screen
    volume(qt_app, c)
    c.save("QA")  # no review yet -> v2 session with null review
    spin(qt_app, lambda: not c.busy)
    project = ProjectStore().load(path)
    ref = project.image_sources[0].acquisition_metadata[assets.KEY]
    a = assets.read(path, ref)
    assert a["schema"] == assets.SESSION_V2 and a[assets.REVIEW_KEY] is None
    legacy = {k: v for k, v in a.items() if k != assets.REVIEW_KEY}
    legacy["schema"] = assets.SESSION
    assets.validate_session(legacy, project)  # v1 still accepted
    run(qt_app, r)
    r.setReviewer("QA")
    r.selectTrack(line_track(r).id)
    r.rejectTrack()
    spin(qt_app, lambda: not c.busy)
    c.save("QA")
    spin(qt_app, lambda: not c.busy)
    project = ProjectStore().load(path)
    head = assets.read(path, project.image_sources[0].acquisition_metadata[assets.KEY])
    review = assets.read(path, head[assets.REVIEW_KEY])
    # Rewriting an event in a later revision of the same review is refused.
    forged = copy.deepcopy(review)
    forged["events"][0]["reviewer"] = "someone else"
    forged_ref = assets.publish(path, forged)
    newer = dict(head, revision=head["revision"] + 1, parent_reference=project.image_sources[0].acquisition_metadata[assets.KEY],
                 revision_id="forged", created_at=head["created_at"])
    newer[assets.REVIEW_KEY] = forged_ref
    newer_ref = assets.publish(path, newer)
    with pytest.raises(ValueError):
        assets.chain(path, newer_ref, project)
    # Save As copies session, review and AUTO result byte-for-byte.
    from sic_xrt_analyzer.results.workspace import publish_dependencies
    other = tmp_path / "copy" / "project.json"
    publish_dependencies(other, project, [], path)
    ProjectStore().save(other, project)
    assert ProjectStore().load(other) == project
    assert (other.parent / review["result_reference"]).read_bytes() == (path.parent / review["result_reference"]).read_bytes()
