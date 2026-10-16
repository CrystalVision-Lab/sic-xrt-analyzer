"""Verify shell boundaries without adding new automatic context transitions."""
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_desktop_research import create_jpeg_source as create_source
from test_result_explorer import ManyCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.ui.bridge import TiffImageProvider


def test_shell_context_layout_and_shared_analysis_command(qt_app, tmp_path, bridge_factory):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = bridge_factory(provider=provider, settings=QSettings(str(tmp_path/'ia.ini'), QSettings.IniFormat))
    bridge.pipeline.adapter = ManyCandidates()
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    assert len(engine.rootObjects()) == 1, warnings
    window = engine.rootObjects()[0]

    def item(name):
        obj = window.findChild(QObject, name)
        if obj is not None:
            return obj
        # Repeater delegates belong to the visual tree, not the QObject tree.
        pending = [window.contentItem()]
        while pending:
            node = pending.pop()
            if node.objectName() == name:
                return node
            pending.extend(node.childItems())
        raise AssertionError(name)

    state, panel = item('uiState'), item('inspectorPanel')
    try:
        for name in ('appMenuBar', 'topToolbar', 'workspaceNavigation', 'centralWorkspace',
                     'imageViewer', 'bottomStatusBar', 'viewerHeader', 'currentFileNavigation',
                     'imageContext', 'analysisDialog', 'resultContext', 'viewerContext', 'roiContext',
                     'fileToolGroup', 'viewerToolGroup', 'roiToolDropdown', 'measurementToolDropdown', 'advancedToolGroup'):
            item(name)
        assert panel.property('activeContext') == 'idle'
        assert not item('confirmAnalysis').property('enabled')
        source = create_source(tmp_path)
        invoke(window, 'selectImagePath', source.path)
        spin(qt_app, lambda: state.property('hasLoadedImage') and not state.property('loading') and not bridge.stack_viewer.initial_loading)
        assert panel.property('activeContext') == 'image'  # JPEG retains analysis image context.
        assert item('currentFileName').property('text') == Path(source.path).name
        for index, context in ((0,'image'),(3,'viewer'),(4,'roi')):
            invoke(window, 'openContext', context)
            assert panel.property('tabIndex') == index
            assert panel.property('activeContext') == context
        invoke(item('prepareAnalysisAction'),'trigger')
        assert item('analysisDialog').property('visible')
        state.setProperty('activeTool', 'ROI')
        state.setProperty('hasRoi', True)
        assert panel.property('activeContext') == 'roi'  # No new tool-driven auto switch.
        run_action = item('runAction')
        # QQuickAction* has no direct Python converter; compare identity in QML.
        engine.rootContext().setContextProperty('checkedButton',item('imagePrepareAnalysis'))
        engine.rootContext().setContextProperty('checkedAction',item('prepareAnalysisAction'))
        expression=QQmlExpression(engine.rootContext(),window,'checkedButton.action === checkedAction')
        assert expression.evaluate()[0] is True and not expression.hasError()
        assert item('cancelAnalysisAction').property('enabled') is False
        state.setProperty('analysisScope', 'FULL_IMAGE')
        QTest.qWait(40)
        assert run_action.property('enabled')
        assert item('confirmAnalysis').property('enabled') == run_action.property('enabled')
        button = item('confirmAnalysis')
        point = button.mapToScene(QPointF(button.property('width')/2, button.property('height')/2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
        spin(qt_app, lambda: bridge.analysis['hasResult'])
        assert bridge.research.state['total'] == 231
        # TD-03 adds the explicit analysis-complete milestone.
        assert panel.property('activeContext') == 'result'
        assert panel.property('lastReason') == 'ANALYSIS_COMPLETE'
        bridge.research.selectCandidate('candidate_000000')
        spin(qt_app, lambda: panel.property('detailContext') == 'candidate')
        assert panel.property('tabIndex') == 2  # Existing focusRequested behavior.
        assert bridge.analysis['hasResult'] and not state.property('candidateRoiId')

        # At the minimum supported size each context leaves useful central space.
        window.resize(1100, 700)
        for index in (0,2,3,4):
            panel.setProperty('tabIndex', index)
            QTest.qWait(35)
            nav, center = item('workspaceNavigation'), item('centralWorkspace')
            assert center.property('width') >= 500
            assert panel.property('width') == pytest.approx(320 if index == 2 else 282)
            assert center.property('x') == pytest.approx(nav.property('width'))
            assert panel.property('x') == pytest.approx(center.property('x') + center.property('width'))
        previous_width = item('centralWorkspace').property('width')
        invoke(item('inspectorPanelAction'), 'trigger')
        QTest.qWait(35)
        assert not panel.property('visible')
        assert item('centralWorkspace').property('width') > previous_width
        invoke(window, 'resetLayout')
        assert panel.property('activeContext') == 'image'
        for index in (1,2,0):
            invoke(window, 'selectWorkspace', index)
            assert item('centralWorkspace').property('currentIndex') == index
        invoke(window,'selectWorkspace',3)
        assert state.property('workspaceIndex')==0  # 3D is accessible only through a stack ROI.
        invoke(window, 'closeImage')
        assert panel.property('activeContext') == 'idle'
        assert not item('confirmAnalysis').property('enabled')
        assert not warnings, warnings
    finally:
        window.close()
        bridge.waitForLoads()
        engine.deleteLater()
