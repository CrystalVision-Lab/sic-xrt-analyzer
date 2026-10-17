"""Design-token ratchet: literal colours and font sizes in QML may only decrease.

New screens use Theme tokens (Theme.qml). When a file is cleaned up, lower its
baseline here so the improvement cannot regress.
"""
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "src" / "sic_xrt_analyzer" / "ui"
HEX = re.compile(r"[\"']#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?[\"']")
PIXEL_SIZE = re.compile(r"pixelSize\s*:\s*\d")

COLOR_BASELINE = {
    "AppIcon.qml": 1,
    "AppUpdatesDialog.qml": 1,
    "DatasetReview.qml": 19,
    "Defect3DScene.qml": 4,
    "DemoImage.qml": 6,
    "FeedbackPanel.qml": 2,
    "ImageJDialog.qml": 2,
    "ImageViewer.qml": 14,
    "ImportedRoiOverlay.qml": 1,
    "ModelUpdatesDialog.qml": 1,
    "OverviewMap.qml": 4,
    "RegistrationWorkspace.qml": 2,
    "ResultDensityOverlay.qml": 1,
    "ReviewGeometryOverlay.qml": 4,
    "SettingsDialog.qml": 4,
    "Stack3DScene.qml": 6,
    "ToolGlyph.qml": 1,
    "UiState.qml": 1,
}

PIXEL_SIZE_BASELINE = {
    "AnalysisDialog.qml": 1,
    "AppUpdatesDialog.qml": 1,
    "DatasetReview.qml": 4,
    "DeviceSetupDialog.qml": 5,
    "FeedbackPanel.qml": 13,
    "ImageViewer.qml": 1,
    "OverviewMap.qml": 1,
    "RegistrationWorkspace.qml": 7,
    "ReportDialog.qml": 1,
    "ReportQueueDialog.qml": 1,
    "ResultCandidateShelf.qml": 6,
    "ResultDensityOverlay.qml": 1,
    "ResultExplorer.qml": 7,
    "Stack3DScene.qml": 2,
    "Stack3DWorkspace.qml": 11,
    "StackPreparationOverlay.qml": 1,
    "StructureLayersDialog.qml": 1,
    "WaferMapWorkspace.qml": 2,
    "WorkflowGuideDialog.qml": 4,
}


def counts(pattern):
    found = {}
    for path in UI.glob("*.qml"):
        if path.name == "Theme.qml":
            continue
        n = len(pattern.findall(path.read_text(encoding="utf-8")))
        if n:
            found[path.name] = n
    return found


def test_literal_colours_do_not_grow():
    grown = {k: v for k, v in counts(HEX).items() if v > COLOR_BASELINE.get(k, 0)}
    assert not grown, f"Use Theme colour tokens instead of literals: {grown}"


def test_literal_font_sizes_do_not_grow():
    grown = {k: v for k, v in counts(PIXEL_SIZE).items() if v > PIXEL_SIZE_BASELINE.get(k, 0)}
    assert not grown, f"Use Theme type tokens (bodySize, smallSize, …) instead of literals: {grown}"
