"""Frozen GUI/worker entry point; whitelist the two existing app-owned modules."""

import multiprocessing
import os
import runpy
import sys
from pathlib import Path


def configure():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    runtime = root / "runtimes"
    if (runtime / "imagej").is_dir():
        os.environ.setdefault("SIC_XRT_IMAGEJ_HOME", str(runtime / "imagej"))
    if (runtime / "fiji").is_dir():
        os.environ.setdefault("SIC_XRT_FIJI_HOME", str(runtime / "fiji"))
    java = runtime / "openjdk"
    if (java / "bin/java.exe").is_file():
        os.environ["JAVA_HOME"] = str(java)
        os.environ["PATH"] = str(java / "bin") + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("QSG_RENDER_LOOP", "basic")


def main():
    multiprocessing.freeze_support()
    configure()
    if "-m" in sys.argv:
        index = sys.argv.index("-m")
        module = sys.argv[index + 1]
        from sic_xrt_analyzer.runtime_process import MODULES

        if module not in MODULES:
            return 2
        sys.argv = sys.argv[index + 1 :]
        runpy.run_module(module, run_name="__main__")
        return 0
    if "--smoke-report" in sys.argv:
        from sic_xrt_analyzer.distribution_smoke import main as smoke

        return smoke(Path(sys.argv[sys.argv.index("--smoke-report") + 1]), [sys.argv[i+1] for i,a in enumerate(sys.argv[:-1]) if a == "--verify-image"])
    from sic_xrt_analyzer.__main__ import main as app

    return app()


if __name__ == "__main__":
    raise SystemExit(main())
