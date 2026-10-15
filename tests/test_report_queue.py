from uuid import uuid4

import pytest

from sic_xrt_analyzer.sync.client import SyncError
from sic_xrt_analyzer.sync.protocol import digest
from sic_xrt_analyzer.sync.report_queue import ReportQueue, validate_report


def payload():
    return {
        "schema": "xrt_correction/v1",
        "report_id": str(uuid4()),
        "created_at": "2026-10-15T01:00:00Z",
        "reason": "결함 아님",
        "comment": "검토",
        "candidates": [{"id": "a", "x": 24, "y": 36, "type": "BPD", "score": 0.8}],
        "run_id": "run-1",
        "source": {
            "sha256": "a" * 64,
            "width": 128,
            "height": 128,
            "dtype": "uint8",
            "page": 0,
        },
        "roi": None,
        "roi_geometry": None,
        "model_version": "model-1",
        "correction": "",
        "crops": [],
        "approval": "UNVERIFIED",
    }


def test_retry_preserves_id_payload_and_requires_exact_receipt(tmp_path):
    q = ReportQueue(tmp_path / "out.sqlite3")
    p = payload()
    q.stage(p)

    class Server:
        endpoint = "https://example.invalid"

        def request(self, method, path, body):
            assert body == p and path == "/api/v1/reports"
            return {
                "report_id": body["report_id"],
                "payload_hash": "bad",
                "status": "ACKNOWLEDGED",
            }

    server = Server()
    with pytest.raises(SyncError, match="ACK_MISMATCH"):
        q.send(q.pending(server.endpoint), server)
    assert q.rows()[0]["state"] == "FAILED"
    q = ReportQueue(q.path)
    assert q.pending("https://different.invalid") == []
    server.request = lambda m, u, b: {
        "report_id": b["report_id"],
        "payload_hash": digest(b),
        "status": "ACKNOWLEDGED",
    }
    q.send(q.pending(server.endpoint), server)
    assert q.counts() == (0, 1) and q.pending(server.endpoint) == []


def test_contract_rejects_private_paths_invalid_coordinates_and_automatic_approval():
    for field, value in (("approval", "APPROVED"), ("source_path", "C:/private.tif")):
        p = payload()
        p[field] = value
        with pytest.raises(ValueError):
            validate_report(p)
    p = payload()
    p["candidates"][0]["x"] = float("nan")
    with pytest.raises(ValueError):
        validate_report(p)
    p = payload()
    p["reason"] = "누락 결함"
    p["candidates"] = []
    with pytest.raises(ValueError):
        validate_report(p)
    p["roi"] = [0, 0, 32, 32]
    validate_report(p)


def test_server_idempotent_and_conflicting_retry_rejected(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "report_store", Path(__file__).parents[1] / "server/xrt_server/reports.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = payload()
    ack = mod.store_report(tmp_path, "user", "device", p)
    assert mod.store_report(tmp_path, "user", "device", p) == ack
    p["comment"] = "changed"
    with pytest.raises(ValueError, match="CONFLICT"):
        mod.store_report(tmp_path, "user", "device", p)


def test_bulk_selection_crops_and_missing_report_are_local(
    qt_app, tmp_path, bridge_factory
):
    from PySide6.QtCore import QSettings, QUrl
    from test_analysis_pipeline import spin
    from test_desktop_research import create_jpeg_source
    from test_result_explorer import ManyCandidates

    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    source = create_jpeg_source(tmp_path)
    assert b.openImage(QUrl.fromLocalFile(source.path).toString())["ok"]
    b.pipeline.adapter = ManyCandidates()
    b.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
    spin(qt_app, lambda: b.analysis["hasResult"])
    for ident in ("candidate_000000", "candidate_000001"):
        b.research.regions.check(ident, True)
    b.reports.stageSelection("중복 후보", "테스트", "", True, 0, 0, 0, 0)
    spin(qt_app, lambda: not b.reports.busy)
    assert not b.reports.error, b.reports.error
    queued = b.reports.queue.pending("https://example.invalid")
    assert len(queued) == 1 and len(queued[0]["payload"]["candidates"]) == 2
    assert len(queued[0]["payload"]["crops"]) == 2
    assert "canonical_path" not in str(queued[0]["payload"])
    assert b.reports.state["sent"] == 0
    b.reports.stageSelection("누락 결함", "", "", False, 20, 20, 80, 80)
    spin(qt_app, lambda: not b.reports.busy)
    assert not b.reports.error
    assert b.reports.state["pending"] == 2
