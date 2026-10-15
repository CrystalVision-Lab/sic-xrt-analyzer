"""Authenticated, idempotent correction receipt storage (never auto-approved)."""

import sqlite3
from pathlib import Path

from sic_xrt_analyzer.sync.protocol import digest, encode
from sic_xrt_analyzer.sync.report_queue import validate_report


def store_report(root, actor, device, payload):
    validate_report(payload)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    signature = digest(payload)
    with sqlite3.connect(root / "correction-reports.sqlite3", timeout=10) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS corrections(actor TEXT,device TEXT,id TEXT,hash TEXT,payload TEXT,PRIMARY KEY(actor,device,id))"
        )
        db.execute(
            "INSERT OR IGNORE INTO corrections VALUES(?,?,?,?,?)",
            (actor, device, payload["report_id"], signature, encode(payload).decode()),
        )
        old = db.execute(
            "SELECT hash FROM corrections WHERE actor=? AND device=? AND id=?",
            (actor, device, payload["report_id"]),
        ).fetchone()
        if old[0] != signature:
            raise ValueError("REPORT_ID_CONFLICT")
    return {
        "report_id": payload["report_id"],
        "payload_hash": signature,
        "status": "ACKNOWLEDGED",
    }
