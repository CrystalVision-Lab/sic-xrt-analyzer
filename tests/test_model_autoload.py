import pytest
from PySide6.QtCore import QSettings
from test_analysis_pipeline import spin

from sic_xrt_analyzer.ui import research_controller as module


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / 'application'
    repo.mkdir()
    (repo / 'pyproject.toml').touch()
    monkeypatch.setattr(module, '__file__', str(repo / 'src/sic_xrt_analyzer/ui/research_controller.py'))
    monkeypatch.delenv('SIC_XRT_MODEL_BUNDLE', raising=False)
    monkeypatch.chdir(tmp_path)
    return repo


def bundle(path):
    path.mkdir(parents=True)
    (path / 'manifest.json').write_text('{}')
    return path


def test_no_settings_finds_deployed_artifact_from_another_directory(project, tmp_path, bridge_factory, monkeypatch):
    deployed = bundle(project / 'artifacts/models/research')
    # An unrelated working directory's model must not replace this app's bundle.
    bundle(tmp_path / 'models/research')
    bridge = bridge_factory(settings=QSettings(str(tmp_path / 'empty.ini'), QSettings.IniFormat))
    loaded = []
    monkeypatch.setattr(bridge.research, 'loadModel', loaded.append)
    bridge.research.load_saved()
    assert loaded == [str(deployed)]


def test_explicit_selection_and_environment_keep_priority(project, tmp_path, bridge_factory, monkeypatch):
    bundle(project / 'artifacts/models/research')
    settings = QSettings(str(tmp_path / 'saved.ini'), QSettings.IniFormat)
    selected = str(tmp_path / 'selected_model')
    settings.setValue('researchModelBundle', selected)
    bridge = bridge_factory(settings=settings)
    loaded = []
    monkeypatch.setattr(bridge.research, 'loadModel', loaded.append)
    bridge.research.load_saved()
    override = str(tmp_path / 'explicit_override')
    monkeypatch.setenv('SIC_XRT_MODEL_BUNDLE', override)
    bridge.research.load_saved()
    assert loaded == [selected, override]


def test_invalid_discovered_bundle_is_not_marked_connected(project, tmp_path, bridge_factory, qt_app):
    bundle(project / 'artifacts/models/research')
    bridge = bridge_factory(settings=QSettings(str(tmp_path / 'empty.ini'), QSettings.IniFormat))
    bridge.research.load_saved()
    spin(qt_app, lambda: not bridge.research.state['loading'])
    assert not bridge.analysis['modelAvailable']
    assert bridge.research.state['error']


def test_no_bundle_explains_how_to_connect(project, tmp_path, bridge_factory):
    bridge = bridge_factory(settings=QSettings(str(tmp_path / 'empty.ini'), QSettings.IniFormat))
    bridge.research.load_saved()
    assert '모델 폴더를 찾지 못했습니다' in bridge.research.state['error']
    assert not bridge.analysis['modelAvailable']


def test_frozen_app_uses_its_directory_not_cwd(project, tmp_path, monkeypatch):
    exe_folder = tmp_path / 'installed'
    expected = bundle(exe_folder / 'models/research')
    bundle(project / 'artifacts/models/research')
    monkeypatch.setattr(module.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(module.sys, 'executable', str(exe_folder / 'analyzer.exe'))
    assert module.bundled_model_path() == expected
