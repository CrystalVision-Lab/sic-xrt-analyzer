import os
import time
from dataclasses import FrozenInstanceError, replace
from threading import Event, get_ident

import numpy as np
import pytest
import tifffile

from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    AnalysisRequest,
    AnalysisScope,
    AnalysisState,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
    Region,
)
from sic_xrt_analyzer.analysis.model_adapter import (
    ModelInputContract,
    ModelOutputContract,
)
from sic_xrt_analyzer.analysis.pipeline import AnalysisPipeline
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource


class TestAdapter:
    __test__ = False
    model_id, model_name, model_version, available, device = "test-only", "Test", "1", True, "test"
    input_contract = ModelInputContract(tuple(AnalysisScope), (1,), ("uint16",),
                                        "native", "none", "grayscale", "preserve uint16")
    output_contract = ModelOutputContract(tuple(GeometryKind), CoordinateSpace.INPUT_LOCAL)

    def __init__(self, mode="success", gate=None):
        self.mode, self.gate = mode, gate
        self.entered = Event()
        self.request = self.image = self.thread = None

    def analyze(self, image, request, cancellation_token):
        self.request, self.image, self.thread = request, image, get_ident()
        self.entered.set()
        if self.gate:
            while not self.gate.wait(.005):
                if self.mode != "noncooperative":
                    cancellation_token.check()
        if self.mode == "error":
            raise RuntimeError("private developer detail")
        geometries = [Geometry(GeometryKind.POINT, points=((100, 200),)),
                      Geometry(GeometryKind.BOUNDING_BOX, bbox=(10, 20, 30, 40)),
                      Geometry(GeometryKind.POLYGON, points=((1, 2), (3, 4), (5, 6))),
                      Geometry(GeometryKind.MASK, bbox=(2, 3, 10, 20),
                               mask_reference="test://mask", mask_encoding="test-only")]
        return AdapterOutput(tuple(Detection(str(i), None, None, None, g) for i, g in enumerate(geometries)),
                             {"count": 4}, {"normalization": "none"})


