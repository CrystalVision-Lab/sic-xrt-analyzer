from PySide6.QtCore import QSettings
from test_analysis_pipeline import spin
from test_desktop_research import create_jpeg_source
from test_result_explorer import ManyCandidates

from sic_xrt_analyzer.ui.region_review import make_regions


def test_spatial_ownership_empty_scan_and_boundary():
    rows = [
        {"id": "a", "x": 255, "y": 12, "type": "BPD"},
        {"id": "b", "x": 256, "y": 12, "type": "TED"},
    ]
    groups = make_regions(rows, 513, 257, 256, True)
    assert len(groups) == 6
    assert groups[0]["rows"] == rows[:1] and groups[1]["rows"] == rows[1:]
    assert groups[-1]["rect"] == [512, 256, 1, 1]
    assert sum(len(g["rows"]) for g in groups) == 2


def test_review_is_explicit_persisted_and_navigation_keeps_neighbors(
    qt_app, tmp_path, bridge_factory, monkeypatch
):
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    )
    b.pipeline.adapter = ManyCandidates()
    b.pipeline.set_source(create_jpeg_source(tmp_path))
    b.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
    spin(qt_app, lambda: b.analysis["hasResult"])
    r = b.research.regions
    r.activate(True)
    r.setEdge(256)
    r.stepArea(0)
    key = r.state["key"]
    r.stepCandidate(1)
    assert r.state["key"] == key
    assert len(r.state["rows"]) > 1 and r.state["reviewed"] == 0
    selected = b.research.selected_id
    r.check(selected, True)
    r.mark("CONFIRMED")
    assert r.state["reviewed"] == 1 and not r.checked, (r.state, r.path, r.session)
    assert r.path.exists()
    r.check(selected, True)
    r.mark("HOLD")
    assert r.state["reviewed"] == 0 and r.records[selected] == "HOLD"
    r.stepArea(1)
    assert r.state["key"] != key
    assert b.feedback.state["eventsCount"] == 0
    # Failed writes preserve existing decisions and can be retried explicitly.
    from sic_xrt_analyzer.ui import region_review
    write = region_review.atomic_json
    def fail(*args):
        raise OSError("synthetic full disk")
    r.checkArea(True)
    prior = dict(r.records)
    monkeypatch.setattr(region_review, "atomic_json", fail)
    r.mark("CONFIRMED")
    assert r.error and r.records == prior and r.checked
    monkeypatch.setattr(region_review, "atomic_json", write)
    r.mark("CONFIRMED")
    assert not r.error and not r.checked
