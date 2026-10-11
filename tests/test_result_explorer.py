import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import Classifier, create_source
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.analysis.contracts import (
    AdapterOutput,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
)
from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


class ManyCandidates(DesktopResearchAdapter):
    def __init__(self):
        super().__init__(None, Classifier())

    def analyze_source(self, request, token):
        rows = []
        for i in range(231):
            kind = ("BPD", "TED", "TSD")[i % 3]
            scores = [0.1, 0.1, 0.1]
            scores[i % 3] = 0.8
            rows.append(Detection(f"candidate_{i:06d}", i % 3, kind, .8,
                                  Geometry(GeometryKind.POINT, ((80 + (i % 15)*24, 80 + (i//15)*24),), coordinate_space=CoordinateSpace.ORIGINAL),
                                  {"point_id": f"source_{i:06d}", "scores": scores, "low_score": i % 5 == 0}))
        return AdapterOutput(tuple(rows), {"counts": {"BPD": 77, "TED": 77, "TSD": 77}}, {})


def test_all_candidates_filters_navigation_export_and_source_reset(qt_app, tmp_path, bridge_factory):
    bridge = bridge_factory(settings=QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    bridge.pipeline.adapter = ManyCandidates()
    bridge.pipeline.set_source(create_source(tmp_path))
    assert bridge.requestAnalysis('FULL_IMAGE', 0, 0, 0, 0, {})
    spin(qt_app, lambda: bridge.analysis['hasResult'])
    r = bridge.research
    assert r.state['total'] == 231 and r.state['pages'] == 3
    r.setResultPage(2)
    assert len(r.state['displayRows']) == 31
    r.selectCandidate('candidate_000230')
    spin(qt_app, lambda: bool(r.state['thumbnailSource']))
    assert r.state['selected']['number'] == 231 and r.state['selectedIndex'] == 230
    assert bridge.provider.research_image.width() == 128
    r.stepCandidate(-1)
    assert r.state['selected']['number'] == 230
    assert r.state['viewedCount'] == 2
    r.setFilter('BPD', True, '')
    assert r.state['selected'] == {} and r.state['thumbnailSource'] == ''
    assert all(p['type'] == 'BPD' and p['low_score'] for p in r.state['filteredPoints'])
    r.setFilter('ALL', False, 'source_000230')
    assert r.state['filteredTotal'] == 1
    r.stepCandidate(1)
    assert r.state['selected']['number'] == 231
    assert r.exportResult(str(tmp_path))
    saved = json.loads((Path(r.state['exportPath'])/'result.json').read_text(encoding='utf-8'))
    assert len(saved['predictions']) == 231  # Filtering never truncates exports.
    assert saved['human_verified'] is False
    bridge.pipeline.set_source(None)
    qt_app.processEvents()
    assert r.state['selected'] == {} and r.state['thumbnailSource'] == '' and r.state['viewedCount'] == 0


def test_qml_filter_click_animation_center_and_marker_hit(qt_app, tmp_path):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path/'ui.ini'), QSettings.IniFormat))
    bridge.pipeline.adapter = ManyCandidates()
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window = engine.rootObjects()[0]
    def item(name):
        pending = [window.contentItem()]
        while pending:
            node = pending.pop()
            if node.objectName() == name:
                return node
            pending.extend(node.childItems())
        raise AssertionError(name + ': ' + '\\n'.join(warnings))
    state = window.findChild(QObject, 'uiState')
    try:
        source = create_source(tmp_path)
        invoke(window, 'selectImagePath', source.path)
        spin(qt_app, lambda: state.property('hasLoadedImage') and not state.property('loading'))
        state.setProperty('analysisScope', 'FULL_IMAGE')
        invoke(window.findChild(QObject, 'runAction'), 'trigger')
        spin(qt_app, lambda: bridge.analysis['hasResult'])
        invoke(window, 'openInspectorTab', 2)
        invoke(item('resultFilterBPD'), 'clicked')
        assert bridge.research.state['filteredTotal'] == 77
        invoke(window.findChild(QObject, 'nextCandidate'), 'clicked')
        animation = window.findChild(QObject, 'candidateFocusAnimation')
        spin(qt_app, lambda: animation.property('running'))
        spin(qt_app, lambda: not animation.property('running'))
        spin(qt_app, lambda: bool(bridge.research.state['thumbnailSource']))
        viewport = window.findChild(QObject, 'viewerViewport')
        frame = window.findChild(QObject, 'imageFrame')
        viewer = window.findChild(QObject, 'imageViewer')
        selected = bridge.research.state['selected']
        scale = viewer.property('displayScale')
        assert frame.property('x') + selected['x']*scale == pytest.approx(viewport.property('width')/2, abs=1)
        assert frame.property('y') + selected['y']*scale == pytest.approx(viewport.property('height')/2, abs=1)
        assert bridge.research.state['selected']['type'] == 'BPD'
        assert state.property('candidateRoiId') == selected['id']
        assert (state.property('roiX'), state.property('roiY'), state.property('roiWidth'), state.property('roiHeight')) == (16, 16, 128, 128)
        assert bridge.analysis['hasResult']  # ROI navigation must preserve the analysis.
        # Select a nearby different visible candidate through the actual image MouseArea.
        target = bridge.research.state['filteredPoints'][1]
        pos = viewport.mapToScene(QPointF(frame.property('x')+target['x']*scale, frame.property('y')+target['y']*scale))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y())))
        spin(qt_app, lambda: bridge.research.state['selected'].get('id') == target['id'])
        assert state.property('roiX') == 88 and state.property('roiY') == 16
        invoke(window.findChild(QObject, 'resultOverview'), 'clicked')
        assert state.property('fitMode') and not animation.property('running')
        # Size changes clamp to the image while preserving the requested size.
        state.setProperty('candidateRoiSize', 256)
        bridge.research.selectCandidate('candidate_000000')
        assert (state.property('roiX'), state.property('roiY')) == (0, 0)
        bridge.research.setFilter('ALL', False, '')
        bridge.research.selectCandidate('candidate_000224')
        assert (state.property('roiX'), state.property('roiY'), state.property('roiWidth'), state.property('roiHeight')) == (256, 256, 256, 256)
        # Filtering away the selected candidate removes only its automatic ROI.
        bridge.research.setFilter('BPD', False, '')
        assert not state.property('hasRoi') and not state.property('candidateRoiId')
        bridge.research.selectCandidate('candidate_000000')
        invoke(window, 'clearRoi')
        assert not state.property('autoCandidateRoi')
        bridge.research.selectCandidate('candidate_000003')
        assert not state.property('hasRoi')
        # Turning tracking off preserves a manual working rectangle across selection/filter changes.
        state.setProperty('autoCandidateRoi', True)
        invoke(state, 'stopCandidateRoiTracking')
        manual_roi = (state.property('roiX'), state.property('roiY'))
        bridge.research.selectCandidate('candidate_000006')
        bridge.research.setFilter('TSD', False, '')
        assert state.property('hasRoi') and (state.property('roiX'), state.property('roiY')) == manual_roi
        # Explicit re-analysis captures and retains the ROI as the old results are invalidated.
        bridge.research.selectCandidate('candidate_000002')
        state.setProperty('candidateRoiSize', 512)
        state.setProperty('autoCandidateRoi', True)
        state.setProperty('analysisScope', 'ROI')
        qt_app.processEvents()
        assert bridge.pipeline.current_roi.width == 512
        invoke(window.findChild(QObject, 'runAction'), 'trigger')
        spin(qt_app, lambda: bridge.analysis['hasResult'])
        assert bridge.pipeline.result.roi == bridge.pipeline.current_roi
        assert state.property('hasRoi') and not state.property('candidateRoiId')
        bridge.research.stepCandidate(1)
        assert state.property('candidateRoiId')
        bridge.pipeline.invalidate()
        qt_app.processEvents()
        assert not state.property('hasRoi')
        assert not warnings, '\n'.join(warnings)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()
