"""Main.qml integration, latest cancellation and exact source/page navigation; software != GPU acceptance."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from test_stack3d import study as engine_study

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.ui.bridge import FileBridge


def spin(app, predicate, timeout=30):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "3D worker timeout"
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def workspace(qt_app, tmp_path):
    p, s, reader, path = engine_study.__wrapped__(tmp_path)
    ProjectStore().save(path, p)
    engine = QQmlApplicationEngine()
    QQuickStyle.setStyle("Basic")
    bridge = FileBridge(
        parent=engine,
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat),
    )
    engine.addImageProvider("tiff", bridge.provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    engine.load(
        QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve()))
    )
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    ui = window.findChild(QObject, "uiState")
    ui.setProperty("workspaceIndex", 3)
    bridge.projects.open(str(path))
    c = bridge.stack3d
    spin(
        qt_app,
        lambda: (
            bridge.projects.project is not None
            and not bridge.projects.busy
            and not c.busy
        ),
    )
    yield bridge, c, window, ui, warnings, path, s, reader
    bridge.waitForLoads()
    window.hide()
    engine.deleteLater()


def settled(app, c):
    spin(app, lambda: not c.busy and c.reader.task is None)


def test_qml_volume_orthogonal_cursor_track_save_reopen(workspace, qt_app):
    b, c, w, _ui, warnings, path, s, _reader = workspace
    assert w.findChild(QObject, "stack3dWorkspace") and not w.findChild(
        QObject, "workspacePlaceholder3"
    )
    assert (
        c.selected == s.source_id
        and c.state["physical_status"] == "PHYSICAL_3D_NOT_READY"
    )
    assert c.configure(3, 4, 32, 28, 0, 7, 1, 1)
    c.generate()
    settled(qt_app, c)
    assert c.volume.pixels.shape == (8, 28, 32) and c.state["ready"]
    assert set(c.scene["urls"]) == {"plane-" + str(i) for i in range(8)} | {
        "xy",
        "xp",
        "yp",
    }
    assert "uint16" in c.hover("xy", 0.4, 0.5)
    c.pick("xp", 0.25, 0.5)
    settled(qt_app, c)
    assert c.cursor == [4, 0, 8]
    c.newTrack("manual structure", "QA")
    assert c.state["track_id"]
    c.record("POINT", "QA", "PROPOSED")
    settled(qt_app, c)
    c.setPage(7)
    settled(qt_app, c)
    c.record("RECTANGLE", "QA", "UNCERTAIN")
    settled(qt_app, c)
    assert len(c.scene["markers"]) == 2 and len(c.scene["segments"]) == 18
    c.save("QA")
    settled(qt_app, c)
    assert c.state["history_revision"] == 1 and not c.dirty
    restored = ProjectStore().load(path)
    assert restored.observations == b.projects.project.observations
    b.projects.open(str(path))
    spin(qt_app, lambda: not b.projects.busy and not c.busy and c.session is not None)
    assert (
        c.roi == [3, 4, 32, 28]
        and c.page_range == [0, 7, 1]
        and len(c.tracks) == 1
        and c.volume is None
    )
    c.generate()
    settled(qt_app, c)
    assert c.cursor[0] == 7
    c.setPhysical(True)
    assert not c.physical and "미준비" in c.error
    assert not warnings, warnings


def test_latest_roi_cancel_memory_limit_and_resource_release(workspace, qt_app):
    _b, c, _w, _ui, warnings, _path, _s, _r = workspace
    c.configure(0, 0, 20, 20, 0, 7, 1, 1)
    c.generate()
    c.configure(2, 3, 10, 12, 1, 5, 2, 1)
    c.generate()
    settled(qt_app, c)
    assert c.volume.selection["roi"] == [2, 3, 10, 12] and c.volume.selection[
        "page_indices"
    ] == [1, 3, 5]
    c.generate()
    c.cancel()
    spin(qt_app, lambda: c.reader.task is None)
    assert c.volume is None and "취소" in c.message
    c.generate()
    settled(qt_app, c)
    c.release()
    assert c.volume is None and not c.bridge.provider.stack3d_images
    assert not warnings, warnings


def test_manual_point_revisions_undo_pause_and_source_guard(workspace, qt_app):
    b, c, _w, _ui, _warnings, _path, _s, _r = workspace
    c.configure(0, 0, 20, 20, 0, 7, 1, 1)
    c.generate()
    settled(qt_app, c)
    c.newTrack("manual", "QA")
    c.record("POINT", "QA", "PROPOSED")
    settled(qt_app, c)
    assert len(c.state["track_points"]) == 1
    c.trackAction("PAUSE", "QA")
    settled(qt_app, c)
    c.record("POINT", "QA", "REVIEWED")
    assert "중단" in c.error
    c.trackAction("RESUME", "QA")
    settled(qt_app, c)
    c.setXY(5, 6)
    settled(qt_app, c)
    c.record("POINT", "QA", "REVIEWED")
    settled(qt_app, c)
    assert len(c.tracks[0]["events"]) == 4 and c.state["track_points"][0][
        "coordinates"
    ] == [5, 6]
    c.undo()
    settled(qt_app, c)
    assert c.state["track_points"][0]["coordinates"] == [0, 0]
    c.useViewerRoi(1, 1, 4, 4)
    assert "다릅니다" in c.error
    c.discardTracks()
    settled(qt_app, c)
    assert not c.tracks
    b.clearImage()
    assert c.volume is None


def test_original_source_page_position_navigation(workspace, qt_app):
    b, c, _w, ui, warnings, _path, s, _r = workspace
    # Use the existing TIFF reader, without full-stack preparation in a unit test.
    b.stack_viewer._preload_enabled = False
    b.stack_viewer._reader.preload_enabled = False
    c.configure(3, 4, 32, 28, 0, 7, 1, 1)
    c.generate()
    settled(qt_app, c)
    c.setPage(4)
    settled(qt_app, c)
    c.setXY(5, 6)
    settled(qt_app, c)
    signals = []
    c.focusRequested.connect(lambda x, y: signals.append((x, y)))
    c.openOriginal()
    spin(qt_app, lambda: bool(signals), timeout=45)
    assert (
        b.original_source.path == s.source_reference
        and b.original_source.page_index == 4
    )
    assert signals == [(8.0, 10.0)] and ui.property("workspaceIndex") == 0
    assert not warnings, warnings


def test_unsaved_manual_track_cannot_be_discarded_by_switch(workspace, qt_app):
    b, c, _w, _ui, _warnings, path, _s, _r = workspace
    c.configure(0, 0, 20, 20, 0, 7, 1, 1)
    c.generate()
    settled(qt_app, c)
    c.newTrack("unsaved observation", "QA")
    c.record("POINT", "QA", "UNCERTAIN")
    settled(qt_app, c)
    snapshot = list(c.tracks)
    assert c.manual_pending
    b.projects.close()
    assert b.projects.project is not None and "초안" in b.projects.error
    b.projects.open(str(path))
    assert not b.projects.busy and c.tracks == snapshot
    c.selectSource("missing-other-source")
    assert c.selected and "초안" in c.error
    c.discardTracks()
    settled(qt_app, c)
    assert not c.manual_pending
    b.projects.close()
    assert b.projects.project is None


def test_progress_does_not_overflow_large_tiff_bytes(workspace, qt_app):
    _b, c, _w, _ui, warnings, _path, _s, _r = workspace
    c.busy = True
    c.epoch = 118
    c._progress.emit(118, 3 * 1024**3, 3 * 1024**3, "SHA bytes")
    qt_app.processEvents()
    assert c.progress[:2] == [3 * 1024**3, 3 * 1024**3]
    assert not warnings, warnings
    c.busy = False


def test_unrelated_project_metadata_does_not_cancel_roi_read(workspace, qt_app):
    b, c, _w, _ui, warnings, _path, _s, _r = workspace
    c.configure(3, 4, 32, 28, 0, 7, 1, 1)
    c.generate()
    b.projects._replace(
        b.projects.project.evolve(project_name="unrelated metadata update")
    )
    settled(qt_app, c)
    assert c.volume is not None and c.volume.pixels.shape == (8, 28, 32)
    assert (
        b.projects.project.project_name == "unrelated metadata update" and not warnings
    )
