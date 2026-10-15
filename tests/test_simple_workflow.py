"""Source-bound results, progressive rendering and optional independent annotations."""

from pathlib import Path
from threading import Event

import numpy as np
import tifffile
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from test_analysis_pipeline import TestAdapter, spin

from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    AnalysisRequest,
    AnalysisScope,
    AnalysisState,
    Detection,
    Geometry,
    GeometryKind,
)
from sic_xrt_analyzer.analysis.pipeline import AnalysisPipeline
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider

pytest_plugins = ("test_toolbar",)


def original(tmp_path, name="source.tif"):
    path = tmp_path / name
    tifffile.imwrite(path, np.full((512, 512), 45000, dtype="uint16"))
    return OriginalImageSource(path)


def test_result_cache_rebinds_reader_and_rejects_new_model_or_identity(
    qt_app, tmp_path
):
    source = original(tmp_path)
    adapter = TestAdapter()
    version = adapter.model_version
    pipeline = AnalysisPipeline(adapter)
    try:
        pipeline.set_source(source)
        pipeline.start(
            AnalysisRequest(
                source,
                AnalysisScope.FULL_IMAGE,
                adapter.model_id,
                adapter.model_version,
            )
        )
        spin(qt_app, lambda: pipeline.state == AnalysisState.COMPLETED)
        ident = pipeline.result.analysis_id
        points = pipeline.result.detections
        pipeline.set_source(None)
        assert pipeline.result is None
        rebound = OriginalImageSource(source.path)
        pipeline.set_source(rebound)
        assert (
            pipeline.result.analysis_id == ident
            and pipeline.result.detections == points
        )
        assert pipeline.result.request.source is rebound
        adapter.model_version = "other"
        pipeline.set_source(rebound)
        assert pipeline.result is None
        adapter.model_version = version
        tifffile.imwrite(source.path, np.full((512, 512), 123, dtype="uint16"))
        pipeline.set_source(OriginalImageSource(source.path))
        assert pipeline.result is None
        assert len(pipeline._cache) <= 8
    finally:
        pipeline.shutdown()


class ProgressAdapter(TestAdapter):
    def __init__(self, gate):
        super().__init__(gate=gate)

    def analyze_source(self, request, token):
        detection = Detection(
            "live", 0, "BPD", 0.8, Geometry(GeometryKind.POINT, ((100, 200),))
        )
        token.report(stage="후보 분석", completed=1, total=2, detections=[detection])
        while not self.gate.wait(0.005):
            token.check()
        token.check()
        return AdapterOutput((detection,))


def test_live_candidates_are_discarded_on_cancel_and_file_switch(qt_app, tmp_path):
    gate = Event()
    adapter = ProgressAdapter(gate)
    pipeline = AnalysisPipeline(adapter)
    source = original(tmp_path)
    try:
        pipeline.set_source(source)
        pipeline.start(
            AnalysisRequest(
                source,
                AnalysisScope.FULL_IMAGE,
                adapter.model_id,
                adapter.model_version,
            )
        )
        spin(qt_app, lambda: len(pipeline.live_detections) == 1)
        assert pipeline.result is None and pipeline.progress["completed"] == 1
        pipeline.set_source(original(tmp_path, "other.tif"))
        gate.set()
        qt_app.processEvents()
        assert not pipeline.live_detections and pipeline.result is None
    finally:
        gate.set()
        pipeline.shutdown()


def test_roi_layers_are_independent_and_source_bound(qt_app, tmp_path, bridge_factory):
    bridge = bridge_factory(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    )
    a = original(tmp_path)
    b = original(tmp_path, "other.tif")
    bridge.original_source = a
    bridge.pipeline.set_source(a)
    bridge.displayLayers.add(10, 20, 100, 80)
    bridge.displayLayers.add(120, 100, 30, 40)
    rows = bridge.displayLayers.rows
    ident = rows[0]["id"]
    bridge.displayLayers.toggle(ident, False)
    assert not rows[0]["visible"] and rows[1]["visible"]
    bridge.original_source = b
    bridge.pipeline.set_source(b)
    assert bridge.displayLayers.rows == []
    bridge.original_source = a
    bridge.pipeline.set_source(a)
    assert (
        len(bridge.displayLayers.rows) == 2 and bridge.displayLayers.rows[0]["x"] == 10
    )


