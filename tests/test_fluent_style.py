"""Exercise the shipping Fluent style in fresh Qt processes, including high DPI."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("scale", ["1", "1.25", "1.5", "2"])
def test_fluent_decisions_selection_and_layout_at_dpi(tmp_path, scale):
    env = {**os.environ, "QT_SCALE_FACTOR": scale, "QT_QPA_PLATFORM": "offscreen",
           "QSG_RENDER_LOOP": "basic", "SIC_XRT_TEST_UI_STYLE": "FluentWinUI3"}
    if sys.platform == "win32":
        env["QT_QPA_FONTDIR"] = str(Path(os.environ["WINDIR"]) / "Fonts")
    selected = "test_shell_geometry or test_analysis_decisions or test_result_summary or qml_jpeg_imported_roi"
    if scale == "1":
        selected += " or test_popup_rows or test_focus_hover or test_text_contrast"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(Path(__file__).with_name("test_visual_density.py")),
         str(Path(__file__).with_name("test_2d_images_roi.py")), "-k", selected, "--basetemp", str(tmp_path / "fluent"),
         "-o", "tmp_path_retention_policy=failed"],
        env=env, capture_output=True, text=True, timeout=240, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
