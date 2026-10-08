"""Metadata/backend agreement, no I/O, stale-state recovery and real QML Run gates."""
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtQml import QQmlExpression, qmlContext
from test_analysis_pipeline import TestAdapter, spin
from test_context_panel import choose
from test_desktop_research import create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import (
    AnalysisException,
    AnalysisRequest,
    AnalysisScope,
)
from sic_xrt_analyzer.analysis.input_preflight import input_preflight
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

pytest_plugins = ('test_toolbar',)


def tiff_source(folder, dtype='uint8', channels=3):
    path = folder / f'{dtype}-{channels}.tif'
    shape = (32, 48) if channels == 1 else (32, 48, channels)
    tifffile.imwrite(path, np.zeros(shape, dtype=dtype), photometric='minisblack' if channels == 1 else 'rgb')
    return OriginalImageSource(path)


@pytest.mark.parametrize('dtype,channels,reasons', [
    ('uint8', 3, []), ('uint16', 1, ['UNSUPPORTED_DTYPE', 'UNSUPPORTED_CHANNEL_COUNT']),
    ('uint8', 1, ['UNSUPPORTED_CHANNEL_COUNT']), ('uint16', 3, ['UNSUPPORTED_DTYPE']),
    ('uint8', 4, ['UNSUPPORTED_CHANNEL_COUNT']),
])
def test_preflight_matches_authoritative_backend_without_extension_rules(tmp_path, dtype, channels, reasons):
    source = tiff_source(tmp_path, dtype, channels)
    adapter = ManyCandidates()
    request = AnalysisRequest(source, AnalysisScope.FULL_IMAGE, adapter.model_id, adapter.model_version)
    result = input_preflight(adapter, source)
    assert result['reasonCodes'] == reasons
    assert result['isCompatible'] == (not reasons)
    assert result['currentInput']['dtype'] == dtype and result['currentInput']['channels'] == channels
    assert result['currentInput']['sourceKind'] == 'TIFF'
    if reasons:
        with pytest.raises(AnalysisException) as caught:
            adapter.input_contract.validate(request)
        assert caught.value.error.code == 'INVALID_INPUT'
    else:
        adapter.input_contract.validate(request)


@pytest.mark.parametrize('case,code', [('no-source', 'SOURCE_NOT_READY'), ('no-model', 'MODEL_NOT_AVAILABLE'), ('loading', 'SOURCE_NOT_READY')])
def test_unknown_is_not_a_format_rejection(tmp_path, case, code):
    source = tiff_source(tmp_path, 'uint16', 1)
    result = input_preflight(None if case == 'no-model' else ManyCandidates(),
                             None if case == 'no-source' else source, waiting=case == 'loading')
    assert result['state'] == 'UNKNOWN' and not result['isCompatible']
    assert result['reasonCodes'] == [code]
    assert '지원하지' not in result['message']
    if case == 'loading':
        assert result['currentInput'] == {}  # Previous-file metadata cannot look current.


def test_missing_contract_fails_closed(tmp_path):
    source = tiff_source(tmp_path)
    adapter = SimpleNamespace(available=True, input_contract=None)
    result = input_preflight(adapter, source)
    assert result['state'] == 'ERROR' and not result['isCompatible']
    assert result['reasonCodes'] == ['MODEL_CONTRACT_UNAVAILABLE']


def test_metadata_only_read_only_and_future_model_contract(tmp_path, monkeypatch):
    source = tiff_source(tmp_path, 'uint16', 1)
    identity, meta = source.identity, source.metadata
    def forbidden(*args, **kwargs):
        pytest.fail('Preflight must not read headers/pixels or invoke inference')
    monkeypatch.setattr(tifffile, 'TiffFile', forbidden)
    monkeypatch.setattr(OriginalImageSource, 'read_region', forbidden)
    adapter = ManyCandidates()
    monkeypatch.setattr(adapter, 'analyze_source', forbidden)
    assert input_preflight(adapter, source)['state'] == 'INCOMPATIBLE'
    adapter.input_contract = TestAdapter.input_contract  # Existing gray16 contract; no model ID branch.
    assert input_preflight(adapter, source)['state'] == 'COMPATIBLE'
    assert source.identity == identity and source.metadata is meta


