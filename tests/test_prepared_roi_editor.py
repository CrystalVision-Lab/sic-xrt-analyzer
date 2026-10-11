"""Full native preparation, cache lifecycle and real ROI editor interactions."""
from pathlib import Path
from threading import Event

import imagecodecs
import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from test_2d_images_roi import invoke, jpeg, point_roi
from test_analysis_pipeline import spin

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource, open_stack
from sic_xrt_analyzer.imaging.imagej_roi import load_rois
from sic_xrt_analyzer.imaging.prepared_image import PreparedPixels
from sic_xrt_analyzer.imaging.roi_edit import export_copy
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.detail_reader import DetailReader
from sic_xrt_analyzer.ui.roi_manager import RoiManager


def test_jpeg_prepare_one_decode_then_no_region_decoder_and_cleanup(qt_app, tmp_path, monkeypatch):
    path = jpeg(tmp_path / 'prepared.jpg', 3200, 2400)
    before = path.stat()
    stack = open_stack(path)
    expected = stack.first_source.read_region(0, 0, 1, 1)[0, 0].tolist()
    calls = []
    real_decode = imagecodecs.jpeg8_decode
    def decode(data, **kwargs):
        calls.append((isinstance(data, np.memmap), isinstance(kwargs['out'], np.memmap)))
        return real_decode(data, **kwargs)
    monkeypatch.setattr(imagecodecs, 'jpeg8_decode', decode)
    try:
        assert stack.prepare_native()
        frame = stack.frame(0)
        cache_directory = Path(frame.source.prepared.directory.name)
        def forbidden(*args):
            raise AssertionError('JPEG must not be decoded again after preparation')
        monkeypatch.setattr(JpegImageSource, '_reader', forbidden)
        for x, y in [(0, 0), (3100, 2300), (1600, 1200)]:
            assert frame.source.read_region(x, y, 1, 1)[0, 0].tolist() == expected
        detail = DetailReader()
        try:
            detail.request(frame, 200, 200, 1000, 500)
            spin(qt_app, lambda: detail.result is not None)
            assert detail.result[1].pixelColor(10, 10).getRgb()[:3] == tuple(expected)
            detail.request(frame, 2200, 1500, 900, 500)
            spin(qt_app, lambda: detail.result is not None and detail.result[0][1] == 2200)
            stack.frame(0, (0, 128))
            assert calls == [(True, True)]
            assert not frame.source.prepared.pixels.flags.writeable
        finally:
            detail.shutdown()
        assert (path.stat().st_size, path.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    finally:
        stack.close()
    assert not cache_directory.exists()


def test_initial_preparation_blocks_viewer_and_cancel_cleans_cache(qt_app, tmp_path, monkeypatch):
    path = jpeg(tmp_path / 'image.jpg', 3200, 2400)
    gate, entered = Event(), Event()
    directories = []
    real_prepare = PreparedPixels.jpeg
    def paused(cache, source, canceled, progress):
        ok = real_prepare(cache, source, canceled, progress)
        directories.append(Path(cache.directory.name))
        entered.set()
        assert gate.wait(5)
        if canceled():
            cache.close()
            return False
        return ok
    monkeypatch.setattr(PreparedPixels, 'jpeg', paused)
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    try:
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(qt_app, entered.is_set)
        assert bridge.stack_viewer.initial_loading and bridge.stack_viewer.frame is None
        assert not bridge.stack_viewer.page(0)
        assert not bridge.stack_viewer.display_range(0, 128)
        bridge.clearImage()
        gate.set()
        spin(qt_app, lambda: bridge.stack_viewer._task is None)
        assert bridge.stack_viewer.frame is None and not bridge.stack_viewer.initial_loading
        assert not directories[0].exists()
    finally:
        gate.set()
        bridge.waitForLoads()


def test_reopening_same_file_releases_previous_native_cache(qt_app, tmp_path):
    path = jpeg(tmp_path / 'large.jpg', 3200, 2400)
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    try:
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(qt_app, lambda: not bridge.stack_viewer.initial_loading)
        first = bridge.stack_viewer.frame.source
        old_directory = Path(first.prepared.directory.name)
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(qt_app, lambda: not bridge.stack_viewer.initial_loading)
        second = bridge.stack_viewer.frame.source
        assert first.identity == second.identity and first is not second
        assert not old_directory.exists()
        directory = Path(second.prepared.directory.name)
        assert directory.exists()
        bridge.clearImage()
        assert not directory.exists()
    finally:
        bridge.waitForLoads()


def test_prepare_failure_preserves_previous_frame_and_removes_partial_cache(qt_app, tmp_path, monkeypatch):
    small = jpeg(tmp_path / 'small.jpg', 3200, 2400)
    large = jpeg(tmp_path / 'large.jpg', 3200, 2400)
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    directories = []
    def failed(data, **kwargs):
        directories.append(Path(kwargs['out'].filename).parent)
        raise RuntimeError('synthetic decode failure')
    try:
        bridge.requestImage(bridge.localUrl(str(small)))
        spin(qt_app, lambda: not bridge.stack_viewer.initial_loading)
        frame = bridge.stack_viewer.frame
        old_cache = Path(frame.source.prepared.directory.name)
        monkeypatch.setattr(imagecodecs, 'jpeg8_decode', failed)
        bridge.requestImage(bridge.localUrl(str(large)))
        spin(qt_app, lambda: not bridge.stack_viewer.initial_loading)
        assert bridge.stack_viewer.frame is frame
        assert 'synthetic decode failure' in bridge.stack_viewer.error
        assert not directories[0].exists()
        assert old_cache.exists()
        assert frame.source.read_region(0, 0, 1, 1).shape == (1, 1, 3)
        bridge.clearImage()
        assert not old_cache.exists()
    finally:
        bridge.waitForLoads()


def manager_for(tmp_path, qt_app, *, polygon=False):
    source = jpeg(tmp_path / 'image.jpg', 1000, 800)
    roi = point_roi()
    if polygon:
        from roifile import ROI_TYPE
        roi.roitype = ROI_TYPE.POLYGON
    file = tmp_path / 'original.roi'
    file.write_bytes(roi.tobytes())
    stack = open_stack(source)
    frame = stack.frame(0)
    manager = RoiManager()
    manager.load([file], frame)
    spin(qt_app, lambda: bool(manager.records))
    return manager, stack, frame, file


@pytest.mark.parametrize('polygon', [False, True])
def test_roi_vertex_translate_undo_redo_export_roundtrip_and_original_preserved(qt_app, tmp_path, polygon):
    manager, stack, frame, original = manager_for(tmp_path, qt_app, polygon=polygon)
    before = original.read_bytes()
    try:
        manager.select_vertex(1, frame)
        assert manager.move_vertex(111.5, 123.25, frame)
        moved = manager.records[0]
        assert moved.paths[0][1] == (111.5, 123.25)
        manager.history()
        assert manager.records[0].paths[0][1] == (100, 120)
        manager.history(True)
        assert manager.records[0] == moved
        assert manager.move_roi(10, 20, frame)
        shifted = manager.records[0]
        assert shifted.paths[0][1] == (121.5, 143.25)
        assert not manager.move_vertex(-1, float('nan'), frame)
        assert manager.records[0] == shifted
        assert not manager.move_roi(10000, 0, frame)
        assert manager.records[0] == shifted
        assert manager.add_vertex(200, 210, frame)
        assert len(manager.records[0].paths[0]) == 4
        manager.delete_vertex(frame)
        assert len(manager.records[0].paths[0]) == 3
        manager.rename('edited', frame)
        copy = tmp_path / 'EditedRoiSet.zip'
        export_copy(copy, manager.records)
        loaded, errors = load_rois([copy], frame.source.metadata)
        assert not errors and loaded[0].name == 'edited'
        assert loaded[0].kind == manager.records[0].kind
        np.testing.assert_allclose(loaded[0].paths, manager.records[0].paths)
        with pytest.raises(FileExistsError):
            export_copy(copy, manager.records)
        with pytest.raises(ValueError):
            export_copy(original, manager.records)
        assert original.read_bytes() == before
        assert manager.dirty
        manager.saved_records = tuple(manager.records)
        assert not manager.dirty
        manager.history()
        assert manager.dirty
    finally:
        manager.shutdown()
        stack.close()


def test_roi_drag_single_undo_and_cancel_and_empty_list_reversible(qt_app, tmp_path):
    manager, stack, frame, _ = manager_for(tmp_path, qt_app)
    try:
        start = manager.records[0]
        count = len(manager.undo_stack)
        assert manager.begin_drag(100, 120, 8, frame)
        for i in range(10):
            manager.move_vertex(110 + i, 130 + i, frame, remember=False)
        manager.finish_drag()
        assert len(manager.undo_stack) == count + 1
        manager.history()
        assert manager.records[0] == start
        assert manager.begin_drag(40, 50, 8, frame)
        manager.move_vertex(70, 80, frame, remember=False)
        manager.finish_drag(cancel=True)
        assert manager.records[0] == start
        manager.clear_list()
        assert not manager.records and manager.dirty
        manager.history()
        assert manager.records == [start]
    finally:
        manager.shutdown()
        stack.close()


def test_qml_mouse_roi_edit_numeric_apply_save_and_discard_guard(qt_app, tmp_path):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'src/sic_xrt_analyzer/ui/Main.qml')))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, 'uiState')
    path = jpeg(tmp_path / 'image.jpg', 1000, 800)
    roi_file = tmp_path / 'original.roi'
    roi_file.write_bytes(point_roi().tobytes())
    original = roi_file.read_bytes()
    try:
        invoke(window, 'selectImagePath', str(path))
        spin(qt_app, lambda: not state.property('loading'))
        bridge.importRois([bridge.localUrl(str(roi_file))])
        spin(qt_app, lambda: bool(bridge.roiState['items']))
        state.setProperty('roiEditMode', True)
        viewer = window.findChild(QObject, 'imageViewer')
        frame = window.findChild(QObject, 'imageFrame')
        mouse = window.findChild(QObject, 'viewerMouseArea')
        scale = viewer.property('displayScale')
        def scene(x, y):
            p = mouse.mapToScene(QPointF(frame.property('x') + x * scale, frame.property('y') + y * scale))
            return QPoint(round(p.x()), round(p.y()))
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, scene(100, 120))
        QTest.mouseMove(window, scene(130, 145), 20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, scene(130, 145))
        np.testing.assert_allclose(bridge.roi_manager.records[0].paths[0][1], (130, 145), atol=2)
        assert bridge.roiState['dirty'] and bridge.roiState['canUndo']
        x_field = window.findChild(QObject, 'roiPointXField')
        y_field = window.findChild(QObject, 'roiPointYField')
        x_field.setProperty('text', '150.5'); y_field.setProperty('text', '160.25')
        invoke(window.findChild(QObject, 'applyRoiPointButton'), 'clicked')
        assert bridge.roi_manager.records[0].paths[0][1] == (150.5, 160.25)
        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, scene(200, 200))
        qt_app.processEvents()
        assert len(bridge.roi_manager.records[0].paths[0]) == 4
        QTest.keyClick(window, Qt.Key_Delete)
        assert len(bridge.roi_manager.records[0].paths[0]) == 3
        invoke(window, 'closeImage')
        assert window.findChild(QObject, 'roiDiscardDialog').property('visible')
        invoke(window.findChild(QObject, 'roiDiscardDialog'), 'reject')
        assert bridge.stack_viewer.frame is not None
        copy = tmp_path / 'EditedRoiSet.zip'
        saved = []
        bridge.roiSaved.connect(saved.append)
        bridge.saveRoiCopy(bridge.localUrl(str(copy)))
        spin(qt_app, lambda: bool(saved))
        assert saved[0]['ok'] and not bridge.roiState['dirty']
        loaded, errors = load_rois([copy], bridge.original_source.metadata)
        assert not errors and loaded[0].paths[0][1] == (150.5, 160.25)
        assert roi_file.read_bytes() == original
        invoke(window, 'closeImage')
        assert bridge.stack_viewer.frame is None and not state.property('roiEditMode')
        assert not warnings, '\n'.join(warnings)
    finally:
        bridge.waitForLoads()
        window.setProperty('allowQuit', True)
        window.close()
        engine.deleteLater()
        qt_app.processEvents()


def test_large_tiff_native_preparation_reads_without_full_copy(tmp_path, monkeypatch):
    path = tmp_path / 'large.tif'
    pixels = tifffile.memmap(path, shape=(7000, 7000, 3), dtype='uint8', photometric='rgb')
    pixels[:] = [1, 2, 3]
    pixels.flush(); pixels._mmap.close()
    before = path.stat()
    stack = open_stack(path)
    progress = []
    try:
        assert stack.prepare_native(progress=lambda *args: progress.append(args))
        assert progress[0][0] < progress[-1][0] == 7000
        assert stack.native_ready
        assert stack.frame(0).pixels is None
        assert stack.first_source.read_region(6999, 6999, 1, 1)[0, 0].tolist() == [1, 2, 3]
        assert (path.stat().st_size, path.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    finally:
        stack.close()
