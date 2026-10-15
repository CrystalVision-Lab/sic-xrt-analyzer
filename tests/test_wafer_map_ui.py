"""Actual QML map drafts, worker invalidation, disk history and safe source navigation."""

import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from test_wafer_map import study as map_study

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.ui.bridge import FileBridge
from sic_xrt_analyzer.wafer_map import assets


def spin(app, predicate):
    end = time.monotonic() + 45
    while not predicate():
        assert time.monotonic() < end, "worker timeout"
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def workspace(qt_app, tmp_path):
    p, _a, s, path = map_study.__wrapped__(tmp_path)
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
    window.findChild(QObject, "uiState").setProperty("workspaceIndex", 1)
    bridge.projects.open(str(path))
    c = bridge.waferMap
    c.activate(True)  # Retain the legacy saved-map API regression independently of the folder UI.
    spin(qt_app, lambda: not bridge.projects.busy and not c.busy)
    c.select(s.source_id)
    yield bridge, c, window, warnings, path, s
    bridge.waitForLoads()
    window.hide()
    engine.deleteLater()


def settled(app, c):
    spin(app, lambda: not c.busy and c.reader.task is None)


def test_draft_edit_save_reload_history_and_layers(workspace, qt_app):
    bridge, c, _window, warnings, path, s = workspace
    c.place(10, 20, 35, 0.3, 0.2)
    c.fit()
    settled(qt_app, c)
    assert c.state["placement"]["status"] == "UNVERIFIED", c.error
    assert sum(c.state["summary"].get(k, 0) for k in ("BPD", "TED", "TSD")) == 2946
    m = np.array(c.selectedPlacement()["matrix"])
    decoded = c.scene.decode_count
    c.move(20, -10)
    settled(qt_app, c)
    assert c.dirty
    c.undo()
    settled(qt_app, c)
    assert np.allclose(c.selectedPlacement()["matrix"], m)
    c.setLayer("BPD", False)
    settled(qt_app, c)
    assert not any(r["layer"] == "BPD" for r in c.frame["paths"])
    assert c.scene.decode_count == decoded
    c.save("QA-only map")
    settled(qt_app, c)
    assert not c.error and not c.dirty, c.error
    stored = ProjectStore().load(path)
    ref = assets.active_reference(stored)
    assert ref
    assert not bridge.projects.dirty and bridge.projects.saved_snapshot == stored
    c.place(999, 888, 45, 0.1, 0.1)
    settled(qt_app, c)
    c.resetPlacement()
    settled(qt_app, c)
    assert np.allclose(c.selectedPlacement()["matrix"], m)
    c.undo()
    settled(qt_app, c)
    assert not np.allclose(c.selectedPlacement()["matrix"], m)
    bridge.projects.open(str(path))
    spin(qt_app, lambda: not bridge.projects.busy and not c.busy)
    assert assets.active_reference(bridge.projects.project) == ref
    assert (
        np.allclose(c.selectedPlacement()["matrix"], m)
        if c.selected
        else np.allclose(c.asset["placements"][0]["matrix"], m)
    )
    assert not c.asset["layers"]["BPD"]
    c.select(s.source_id)
    c.move(5, 0)
    settled(qt_app, c)
    c.save("QA revision 2")
    settled(qt_app, c)
    assert len(c.history) == 2 and c.history[-1][0] == ref, c.error
    c.restoreHistory(ref)
    settled(qt_app, c)
    assert c.dirty
    c.save("QA restore as revision 3")
    settled(qt_app, c)
    assert len(c.history) == 3, c.error
    assert not warnings, warnings


def test_physical_requires_independent_points_and_no_implicit_verification(
    workspace, qt_app
):
    _bridge, c, _w, warnings, _path, _s = workspace
    c.addGroup(
        "QA synthetic measured wafer",
        "PHYSICAL",
        "QA-WAFER",
        "QA-coordinates",
        "mm",
        "synthetic origin",
        "X_RIGHT_Y_DOWN",
        "QA-only known grid",
        "4 5 10",
        "QA-only",
    )
    settled(qt_app, c)
    assert not c.error, c.error
    c.place(1, 2, 0, 0.01, 0.02)
    c.fit()
    settled(qt_app, c)
    assert c.selectedPlacement()["status"] == "UNVERIFIED"
    c.verifyPlacement("", "QA", "10 10 1.1 2.2", 0.005)
    assert c.error and c.selectedPlacement()["status"] == "UNVERIFIED"
    c.verifyPlacement(
        "QA known transform",
        "QA-only",
        "10 10 1.1 2.2\n600 10 7 2.2\n10 480 1.1 11.6",
        0.005,
    )
    settled(qt_app, c)
    assert c.selectedPlacement()["status"] == "VERIFIED", c.error
    c.save("QA-only")
    settled(qt_app, c)
    assert not c.error, c.error
    c.move(10, 0)
    settled(qt_app, c)
    assert c.selectedPlacement()["status"] == "UNVERIFIED"
    c.discard()
    settled(qt_app, c)
    assert c.selectedPlacement()["status"] == "VERIFIED"
    assert not warnings, warnings