def test_existing_jpeg_decoded_metadata_is_the_truth(tmp_path):
    path = tmp_path/'encoded-gray.jpg'
    Image.fromarray(np.zeros((48, 64), np.uint8)).save(path)
    source = JpegImageSource(path)
    # The unchanged JPEG reader already publishes/decodes RGB8. Preflight does
    # not infer channels from a suffix or add another grayscale conversion.
    assert source.read_region(0, 0, 16, 16).shape == (16, 16, 3)
    result = input_preflight(ManyCandidates(), source)
    assert result['isCompatible'] and result['currentInput']['channels'] == source.metadata.channels == 3


class RecordingAdapter(ManyCandidates):
    def __init__(self):
        super().__init__()
        self.requests = []

    def analyze_source(self, request, token):
        self.requests.append(request)
        return super().analyze_source(request, token)


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
@pytest.mark.parametrize('scope', ['FULL_IMAGE', 'ROI'])
def test_uint16_shared_action_gate_and_other_tools_remain_available(workbench, size, scope):
    w = workbench
    adapter = RecordingAdapter()
    w.bridge.pipeline.adapter = adapter
    w.bridge.pipeline.invalidate()
    w.window.resize(*size)
    spin(w.app, lambda: w.panel.x()+w.panel.width() <= w.window.width()+1)
    choose(w, 'analysis')
    w.state.setProperty('analysisScope', scope)
    if scope == 'ROI':
        w.state.setProperty('roiStartX', .1); w.state.setProperty('roiStartY', .1)
        w.state.setProperty('roiEndX', .5); w.state.setProperty('roiEndY', .5)
        w.state.setProperty('hasRoi', True)
    w.app.processEvents()
    before = w.bridge.original_source.identity
    assert w.state.property('generalReady') and not w.state.property('canAnalyze')
    assert w.state.property('inputCompatibilityState') == 'INCOMPATIBLE'
    for name in ('contextRunAnalysis', 'menuRunAnalysis', 'runAction'):
        assert not w.item(name).property('enabled'), name
    w.same_action('contextRunAnalysis', 'menuRunAnalysis')
    invoke(w.item('runAction'), 'trigger')
    w.app.processEvents()
    assert not adapter.requests and w.bridge.pipeline.error is None
    assert '16비트 단일 채널' in w.item('analysisInputSummary').property('text')
    requirement = w.item('analysisModelInputRequirement')
    assert requirement.property('visible') and '8비트 RGB' in requirement.property('text')
    assert '현재 입력은 이 모델에서 지원하지 않습니다' in w.item('analysisReadinessReasons').property('text')
    accessible = QQmlExpression(qmlContext(requirement), requirement, 'Accessible.name')
    description = accessible.evaluate()[0]
    assert not accessible.hasError()
    assert '16비트 단일 채널' in description and '8비트 RGB' in description
    for name in ('analysisInputSummary', 'analysisModelInputRequirement', 'contextRunAnalysis'):
        item = w.item(name); p = item.mapToScene(QPointF())
        assert 0 <= p.y() and p.y()+item.height() <= size[1]-28, name
    for name in ('roiAction', 'zoomInAction', 'actualSizeAction', 'importRoisAction'):
        assert w.item(name).property('enabled'), name
    w.bridge.newPointRoi()
    assert len(w.bridge.roi_manager.records) == 1
    assert w.state.property('stackFeaturesVisible')
    assert w.bridge.setDisplayRange(0, 10000)
    spin(w.app, lambda: not w.bridge.stack_viewer.busy)
    assert w.bridge.original_source.identity == before
    invoke(w.window, 'imagejTools')  # Incompatibility does not gate ImageJ UI.
    assert w.panel.property('requestedContext') == 'analysis'


