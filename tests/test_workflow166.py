"""First-run decisions, playback pacing and packaged guide consistency."""
import json
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from test_analysis_pipeline import spin


def test_first_run_local_choice_persists_and_secret_field_clears(qt_app, tmp_path, bridge_factory):
    settings = QSettings(str(tmp_path / 'setup.ini'), QSettings.IniFormat)
    bridge = bridge_factory(settings=settings)
    assert bridge.centralSync.state['setupNeeded']
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    engine.addImageProvider('tiff', bridge.provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    engine.load(QUrl.fromLocalFile(str(Path('src/sic_xrt_analyzer/ui/Main.qml').resolve())))
    window = engine.rootObjects()[0]
    dialog = window.findChild(QObject, 'deviceSetupDialog')
    spin(qt_app, lambda: dialog.property('visible'))
    field = window.findChild(QObject, 'setupCredential')
    field.setProperty('text', 'xrt_synthetic_not_a_real_secret')
    QMetaObject.invokeMethod(dialog, 'close')
    spin(qt_app, lambda: not dialog.property('visible'))
    assert field.property('text') == ''
    assert not bridge.centralSync.state['setupNeeded']
    assert not bridge.centralSync.endpoint
    assert 'xrt_synthetic' not in Path(settings.fileName()).read_text()
    second = bridge_factory(settings=QSettings(settings.fileName(), QSettings.IniFormat))
    assert not second.centralSync.state['setupNeeded']
    window.close()
    engine.deleteLater()


def test_playback_speed_rescales_active_timer_without_changing_analysis(bridge_factory):
    c = bridge_factory().defect3d
    c.timer.start(4000)
    before = c.timer.remainingTime()
    c.setPlaybackSpeed(2)
    assert 0 < c.timer.remainingTime() <= before // 2 + 20
    assert c.state['playbackSpeed'] == 2
    c.setPlaybackSpeed(float('nan'))
    assert c.state['playbackSpeed'] == 2
    c.timer.stop()
    c.paused = True
    c.setPlaybackSpeed(.5)
    assert c.paused and not c.timer.isActive()
    assert c.sensitivity == 1.0 and not c.anchors


def test_web_and_packaged_offline_guide_have_same_content(bridge_factory):
    guide = bridge_factory().workflowGuide
    assert guide == json.loads(Path('web/src/workflow-guide.json').read_text(encoding='utf-8'))
    assert len(guide['groups']) >= 5
    for group in guide['groups']:
        assert group['tabs'] and all(tab['steps'] for tab in group['tabs'])