def spin(app, predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Background job did not reach the expected condition")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "original.tif"
    mapped = tifffile.memmap(path, shape=(2500, 1500), dtype="uint16", photometric="minisblack")
    mapped[:] = 51000
    mapped.flush()
    mapped._mmap.close()
    return OriginalImageSource(path)


@pytest.fixture
def controllers():
    items = []
    yield items
    for pipeline, gate in items:
        if gate:
            gate.set()
        pipeline.shutdown()


def controller(controllers, source, adapter):
    p = AnalysisPipeline(adapter)
    p.set_source(source)
    controllers.append((p, getattr(adapter, "gate", None)))
    return p


def request(source, **kwargs):
    return AnalysisRequest(source, AnalysisScope.ROI, "test-only", "1", Region(1000, 2000, 400, 400), **kwargs)


def test_completed_original_mapping_and_traceability(qt_app, controllers, source):
    adapter = TestAdapter()
    p = controller(controllers, source, adapter)
    assert p.state == AnalysisState.READY
    transitions = []
    p.changed.connect(lambda: transitions.append(p.state))
    req = request(source, parameters={"threshold": .5})
    assert p.start(req) and p.state == AnalysisState.RUNNING
    spin(qt_app, lambda: p.state == AnalysisState.COMPLETED)
    result = p.result
    assert AnalysisState.RUNNING in transitions and AnalysisState.COMPLETED in transitions
    assert adapter.thread != get_ident() and adapter.image.dtype == np.uint16
    assert adapter.image.shape == (400, 400) and np.all(adapter.image == 51000)
    assert result.detections[0].geometry.points == ((1100, 2200),)
    assert result.detections[1].geometry.bbox == (1010, 2020, 30, 40)
    assert result.detections[2].geometry.points[0] == (1001, 2002)
    assert result.detections[3].geometry.bbox == (1002, 2003, 10, 20)
    assert all(d.geometry.coordinate_space == CoordinateSpace.ORIGINAL for d in result.detections)
    assert result.analysis_id == req.analysis_id and result.source_identity == source.identity
    assert result.parameters == req.parameters and result.model_id == "test-only"
    assert result.model_version == "1" and result.scope == AnalysisScope.ROI and result.roi == req.roi
    assert result.duration > 0 and result.completed_at >= result.started_at >= req.created_at
    assert result.preprocessing["normalization"] == "none"
    p.set_current_roi(req.roi)
    assert not p.result_roi_mismatch
    p.set_current_roi(Region(0, 0, 10, 10))
    assert p.result_roi_mismatch and p.result is result


def test_request_snapshot_during_run(qt_app, controllers, source):
    gate = Event()
    adapter = TestAdapter(gate=gate)
    p = controller(controllers, source, adapter)
    params = {"nested": {"sizes": [1, 2]}}
    req = request(source, parameters=params)
    p.start(req)
    spin(qt_app, adapter.entered.is_set)
    params["nested"]["sizes"].append(3)
    p.set_current_roi(Region(0, 0, 1, 1))
    with pytest.raises(TypeError):
        req.parameters["nested"]["sizes"] = (3,)
    with pytest.raises(FrozenInstanceError):
        req.roi = None
    gate.set()
    spin(qt_app, lambda: p.state == AnalysisState.COMPLETED)
    assert p.result.roi == Region(1000, 2000, 400, 400)
    assert p.result.parameters["nested"]["sizes"] == (1, 2)
    assert p.result_roi_mismatch


@pytest.mark.parametrize("mode", ["success", "noncooperative"])
def test_cancel_ignores_late_result(qt_app, controllers, source, mode):
    gate = Event()
    adapter = TestAdapter(mode, gate)
    p = controller(controllers, source, adapter)
    p.start(request(source))
    spin(qt_app, adapter.entered.is_set)
    p.cancel()
    assert p.state == AnalysisState.CANCELED and p.error.code == "CANCELED"
    gate.set()
    spin(qt_app, lambda: not p._tasks)
    assert p.state == AnalysisState.CANCELED and p.result is None


def test_failure_is_safe_and_logged(qt_app, controllers, source, caplog):
    p = controller(controllers, source, TestAdapter("error"))
    p.start(request(source))
    spin(qt_app, lambda: p.state == AnalysisState.FAILED)
    assert p.error.code == "INFERENCE_FAILED"
    assert "private developer detail" in p.error.detail
    assert "private developer detail" not in p.error.message
    assert "private developer detail" in caplog.text
    assert not p.result.detections


def test_new_source_or_page_discards_old_completion(qt_app, controllers, source, tmp_path):
    gate = Event()
    adapter = TestAdapter("noncooperative", gate)
    p = controller(controllers, source, adapter)
    p.start(request(source))
    spin(qt_app, adapter.entered.is_set)
    new_path = tmp_path / "b.tif"
    with tifffile.TiffWriter(new_path) as writer:
        writer.write(np.zeros((10, 10), np.uint16))
        writer.write(np.ones((10, 10), np.uint16))
    p.set_source(OriginalImageSource(new_path, 1))
    gate.set()
    spin(qt_app, lambda: not p._tasks)
    assert p.state == AnalysisState.READY and p.result is None
    assert p.source.page_index == 1


def test_new_request_supersedes_old_run(qt_app, controllers, source):
    gate = Event()
    adapter = TestAdapter("noncooperative", gate)
    p = controller(controllers, source, adapter)
    first, second = request(source), request(source)
    p.start(first)
    spin(qt_app, adapter.entered.is_set)
    assert p.start(second)
    gate.set()
    spin(qt_app, lambda: p.state == AnalysisState.COMPLETED)
    assert p.result.analysis_id == second.analysis_id
    assert not p.start(second) and p.error.code == "INVALID_INPUT"


@pytest.mark.parametrize("during_run", [True, False])
def test_file_change_invalidates_job_or_result(qt_app, controllers, source, during_run):
    gate = Event() if during_run else None
    adapter = TestAdapter("noncooperative", gate)
    p = controller(controllers, source, adapter)
    p.start(request(source))
    spin(qt_app, adapter.entered.is_set if during_run else lambda: p.state == AnalysisState.COMPLETED)
    stat = os.stat(source.path)
    os.utime(source.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    p.refresh_source()
    assert p.state == AnalysisState.FAILED and p.error.code == "SOURCE_CHANGED"
    assert p.result is None and p.source is None
    if gate:
        gate.set()
        spin(qt_app, lambda: not p._tasks)
        assert p.result is None


def test_unavailable_and_input_contract_rejection(controllers, source):
    p = controller(controllers, source, None)
    assert p.state == AnalysisState.UNAVAILABLE
    assert not p.start(request(source)) and p.error.code == "MODEL_NOT_AVAILABLE"
    adapter = TestAdapter()
    adapter.input_contract = replace(adapter.input_contract, supported_scopes=(AnalysisScope.ROI,))
    p = controller(controllers, source, adapter)
    req = AnalysisRequest(source, AnalysisScope.FULL_IMAGE, "test-only", "1")
    assert not p.start(req) and p.error.code == "UNSUPPORTED_SCOPE"
    adapter.input_contract = replace(adapter.input_contract, accepted_dtypes=("uint8",))
    assert not p.start(request(source)) and p.error.code == "INVALID_INPUT"


def test_full_image_and_already_original_output(qt_app, controllers, source):
    adapter = TestAdapter()
    adapter.output_contract = replace(adapter.output_contract, coordinate_space=CoordinateSpace.ORIGINAL)
    def analyze(image, request, token):
        assert image.shape == (2500, 1500) and image.dtype == np.uint16
        return AdapterOutput((Detection("1", None, None, None,
                             Geometry(GeometryKind.POINT, points=((1100, 2200),),
                                      coordinate_space=CoordinateSpace.ORIGINAL)),))
    adapter.analyze = analyze
    p = controller(controllers, source, adapter)
    assert p.start(AnalysisRequest(source, AnalysisScope.FULL_IMAGE, "test-only", "1"))
    spin(qt_app, lambda: p.state == AnalysisState.COMPLETED)
    assert p.result.detections[0].geometry.points == ((1100, 2200),)


def test_contracts_reject_ambiguous_scope_and_invalid_output(qt_app, controllers, source):
    with pytest.raises(ValueError):
        AnalysisRequest(source, AnalysisScope.FULL_IMAGE, "test-only", "1", Region(0, 0, 1, 1))
    with pytest.raises(ValueError):
        AnalysisRequest(source, AnalysisScope.ROI, "test-only", "1")
    with pytest.raises(ValueError):
        request(source, parameters={"unsafe": object()})
    adapter = TestAdapter()
    adapter.analyze = lambda *args: AdapterOutput((Detection("1", None, None, None,
                                                 Geometry(GeometryKind.POINT, points=((401, 1),))),))
    p = controller(controllers, source, adapter)
    p.start(request(source))
    spin(qt_app, lambda: p.state == AnalysisState.FAILED)
    assert p.error.code == "INFERENCE_FAILED" and not p.result.detections
