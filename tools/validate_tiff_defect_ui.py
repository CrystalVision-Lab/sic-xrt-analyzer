"""Explicit TIFF viewer-only regression: no detector, inference or experiment import."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from validate_defect_result_ui import invoke

from sic_xrt_analyzer.ui.prepared_view import PreparedView


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    QQuickStyle.setStyle('Basic')
    s = Session.__new__(Session)
    report = {'files': [], 'manual_mouse_acceptance': 'PENDING'}
    paint = PreparedView.paint
    try:
        with patch.object(PreparedView, 'paint', lambda item, painter: s.paint(paint, item, painter)):
            Session.__init__(s, app, args.output)
            s.window.setTitle('XRT-RESULT-TD-03 TIFF viewer-only QA')
            s.window.raise_()
            s.window.requestActivate()
            for number, original in enumerate(args.image, 1):
                original = original.resolve()
                before = digest(original)
                row = {'file': original.name, 'sha_before': before}
                report['files'].append(row)
                row['open_s'] = s.open(original)
                assert s.bridge.pipeline.adapter is None
                assert not s.ui.property('canAnalyze')
                c = s.bridge.experiments
                # An explicit attempt must be rejected before bundle file access.
                c.load(str(args.output / 'does-not-exist'))
                assert not c.loading and not c.rows and '3D' in c.error
                invoke(s.window, 'requestContext', 'result', 'MANUAL')
                assert not s.item('importExperiment').isVisible()
                assert not s.item('resultTotal').isVisible()
                invoke(s.window, 'requestContext', 'viewer', 'MANUAL')
                row['pages'] = [1]
                for page in (s.bridge.original_source.metadata.page_count // 2, s.bridge.original_source.metadata.page_count - 1):
                    assert s.bridge.requestPage(page)
                    spin(app, lambda page=page: s.bridge.original_source.page_index == page and not s.bridge.stack_viewer.busy, 180)
                    assert s.viewer.isVisible() and not c.rows
                    assert s.bridge.pipeline.result is None
                    assert not s.item('geometryOverlay').isVisible()
                    row['pages'].append(page + 1)
                assert s.window.grabWindow().save(str(args.output / f'{number}-viewer.png'))
                invoke(s.window, 'closeImage')
                assert not c.rows and not s.bridge.original_source
                row['sha_after'] = digest(original)
                assert row['sha_after'] == before
                row.update(status='PASS', inference_runs=0, experiment_blocked=True)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            assert not s.warnings, s.warnings
            report.update(status='PASS', qml_warnings=s.warnings)
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if hasattr(s, 'window'):
            s.close()


if __name__ == '__main__':
    main()
