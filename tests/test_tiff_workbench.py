"""TD-09 TIFF workbench: real toolbar, page-local ROI and embedded processing."""

import hashlib

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_desktop_research import create_jpeg_source
from test_ui_analysis_contract import invoke

pytest_plugins = ("test_toolbar",)


def point(w, x, y):
    frame = w.item("imageFrame")
    scale = w.item("imageViewer").property("displayScale")
    return (
        w.item("viewerMouseArea")
        .mapToScene(QPointF(frame.x() + x * scale, frame.y() + y * scale))
        .toPoint()
    )


def test_single_tiff_measure_clear_and_jpeg_restore(workbench):
    w = workbench
    path = w.path.parent / "single-disguised.jpg"
    raw = np.arange(256 * 256, dtype=np.uint16).reshape(256, 256)
    tifffile.imwrite(path, raw)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    w.open(path)
    assert w.state.property("tiffMode") and not w.state.property("stackFeaturesVisible")
    assert w.item("stackViewerToolGroup").property("visible")
    assert not w.item("imagePrepareAnalysis").property("visible")
    w.click("tiffToolRectangle")
    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 40, 50))
    QTest.mouseMove(w.window, point(w, 100, 110), 20)
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 100, 110))
    roi = w.bridge.roi_manager.records[-1]
    assert roi.page_index is None
    w.click("tiffMeasure")
    assert w.bridge.measurements.rows[-1]["metric"] == "Area"
    assert w.bridge.measurements.rows[-1]["value"] == pytest.approx(3600, abs=120)
    assert "Area" in w.item("tiffMeasurementSummary").property("text")
    w.bridge.selectImportedRoi("")
    assert not w.item("tiffMeasure").property("enabled")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    w.bridge.roi_manager.clear()
    w.open(create_jpeg_source(w.path.parent).path)
    assert w.item("imagePrepareAnalysis").property("visible") and not w.item(
        "stackViewerToolGroup"
    ).property("visible")
    assert w.state.property("activeTool") == "Pan" and not w.bridge.roi_manager.records
    QTest.keyClick(w.window, Qt.Key_R)
    assert w.state.property("activeTool") == "ROI"


@pytest.mark.parametrize("kind", ["Gaussian", "Threshold", "Background"])
def test_friendly_processing_confirmation_creates_copy(workbench, kind):
    w = workbench
    path = w.path.parent / "processing.tif"
    raw = np.full((64, 64), 2000, np.uint16)
    raw[20:44, 20:44] = 12000
    tifffile.imwrite(path, raw)
    before = path.read_bytes()
    w.open(path)
    invoke(w.window, "processTiff", kind)
    dialog = w.item("imagejProcessingDialog")
    assert dialog.property("visible")
    if kind == "Threshold":
        w.item("processingLower").setProperty("text", "5000")
        w.item("processingUpper").setProperty("text", "13000")
    else:
        w.item("processingRadius").setProperty(
            "text", "2" if kind == "Gaussian" else "10"
        )
    w.click("processingApply")
    spin(
        w.app,
        lambda: not w.bridge.workbench.busy and not w.state.property("opening"),
        30,
    )
    assert not w.bridge.workbench.error, w.bridge.workbench.error
    assert w.bridge.original_source.path != str(path)
    processed = w.bridge.original_source.read_full()
    assert processed.dtype == (np.uint8 if kind == "Threshold" else np.uint16)
    if kind == "Threshold":
        np.testing.assert_array_equal(
            processed, np.where(raw >= 5000, 255, 0).astype(np.uint8)
        )
    else:
        assert not np.array_equal(raw, processed)
    assert path.read_bytes() == before
    assert not w.item("imagePrepareAnalysis").property("visible")


