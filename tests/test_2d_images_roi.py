"""Image formats, bounded reads and imported overlays use synthetic data only."""
import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event
from zipfile import ZipFile

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    QSettings,
    Qt,
    QUrl,
)
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from roifile import ROI_TYPE, ImagejRoi
from test_analysis_pipeline import spin

from sic_xrt_analyzer.imaging.image_stack import (
    JpegImageSource,
    SampledImageStack,
    image_array,
    open_stack,
)
from sic_xrt_analyzer.imaging.imagej_roi import decode_roi, load_rois
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource, SourceError
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.detail_reader import DetailReader
from sic_xrt_analyzer.ui.latest_reader import LatestReader
from sic_xrt_analyzer.ui.roi_manager import RoiManager


def invoke(obj, name, *args):
    assert QMetaObject.invokeMethod(obj, name, *(Q_ARG('QVariant', a) for a in args))


def jpeg(path, width=320, height=240):
    image = QImage(width, height, QImage.Format_RGB888)
    image.fill('#648cc8')
    assert image.save(str(path), 'JPEG', 95)
    return path


def point_roi(name='synthetic-points', position=0):
    roi = ImagejRoi.frompoints([[40, 50], [100, 120], [160, 80]])
    roi.roitype = ROI_TYPE.POINT
    roi.name = name
    roi.position = position
    roi.stroke_color = b'\xff\x00\xff\x00'
    return roi


def test_jpeg_metadata_window_region_identity_and_original_orientation(tmp_path):
    path = jpeg(tmp_path / 'image.JPEG', 321, 241)
    # A valid EXIF orientation 6 tag must not rotate encoded ImageJ coordinates.
    exif = b'Exif\0\0II*\0\x08\0\0\0\x01\0\x12\x01\x03\0\x01\0\0\0\x06\0\0\0\0\0\0\0'
    data = path.read_bytes()
    path.write_bytes(data[:2] + b'\xff\xe1' + (len(exif) + 2).to_bytes(2, 'big') + exif + data[2:])
    before = path.stat()
    stack = open_stack(path)
    source = stack.first_source
    try:
        assert isinstance(stack, SampledImageStack) and source.metadata.format == 'JPEG'
        assert (source.metadata.width, source.metadata.height, source.metadata.channels) == (321, 241, 3)
        frame = stack.frame(0)
        assert not frame.preview.sampled and frame.pixels.shape == (241, 321, 3)
        expected_reader = QImageReader(str(path))
        expected_reader.setAutoTransform(False)
        expected = image_array(expected_reader.read())
        np.testing.assert_array_equal(source.read_region(10, 20, 30, 40), expected[20:60, 10:40])
        changed = stack.frame(0, (0, 128))
        assert changed.preview.image.pixelColor(0, 0) != frame.preview.image.pixelColor(0, 0)
        np.testing.assert_array_equal(changed.pixels, expected)
        with pytest.raises(FrozenInstanceError):
            source.path = 'other'
        with pytest.raises(SourceError):
            source.read_region(-1, 0, 1, 1)
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        os.utime(path, ns=(after.st_atime_ns, after.st_mtime_ns + 1_000_000))
        with pytest.raises(SourceError, match='changed'):
            stack.frame(0)
    finally:
        stack.close()


def test_large_jpeg_is_sampled_and_exact_pixel_restored_async(qt_app, tmp_path):
    path = jpeg(tmp_path / 'large.jpg', 3500, 3000)
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.IniFormat))
    try:
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(qt_app, lambda: not bridge.stack_viewer.initial_loading)
        frame = bridge.stack_viewer.frame
        assert frame is not None and frame.pixels is None and frame.preview.sampled
        assert max(frame.preview.image.width(), frame.preview.image.height()) <= 2048
        assert bridge.pipeline.source is None and not bridge.stackState['browsePreview']
        assert bridge.pixelValue(2100, 2300) == ''
        spin(qt_app, lambda: bool(bridge.pixelValue(2100, 2300)))
        expected = frame.source.read_region(2100, 2300, 1, 1)[0, 0]
        assert bridge.pixelValue(2100, 2300) == ', '.join(str(v) for v in expected)
        assert bridge.pixel_reader.tile[-1].nbytes <= 128 * 128 * 3
        bridge.clearImage()
        assert bridge.pixel_reader.tile is None and bridge.pixelValue(2100, 2300) == ''
    finally:
        bridge.waitForLoads()


