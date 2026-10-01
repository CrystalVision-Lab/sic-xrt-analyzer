"""Preferences must survive restarts and reject unsupported values."""
from PySide6.QtCore import QSettings

from sic_xrt_analyzer.ui.bridge import DEFAULTS, FileBridge


def test_applied_preferences_and_recent_privacy(tmp_path):
    path = str(tmp_path / "settings.ini")
    bridge = FileBridge(settings=QSettings(path, QSettings.IniFormat))
    bridge.recordRecentFile(str(tmp_path / "first.tif"))
    bridge.recordRecentFile(str(tmp_path / "second.tif"))
    applied = bridge.applyPreferences({**DEFAULTS, "recentFileLimit": 1, "smoothImages": False, "defaultView": "200"})
    assert len(bridge.recentFiles) == 1
    restored = FileBridge(settings=QSettings(path, QSettings.IniFormat))
    assert restored.preferences() == applied
    assert restored.recentFiles == bridge.recentFiles
    bridge.applyPreferences({**applied, "rememberRecentFiles": False})
    assert not FileBridge(settings=QSettings(path, QSettings.IniFormat)).recentFiles
    assert bridge.recentFiles  # Session navigation still works.
    assert bridge.applyPreferences({"recentFileLimit": -1, "defaultView": "unsupported", "viewerBackground": "white", "smoothImages": "false"}) == DEFAULTS


def test_legacy_relative_zoom_migrates_to_fit(tmp_path):
    settings = QSettings(str(tmp_path / "legacy.ini"), QSettings.IniFormat)
    settings.setValue("preferences", {"defaultZoom": 2, "smoothImages": False, "recentFileLimit": 3})
    bridge = FileBridge(settings=settings)
    assert bridge.preferences()["defaultView"] == "fit"
    assert not bridge.preferences()["smoothImages"]
    assert bridge.preferences()["recentFileLimit"] == 3
    assert "defaultZoom" not in bridge.preferences()
    bridge.applyPreferences(bridge.preferences())
    assert "defaultZoom" not in settings.value("preferences")
