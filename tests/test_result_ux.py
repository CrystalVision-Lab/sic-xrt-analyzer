"""TD-05 real Result controls, shared selection/filter and immutable exports."""
import json
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QSignalSpy, QTest
from test_analysis_pipeline import spin
from test_context_panel import LifecycleAdapter, choose
from test_desktop_research import create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
)

pytest_plugins = ('test_toolbar',)


class DistributedCandidates(ManyCandidates):
    def analyze_source(self, request, token):
        rows = []
        for kind, count in [('BPD', 245), ('TED', 1398), ('TSD', 1303)]:
            index = ('BPD', 'TED', 'TSD').index(kind)
            for _ in range(count):
                i = len(rows)
                scores = [0.1, 0.1, 0.1]
                scores[index] = 0.8
                if i == 0:
                    scores = [0.6605, 0.3365, 0.003]
                rows.append(Detection(
                    f'candidate_{i:06d}', index, kind, scores[index],
                    Geometry(GeometryKind.POINT, ((80 + i % 15 * 24, 80 + i // 15 % 15 * 24),),
                             coordinate_space=CoordinateSpace.ORIGINAL),
                    {'point_id': f'source_{i:06d}', 'scores': scores, 'low_score': i % 5 == 0}))
        return AdapterOutput(tuple(rows), {'counts': {'BPD': 245, 'TED': 1398, 'TSD': 1303}}, {})


def analyzed(w, adapter=None):
    w.bridge.pipeline.adapter = adapter or DistributedCandidates()
    w.open(create_source(w.path.parent).path)
    w.click('imagePrepareAnalysis')
    w.click('contextRunAnalysis')
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    QTest.qWait(40)
    assert w.panel.property('requestedContext') == 'result'
    return w.bridge.research


def evaluate(w, code):
    expr = QQmlExpression(w.engine.rootContext(), w.state, code)
    value = expr.evaluate()[0]
    assert not expr.hasError(), expr.error().toString()
    return value


@pytest.mark.parametrize('kind,total', [('ALL', 2946), ('BPD', 245), ('TED', 1398), ('TSD', 1303)])
def test_summary_filter_navigation_and_overlay_share_state(workbench, kind, total):
    w = workbench
    r = analyzed(w)
    original = w.bridge.pipeline.result
    assert w.item('resultTotal').property('text') == '총 후보 2,946개'
    assert r.state['counts'] == {'BPD': 245, 'TED': 1398, 'TSD': 1303}
    for name, color in [('BPD', '#ffad42'), ('TED', '#50e0ee'), ('TSD', '#ff78c4')]:
        assert evaluate(w, f'resultPresentation.colorFor("{name}")') == color
        assert w.item('resultFilter' + name).property('text') == name + ' ' + f'{r.state["counts"][name]:,}'
    assert not r.state['selected']  # Preserve explicit first selection.
    w.click('resultFilter' + kind)
    assert r.state['filteredTotal'] == total
    assert '0 /' not in w.item('candidateIndex').property('text')
    assert w.item('emptyCandidateDetail').property('visible')
    w.click('nextCandidate')
    selected = r.state['selected']
    assert r.state['selectedIndex'] == 0
    assert w.item('candidateIndex').property('text') == '후보 1 / ' + f'{total:,}'
    assert w.item('selectedCandidateHeader').property('text') == f'후보 #{selected["number"]} · {selected["type"]}'
    assert evaluate(w, 'research.selected.id === research.displayRows[0].id') is True
    assert evaluate(w, 'research.filteredPoints.length') == total
    overlay = w.item('analysisOverlay')
    assert overlay.property('selected')['id'] == selected['id']
    assert len(overlay.property('points')) == total
    assert overlay.property('selectedOpacity') > overlay.property('candidateOpacity')
    if kind != 'ALL':
        assert all(p['type'] == kind for p in overlay.property('points'))
    w.click('nextCandidate')
    assert r.state['selectedIndex'] == 1
    w.click('previousCandidate')
    assert r.state['selectedIndex'] == 0
    assert w.bridge.pipeline.result is original
    assert len(original.detections) == 2946


def test_filter_retains_matching_selection_and_clears_excluded_selection(workbench):
    w = workbench
    r = analyzed(w)
    r.selectCandidate('candidate_000240')
    QTest.qWait(60)
    w.click('resultFilterBPD')
    assert r.state['selected']['id'] == 'candidate_000240'
    assert r.state['selectedIndex'] == 240 and r.state['page'] == 2
    assert w.item('candidateIndex').property('text') == '후보 241 / 245'
    assert w.item('candidateRow241').property('visible')
    w.click('resultFilterTED')
    assert r.state['selected'] == {} and r.state['thumbnailSource'] == ''
    assert not w.state.property('candidateRoiId')
    assert not w.item('analysisOverlay').property('selected')
    assert w.item('candidateIndex').property('text') == '후보 선택 전'
    assert w.item('emptyCandidateDetail').property('visible')
    w.click('nextCandidate')
    assert r.state['selected']['number'] == 246
    assert w.item('candidateIndex').property('text') == '후보 1 / 1,398'


@pytest.mark.parametrize('score,expected', [(0.6605, '66.1%'), (0.3365, '33.7%'), (0.003, '0.3%'), (1.0, '100%')])
def test_confidence_presentation_preserves_raw_values(workbench, score, expected):
    w = workbench
    assert evaluate(w, f'resultPresentation.confidence({score})') == expected
    assert evaluate(w, f'resultPresentation.raw({score})') == str(score).removesuffix('.0')


def test_detail_raw_score_export_and_research_controls_preserved(workbench, tmp_path):
    w = workbench
    r = analyzed(w)
    original = w.bridge.pipeline.result
    assert r.exportResult(str(tmp_path / 'before'))
    before = Path(r.state['exportPath'])
    snapshot = {p.name: p.read_bytes() for p in before.iterdir() if p.is_file()}
    w.click('nextCandidate')
    assert w.item('candidateConfidence').property('text') == '66.1%'
    w.click('candidateDetails')
    assert w.item('candidateDetailDialog').property('visible')
    assert w.item('rawScoreBPD').property('text') == 'BPD  66.1%   /   0.6605'
    assert w.item('rawScoreTED').property('text') == 'TED  33.7%   /   0.3365'
    assert w.item('rawScoreTSD').property('text') == 'TSD  0.3%   /   0.003'
    w.click('copyCandidate')
    assert 'X=80' in w.app.clipboard().text()
    QTest.keyClick(w.window, Qt.Key_Escape)
    w.click('resultOptions')
    assert w.item('resultOptionsDialog').property('visible')
    w.click('lowScoreFilter')
    assert r.state['filterLow'] and r.state['filteredTotal'] == 590
    w.click('lowScoreFilter')
    w.click('autoCandidateRoi')
    assert not w.state.property('autoCandidateRoi')
    w.click('autoCandidateRoi')
    assert w.state.property('autoCandidateRoi')
    w.item('candidateRoiSize').forceActiveFocus()
    QTest.keyClick(w.window, Qt.Key_Down)
    QTest.keyClick(w.window, Qt.Key_Return)
    QTest.qWait(40)
    assert w.state.property('candidateRoiSize') == 256
    w.click('resultLayerVisibility')
    assert not w.item('analysisOverlay').property('visible')
    w.click('resultLayerVisibility')
    search = w.item('candidateSearch')
    search.forceActiveFocus()
    for char in 'source_000240':
        QTest.keyClick(w.window, Qt.Key(ord(char.upper())))
    assert r.state['filteredTotal'] == 1 and not r.state['selected']
    QTest.keyClick(w.window, Qt.Key_Escape)
    assert w.item('resultFilterSummary').property('text').endswith('검색 적용')
    w.click('nextCandidate')
    assert r.state['selected']['number'] == 241
    w.click('resultRunInfo')
    assert w.item('resultInfoDialog').property('visible')
    QTest.keyClick(w.window, Qt.Key_Escape)
    assert r.exportResult(str(tmp_path / 'after'))
    after = Path(r.state['exportPath'])
    assert {p.name: p.read_bytes() for p in after.iterdir() if p.is_file()} == snapshot
    data = json.loads((after / 'result.json').read_text(encoding='utf-8'))
    assert len(data['predictions']) == 2946
    assert data['predictions'][0]['scores'] == [0.6605, 0.3365, 0.003]
    assert w.bridge.pipeline.result is original
    assert w.item('analysisExportButton').property('enabled')
    explorer = w.item('resultExplorer')
    signal_index = explorer.metaObject().indexOfSignal('exportRequested()')
    assert signal_index >= 0
    exported = QSignalSpy(explorer, explorer.metaObject().method(signal_index))
    assert exported.isValid()
    QTest.qWait(60)  # Settle the newly visible export-path footer layout.
    w.click('analysisExportButton')
    assert exported.count() == 1
    dialog = next(obj for obj in w.window.findChildren(type(w.state))
                  if obj.property('title') == '결과를 저장할 폴더')
    assert dialog.property('visible')
    invoke(dialog, 'reject')
    spin(w.app, lambda: not dialog.property('visible'))
    QTest.qWait(100)  # Let the native folder dialog release its window before engine disposal.


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_result_fixed_information_and_list_bounds(workbench, size):
    w = workbench
    w.window.resize(*size)
    r = analyzed(w)
    w.click('nextCandidate')
    for name in ('resultTotal', 'resultFilterBPD', 'candidateIndex', 'selectedCandidateHeader',
                 'candidateConfidence', 'candidateList', 'analysisExportButton', 'resultOptions'):
        item = w.item(name)
        p = item.mapToScene(QPointF())
        assert item.property('visible'), name
        assert 0 <= p.y() and p.y() + item.property('height') <= size[1] - 28, (name, p)
        assert 0 <= p.x() and p.x() + item.property('width') <= size[0], (name, p)
    assert w.item('candidateList').property('height') >= 80
    header_y = w.item('resultTotal').mapToScene(QPointF()).y()
    w.item('candidateList').setProperty('contentY', 1500)
    QTest.qWait(50)
    assert w.item('resultTotal').mapToScene(QPointF()).y() == header_y
    # Returning to a selected candidate reveals its list row.
    r.selectCandidate('candidate_000099')
    QTest.qWait(40)
    row = w.item('candidateRow100')
    assert row.mapToScene(QPointF()).y() >= w.item('candidateList').mapToScene(QPointF()).y() - 1
    w.click('nextCandidate')
    assert r.state['selected']['number'] == 101 and r.state['page'] == 1
    assert w.item('candidateRow101').property('visible')


def test_empty_zero_new_run_and_new_file_discard_stale_selection(workbench):
    w = workbench
    choose(w, 'result')
    assert w.item('resultLifecycleMessage').property('text') == '아직 분석 결과가 없습니다.'
    assert not w.item('candidateList').property('visible')
    r = analyzed(w)
    w.click('resultFilterBPD')
    w.click('nextCandidate')
    old_id = r.state['runInfo']['analysisId']
    adapter = LifecycleAdapter('empty')
    w.bridge.pipeline.adapter = adapter
    choose(w, 'analysis')
    w.click('contextRunAnalysis')
    spin(w.app, adapter.entered.is_set)
    try:
        choose(w, 'result')
        assert not w.state.property('hasResult')
        assert not r.state['selected'] and not r.state['points']
        assert not w.item('analysisOverlay').property('visible')
    finally:
        adapter.release.set()
    spin(w.app, lambda: w.bridge.analysis['hasResult'])
    assert r.state['runInfo']['analysisId'] != old_id
    assert r.state['filterKind'] == 'BPD'  # Existing filter persistence policy.
    assert w.item('resultLifecycleMessage').property('text') == '후보가 발견되지 않았습니다.'
    assert not w.item('candidateList').property('visible')
    assert not w.item('nextCandidate').property('visible')
    assert w.item('analysisExportButton').property('enabled')
    assert '0 / 0' not in w.item('candidateIndex').property('text')
    w.open(w.path)
    assert not r.state['selected'] and not r.state['points']
    assert w.panel.property('requestedContext') == 'image'


def test_assigned_class_is_not_recomputed_from_score_vector(workbench):
    class AssignedCandidates(DistributedCandidates):
        def analyze_source(self, request, token):
            output = super().analyze_source(request, token)
            first = replace(output.detections[0], metadata={'scores': [0.2, 0.7, 0.1]})
            return replace(output, detections=(first,) + output.detections[1:])

    w = workbench
    r = analyzed(w, AssignedCandidates())
    w.click('nextCandidate')
    assert r.state['selected']['type'] == 'BPD'
    assert w.item('selectedCandidateHeader').property('text') == '후보 #1 · BPD'
    assert w.item('candidateConfidence').property('text') == '66.1%'