def test_folder_map_reads_images_and_provider_without_project(
    qt_app, tmp_path, bridge_factory
):
    from PIL import Image

    Image.new("RGB", (80, 60), (30, 40, 50)).save(tmp_path / "one.jpg")
    tifffile.imwrite(tmp_path / "two.tif", np.full((70, 60), 50000, dtype="uint16"))
    tifffile.imwrite(
        tmp_path / "stack.tif",
        np.ones((4, 32, 32), dtype="uint16"),
        photometric="minisblack",
    )
    bridge = bridge_factory(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    )
    bridge.folderMap.open(str(tmp_path))
    spin(qt_app, lambda: not bridge.folderMap.state["busy"])
    assert (
        len(bridge.folderMap.state["rows"]) == 2
        and len(bridge.provider.folder_images) == 2
    )
    assert bridge.projects.project is None


def test_empty_viewer_has_no_analysis_panel_and_3d_navigation(qt_app, tmp_path):
    from PySide6.QtQuickControls2 import QQuickStyle

    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(
        provider, engine, QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    )
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda rows: warnings.extend(r.toString() for r in rows))
    engine.load(
        QUrl.fromLocalFile(
            str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")
        )
    )
    try:
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        qt_app.processEvents()
        assert not window.findChild(QObject, "imagePrepareAnalysis").property("visible")
        assert not window.findChild(QObject, "inspectorPanel").property("visible")
        assert window.findChild(QObject, "analysisDialog") is not None
        assert not warnings, "\n".join(warnings)
    finally:
        bridge.waitForLoads()
        engine.deleteLater()
        qt_app.processEvents()


def test_optional_report_stores_sha_roi_without_changing_prediction(
    qt_app, tmp_path, bridge_factory, monkeypatch
):
    import hashlib
    import json

    from test_desktop_research import create_jpeg_source
    from test_result_explorer import ManyCandidates

    monkeypatch.setenv("SIC_XRT_REPORT_DIR", str(tmp_path / "reports"))
    bridge = bridge_factory(
        settings=QSettings(str(tmp_path / "report.ini"), QSettings.IniFormat)
    )
    bridge.pipeline.adapter = ManyCandidates()
    source = create_jpeg_source(tmp_path)
    assert bridge.openImage(QUrl.fromLocalFile(source.path).toString())["ok"]
    assert bridge.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
    spin(qt_app, lambda: bridge.analysis["hasResult"])
    before = bridge.pipeline.result
    bridge.research.selectCandidate("candidate_000000")
    bridge.reports.submit("영역이 다름", "QA", 30, 40, 100, 120)
    spin(qt_app, lambda: not bridge.reports.state["busy"])
    assert not bridge.reports.state["error"]
    record = json.loads(Path(bridge.reports.state["saved"]).read_text(encoding="utf-8"))
    assert record["roi"] == [30, 40, 100, 120]
    assert (
        record["source_sha256"]
        == hashlib.sha256(Path(source.path).read_bytes()).hexdigest()
    )
    assert record["approval"] == "UNVERIFIED" and record["candidate"]["type"] == "BPD"
    assert (
        bridge.pipeline.result is before and bridge.feedback.state["eventsCount"] == 0
    )


