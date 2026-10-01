"""Recent files contain only selected paths and survive app restarts."""

from PySide6.QtCore import QSettings

from sic_xrt_analyzer.__main__ import FileBridge


def test_recent_files_are_unique_bounded_and_persistent(tmp_path):
    settings_path = tmp_path / "preferences.ini"
    bridge = FileBridge(settings=QSettings(str(settings_path), QSettings.IniFormat))
    paths = [tmp_path / f"image-{index}.tif" for index in range(12)]
    for path in paths:
        path.touch()
        bridge.recordRecentFile(str(path))
    bridge.recordRecentFile(str(paths[5]))

    assert len(bridge.recentFiles) == 10
    assert bridge.recentFiles[0] == str(paths[5])
    assert bridge.recentFiles.count(str(paths[5])) == 1
    assert str(paths[0]) not in bridge.recentFiles
    assert bridge.isAccessible(str(paths[5]))

    restored = FileBridge(settings=QSettings(str(settings_path), QSettings.IniFormat))
    assert restored.recentFiles == bridge.recentFiles
    paths[5].unlink()
    assert not restored.isAccessible(str(paths[5]))
    restored.clearRecentFiles()
    assert restored.recentFiles == []
