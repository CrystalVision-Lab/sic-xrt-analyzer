import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from test_analysis_pipeline import spin
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import AnalysisRequest, AnalysisScope, Region
from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
from sic_xrt_analyzer.analysis.model_adapter import CancellationToken
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


class Classifier:
    manifest: ClassVar = {"bundle_id": "fixture", "model_sha256": "a" * 64}

    def predict(self, patches):
        assert all(p.shape == (128, 128, 3) for p in patches)
        return np.tile([.1, .8, .1], (len(patches), 1))


def create_source(tmp_path):
    path = tmp_path / "image.tif"
    image = np.zeros((512, 512, 3), np.uint8)
    image[250:258, 250:258] = 255
    tifffile.imwrite(path, image, photometric="rgb")
    return OriginalImageSource(path)


def test_source_adapter_preserves_coordinates_and_scope_without_full_read(tmp_path, monkeypatch):
    source = create_source(tmp_path)
    def forbidden(_):
        raise AssertionError("must not read the whole image")
    monkeypatch.setattr(OriginalImageSource, "read_full", forbidden)
    adapter = DesktopResearchAdapter(None, Classifier())
    points = [{"x": 256.2, "y": 256, "point_id": "a"}, {"x": 256, "y": 256},
              {"x": 130, "y": 130}, {"x": 0, "y": 0}]
    request = AnalysisRequest(source, AnalysisScope.ROI, adapter.model_id, adapter.model_version,
                              Region(128, 128, 256, 256), {"point_mode": "provided_coordinates", "points": points})
    result = adapter.analyze_source(request, CancellationToken())
    assert len(result.detections) == 1
    assert result.detections[0].geometry.points == ((256.2, 256.0),)
    assert dict(result.summary["excluded"]) == {"duplicate_center": 1, "incomplete_patch": 1, "outside_scope": 1}
    assert not result.summary["human_verified"]


def test_auto_candidates_and_cancellation(tmp_path):
    source = create_source(tmp_path)
    adapter = DesktopResearchAdapter(None, Classifier())
    request = AnalysisRequest(source, AnalysisScope.FULL_IMAGE, adapter.model_id, adapter.model_version)
    result = adapter.analyze_source(request, CancellationToken())
    assert len(result.detections) == 1
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception, match="취소"):
        adapter.analyze_source(request, token)


def test_invalid_model_load_is_reported_without_ready_state(qt_app, tmp_path, bridge_factory):
    bridge = bridge_factory(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    bridge.research.loadModel(str(tmp_path))
    spin(qt_app, lambda: not bridge.research.state["loading"])
    assert bridge.research.state["error"]
    assert bridge.pipeline.adapter is None


def test_csv_binding_export_and_replaced_image(qt_app, tmp_path, bridge_factory):
    source = create_source(tmp_path)
    bridge = bridge_factory(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    bridge.pipeline.adapter = DesktopResearchAdapter(None, Classifier())
    bridge.pipeline.set_source(source)
    csv = tmp_path / "points.csv"
    csv.write_text("point_id,x,y\np1,256,256\n", encoding="utf-8")
    bridge.research.setCoordinates(str(csv))
    assert bridge.research.state["coordinatesCount"] == 1
    assert bridge.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {"point_mode": "provided_coordinates"})
    spin(qt_app, lambda: bridge.analysis["hasResult"])
    assert bridge.research.state["counts"] == {"TED": 1}
    assert bridge.research.exportResult(str(tmp_path))
    saved = json.loads((Path(bridge.research.state["exportPath"]) / "result.json").read_text(encoding="utf-8"))
    assert saved["predictions"][0]["x"] == 256
    assert saved["human_verified"] is False
    bridge.pipeline.set_source(None)
    assert not bridge.research.state["points"] and bridge.research.state["coordinatesCount"] == 0
    assert not bridge.research.exportResult(str(tmp_path))


def test_real_qml_run_button_results_overlay_and_export(qt_app, tmp_path):
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    bridge.pipeline.adapter = DesktopResearchAdapter(None, Classifier())
    bridge.pipeline.invalidate()
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    try:
        source = create_source(tmp_path)
        invoke(window, "selectImagePath", source.path)
        spin(qt_app, lambda: state.property("hasLoadedImage") and not state.property("loading"))
        state.setProperty("analysisScope", "FULL_IMAGE")
        run = window.findChild(QObject, "runAction")
        assert run.property("enabled")
        invoke(run, "trigger")
        spin(qt_app, lambda: bridge.analysis["hasResult"])
        invoke(window, "openInspectorTab", 2)
        qt_app.processEvents()
        assert bridge.research.state["total"] == 1
        assert window.findChild(QObject, "researchModelStatus").property("text") == "연구 모델 연결됨"
        overlay = window.findChild(QObject, "analysisOverlay")
        assert overlay.property("visible")
        assert window.findChild(QObject, "analysisExportButton").property("enabled")
        assert not warnings, "\n".join(warnings)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()