def test_request_cancels_gesture_and_text_shortcuts_do_not_change_tool(workbench):
    w = workbench
    w.click("tiffToolPolygon")
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 40, 40))
    assert w.item("roiFlowState").property("isDrawing")
    w.bridge.requestPage(1)
    assert not w.item("roiFlowState").property("isDrawing")
    QTest.keyClick(w.window, Qt.Key_Return)
    assert not w.bridge.roi_manager.records
    spin(w.app, lambda: w.state.property("pageIndex") == 1)
    QTest.keyClick(w.window, Qt.Key_R)
    assert w.state.property("activeTool") == "Rectangle" and not w.state.property(
        "hasRoi"
    )
    invoke(w.window, "processTiff", "Gaussian")
    w.item("processingRadius").forceActiveFocus()
    QTest.keyClick(w.window, Qt.Key_H)
    QTest.keyClick(w.window, Qt.Key_R)
    assert w.state.property("activeTool") == "Rectangle"
    invoke(w.item("imagejProcessingDialog"), "close")
    choose(w, "roi")
    assert not w.item("analysisRoiState").property("visible")
    assert not w.item("selectImportedBoundsButton").property("visible")


def test_current_page_ready_is_distinct_from_whole_stack(workbench):
    w = workbench
    w.bridge.stack_viewer.initial_loading = True
    w.bridge.stackChanged.emit()
    w.app.processEvents()
    assert w.item("tiffLoadState").property("imagejReady")
    assert w.item("toolRectangleAction").property("enabled")
    assert not w.item("advancedProjectAction").property("enabled")
    w.bridge.workbench.gesture("Rectangle", [[10, 10], [20, 20]])
    assert not w.bridge.workbench.error
    w.bridge.measurements.measure()
    assert w.bridge.measurements.rows[-1]["value"] == 100
    w.bridge.workbench.execute("command", "Invert", "", True)
    assert w.bridge.workbench.error and not w.bridge.workbench.busy
    w.bridge.stack_viewer.initial_loading = False
    w.bridge.stackChanged.emit()


def test_picker_brush_fill_from_more_menu_preserve_original(workbench):
    w = workbench
    path = w.path.parent / "drawing-tools.tif"
    raw = np.zeros((64, 64), np.uint8)
    raw[24:48, 24:48] = 96
    tifffile.imwrite(path, raw)
    before = path.read_bytes()
    w.open(path)
    assert w.bridge.setDisplayRange(0, 255)
    spin(w.app, lambda: not w.bridge.stack_viewer.busy)

    w.select("tiffMore", "tiffMorePicker")
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 32, 32))
    assert w.bridge.workbench.color == "#606060"
    assert not w.bridge.roi_manager.records
    w.bridge.workbench.configure("#ffffff", 1, 0, "")

    w.select("tiffMore", "tiffMoreBrush")
    QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 8, 8))
    QTest.mouseMove(w.window, point(w, 16, 8), 20)
    QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 16, 8))
    spin(
        w.app,
        lambda: not w.bridge.workbench.busy and not w.state.property("opening"),
        30,
    )
    assert not w.bridge.workbench.error, w.bridge.workbench.error
    brushed = w.bridge.original_source.read_full()
    assert brushed.dtype == np.uint8 and brushed[8, 12] == 255
    assert brushed[32, 32] == 96 and brushed[5, 5] == 0
    assert w.bridge.original_source.path != str(path)

    w.select("tiffMore", "tiffMoreFill")
    QTest.mouseClick(w.window, Qt.LeftButton, Qt.NoModifier, point(w, 32, 32))
    spin(
        w.app,
        lambda: not w.bridge.workbench.busy and not w.state.property("opening"),
        30,
    )
    assert not w.bridge.workbench.error, w.bridge.workbench.error
    filled = w.bridge.original_source.read_full()
    assert filled[32, 32] == 255 and filled[5, 5] == 0 and filled[8, 12] == 255
    assert path.read_bytes() == before
    assert (
        w.state.property("tiffMode") and not w.item("imagePrepareAnalysis").isVisible()
    )