def test_file_loading_model_and_close_recompute_without_stale_compatibility(workbench):
    w = workbench
    rgb = create_source(w.path.parent)
    w.open(rgb.path)
    assert w.state.property('canAnalyze')
    w.state.setProperty('opening', True)
    assert w.state.property('inputCompatibilityState') == 'UNKNOWN'
    assert not w.state.property('canAnalyze')
    w.state.setProperty('opening', False)
    w.open(w.path)
    assert w.state.property('inputCompatibilityState') == 'INCOMPATIBLE'
    gray = TestAdapter()
    w.bridge.pipeline.adapter = gray; w.bridge.pipeline.invalidate(); w.app.processEvents()
    assert w.state.property('inputCompatibilityState') == 'COMPATIBLE'
    w.bridge.pipeline.adapter = None; w.bridge.pipeline.invalidate(); w.app.processEvents()
    assert not w.state.property('canAnalyze')
    w.bridge.pipeline.adapter = RecordingAdapter(); w.bridge.pipeline.invalidate(); w.app.processEvents()
    assert w.state.property('inputCompatibilityState') == 'INCOMPATIBLE'
    w.open(rgb.path)
    assert w.state.property('canAnalyze')
    invoke(w.window, 'closeImage')
    assert w.state.property('inputCompatibilityState') == 'UNKNOWN' and not w.state.property('canAnalyze')


def test_heterogeneous_page_uses_current_page_metadata(workbench):
    w = workbench; path = w.path.parent/'mixed-pages.tif'
    with tifffile.TiffWriter(path) as writer:
        writer.write(np.zeros((64, 80, 3), np.uint8), photometric='rgb')
        writer.write(np.zeros((64, 80), np.uint16), photometric='minisblack')
    w.open(path)
    assert w.state.property('inputCompatibilityState') == 'COMPATIBLE'
    assert w.bridge.requestPage(1)
    assert not w.state.property('canAnalyze')
    spin(w.app, lambda: w.bridge.stack_viewer.frame.source.page_index == 1 and not w.bridge.stack_viewer.busy)
    w.app.processEvents()
    current = w.bridge.analysis['inputPreflight']['currentInput']
    assert current['currentPage'] == 1 and current['dtype'] == 'uint16' and current['channels'] == 1
    assert w.state.property('inputCompatibilityState') == 'INCOMPATIBLE'


@pytest.mark.parametrize('scope', ['FULL_IMAGE', 'ROI'])
def test_backend_direct_invalid_request_is_rejected_before_inference(workbench, scope):
    w = workbench; adapter = RecordingAdapter(); w.bridge.pipeline.adapter = adapter
    assert not w.bridge.requestAnalysis(scope, 0, 0, 256, 256, {})
    assert w.bridge.analysis['errorCode'] == 'INVALID_INPUT' and not adapter.requests
    assert w.bridge.pipeline._active is None


@pytest.mark.parametrize('scope', ['FULL_IMAGE', 'ROI'])
def test_compatible_one_click_full_and_roi_requests_keep_contract(workbench, scope):
    w = workbench; adapter = RecordingAdapter(); w.bridge.pipeline.adapter = adapter
    w.open(create_source(w.path.parent).path)
    choose(w, 'analysis'); w.state.setProperty('analysisScope', scope)
    if scope == 'ROI':
        w.state.setProperty('roiStartX', 0); w.state.setProperty('roiStartY', 0)
        w.state.setProperty('roiEndX', 1); w.state.setProperty('roiEndY', 1)
        w.state.setProperty('hasRoi', True)
    w.app.processEvents()
    assert w.state.property('canAnalyze') and w.item('contextRunAnalysis').property('enabled')
    w.click('contextRunAnalysis')
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    assert len(adapter.requests) == 1 and adapter.requests[0].scope.value == scope
    assert (adapter.requests[0].roi is not None) == (scope == 'ROI')
    assert len(w.bridge.pipeline.result.detections) == 231
    assert w.panel.property('requestedContext') == 'result'


def test_model_contract_missing_ui_error_has_no_false_scope_warning(workbench):
    w = workbench; adapter = RecordingAdapter(); adapter.input_contract = None
    w.bridge.pipeline.adapter = adapter; w.bridge.pipeline.invalidate(); choose(w, 'analysis')
    assert w.state.property('inputCompatibilityState') == 'ERROR'
    reasons = w.item('analysisReadinessReasons').property('text')
    assert '입력 계약을 확인할 수 없습니다' in reasons and '분석 범위를 지원하지' not in reasons
    assert not w.item('runAction').property('enabled')