def test_bpd_area_is_separate_from_original_classification_and_scores(tmp_path):
    from test_bpd_structure import source_for
    from test_desktop_research import Classifier

    from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
    from sic_xrt_analyzer.analysis.model_adapter import CancellationToken

    source, _ = source_for(tmp_path, "straight", rgb=True, offset=(64, 64))
    adapter = DesktopResearchAdapter(None, Classifier())
    adapter.classifier.predict = lambda patches: np.tile(
        np.array([0.8, 0.1, 0.1]), (len(patches), 1)
    )
    params = {
        "point_mode": "provided_coordinates",
        "points": [{"x": 144, "y": 144, "point_id": "QA"}],
        "include_regions": True,
    }
    request = AnalysisRequest(
        source,
        AnalysisScope.FULL_IMAGE,
        adapter.model_id,
        adapter.model_version,
        parameters=params,
    )
    output = adapter.analyze_source(request, CancellationToken())
    from dataclasses import replace

    plain = adapter.analyze_source(
        replace(request, parameters={**params, "include_regions": False}),
        CancellationToken(),
    )
    a, b = output.detections[0], plain.detections[0]
    assert a.metadata["bpd_region"] and not b.metadata["bpd_region"]
    assert (
        a.geometry == b.geometry
        and a.class_name == b.class_name
        and a.confidence == b.confidence
    )
    assert a.metadata["scores"] == b.metadata["scores"]
    region = adapter._region(
        source, {"x": 144, "y": 144, "cx": 144, "cy": 144}, CancellationToken()
    )
    assert len(region) >= 3 and all(0 <= x < source.metadata.width and 0 <= y < source.metadata.height for x, y in region)
    # This fixture contains a 120px bright line, not a line wider than 128px.
    assert max(x for x, _ in region) - min(x for x, _ in region) >= 120


def test_optional_area_error_does_not_discard_classification(tmp_path, monkeypatch):
    from test_bpd_structure import source_for
    from test_desktop_research import Classifier

    from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
    from sic_xrt_analyzer.analysis.model_adapter import CancellationToken

    source, _ = source_for(tmp_path, "straight", rgb=True, offset=(64, 64))
    adapter = DesktopResearchAdapter(None, Classifier())
    adapter.classifier.predict = lambda patches: np.tile(
        np.array([0.8, 0.1, 0.1]), (len(patches), 1)
    )
    params = {
        "point_mode": "provided_coordinates",
        "points": [{"x": 144, "y": 144}],
        "include_regions": True,
    }
    request = AnalysisRequest(
        source,
        AnalysisScope.FULL_IMAGE,
        adapter.model_id,
        adapter.model_version,
        parameters=params,
    )

    def fail(*args):
        raise ValueError("synthetic irregular region")

    monkeypatch.setattr(adapter, "_region", fail)
    result = adapter.analyze_source(request, CancellationToken())
    assert len(result.detections) == 1 and result.detections[0].class_name == "BPD"
    assert result.detections[0].metadata["region_error"] == "ValueError"
    assert result.detections[0].geometry.points == ((144, 144),)


def test_polygon_report_and_layer_visibility_preserve_original_roi(
    workbench, tmp_path, monkeypatch
):
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from test_result_explorer import ManyCandidates
    from test_result_ux import analyzed
    from test_ui_analysis_contract import invoke

    monkeypatch.setenv("SIC_XRT_REPORT_DIR", str(tmp_path / "reports"))
    w = workbench
    analyzed(w, ManyCandidates())
    w.bridge.research.selectCandidate("candidate_000000")
    w.bridge.workbench.gesture("Polygon", [[40, 40], [150, 40], [150, 150], [40, 150]])
    original = w.bridge.roi_manager.records[0]
    w.window.grabWindow()
    QTest.qWait(35)
    assert not w.state.property("hasRoi")
    w.click("layerTools")
    w.click("addRoiLayer")
    layer = w.bridge.displayLayers.rows[0]
    assert (
        layer["paths"] == [list(path) for path in original.paths]
        or tuple(tuple(tuple(p) for p in path) for path in layer["paths"])
        == original.paths
    )
    assert not w.state.property("roiLayerVisible")
    w.bridge.displayLayers.toggle(layer["id"], False)
    assert not w.item("importedRoiOverlay").property("layerVisible")
    assert not w.item("annotationLayers").property("rows")[0]["visible"]
    QTest.keyClick(w.window, Qt.Key_Escape)
    invoke(w.window, "openContext", "result")
    w.window.grabWindow()
    QTest.qWait(35)
    w.click("reportCandidate")
    w.click("submitReport")
    spin(w.app, lambda: not w.bridge.reports.state["busy"])
    assert not w.bridge.reports.state["error"]
    report = json.loads(
        Path(w.bridge.reports.state["saved"]).read_text(encoding="utf-8")
    )
    assert report["roi_geometry"]["kind"] == "polygon"
    assert (
        tuple(tuple(tuple(p) for p in path) for path in report["roi_geometry"]["paths"])
        == original.paths
    )
    assert w.bridge.roi_manager.records[0] is original
