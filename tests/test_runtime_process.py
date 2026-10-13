"""Frozen routing changes only the executable, never worker contracts."""

import sys

import pytest

from sic_xrt_analyzer.runtime_process import worker_command


def test_source_worker_contract():
    assert worker_command(
        "sic_xrt_analyzer.imaging.imagej_service", unbuffered=True
    ) == [sys.executable, "-u", "-m", "sic_xrt_analyzer.imaging.imagej_service"]
    with pytest.raises(ValueError):
        worker_command("untrusted.module")


def test_frozen_requires_owned_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SiCXrtAnalyzer.exe"))
    with pytest.raises(RuntimeError):
        worker_command("sic_xrt_analyzer.model_updates.validation", "bundle")
    helper = tmp_path / "SiCXrtWorker.exe"
    helper.write_bytes(b"SYNTHETIC_ONLY")
    assert worker_command("sic_xrt_analyzer.model_updates.validation", "bundle") == [
        str(helper),
        "-m",
        "sic_xrt_analyzer.model_updates.validation",
        "bundle",
    ]
