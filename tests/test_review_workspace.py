"""Append-only semantics, original-pixel editing and actual Qt review clicks."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_project_workspace import analyze, jpg, wait
from test_result_domain import MANIFEST, graph_fields, legacy
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.adapter import import_legacy_result
from sic_xrt_analyzer.results.contracts import ReviewTarget
from sic_xrt_analyzer.results.geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
)
from sic_xrt_analyzer.results.review_workspace import (
    GeometryDraft,
    add_manual,
    append_review,
)
from sic_xrt_analyzer.results.reviews import ReviewRepository
from sic_xrt_analyzer.results.serialization import dumps, loads, plain
from sic_xrt_analyzer.results.validation import new_id

pytest_plugins = ("test_toolbar",)


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "original.jpg"
    Image.fromarray(np.full((96, 96, 3), 125, np.uint8)).save(path)
    source = JpegImageSource(path)
    return import_legacy_result(
        AnalysisProject("Review fixture"), legacy(source), model_manifest=MANIFEST
    )


def append(
    p,
    reviewer="alice",
    existence="PRESENT",
    classification="TED",
    geometry="ACCEPTED",
    **kwargs,
):
    o = p.observations[0]
    return append_review(
        p,
        ReviewTarget.OBSERVATION,
        o.observation_id,
        reviewer,
        existence,
        classification,
        geometry,
        "independent review",
        source_id=p.image_sources[0].source_id,
        run_id=o.run_id,
        **kwargs,
    )


def test_independent_decisions_append_revision_conflict_and_no_ground_truth(
    project, tmp_path
):
    old = dumps(project)
    p, e1 = append(project)
    assert (
        p.schema_version == "1.1.0"
        and e1.corrected_class == "TED"
        and e1.existence.value == "PRESENT"
    )
    p, e2 = append(p, classification="BPD")
    assert e2.parent_review_ids == (e1.review_id,) and e2.revision == 2
    p, e3 = append(p, reviewer="bob", classification="TED")
    state = ReviewRepository().current(p, e1.target_type, e1.target_id)
    assert (
        state.conflict
        and state.status.value == "NEEDS_REVIEW"
        and not state.assessment.ground_truth_eligible
    )
    assert (
        p.predictions == project.predictions
        and p.observations == project.observations
        and p.geometries == project.geometries
    )
    assert dumps(project) == old
    path = tmp_path / "reviews.json"
    ProjectStore().save(path, p)
    assert ProjectStore().load(path) == p and len(p.review_events) == 3
    assert ReviewRepository().append(p, e3) is p
    with pytest.raises(ValueError):
        ReviewRepository().append(p, replace(e3, comment="different"))


def test_legacy_codec_explicit_version_fields_no_invented_judgements(project):
    payload = json.loads(dumps(project))
    assert payload["schema_version"] == "1.0.0"
    assert loads(dumps(project)) == project
    p, _e = append(project)
    assert loads(dumps(p)) == p
    malformed = json.loads(dumps(p))
    malformed["schema_version"] = "1.0.0"
    malformed["project"]["schema_version"] = "1.0.0"
    with pytest.raises(ValueError):
        loads(json.dumps(malformed))
    del malformed["project"]["review_events"][0]["existence"]
    with pytest.raises(ValueError):
        loads(json.dumps(malformed))


@pytest.mark.parametrize(
    "existence,classification,geometry",
    [
        ("PRESENT", "UNKNOWN", "UNCERTAIN"),
        ("ABSENT", "UNKNOWN", "NOT_REVIEWED"),
        ("UNCERTAIN", "NOT_REVIEWED", "NOT_REVIEWED"),
        ("NOT_REVIEWED", "TED", "NOT_REVIEWED"),
    ],
)
def test_independent_partial_judgements_survive(
    project, existence, classification, geometry
):
    p, _e = append(
        project, existence=existence, classification=classification, geometry=geometry
    )
    restored = loads(dumps(p)).review_events[-1]
    assert (
        restored.existence.value,
        restored.class_decision.value,
        restored.geometry_decision.value,
    ) == (existence, classification, geometry)


@pytest.mark.parametrize("bad", ["", " ", "bad\nuser", "a" * 121])
def test_reviewer_invalid_preserves_project(project, bad):
    before = dumps(project)
    with pytest.raises(ValueError):
        append(project, reviewer=bad)
    assert before == dumps(project)


def test_wrong_source_run_and_immutable_geometry_rejected(project):
    o = project.observations[0]
    for source, run in (
        ("absent", o.run_id),
        (project.image_sources[0].source_id, "absent"),
        (project.image_sources[0].source_id, None),
    ):
        with pytest.raises(ValueError):
            append_review(
                project,
                ReviewTarget.OBSERVATION,
                o.observation_id,
                "a",
                "PRESENT",
                "BPD",
                "ACCEPTED",
                source_id=source,
                run_id=run,
            )
    original = project.geometries[0]
    with pytest.raises(ValueError):
        append(project, geometry=original)


@pytest.mark.parametrize(
    "kind,points",
    [
        ("POINT", [[20, 20]]),
        ("POLYLINE", [[10, 10], [20, 20], [40, 20]]),
        ("POLYGON", [[10, 10], [50, 10], [40, 50]]),
    ],
)
def test_geometry_copy_move_insert_delete_undo_and_restore(project, kind, points):
    source = project.image_sources[0]
    g = DefectGeometry(
        new_id(),
        source.source_id,
        0,
        DefectGeometryKind(kind),
        GeometrySource.RULE_BASED,
        points=tuple(map(tuple, points)),
    )
    d = GeometryDraft(source, geometry=g)
    original = plain(g)
    assert d.select(*points[0], 1)
    d.move(12.25, 13.75)
    moved = d.finish()
    assert (
        moved.geometry_source == GeometrySource.HUMAN
        and moved.geometry_id != g.geometry_id
    )
    d.undo()
    assert d.data == original
    d.add(45, 30)
    d.delete()
    d.undo()
    d.restore()
    assert d.data == original and plain(g) == original
    with pytest.raises(ValueError):
        d.move(-1, 0)


@pytest.mark.parametrize(
    "points",
    [
        [[0, 0], [20, 0], [40, 0]],
        [[0, 0], [20, 20], [0, 20], [20, 0]],
        [[0, 0], [30, 0], [10, 20], [20, -1]],
        [[0, 0], [20, 0], [0, 20], [20, 0]],
    ],
)
def test_polygon_invalid_is_not_committed(project, points):
    d = GeometryDraft(project.image_sources[0], kind="POLYGON")
    d.data["points"] = points
    with pytest.raises(ValueError):
        d.finish()


def test_y_graph_junction_incident_edges_ids_connectivity_path_and_undo(project):
    source = project.image_sources[0]
    g = DefectGeometry(
        new_id(),
        source.source_id,
        0,
        DefectGeometryKind.BRANCHED_GRAPH,
        GeometrySource.RULE_BASED,
        **graph_fields(),
    )
    d = GeometryDraft(source, geometry=g)
    original = plain(g)
    assert d.select(20, 20, 1)
    d.move(24, 22)
    moved = d.finish()
    assert [n.node_id for n in moved.nodes] == [n.node_id for n in g.nodes]
    assert [e.edge_id for e in moved.edges] == [e.edge_id for e in g.edges]
    assert moved.edges[0].points[0] == (24, 22)
    d.add_edge_vertex("e2", 25, 16)
    assert d.finish().edges[1].points[0] == (24, 22)
    d.edge("e3", "", True)
    with pytest.raises(ValueError):
        d.finish()
    d.undo()
    d.restore()
    assert d.data == original and plain(g) == original


@pytest.mark.parametrize("kind", ["POINT", "POLYLINE", "POLYGON", "BRANCHED_GRAPH"])
def test_manual_missing_instance_has_no_fake_predictions(project, kind):
    d = GeometryDraft(project.image_sources[0], kind=kind)
    for p in [[10, 10], [40, 10], [20, 30]]:
        d.add(*p)
    geometry = d.finish()
    p, event, i = add_manual(
        project, geometry.source_id, geometry, "local-researcher", "UNKNOWN", "missed"
    )
    assert (
        i.linked_observations == ()
        and i.instance_status == "HUMAN"
        and not i.assessment.ground_truth_eligible
    )
    assert (
        p.observations == project.observations and p.predictions == project.predictions
    )
    assert (
        event.original_prediction["prediction_ids"] == ()
        and event.reviewer_id == "local-researcher"
    )
    assert loads(dumps(p)) == p


def prepare(w, tmp_path):
    path = jpg(w, tmp_path)
    analyze(w)
    c = w.bridge.projects
    c.save(str(tmp_path / "review-study.json"), "Study")
    wait(w)
    r = w.bridge.research
    r.selectCandidate(r.rows[0]["id"])
    spin(w.app, lambda: bool(r.thumbnail_source))
    v = w.bridge.reviews
    v.setReviewer("researcher-a")
    invoke(w.window, "requestContext", "result", "MANUAL")
    w.window.setProperty("inspectorCollapsed", False)
    return c, r, v, path



def mount_legacy_review(w):
    """Exercise the retained review component without adding it to normal navigation."""
    ui_dir=(Path(__file__).parents[1]/"src/sic_xrt_analyzer/ui").resolve().as_uri()
    component=QQmlComponent(w.engine)
    component.setData(('import QtQuick\nimport QtQuick.Controls\nimport "'+ui_dir+'"\n'+
        'SurfaceDialog {id:host;property QtObject theme;property QtObject uiState;'+
        'modal:true;title:"Legacy review QA";width:460;height:Math.min(610,parent.height-40);'+
        'x:(parent.width-width)/2;y:(parent.height-height)/2;standardButtons:Dialog.Close;'+
        'ReviewWorkspace {anchors.fill:parent;theme:host.theme;uiState:host.uiState}}').encode(),QUrl())
    popup=component.createWithInitialProperties({"parent":w.window.contentItem(),"theme":w.window.property("shellTheme"),"uiState":w.state},w.engine.rootContext())
    assert popup, [e.toString() for e in component.errors()]
    popup.setParent(w.window)
    w.legacy_review_component,w.legacy_review_popup=component,popup
    invoke(popup,"open")


def render(w):
    w.window.grabWindow()
    QTest.qWait(50)


@pytest.mark.parametrize("size", [(1100, 700), (1440, 900), (1920, 1080)])
def test_actual_qml_review_clicks_persistence_conflict_and_predictions(
    workbench, tmp_path, size
):
    w = workbench
    c, _r, v, path = prepare(w, tmp_path)
    w.window.resize(*size)
    render(w)
    original = c.project.predictions
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    w.click("reportCandidate")
    assert w.item("reportDialog").property("visible")
    invoke(w.item("reportDialog"),"close")
    assert v.enter()
    mount_legacy_review(w)
    render(w)
    assert v.mode == "REVIEW" and v.state["ready"]
    w.click("reviewExistencePRESENT")
    w.click("reviewClassTED")
    render(w)
    # Scroll viewport to actual save button, then click the rendered item.
    workspace = w.item("reviewWorkspace")
    save = w.item("reviewCommit")
    flick = workspace.property("contentItem")
    flick.setProperty(
        "contentY",
        max(
            0,
            save.mapToScene(QPointF()).y()
            - workspace.mapToScene(QPointF()).y()
            + float(flick.property("contentY"))
            - 150,
        ),
    )
    render(w)
    w.click("reviewCommit")
    assert (
        len(c.project.review_events) == 1
        and c.dirty
        and c.project.predictions == original
    ), (v.error, v.state)
    v.setReviewer("researcher-b")
    v.decisions("PRESENT", "BPD", "ACCEPTED", "different reviewer")
    assert v.commit(False)
    assert v.state["selected"]["conflict"] and len(v.state["history"]) == 2
    c.save("", "")
    wait(w)
    assert not c.dirty
    p = ProjectStore().load(c.path)
    assert p.predictions == original and len(p.review_events) == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    assert not w.warnings, w.warnings


@pytest.mark.parametrize(
    "zoom,dpi", [(None, 1), (1, 1), (4, 1), (1, 1.25), (4, 1.25), (1, 1.5), (4, 1.5)]
)
def test_viewer_geometry_drag_original_coords_undo_cancel_and_roi_isolation(
    workbench, tmp_path, zoom, dpi
):
    w = workbench
    c, _r, v, _ = prepare(w, tmp_path)
    assert v.enter()
    v.edit()
    assert v.draft
    invoke(w.item("candidateFocusAnimation"), "stop")
    w.state.setProperty("displayPixelRatio", dpi)
    if zoom is None:
        invoke(w.item("imageViewer"), "fitView")
    else:
        invoke(w.item("imageViewer"), "setActualZoom", zoom)
    view = w.item("imageViewer")
    point = v.draft.data["points"][0]
    scale = float(view.property("displayScale"))
    view.setProperty("panX", (256 - point[0]) * scale)
    view.setProperty("panY", (256 - point[1]) * scale)
    render(w)
    frame = w.item("imageFrame")
    mouse = w.item("viewerMouseArea")
    local = frame.mapToItem(mouse, QPointF(point[0] * scale, point[1] * scale))
    scene = mouse.mapToScene(local)
    original = plain(c.project.geometries[0])
    before = (float(view.property("panX")), float(view.property("panY")))
    a = QPoint(round(scene.x()), round(scene.y()))
    b = a + QPoint(12, 8)
    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(w.window, b, 40)
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, b)
    render(w)
    actual = v.draft.data["points"][0]
    assert actual == pytest.approx(
        [point[0] + 12 / scale, point[1] + 8 / scale], abs=1 / scale
    )
    assert before == (float(view.property("panX")), float(view.property("panY")))
    assert plain(c.project.geometries[0]) == original and not w.state.property(
        "roiEditMode"
    )
    QTest.keyClick(w.window, Qt.Key_Z, Qt.ControlModifier)
    assert v.draft.data["points"][0] == point
    v.cancel()
    assert not v.pending and c.project.review_events == ()
    assert not w.warnings, w.warnings


def test_pending_source_run_and_app_exit_guard_failed_save_and_saved_review(
    workbench, tmp_path, monkeypatch
):
    w = workbench
    c, r, v, _ = prepare(w, tmp_path)
    assert v.enter()
    v.decisions("PRESENT", "TED", "ACCEPTED", "note")
    prior = c.project
    c.selectRun(c.project.analysis_runs[0].run_id)
    assert c.project is prior and not c.busy
    invoke(w.window, "closeImage")
    render(w)
    assert w.item("reviewDiscardDialog").property("visible")
    w.click("reviewDiscardCancel")
    assert v.pending
    assert v.commit(False)
    disk = Path(c.path).read_bytes()
    monkeypatch.setattr(
        ProjectStore,
        "save",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk failure")),
    )
    c.save("", "")
    wait(w)
    assert c.dirty and "disk failure" in c.error and Path(c.path).read_bytes() == disk
    monkeypatch.undo()
    c.save("", "")
    wait(w)
    v.cancel()
    c.selectRun(c.project.analysis_runs[0].run_id)
    wait(w)
    spin(w.app, lambda: r.saved is not None and r.pixels_available)
    r.selectCandidate(r.rows[0]["id"])
    assert v.enter() and v.state["ready"]
    v.decisions("UNCERTAIN", "UNKNOWN", "UNCERTAIN", "saved review")
    assert v.commit(False)
    assert (
        c.project.review_events[-1].parent_review_ids
        and len(c.project.review_events) == 2
    )


def test_review_disk_next_failure_keeps_target_and_dirty(
    workbench, tmp_path, monkeypatch
):
    w = workbench
    c, _r, v, _ = prepare(w, tmp_path)
    assert v.enter()
    target = v.target_id
    v.decisions("PRESENT", "TED", "ACCEPTED", "disk test")
    monkeypatch.setattr(
        ProjectStore,
        "save",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")),
    )
    v.saveAndNext()
    wait(w)
    assert v.target_id == target and c.dirty and len(c.project.review_events) == 1
    assert "실패" in v.error and not v.next_after_save
    monkeypatch.undo()
    v.saveAndNext()
    wait(w)
    assert v.target_id != target and not c.dirty


def test_missing_source_history_and_new_visual_review_blocked(workbench, tmp_path):
    w = workbench
    c, r, v, path = prepare(w, tmp_path)
    assert v.enter()
    v.decisions("PRESENT", "TED", "ACCEPTED", "prior decision")
    assert v.commit(False)
    c.save("", "")
    wait(w)
    run = c.project.analysis_runs[0]
    v.cancel()
    w.bridge.clearImage()
    path.rename(tmp_path / "missing.jpg")
    c.selectRun(run.run_id)
    wait(w)
    r.selectCandidate(r.rows[0]["id"])
    assert v.enter() and not v.state["ready"] and len(v.state["history"]) == 1
    before = c.project
    v.decisions("PRESENT", "BPD", "ACCEPTED", "")
    assert not v.commit(False)
    assert c.project is before
    v.edit()
    assert v.draft is None


def test_manual_branch_qml_add_move_path_delete_cancel(workbench, tmp_path):
    w = workbench
    c, _r, v, _ = prepare(w, tmp_path)
    v.addManual("BRANCHED_GRAPH")
    invoke(w.item("candidateFocusAnimation"), "stop")
    invoke(w.item("imageViewer"), "fitView")
    render(w)
    frame = w.item("imageFrame")
    scale = w.item("imageViewer").property("displayScale")

    def click_pixel(x, y):
        point = frame.mapToScene(QPointF(x * scale, y * scale))
        QTest.mouseClick(
            w.window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
        render(w)

    for x, y in [(200, 200), (170, 150), (240, 210), (180, 240)]:
        click_pixel(x, y)
    assert len(v.draft.data["nodes"]) == 4 and len(v.draft.data["edges"]) == 3
    # Explicitly branch from center after selecting it; keep immutable graph IDs.
    v.setTool("move")
    v.press(200, 200, 3)
    v.release(False)
    v.setTool("add")
    v.press(230, 150, 3)
    v.release(False)
    graph = v.draft.finish()
    assert len(graph.nodes) == 5
    selected = v.draft.selected
    v.deleteVertex()
    v.undo()
    assert len(v.draft.finish().nodes) == 5
    assert selected.startswith("n:")
    v.decisions("PRESENT", "BPD", "ACCEPTED", "manual graph")
    assert v.commit(False)
    assert (
        c.project.defect_instances[-1].instance_status == "HUMAN"
        and c.project.defect_instances[-1].linked_observations == ()
    )
    assert len(c.project.predictions) == 2946
    v.edit()
    prior = plain(c.project.geometries[-1])
    v.cancel()
    assert plain(c.project.geometries[-1]) == prior
    assert not w.warnings, w.warnings


def test_codec_refuses_legacy_version_downgrade_instead_of_losing_decisions(project):
    reviewed, _ = append(project)
    object.__setattr__(reviewed, "schema_version", "1.0.0")
    with pytest.raises(ValueError):
        dumps(reviewed)


def test_corrected_human_geometry_append_and_atomic_disk_failure_preserve_original(
    project, tmp_path, monkeypatch
):
    from sic_xrt_analyzer.results import persistence

    d = GeometryDraft(project.image_sources[0], geometry=project.geometries[0])
    d.select(*d.data["points"][0], 1)
    d.move(20.5, 21.75)
    g = d.finish()
    o = project.observations[0]
    reviewed, event = append_review(
        project,
        ReviewTarget.OBSERVATION,
        o.observation_id,
        "alice",
        "PRESENT",
        "BPD",
        "CORRECTED",
        geometry=g,
        source_id=g.source_id,
        run_id=o.run_id,
    )
    assert (
        reviewed.geometries[:-1] == project.geometries
        and event.corrected_geometry_reference == g.geometry_id
    )
    path = tmp_path / "atomic.json"
    ProjectStore().save(path, project)
    before = path.read_bytes()
    monkeypatch.setattr(
        persistence.os,
        "replace",
        lambda *a: (_ for _ in ()).throw(OSError("failed publish")),
    )
    with pytest.raises(OSError):
        ProjectStore().save(path, reviewed, expected_revision=project.revision)
    assert path.read_bytes() == before
    monkeypatch.undo()
    ProjectStore().save(path, reviewed, expected_revision=project.revision)
    assert ProjectStore().load(path) == reviewed


def test_graph_opaque_node_edge_ids_keep_colons(project):
    from sic_xrt_analyzer.results.geometry import GraphEdge, GraphNode

    source = project.image_sources[0]
    g = DefectGeometry(
        new_id(),
        source.source_id,
        0,
        DefectGeometryKind.BRANCHED_GRAPH,
        GeometrySource.HUMAN,
        nodes=(GraphNode("n:a", 10, 10), GraphNode("n:b", 30, 30)),
        edges=(
            GraphEdge("edge:original", "n:a", "n:b", ((10, 10), (20, 18), (30, 30))),
        ),
    )
    d = GeometryDraft(source, geometry=g)
    assert d.select(10, 10, 1)
    d.move(12, 13)
    assert d.finish().edges[0].points[0] == (12, 13)
    assert d.select(20, 18, 1)
    d.move(21, 22)
    d.delete()
    d.undo()
    assert d.finish().edges[0].edge_id == "edge:original"


def test_actual_review_typing_does_not_trigger_global_r_h_shortcuts(
    workbench, tmp_path
):
    w = workbench
    _c, _r, v, _path = prepare(w, tmp_path)
    assert v.enter()
    mount_legacy_review(w)
    render(w)
    note = w.item("reviewComment")
    note.forceActiveFocus()
    render(w)
    assert w.window.property("editingText")
    for char in "research review: bpd to ted":
        QTest.keyClick(
            w.window,
            Qt.Key(ord(char.upper())),
            Qt.ShiftModifier if char.isupper() else Qt.NoModifier,
        )
    render(w)
    assert v.comment == "research review: bpd to ted", (
        v.comment,
        note.property("text"),
    )
    assert w.state.property("activeTool") == "Pan" and note.property("activeFocus")
    v.decisions("PRESENT", "TED", "ACCEPTED", v.comment)
    assert v.commit(False)
    assert _c.project.review_events[-1].comment == "research review: bpd to ted"


def test_review_index_resolves_typed_observation_links(workbench, tmp_path):
    from sic_xrt_analyzer.results.contracts import DefectInstance, ObservationLink

    c, _r, v, _ = prepare(workbench, tmp_path)
    p = c.project
    o = p.observations[0]
    g = next(g for g in p.geometries if g.geometry_id == o.geometry_id)
    instance = DefectInstance(
        new_id(),
        g.source_id,
        g.geometry_id,
        (ObservationLink(o.observation_id),),
        "BPD",
    )
    c._replace(p.evolve(defect_instances=p.defect_instances + (instance,)))
    row = next(row for row in v.rows if row["id"] == instance.instance_id)
    assert row["linkedObservations"] == [
        {
            "id": o.observation_id,
            "candidateId": o.source_candidate_id,
            "label": o.assigned_class or "UNKNOWN",
            "runId": o.run_id,
        }
    ]
    assert not workbench.warnings
