from pathlib import Path

import pytest

from tools.windows_build_environment import (
    isolated_environment,
    validate_binary_sources,
)


def test_foreign_tool_paths_cannot_influence_dependency_search(tmp_path):
    original = {"PATH": str(tmp_path / "poppler"), "PYTHONPATH": "foreign",
                "QT_PLUGIN_PATH": "foreign-qt", "WINDIR": str(tmp_path / "windows")}
    clean = isolated_environment(original, python_base=tmp_path / "python",
                                 python_env=tmp_path / "venv", jdk=tmp_path / "jdk")
    assert "poppler" not in clean["PATH"]
    assert "PYTHONPATH" not in clean and "QT_PLUGIN_PATH" not in clean
    assert str(tmp_path / "python" / "DLLs") in clean["PATH"]
    assert clean["JAVA_HOME"] == str(tmp_path / "jdk")
    assert original["PYTHONPATH"] == "foreign"


def test_stale_analysis_rejects_foreign_icu(tmp_path):
    with pytest.raises(RuntimeError, match="Foreign binary dependency: icuuc.dll"):
        validate_binary_sources([
            ("icuuc.dll", str(tmp_path / "poppler" / "icuuc.dll"), "BINARY"),
        ], [tmp_path / "venv", tmp_path / "windows"])


def test_allowed_python_and_qt_libraries_pass(tmp_path):
    validate_binary_sources([
        ("Qt6Core.dll", str(tmp_path / "venv" / "PySide6" / "Qt6Core.dll"), "BINARY"),
        ("python313.dll", str(tmp_path / "python" / "python313.dll"), "BINARY"),
    ], [tmp_path / "venv", tmp_path / "python"])


def test_prefix_lookalike_is_not_trusted(tmp_path):
    with pytest.raises(RuntimeError, match="Foreign binary"):
        validate_binary_sources([
            ("icuuc.dll", str(tmp_path / "venv-foreign" / "icuuc.dll"), "BINARY"),
        ], [Path(tmp_path / "venv")])
