"""Continuous-session RC regression with explicitly synthetic inputs/adapter."""
import json
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_desktop_research import create_source
from test_result_ux import DistributedCandidates
from test_roi_ux import draw
from test_ui_analysis_contract import invoke

pytest_plugins = ('test_toolbar',)


@pytest.mark.parametrize('size', [(1100,700),(1440,900)])
def test_continuous_analysis_result_roi_export_and_file_switch(workbench, size):
    w = workbench
    w.window.resize(*size)
    w.bridge.pipeline.adapter = DistributedCandidates()
    rgb = create_source(w.path.parent)
    for _cycle in range(3):
        w.open(rgb.path)
        assert not w.bridge.research.state['points']
        assert not w.bridge.roi_manager.records
        w.click('imagePrepareAnalysis')
        w.state.setProperty('analysisScope','FULL_IMAGE')
        w.click('contextRunAnalysis')
        spin(w.app,lambda:w.bridge.analysis['hasResult'])
        assert w.panel.property('requestedContext') == 'result'
        original = w.bridge.pipeline.result
        assert w.bridge.research.exportResult(str(w.path.parent))
        first = json.loads((Path(w.bridge.research.export_path)/'result.json').read_text(encoding='utf8'))
        for kind,total in [('BPD',245),('TED',1398),('TSD',1303),('ALL',2946)]:
            w.click('resultFilter'+kind)
            assert w.bridge.research.state['filteredTotal'] == total
            assert len(w.item('analysisOverlay').property('points')) == total
            w.click('nextCandidate'); w.click('nextCandidate'); w.click('previousCandidate')
            assert w.bridge.pipeline.result is original
        assert w.bridge.research.exportResult(str(w.path.parent))
        second = json.loads((Path(w.bridge.research.export_path)/'result.json').read_text(encoding='utf8'))
        assert first == second
        choose(w,'roi'); w.click('roiSpecifyArea'); draw(w)
        region = w.bridge.pipeline.current_roi
        assert region and w.bridge.pipeline.result is original
        choose(w,'analysis'); w.state.setProperty('analysisScope','ROI')
        w.click('contextRunAnalysis'); spin(w.app,lambda:w.bridge.analysis['hasResult'])
        assert w.bridge.pipeline.result.roi == region
        # A genuinely different source must clear old results and automatic ROI.
        w.open(w.path)
        assert not w.bridge.research.state['points']
        assert not w.state.property('hasRoi')
        assert not w.bridge.analysis['hasResult']
        assert w.panel.property('requestedContext') == 'image'
        QTest.qWait(30)
    invoke(w.window,'closeImage')
    assert not w.state.property('hasImage')


def test_invalid_open_recovers_without_reusing_result_or_coordinates(workbench):
    w = workbench
    source = create_source(w.path.parent)
    w.bridge.pipeline.adapter = DistributedCandidates()
    w.open(source.path)
    choose(w,'analysis'); w.click('contextRunAnalysis')
    spin(w.app,lambda:w.bridge.analysis['hasResult'])
    old_source = w.bridge.original_source
    invoke(w.window,'selectImagePath',str(w.path.parent/'missing-original.tif'))
    spin(w.app,lambda:not w.state.property('opening'))
    assert w.state.property('loadError')
    assert w.bridge.original_source is old_source
    assert not w.bridge.research.state['points']
    w.open(source.path)
    assert not w.state.property('loadError')
    choose(w,'analysis'); w.click('contextRunAnalysis')
    spin(w.app,lambda:w.bridge.analysis['hasResult'])
    assert w.bridge.research.state['total'] == 2946
