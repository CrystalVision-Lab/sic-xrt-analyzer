"""Preferences must survive restarts and reject unsupported values."""
from PySide6.QtCore import QSettings

from sic_xrt_analyzer.ui.bridge import DEFAULTS, FileBridge


def test_applied_preferences_and_recent_privacy(tmp_path):
    path = str(tmp_path / "settings.ini")
    bridge = FileBridge(settings=QSettings(path, QSettings.IniFormat))
    bridge.recordRecentFile(str(tmp_path / "first.tif"))
    bridge.recordRecentFile(str(tmp_path / "second.tif"))
    applied = bridge.applyPreferences({**DEFAULTS, "recentFileLimit": 1, "smoothImages": False, "defaultZoom": 2})
    assert len(bridge.recentFiles) == 1
    restored = FileBridge(settings=QSettings(path, QSettings.IniFormat))
    assert restored.preferences() == applied
    assert restored.recentFiles == bridge.recentFiles
    bridge.applyPreferences({**applied, "rememberRecentFiles": False})
    assert not FileBridge(settings=QSettings(path, QSettings.IniFormat)).recentFiles
    assert bridge.recentFiles  # Session navigation still works.
    assert bridge.applyPreferences({"recentFileLimit": -1, "defaultZoom": 500, "viewerBackground": "white", "smoothImages": "false"}) == DEFAULTS

