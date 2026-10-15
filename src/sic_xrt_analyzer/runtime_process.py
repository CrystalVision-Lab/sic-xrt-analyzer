"""Resolve app-owned helper processes in source and frozen Windows distributions."""

import sys
from pathlib import Path

MODULES = {
    "sic_xrt_analyzer.imaging.imagej_service",
    "sic_xrt_analyzer.model_updates.validation",
}


def worker_command(module, *arguments, unbuffered=False):
    if module not in MODULES:
        raise ValueError("Unsupported application worker")
    executable = sys.executable
    if getattr(sys, "frozen", False):
        helper = Path(sys.executable).resolve().with_name("SiCXrtWorker.exe")
        if not helper.is_file():
            raise RuntimeError("Installed worker executable is missing")
        executable = str(helper)
    return [
        executable,
        *(["-u"] if unbuffered else []),
        "-m",
        module,
        *map(str, arguments),
    ]
