import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from test_registration import pair as registration_pair

from sic_xrt_analyzer.results import ProjectStore
from sic_xrt_analyzer.ui.bridge import FileBridge


@pytest.fixture
def pair(tmp_path):
    return registration_pair.__wrapped__(tmp_path)


def spin(app, predicate, seconds=30):
    end = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < end, "worker deadline"
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def workspace(qt_app, tmp_path, pair):
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = FileBridge(
        parent=engine,
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat),
    )
    engine.addImageProvider("tiff", bridge.provider)
    bridge.centralSync.dismissSetup()  # Existing-user workflow; first run is covered separately.
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda es: warnings.extend(e.toString() for e in es))
    engine.load(
        QUrl.fromLocalFile(str(Path("src/sic_xrt_analyzer/ui/Main.qml").resolve()))
    )
    assert engine.rootObjects(), warnings
    project, a, b, _m = pair
    path = tmp_path / "project.json"
    ProjectStore().save(path, project)
    bridge.projects.open(str(path))
    spin(qt_app, lambda: not bridge.projects.busy)
    controller = bridge.registration
    controller.select(a.source_id, b.source_id)
    yield bridge, controller, engine.rootObjects()[0], warnings, path
    bridge.waitForLoads()
    engine.deleteLater()


def test_qml_compare_landmarks_approval_restore(workspace, qt_app):
    bridge, c, window, warnings, path = workspace
    window.findChild(
        __import__("PySide6.QtCore", fromlist=["QObject"]).QObject, "uiState"
    ).setProperty("workspaceIndex", 2)
    c.prepare()
    spin(qt_app, lambda: c.session is not None and not c.busy and not c.render_busy)
    assert not c.error, c.error
    c.run("sift", "translation")
    spin(qt_app, lambda: not c.busy and not c.render_busy)
    assert c.state["status"] == "NEEDS_REVIEW", c.error
    assert len(bridge.projects.project.image_relationships) == 1
    original_matrix = c.asset["matrix"]
    for zoom in (1, 2, 4):
        c.zoomAt(zoom / c.zoom, c.width / 2, c.height / 2)
        spin(qt_app, lambda: not c.render_busy)
        c.pan(10, -5)
        spin(qt_app, lambda: not c.render_busy)
        assert c.frame["levels"] == ["original_crop", "original_crop"]
    c.approveAndSave("test-local-reviewer")
    spin(qt_app, lambda: not c.busy)
    assert c.asset["status"] == "ACCEPTED", c.error
    assert not bridge.projects.dirty
    restored = ProjectStore().load(path)
    assert len(restored.image_relationships) == 2
    bridge.projects.close()
    bridge.projects.open(str(path))
    spin(qt_app, lambda: not bridge.projects.busy and not c.busy and not c.render_busy)
    assert c.asset["status"] == "ACCEPTED" and c.asset["matrix"] == original_matrix
    c.beginLandmarks()
    spin(qt_app, lambda: not c.render_busy)
    c.landmarks = [
        {"before": [20, 20], "after": [33, 13], "inlier": True},
        {"before": [450, 30], "after": [463, 23], "inlier": True},
        {"before": [30, 460], "after": [43, 453], "inlier": True},
    ]
    c.editPoint(0, "before", 20, 20)
    c.run("manual", "translation")
    spin(qt_app, lambda: not c.busy and not c.render_busy)
    assert c.asset["status"] == "NEEDS_REVIEW"
    assert len(bridge.projects.project.image_relationships) == 3
    assert not warnings, warnings


def test_cancel_switch_and_tiff_gate(workspace, qt_app, pair):
    bridge, c, _window, warnings, _path = workspace
    c.prepare()
    c.cancel()
    spin(qt_app, lambda: c.reader.task is None)
    assert c.session is None and not c.busy
    p, a, b, _m = pair
    c.select(a.source_id, a.source_id)
    c.prepare()
    assert "서로 다른" in c.error
    from dataclasses import replace

    sources = (replace(a, acquisition_metadata={"format": "TIFF"}), b)
    bridge.projects._replace(p.evolve(image_sources=sources))
    c.select(a.source_id, b.source_id)
    c.prepare()
    assert "TIFF" in c.error
    bridge.projects._replace(p)
    c.select(a.source_id, b.source_id)
    c.prepare()
    spin(qt_app, lambda: c.session is not None and not c.busy and not c.render_busy)
    c.run("sift", "translation")
    bridge.projects.close()
    spin(qt_app, lambda: c.reader.task is None)
    assert c.asset is None and not c.busy
    assert not warnings, warnings


def test_same_project_reload_restores_disk_registration(workspace, qt_app):
    bridge, c, _window, warnings, path = workspace
    c.prepare()
    spin(qt_app, lambda: not c.busy and not c.render_busy)
    c.run("sift", "translation")
    spin(qt_app, lambda: not c.busy and not c.render_busy)
    c.approveAndSave("qa-only")
    spin(qt_app, lambda: not c.busy)
    registered = c.asset["registration_id"]
    c.beginLandmarks()
    spin(qt_app, lambda: not c.render_busy)
    assert c.asset is None
    bridge.projects.open(str(path))
    spin(qt_app, lambda: not bridge.projects.busy and not c.busy and not c.render_busy)
    assert c.asset["registration_id"] == registered and c.asset["status"] == "ACCEPTED"
    assert not warnings, warnings