def test_large_tiff_preview_does_not_read_full_and_bounded_roi_is_exact(qt_app, tmp_path, monkeypatch):
    path = tmp_path / 'large-rgb.tif'
    mapped = tifffile.memmap(path, shape=(7000, 7000, 3), dtype='uint8', photometric='rgb')
    mapped[:] = [40, 80, 120]
    mapped[3456, 2345] = [7, 19, 31]
    mapped.flush()
    mapped._mmap.close()
    before = path.stat()
    def forbidden(*args):
        raise AssertionError('The large page must not be copied in full')
    monkeypatch.setattr(OriginalImageSource, 'read_full', forbidden)
    stack = open_stack(path, browse_enabled=True)
    try:
        frame = stack.frame(0)
        assert frame.pixels is None and frame.preview.sampled
        assert max(frame.preview.image.width(), frame.preview.image.height()) <= 2048
        assert stack.samples.nbytes <= stack.max_cache_bytes
        np.testing.assert_array_equal(frame.source.read_region(2345, 3456, 1, 1)[0, 0], [7, 19, 31])
        detail = DetailReader()
        try:
            detail.request(frame, 2340, 3450, 20, 20)
            spin(qt_app, lambda: detail.result is not None)
            assert detail.result[1].pixelColor(5, 6).getRgb()[:3] == (7, 19, 31)
            detail.request(frame, 0, 0, 7000, 7000)
            assert detail.result is None and not detail.busy
        finally:
            detail.shutdown()
        with pytest.raises(SourceError, match='budget'):
            frame.source.read_region(0, 0, 7000, 7000)
        assert (path.stat().st_size, path.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    finally:
        stack.close()
    assert stack.samples is None


def test_bad_image_and_large_compressed_tiff_have_clear_errors(tmp_path):
    bad = tmp_path / 'bad.jpg'
    bad.write_bytes(b'not a JPEG')
    with pytest.raises(SourceError, match='TIFF'):
        open_stack(bad)
    with pytest.raises(SourceError):
        JpegImageSource(bad)
    path = tmp_path / 'compressed.tif'
    tifffile.imwrite(path, np.zeros((9, 11), np.uint16), compression='deflate')
    source = OriginalImageSource(path)
    with pytest.raises(SourceError, match='영역 디코더'):
        source.read_sampled()


@pytest.mark.parametrize('kind', [ROI_TYPE.POINT, ROI_TYPE.POLYGON, ROI_TYPE.POLYLINE, ROI_TYPE.LINE, ROI_TYPE.RECT, ROI_TYPE.OVAL])
def test_roi_shapes_original_bounds_color_and_position(tmp_path, kind):
    image = tmp_path / 'image.tif'
    tifffile.imwrite(image, np.zeros((200, 200), np.uint16))
    meta = OriginalImageSource(image).metadata
    roi = point_roi()
    roi.roitype = kind
    if kind in (ROI_TYPE.LINE, ROI_TYPE.RECT, ROI_TYPE.OVAL):
        roi.integer_coordinates = roi.subpixel_coordinates = None
        roi.left, roi.top, roi.right, roi.bottom = 40, 50, 160, 120
        roi.x1, roi.y1, roi.x2, roi.y2 = 40, 50, 160, 120
    decoded = decode_roi(roi.tobytes(), 'test.roi', meta)
    assert decoded.color == '#00ff00' and decoded.page_index is None
    assert decoded.bbox[0] >= 0 and decoded.bbox[0] + decoded.bbox[2] <= 200
    assert decoded.kind == ('point' if kind == ROI_TYPE.POINT else 'line' if kind in (ROI_TYPE.LINE, ROI_TYPE.POLYLINE) else 'polygon')
    roi.position = 2
    with pytest.raises(ValueError, match='페이지 위치'):
        decode_roi(roi.tobytes(), 'test.roi', meta)


def test_roi_zip_partial_error_no_extraction_and_wrong_image_rejected(tmp_path):
    path = jpeg(tmp_path / 'image.jpg')
    meta = JpegImageSource(path).metadata
    archive = tmp_path / 'RoiSet.zip'
    with ZipFile(archive, 'w') as zip_file:
        zip_file.writestr('../../point.roi', point_roi().tobytes())
        zip_file.writestr('empty.roi', b'')
        zip_file.writestr('not-data.txt', b'ignored')
    before = archive.stat()
    records, errors = load_rois([archive], meta)
    assert len(records) == 1 and len(errors) == 1 and 'empty.roi' in errors[0]
    assert not (tmp_path / 'point.roi').exists()
    assert (archive.stat().st_size, archive.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    wrong = ImagejRoi.frompoints([[400, 500], [600, 700]])
    wrong.roitype = ROI_TYPE.POINT
    with pytest.raises(ValueError, match='범위'):
        decode_roi(wrong.tobytes(), 'wrong.roi', meta)


def test_latest_reader_rejects_stale_results_and_uses_latest_pending(qt_app):
    worker = LatestReader()
    gate, entered = Event(), Event()
    seen = []
    def blocked():
        entered.set()
        assert gate.wait(5)
        return 'old'
    worker.ready.connect(lambda value, error: seen.append((value, error)))
    try:
        worker.submit(blocked)
        spin(qt_app, entered.is_set)
        worker.submit(lambda: 'middle')
        worker.submit(lambda: 'latest')
        gate.set()
        spin(qt_app, lambda: bool(seen))
        assert seen == [('latest', '')]
    finally:
        gate.set()
        worker.shutdown()


def test_qml_jpeg_imported_roi_overlay_pan_zoom_visibility_and_file_switch(qt_app, tmp_path):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / 'ui.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'src/sic_xrt_analyzer/ui/Main.qml')))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, 'uiState')
    path = jpeg(tmp_path / 'image.jpg', 3200, 2400)
    roi = tmp_path / 'points.roi'
    roi.write_bytes(point_roi().tobytes())
    try:
        invoke(window, 'selectImagePath', str(path))
        spin(qt_app, lambda: not state.property('loading'))
        assert state.property('imageFormat') == 'JPEG' and not bridge.analysis['sourceReady']
        assert bridge.importRois([bridge.localUrl(str(roi))])
        spin(qt_app, lambda: len(bridge.roiState['items']) == 1)
        QTest.qWait(50)
        assert window.findChild(QObject, 'inspectorPanel').property('tabIndex') == 4
        overlay = window.findChild(QObject, 'importedRoiOverlay')
        frame = window.findChild(QObject, 'imageFrame')
        viewer = window.findChild(QObject, 'imageViewer')
        assert overlay.property('imageX') == frame.property('x')
        invoke(viewer, 'zoomIn')
        viewer.setProperty('panX', 31)
        viewer.setProperty('panY', -17)
        qt_app.processEvents()
        assert overlay.property('imageX') == frame.property('x') and overlay.property('imageY') == frame.property('y')
        invoke(window.findChild(QObject, 'actualSizeAction'), 'trigger')
        spin(qt_app, lambda: bridge.detailState['ready'])
        assert bridge.detailState['width'] <= 2048 and bridge.detailState['height'] <= 2048
        assert bridge.provider.detail_image.size().width() == bridge.detailState['width']
        bridge.setDisplayRange(0, 100)
        spin(qt_app, lambda: not bridge.stack_viewer.busy and bridge.stack_viewer.frame.high == 100)
        spin(qt_app, lambda: bridge.detailState['ready'])
        assert bridge.provider.detail_image.pixelColor(10, 10).red() >= 254
        item = bridge.roiState['items'][0]
        bridge.setImportedRoiVisible(item['id'], False)
        assert not bridge.roiState['items'][0]['visible']
        bridge.setImportedRoiVisible(item['id'], True)
        button = window.findChild(QObject, 'selectImportedBoundsButton')
        origin = button.mapToScene(QPointF(button.property('width') / 2, button.property('height') / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(origin.x()), round(origin.y())))
        assert state.property('hasRoi')
        assert state.property('roiX') == 40 and state.property('roiY') == 50
        assert not window.findChild(QObject, 'runAction').property('enabled')
        second = tmp_path / 'other.tif'
        tifffile.imwrite(second, np.zeros((200, 200), np.uint16))
        invoke(window, 'selectImagePath', str(second))
        spin(qt_app, lambda: not state.property('loading'))
        assert bridge.roiState['items'] == [] and not state.property('hasRoi')
        assert not bridge.detailState['ready'] and bridge.provider.detail_image.isNull()
        assert bridge.analysis['inputSource'] == 'Original TIFF'
        assert not warnings, '\n'.join(warnings)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()


def test_roi_import_canceled_on_file_change_and_page_filtering(qt_app, tmp_path, monkeypatch):
    path = tmp_path / 'stack.tif'
    tifffile.imwrite(path, np.zeros((3, 200, 200), np.uint16), imagej=True, metadata={'axes': 'TYX'})
    stack = open_stack(path)
    frame = stack.frame(0)
    manager = RoiManager()
    roi_path = tmp_path / 'page-two.roi'
    roi_path.write_bytes(point_roi(position=2).tobytes())
    gate, entered = Event(), Event()
    from sic_xrt_analyzer.ui import roi_manager
    real_load = roi_manager.load_rois
    def paused(*args, **kwargs):
        entered.set()
        assert gate.wait(5)
        return real_load(*args, **kwargs)
    monkeypatch.setattr(roi_manager, 'load_rois', paused)
    try:
        manager.load([roi_path], frame)
        spin(qt_app, entered.is_set)
        manager.clear()
        gate.set()
        spin(qt_app, lambda: manager.reader.task is None)
        assert manager.records == [] and not manager.busy
        monkeypatch.setattr(roi_manager, 'load_rois', real_load)
        manager.load([roi_path], frame)
        spin(qt_app, lambda: bool(manager.records))
        assert not manager.view(frame)[0]['active']
        assert manager.view(stack.frame(1))[0]['active']
        assert not manager.view(stack.frame(2))[0]['active']
    finally:
        gate.set()
        manager.shutdown()
        stack.close()


def test_roi_limits_and_unsupported_subtypes_report_without_mutating_prior_list(qt_app, tmp_path):
    meta = JpegImageSource(jpeg(tmp_path / 'image.jpg')).metadata
    oversized = tmp_path / 'oversized.roi'
    with oversized.open('wb') as file:
        file.truncate(4 * 1024**2 + 1)
    records, errors = load_rois([oversized], meta)
    assert not records and errors
    roi = point_roi()
    from roifile import ROI_SUBTYPE
    roi.subtype = ROI_SUBTYPE.TEXT
    with pytest.raises(ValueError, match='하위 형식'):
        decode_roi(roi.tobytes(), 'text.roi', meta)
