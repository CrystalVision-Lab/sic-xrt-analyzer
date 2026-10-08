"""Read-only TD-11 checks with real local RGB/TIFF/model inputs; artifacts stay local.

QTest exercises application controls, not human Windows native file dialog clicks.
"""
import argparse
import json
from pathlib import Path

from PySide6.QtCore import QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle
from validate_rc_session import Session, digest, real_model_flow, stack_flow

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.analysis.input_preflight import input_preflight
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jpeg', type=Path, required=True)
    parser.add_argument('--tiff', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    for protected in (args.jpeg.resolve().parent, args.tiff.resolve().parent, args.model.resolve()):
        if args.output.is_relative_to(protected):
            parser.error('Output must be separate from read-only source/model directories')
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    QQuickStyle.setStyle('Basic')
    session = Session(app, args.output, Path('src/sic_xrt_analyzer/ui').resolve())
    bridge = session.bridge
    model_files = [args.model/'manifest.json', args.model/'model.onnx']
    original_hashes = {p.name: digest(p) for p in model_files}
    report = {'platform': app.platformName(), 'td10_status': 'PARTIAL / MITIGATED / REMAINS',
              'implicit_conversion_added': False, 'inference_preflight_observations': []}
    observed_ids = set()
    def observed():
        if bridge.pipeline.state == AnalysisState.RUNNING and bridge.pipeline._active:
            request = bridge.pipeline._active.request
            if request.analysis_id not in observed_ids:
                observed_ids.add(request.analysis_id)
                preflight = bridge.analysis['inputPreflight']
                assert preflight['state'] == 'COMPATIBLE', preflight
                report['inference_preflight_observations'].append({
                    'scope': request.scope.value, 'dtype': request.source.metadata.dtype,
                    'channels': request.source.metadata.channels, 'state': preflight['state']})
    bridge.pipeline.changed.connect(observed)
    try:
        report['real_rgb'] = real_model_flow(session, args.jpeg, args.model)
        rgb_preflight = bridge.analysis['inputPreflight']
        assert rgb_preflight['isCompatible'] and session.state.property('canAnalyze')
        report['rgb_preflight'] = rgb_preflight
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding='utf8'))['model_flow']
            same = (baseline['model']['hash'] == report['real_rgb']['model']['hash']
                    and baseline['sha256_before'] == report['real_rgb']['sha256_before'])
            report['baseline_source_model_match'] = same
            if same:
                assert baseline['total'] == report['real_rgb']['total']
                assert baseline['counts'] == report['real_rgb']['counts']
                report['full_counts_unchanged'] = True
                same_roi = baseline['roi'] == report['real_rgb']['roi']
                report['roi_geometry_matches_baseline'] = same_roi
                if same_roi:
                    assert baseline['roi_inference_count'] == report['real_rgb']['roi_inference_count']
                    report['roi_count_unchanged'] = True
        adapter = bridge.pipeline.adapter
        calls = []
        original_analyze = adapter.analyze_source
        def record_invalid_inference(request, token):
            calls.append(request.source.metadata.dtype)
            return original_analyze(request, token)
        adapter.analyze_source = record_invalid_inference
        session.open(args.tiff)
        session.choose('analysis')
        preflight = bridge.analysis['inputPreflight']
        assert preflight['state'] == 'INCOMPATIBLE'
        assert set(preflight['reasonCodes']) == {'UNSUPPORTED_DTYPE', 'UNSUPPORTED_CHANNEL_COUNT'}
        for scope in ('FULL_IMAGE', 'ROI'):
            session.state.setProperty('analysisScope', scope)
            session.state.setProperty('hasRoi', True)
            session.state.setProperty('roiStartX', .1); session.state.setProperty('roiStartY', .1)
            session.state.setProperty('roiEndX', .4); session.state.setProperty('roiEndY', .4)
            for name in ('runAction', 'contextRunAnalysis', 'menuRunAnalysis'):
                assert not session.item(name).property('enabled'), name
            assert QMetaObject.invokeMethod(session.item('runAction'), 'trigger')
            assert not calls and bridge.pipeline.error is None
        report['real_uint16_preflight'] = preflight
        report['uint16_inference_calls'] = len(calls)
        session.save_capture('uint16-incompatible-1100')
        report['real_stack_tools'] = stack_flow(session, args.tiff)
        assert not report['real_stack_tools']['run_enabled_for_uint16']
        assert not calls
        report['real_uint16_headers'] = []
        for path in sorted(args.tiff.parent.glob('*.tif')):
            source = OriginalImageSource(path)
            state = input_preflight(adapter, source)
            assert state['state'] == 'INCOMPATIBLE'
            report['real_uint16_headers'].append({'file': path.name, **state['currentInput'],
                                                  'state': state['state'], 'reasonCodes': state['reasonCodes']})
        assert not bridge.requestAnalysis('FULL_IMAGE', 0, 0, 0, 0, {})
        assert bridge.analysis['errorCode'] == 'INVALID_INPUT' and not calls
        report['backend_direct_invalid_input'] = 'PASS'
        for p in model_files:
            assert digest(p) == original_hashes[p.name]
        report['model_files_unchanged'] = True
        session.open(args.jpeg)
        assert bridge.analysis['inputPreflight']['isCompatible']
        # The deliberate uint16 ROI case left ROI scope selected. A new file
        # correctly clears its area; input compatibility alone is not readiness.
        report['recovery_preserved_scope'] = session.state.property('analysisScope')
        session.state.setProperty('analysisScope', 'FULL_IMAGE')
        assert session.state.property('canAnalyze')
        report['compatible_recovery'] = True
    finally:
        report['shutdown_seconds'] = session.close()
        report['qml_warnings'] = session.warnings
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    assert not session.warnings, session.warnings
    print(json.dumps({'status': 'PASS', 'full_total': report['real_rgb']['total'],
                      'full_counts': report['real_rgb']['counts'],
                      'roi_count': report['real_rgb']['roi_inference_count'],
                      'uint16_inference_calls': report['uint16_inference_calls'],
                      'real_tiff_headers': len(report['real_uint16_headers']),
                      'qml_warnings': len(report['qml_warnings'])}), flush=True)


if __name__ == '__main__':
    main()
