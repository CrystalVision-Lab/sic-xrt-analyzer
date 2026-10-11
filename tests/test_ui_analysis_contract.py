"""QML consumes real pipeline state; fake adapter injection exists only in tests."""
from pathlib import Path
from threading import Event

import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import TestAdapter, spin

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def invoke(obj, method, *args):
    assert QMetaObject.invokeMethod(obj, method, *(Q_ARG("QVariant", arg) for arg in args))


def test_ui_original_metadata_and_pipeline_states(qt_app, tmp_path):
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    run = window.findChild(QObject, "runAction")
    cancel = window.findChild(QObject, "cancelAnalysisAction")
    gate = Event()
    try:
        assert bridge.pipeline.adapter is None and bridge.analysis["state"] == "UNAVAILABLE"
        assert bridge.analysis["modelName"] == bridge.analysis["device"] == ""
        assert not run.property("enabled") and not cancel.property("enabled")
        path = tmp_path / "large-original.tif"
        mapped = tifffile.memmap(path, shape=(6000, 8000), dtype="uint16", photometric="minisblack")
        mapped[:] = 50000
        mapped.flush()
        mapped._mmap.close()
        invoke(window, "selectImagePath", str(path))
        spin(qt_app, lambda: not state.property("loading"))
        assert state.property("hasLoadedImage")
        assert (state.property("imageWidth"), state.property("imageHeight")) == (8000, 6000)
        assert (state.property("previewWidth"), state.property("previewHeight")) == (4000, 3000)
        invoke(window, "openInspectorTab", 0)
        assert window.findChild(QObject, "previewSizeRow").property("visible")
        assert bridge.original_source is bridge.pipeline.source
        assert bridge.analysis["inputSource"] == "Original TIFF"
        assert not run.property("enabled")

        adapter = TestAdapter("noncooperative", gate)
        bridge.pipeline.adapter = adapter  # Test-only injection, never an app preference/flag.
        bridge.pipeline.invalidate()
        qt_app.processEvents()
        assert state.property("modelAvailable")
        assert not run.property("enabled")  # Scope still not selected.
        state.setProperty("roiStartX", .125)
        state.setProperty("roiStartY", 1 / 3)
        state.setProperty("roiEndX", .175)
        state.setProperty("roiEndY", .4)
        state.setProperty("hasRoi", True)
        state.setProperty("analysisScope", "ROI")
        qt_app.processEvents()
        assert run.property("enabled")
        invoke(run, "trigger")
        spin(qt_app, adapter.entered.is_set)
        assert state.property("analysisRunning") and cancel.property("enabled")
        assert not run.property("enabled")
        # A model waits in a worker while keyboard navigation and QML are responsive.
        QTest.keyClick(window, Qt.Key_H)
        assert state.property("activeTool") == "Pan"
        invoke(window.findChild(QObject, "actualSizeAction"), "trigger")
        assert state.property("zoomLabel") == "100%"
        state.setProperty("roiStartX", .25)
        qt_app.processEvents()
        assert adapter.request.roi.x == 1000
        gate.set()
        spin(qt_app, lambda: state.property("hasResult"))
        assert bridge.pipeline.result.detections[0].geometry.points == ((1100, 2200),)
        assert bridge.analysis["resultRoiMismatch"]

        # A failed new open preserves the original/viewer but clears its analysis result.
        original = bridge.original_source
        bad = tmp_path / "bad.tif"
        bad.write_bytes(b"bad TIFF")
        invoke(window, "selectImagePath", str(bad))
        spin(qt_app, lambda: not state.property("loading"))
        assert state.property("loadError") and bridge.original_source is original
        assert not state.property("hasResult")
        # Unknown internal detail cannot escape through the UI map.
        from sic_xrt_analyzer.analysis.contracts import AnalysisError
        bridge.pipeline.error = AnalysisError("INFERENCE_FAILED", "Traceback: secret detail", "detail")
        bridge.pipeline.state = AnalysisState.FAILED
        bridge.pipeline.changed.emit()
        assert "secret detail" not in bridge.analysis["errorMessage"]
        invoke(window, "closeImage")
        assert bridge.original_source is None and not bridge.analysis["sourceReady"]
        assert not state.property("hasResult")
        assert not warnings, "\n".join(warnings)
    finally:
        gate.set()
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()
