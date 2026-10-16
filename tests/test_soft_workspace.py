"""Distribution -> spatial review -> comparison uses real result/controller state."""

import json

from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_result_ux import analyzed

pytest_plugins = ("test_toolbar",)


def test_density_selection_review_and_original_preserve_result(workbench):
    w = workbench
    r = analyzed(w)
    w.state.setProperty("resultViewMode", "distribution")
    regions = r.regions
    regions.setEdge(256)
    original = w.bridge.pipeline.result
    assert sum(c["count"] for c in regions.state["mapCells"]) == len(r.filtered)
    assert not r.selected_id
    assert w.item("resultDensityOverlay").property("visible")
    assert w.item("analysisOverlay").property("visible")
    # Hidden lists must not create candidate delegates during overview/restoration.
    assert w.item("resultCandidateGrid").property("count") == 0
    assert w.item("candidateList").property("count") == 0
    cell = regions.state["mapCells"][-1]
    regions.selectArea(cell["id"])
    spin(w.app, lambda: w.state.property("resultViewMode") == "area")
    assert regions.state["current"] == cell["id"]
    spin(w.app, lambda: w.item("resultCandidateGrid").property("count") == len(regions.state["rows"]))
    assert regions.state["reviewed"] == 0
    QTest.qWait(500)
    viewer = w.item("imageViewer")
    before = tuple(viewer.property(k) for k in ("panX", "panY", "displayScale"))
    regions.stepCandidate(1)
    QTest.qWait(50)
    assert before == tuple(viewer.property(k) for k in ("panX", "panY", "displayScale"))
    regions.mark("CONFIRMED")
    assert regions.state["reviewed"] == 1
    w.state.setProperty("resultViewMode", "image")
    QTest.qWait(30)
    assert not w.item("analysisOverlay").property("visible")
    assert w.bridge.pipeline.result is original


def test_comparison_pages_check_selection_and_no_transmission(workbench):
    w = workbench
    r = analyzed(w)
    region = r.regions
    w.state.setProperty("resultViewMode", "compare")
    spin(w.app, lambda: bool(region.state["compareRows"][0]["thumbnail"]))
    first = region.state["compareRows"][0]
    region.check(first["id"], True)
    region.setComparePage(1)
    spin(w.app, lambda: bool(region.state["compareRows"][0]["thumbnail"]))
    assert first["id"] not in {p["id"] for p in region.state["compareRows"]}
    assert region.state["checked"] == [first["id"]]
    assert len(region.state["compareRows"]) == 24
    assert len(w.bridge.provider.region_images) == 24
    region.mark("HOLD")
    assert region.records == {first["id"]: "HOLD"}
    assert not region.checked
    assert w.bridge.reports.state["pending"] == 0
    r.setFilter("TSD", False, "")
    spin(w.app, lambda: bool(region.state["compareRows"][0]["thumbnail"]))
    assert region.state["comparePage"] == 0
    assert all(row["type"] == "TSD" for row in region.state["compareRows"])
    assert sum(c["count"] for c in region.state["mapCells"]) == r.state["filteredTotal"]


def test_next_unreviewed_and_invalid_area_do_not_create_decisions(workbench):
    w = workbench
    r = analyzed(w)
    regions = r.regions
    regions.setEdge(256)
    regions.selectArea(regions.groups[0]["id"])
    regions.checkArea(True)
    regions.mark("CONFIRMED")
    first = regions.current
    before = dict(regions.records)
    regions.nextUnreviewed()
    assert regions.current != first and regions.records == before
    current = regions.current
    regions.selectArea("invalid")
    assert regions.current == current and regions.records == before


def test_comparison_navigation_reveals_selected_page(workbench):
    w = workbench
    r = analyzed(w)
    r.selectCandidate("candidate_000023")
    w.state.setProperty("resultViewMode", "compare")
    QTest.qWait(50)
    assert r.regions.state["comparePage"] == 0
    w.click("nextCandidate")
    assert r.selected_id == "candidate_000024"
    spin(w.app, lambda: r.regions.state["comparePage"] == 1)
    assert w.item("shelfCandidate25").property("visible")
    r.selectCandidate("candidate_000240")
    spin(w.app, lambda: r.regions.state["comparePage"] == 10)
    assert w.item("shelfCandidate241").property("visible")
    assert r.regions.state["reviewed"] == 0


def test_cached_comparison_ignores_late_error_from_previous_page(workbench, monkeypatch):
    from threading import Event

    w = workbench
    r = analyzed(w)
    w.state.setProperty("resultViewMode", "compare")
    spin(w.app, lambda: all(p["thumbnail"] for p in r.regions.state["compareRows"]))
    source = r.display_result.request.source
    entered, release = Event(), Event()

    def fail_later(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise OSError("Synthetic previous-page read error")

    monkeypatch.setattr(type(source), "read_region", fail_later)
    try:
        r.regions.setComparePage(1)
        spin(w.app, entered.is_set)
        r.regions.setComparePage(0)
        assert all(p["thumbnail"] for p in r.regions.state["compareRows"])
    finally:
        release.set()
    spin(w.app, lambda: r.regions.thumbnails.task is None)
    assert not r.regions.state["thumbnailError"]
    assert all(p["thumbnail"] for p in r.regions.state["compareRows"])


def test_all_result_views_leave_export_content_unchanged(workbench, tmp_path):
    w = workbench
    r = analyzed(w)
    assert r.exportResult(str(tmp_path / "before"))
    from pathlib import Path

    before = json.loads(
        (Path(r.export_path) / "result.json").read_text(encoding="utf-8")
    )
    for mode in ("distribution", "area", "compare", "image"):
        w.state.setProperty("resultViewMode", mode)
        QTest.qWait(20)
    r.regions.check(r.filtered[0]["id"], True)
    r.regions.mark("CONFIRMED")
    assert r.exportResult(str(tmp_path / "after"))
    after = json.loads(
        (Path(r.export_path) / "result.json").read_text(encoding="utf-8")
    )
    assert before == after
