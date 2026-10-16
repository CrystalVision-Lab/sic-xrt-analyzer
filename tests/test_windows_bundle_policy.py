import runpy
from pathlib import Path

import pytest

policy = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/windows_bundle_policy.py"))


@pytest.mark.parametrize("name", [
    "runtimes/fiji/jars/linux64/native.jar", "runtimes/fiji/jars/macos-arm64/native.jar",
    "runtimes/openjdk/jmods/java.base.jmod", "runtimes/openjdk/lib/src.zip",
    "PySide6/Qt6WebEngineCore.dll", "PySide6/qml/QtWebEngine/qmldir",
    "PySide6/plugins/webview/qtwebview_webengine.dll",
])
def test_excludes_only_reviewed_packaging_inputs(name):
    assert policy["exclusion_reason"](name)
    assert policy["exclusion_reason"](name.replace("/", "\\"))


@pytest.mark.parametrize("name", [
    "runtimes/fiji/jars/win64/native.jar", "runtimes/fiji/jars/imagej-common.jar",
    "runtimes/fiji/plugins/Compiler.jar", "runtimes/openjdk/bin/javac.exe",
    "runtimes/openjdk/lib/modules", "runtimes/openjdk/legal/java.base/LICENSE",
    "PySide6/qml/QtQuick3D/qmldir", "PySide6/qml/QtQuick/Controls/FluentWinUI3/Button.qml",
    "imagecodecs/_jpeg2k.pyd", "PySide6/qml/QtWebEngineOther/plugin.dll",
])
def test_dynamic_runtime_and_license_inputs_are_preserved(name):
    assert policy["exclusion_reason"](name) is None


def test_size_audit_is_based_on_actual_files_without_modifying_inputs(tmp_path):
    keep, drop = tmp_path / "keep", tmp_path / "drop"
    keep.write_bytes(b"required")
    drop.write_bytes(b"source")
    entries = [("runtimes/openjdk/lib/modules", str(keep), "DATA"),
               ("runtimes/openjdk/lib/src.zip", str(drop), "DATA")]
    kept, removed = policy["slim_toc"](entries)
    assert kept == entries[:1] and removed[0]["bytes"] == 6
    assert keep.read_bytes() == b"required" and drop.read_bytes() == b"source"
