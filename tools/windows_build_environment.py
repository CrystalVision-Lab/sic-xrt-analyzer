"""Keep unrelated developer tools out of frozen Windows dependency resolution."""

import os
from pathlib import Path


def isolated_environment(environ, *, python_base, python_env, jdk):
    environment = dict(environ)
    windows = Path(environment.get("WINDIR", "C:/Windows")).resolve()
    for name in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QML_IMPORT_PATH",
                 "QML2_IMPORT_PATH", "QTDIR"):
        environment.pop(name, None)
    environment["JAVA_HOME"] = str(jdk)
    environment["XRT_BUILD_JDK"] = str(jdk)
    environment["PATH"] = os.pathsep.join(str(p) for p in (
        python_env / "Scripts", python_base, python_base / "DLLs",
        jdk / "bin", windows / "System32", windows,
    ))
    return environment


def validate_binary_sources(binaries, roots):
    """Reject foreign DLLs even when Analysis reuses an older dependency cache."""
    allowed = tuple(Path(root).resolve() for root in roots)
    for name, source, kind in binaries:
        if kind == "BINARY" and not any(Path(source).resolve().is_relative_to(p) for p in allowed):
            raise RuntimeError(
                f"Foreign binary dependency: {name} from {source}. "
                "Rebuild with the isolated environment and a fresh work cache."
            )