def test_tiff_cancel_missing_and_candidate_source_route(workspace, qt_app):
    bridge, c, window, warnings, path, s = workspace
    c.place(0, 0, 0, 1, 1)
    c.fit()
    settled(qt_app, c)
    c.save("QA")
    settled(qt_app, c)
    # Point selection carries persisted IDs/Source/Run; existing Viewer handles focus.
    row = next(r for r in c.frame["paths"] if r["layer"] == "BPD")
    xy = row["paths"][0][0]
    assert c.hit(*xy)
    c.selected_target = row
    c.openSelected(True)
    spin(
        qt_app,
        lambda: (
            not bridge.projects.busy
            and not bridge.stack_viewer.busy
            and bridge.projects.selected_run == row["run_id"]
        ),
    )
    spin(
        qt_app,
        lambda: (
            bridge.research.state["selection"]["id"]
            == next(
                o.source_candidate_id
                for o in bridge.projects.project.observations
                if o.observation_id == row["target_id"]
            )
        ),
    )
    assert bridge.projects.selected_source == s.source_id
    assert window.findChild(QObject, "uiState").property("workspaceIndex") == 0
    window.findChild(QObject, "uiState").setProperty("workspaceIndex", 1)
    settled(qt_app, c)
    # Cancel render/project activation must reject old frames.
    c.requestFrame(700, 500)
    c.cancel()
    bridge.projects.close()
    spin(qt_app, lambda: c.reader.task is None)
    assert not c.frame and not c.asset
    bridge.projects.open(str(path))
    spin(qt_app, lambda: not bridge.projects.busy and not c.busy)
    Path(s.source_reference).unlink()
    c.requestFrame(700, 500)
    settled(qt_app, c)
    assert c.frame["tiles"][0]["availability"] == "MISSING"
    assert not bridge.provider.wafer_images
    c.projects._replace(
        bridge.projects.project.evolve(
            image_sources=tuple(
                replace(x, acquisition_metadata={"format": "TIFF"})
                for x in bridge.projects.project.image_sources
            )
        )
    )
    c.select(s.source_id)
    c.place(0, 0, 0, 1, 1)
    assert "TIFF" in c.error
    assert bridge.pipeline.result is None
    assert not warnings, warnings


def test_y_up_pan_zoom_anchor_and_move_are_screen_consistent(workspace, qt_app):
    _bridge, c, _window, warnings, _path, _s = workspace
    c.addGroup(
        "QA Y-up",
        "PHYSICAL",
        "QA-WAFER",
        "QA-UP",
        "mm",
        "QA origin",
        "X_RIGHT_Y_UP",
        "QA-only",
        "",
        "",
    )
    c.place(1, 2, 0, 0.01, 0.02)
    c.fit()
    settled(qt_app, c)
    from sic_xrt_analyzer.wafer_map.mapping import inverse, points, view

    group = c.asset["groups"][-1]
    anchor = [c.width * 0.7, c.height * 0.3]
    world = points(
        inverse(view(c.centre, c.zoom, c.width, c.height, group["axes"])), [anchor]
    )[0]
    c.zoomAt(2, *anchor)
    settled(qt_app, c)
    assert np.allclose(
        points(view(c.centre, c.zoom, c.width, c.height, group["axes"]), [world])[0],
        anchor,
    )
    original = np.array(c.selectedPlacement()["matrix"])
    border = np.array(c.frame["tiles"][0]["border"])
    c.move(30, 20)
    settled(qt_app, c)
    assert np.allclose(np.array(c.frame["tiles"][0]["border"]) - border, [30, 20])
    c.undo()
    settled(qt_app, c)
    assert np.allclose(c.selectedPlacement()["matrix"], original)
    before = np.array(c.frame["tiles"][0]["border"])
    c.pan(20, -30)
    settled(qt_app, c)
    assert np.allclose(np.array(c.frame["tiles"][0]["border"]) - before, [20, -30])
    assert not warnings
