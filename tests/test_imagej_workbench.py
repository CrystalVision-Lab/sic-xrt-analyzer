"""Pixel fidelity, tool ROI interchange and actual embedded macro/plugin execution."""
import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from roifile import ROI_SUBTYPE, ROI_TYPE, ImagejRoi
from test_analysis_pipeline import spin
from test_prepared_roi_editor import invoke

from sic_xrt_analyzer.imaging.display_pyramid import DisplayPyramid
from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import decode_roi
from sic_xrt_analyzer.imaging.imagej_runtime import runtime_directory
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.imaging.roi_edit import encode_roi
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def test_area_pyramid_has_screen_resolution_and_native_exact_pixels(tmp_path):
    pixels = np.random.default_rng(19).integers(0, 65536, (1025, 1031), dtype=np.uint16)
    path = tmp_path / 'source.tif'
    tifffile.imwrite(path, pixels)
    before = hashlib.sha256(path.read_bytes()).digest()
    pyramid = DisplayPyramid(OriginalImageSource(path))
    cache = Path(pyramid.directory.name)
    try:
        assert pyramid.prepare()
        for scale in (.03125, .1, .25, .5, .75, 1, 2, 16):
            region, _x, _y, factor = pyramid.region(scale, 16, 16, 800, 800)
            assert scale * factor <= 1 or factor == 1
            if scale >= 1:
                np.testing.assert_array_equal(region, pixels[16:816, 16:816])
        expected = np.rint(pixels[:1024, :1030].astype(np.float32).reshape(512, 2, 515, 2).mean(axis=(1,3))).astype(np.uint16)
        np.testing.assert_array_equal(pyramid.levels[1][:512, :515], expected)
    finally:
        pyramid.close()
    assert not cache.exists() and hashlib.sha256(path.read_bytes()).digest() == before


def test_prepared_painter_never_falls_back_or_redecodes(qt_app, tmp_path, monkeypatch):
    from sic_xrt_analyzer.imaging.image_stack import SampledImageStack
    path = tmp_path / 'pixels.tif'
    pixels = np.indices((3000, 3000)).sum(axis=0).astype(np.uint16) % 2 * 65535
    tifffile.imwrite(path, pixels)
    stack = SampledImageStack(OriginalImageSource(path))
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    view = PreparedView()
    try:
        assert stack.prepare_native()
        frame = stack.frame(0, (0, 65535))
        bridge.stack_viewer.frame = frame
        view.bridge = bridge
        view.setWidth(256); view.setHeight(256)
        def forbidden(*args, **kwargs):
            raise AssertionError('No decode or original region IO during zoom')
        monkeypatch.setattr(OriginalImageSource, 'read_region', forbidden)
        for scale in (.125, .25, .5, 1, 2, 8):
            view.viewTransform = [0., 0., scale]
            image = QImage(256, 256, QImage.Format_RGB32)
            image.fill(Qt.magenta)
            painter = QPainter(image)
            view.paint(painter)
            painter.end()
            if scale < 1:
                assert abs(image.pixelColor(100, 100).red() - 128) <= 1
            else:
                for x in range(8):
                    assert image.pixelColor(x, 0).red() == int(pixels[0, int(x / scale)] // 257)
    finally:
        bridge.waitForLoads(); stack.close()


@pytest.fixture(scope='module')
def imagej():
    pytest.importorskip('jpype')
    if not (runtime_directory() / 'ij-1.54p.jar').is_file():
        pytest.skip('Run tools/setup_imagej.py for embedded ImageJ integration tests')
    runtime = ImageJClient()
    yield runtime
    runtime.close()


def test_real_ijm_measurement_histogram_profile_and_source_unchanged(imagej, tmp_path):
    pixels = np.arange(1024, dtype=np.uint16).reshape(32,32)
    path = tmp_path / 'original.tif'
    tifffile.imwrite(path, pixels)
    original = path.read_bytes()
    stack = open_stack(path)
    try:
        frame = stack.frame(0)
        result = imagej.run(frame, macro='run("Invert"); run("Gaussian Blur...", "sigma=1"); run("Measure");')
        out = tifffile.imread(result['path'])
        assert out.dtype == np.uint16 and out.shape == pixels.shape
        assert 480 < float(out.mean()) < 540 and result['rows'] and 'Mean' in result['headings']
        histogram = imagej.statistics(frame, None, 'Histogram')
        assert sum(histogram['plot']) == 1024
        assert len(imagej.commands()) >= 400
        assert imagej.wand(frame, 5, 5, 20)
        with pytest.raises(RuntimeError):
            imagej.run(frame, macro='this_is_not_a_macro_function();')
    finally:
        stack.close()
    assert path.read_bytes() == original


def test_java_plugin_runs_inside_same_jvm_and_multi_page_macro_result(imagej, tmp_path):
    directory = tmp_path / 'plugins'
    directory.mkdir()
    code = directory / 'Test_Native_Plugin.java'
    code.write_text('import ij.IJ; import ij.plugin.PlugIn; public class Test_Native_Plugin implements PlugIn { public void run(String arg) { IJ.getImage().getProcessor().add(10); } }')
    subprocess.run(['javac', '-cp', str(runtime_directory() / 'ij-1.54p.jar'), str(code)], check=True, capture_output=True)
    filter_code = directory / 'Test_Native_Filter.java'
    filter_code.write_text('import ij.ImagePlus; import ij.plugin.filter.PlugInFilter; import ij.process.ImageProcessor; public class Test_Native_Filter implements PlugInFilter { public int setup(String arg, ImagePlus imp) { return DOES_8G; } public void run(ImageProcessor ip) { ip.add(5); } }')
    subprocess.run(['javac', '-cp', str(runtime_directory() / 'ij-1.54p.jar'), str(filter_code)], check=True, capture_output=True)
    imagej.add_classpath(str(directory))
    path = tmp_path / 'plugin-source.tif'
    tifffile.imwrite(path, np.full((16,16), 20, np.uint8))
    stack = open_stack(path)
    try:
        result = imagej.run(stack.frame(0), plugin='Test_Native_Plugin')
        assert np.all(tifffile.imread(result['path']) == 30)
        result = imagej.run(stack.frame(0), plugin='Test_Native_Filter')
        assert np.all(tifffile.imread(result['path']) == 35)
        result = imagej.run(stack.frame(0), macro='newImage("pages", "16-bit black", 8, 8, 3); for(i=1;i<=3;i++) { setSlice(i); setPixel(0,0,i*100); }')
        with tifffile.TiffFile(result['path']) as tif:
            assert len(tif.pages) == 3
            assert [int(p.asarray()[0,0]) for p in tif.pages] == [100,200,300]
        pages = open_stack(result['path'])
        try:
            projection = imagej.run(pages.frame(0), command='Z Project...', options='projection=[Max Intensity]', whole_stack=True)
            assert projection['pages'] == 1
            assert int(tifffile.imread(projection['path'])[0,0]) == 300
        finally:
            pages.close()
    finally:
        stack.close()


def test_bigtiff_page_axis_projection_preserves_original(imagej, tmp_path):
    path = tmp_path / 'bigtiff-stack.tif'
    raw = np.stack([np.full((24,32), v, np.uint16) for v in (100, 200, 300)])
    tifffile.imwrite(path, raw, bigtiff=True, photometric='minisblack')
    original = path.read_bytes()
    stack = open_stack(path)
    try:
        result = imagej.run(stack.frame(0), command='Z Project...', options='projection=[Max Intensity]', whole_stack=True)
        assert result['pages'] == 1
        np.testing.assert_array_equal(tifffile.imread(result['path']), raw[2])
    finally:
        stack.close()
    assert path.read_bytes() == original


def test_image_and_measurement_exports_refuse_overwrite(qt_app, tmp_path):
    path = tmp_path / 'readonly-source.tif'
    tifffile.imwrite(path, np.full((10,12), 55, np.uint16))
    original = path.read_bytes()
    stack = open_stack(path)
    bridge = FileBridge(settings=QSettings(str(tmp_path/'save.ini'), QSettings.IniFormat))
    bridge.stack_viewer.frame = stack.frame(0)
    workbench = bridge.workbench
    try:
        copy = tmp_path / 'working-copy.tif'
        workbench.saveImageCopy(bridge.localUrl(str(copy)))
        spin(qt_app, lambda: not workbench.busy)
        assert not workbench.error and copy.read_bytes() == original
        workbench.saveImageCopy(bridge.localUrl(str(path)))
        spin(qt_app, lambda: not workbench.busy)
        assert workbench.error and path.read_bytes() == original
        workbench.headings, workbench.rows = 'Area\tMean', ['120\t55']
        table = tmp_path / 'results.tsv'
        workbench.saveResults(bridge.localUrl(str(table)))
        spin(qt_app, lambda: not workbench.busy)
        assert table.read_text(encoding='utf-8-sig') == 'Area\tMean\n120\t55\n'
        workbench.rows = ['1\t99']
        workbench.saveResults(bridge.localUrl(str(table)))
        spin(qt_app, lambda: not workbench.busy)
        assert workbench.error and '120\t55' in table.read_text(encoding='utf-8-sig')
    finally:
        bridge.waitForLoads(); stack.close()


def test_toolbar_gestures_export_native_roi_types(qt_app, tmp_path):
    path = tmp_path / 'tools.tif'
    tifffile.imwrite(path, np.zeros((300,300), np.uint16))
    bridge = FileBridge(settings=QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    stack = open_stack(path)
    bridge.stack_viewer.frame = stack.frame(0)
    workbench = bridge.workbench
    gestures = {'Rectangle': [[10,20],[80,90]], 'Oval': [[20,20],[100,100]], 'Polygon': [[10,10],[20,10],[20,20]],
                'Freehand': [[10,10],[20,10],[20,20],[15,18]], 'Line': [[10,10],[40,40]],
                'Polyline': [[10,10],[20,20],[20,40]], 'FreeLine': [[10,10],[20,20],[15,20]],
                'Angle': [[10,10],[20,20],[30,10]], 'Point': [[15,15]], 'Text': [[15,15]], 'Arrow': [[20,20],[80,80]]}
    try:
        for tool, points in gestures.items():
            workbench.gesture(tool, points)
            assert not workbench.error, workbench.error
            record = bridge.roi_manager.records[-1]
            roi = ImagejRoi.frombytes(encode_roi(record))
            expected = {'Rectangle':ROI_TYPE.RECT,'Oval':ROI_TYPE.OVAL,'Text':ROI_TYPE.RECT,'Arrow':ROI_TYPE.LINE,'Angle':ROI_TYPE.ANGLE}
            if tool in expected:
                assert roi.roitype == expected[tool]
            restored = decode_roi(encode_roi(record), tool+'.roi', stack.first_source.metadata)
            assert restored.kind == record.kind
            if tool in ('Text','Arrow'):
                assert roi.subtype == (ROI_SUBTYPE.TEXT if tool == 'Text' else ROI_SUBTYPE.ARROW)
                assert restored.tool == tool
        bridge.roi_manager.history()
        assert len(bridge.roi_manager.records) == len(gestures) - 1
    finally:
        bridge.waitForLoads(); stack.close()


def test_qml_toolbar_rectangle_oval_and_polygon_mouse(qt_app, tmp_path):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff',provider)
    engine.rootContext().setContextProperty('fileBridge',bridge)
    warnings=[]
    engine.warnings.connect(lambda items: warnings.extend(x.toString() for x in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'src/sic_xrt_analyzer/ui/Main.qml')))
    window=engine.rootObjects()[0]
    state=window.findChild(QObject,'uiState')
    path=tmp_path / 'mouse.tif'
    tifffile.imwrite(path,np.zeros((2,200,200),np.uint16),photometric='minisblack')
    try:
        invoke(window,'selectImagePath',str(path))
        spin(qt_app,lambda: not state.property('loading') and not bridge.stack_viewer.initial_loading)
        mouse=window.findChild(QObject,'viewerMouseArea')
        frame=window.findChild(QObject,'imageFrame')
        scale=window.findChild(QObject,'imageViewer').property('displayScale')
        def at(x,y):
            p=mouse.mapToScene(__import__('PySide6.QtCore',fromlist=['QPointF']).QPointF(frame.property('x')+x*scale,frame.property('y')+y*scale))
            return QPoint(round(p.x()),round(p.y()))
        for tool in ('Rectangle','Oval'):
            state.setProperty('activeTool',tool)
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,at(10,20))
            QTest.mouseMove(window,at(50,60),10)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,at(50,60))
            assert bridge.roi_manager.records[-1].tool == tool
        state.setProperty('activeTool','Polygon')
        for x,y in ((70,70),(100,70),(100,100)):
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,at(x,y))
        QTest.keyClick(window,Qt.Key_Return)
        assert bridge.roi_manager.records[-1].kind == 'polygon'
        window.setWidth(1100);window.setHeight(700);QTest.qWait(40)
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)
        # Annotation tools now live in the measurement dropdown.
        invoke(window.findChild(QObject, 'measurementToolDropdown'), 'clicked')
        QTest.qWait(40)
        # Keep the complete scene's Python wrappers alive while pumping Qt events.
        scene = list(visual_items(window.contentItem()))
        arrow = next(i for i in scene if i.objectName() == 'measurementArrow')
        assert arrow.isVisible() and arrow.mapToScene(__import__('PySide6.QtCore',fromlist=['QPointF']).QPointF()).x() + arrow.width() < 1100
        assert not warnings, '\n'.join(warnings)
    finally:
        window.setProperty('allowQuit',True);window.close();bridge.waitForLoads();engine.deleteLater();qt_app.processEvents()


def test_stack_page_display_is_prepared_at_native_resolution_before_scrub(qt_app, tmp_path):
    path = tmp_path / 'prepared-stack.tif'
    raw = np.random.default_rng(42).integers(0,65536,(3,1100,1100),dtype=np.uint16)
    tifffile.imwrite(path,raw,imagej=True,metadata={'axes':'TYX'})
    bridge = FileBridge(settings=QSettings(str(tmp_path/'stack.ini'),QSettings.IniFormat))
    try:
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(qt_app,lambda: not bridge.stack_viewer.initial_loading and bridge.stack_viewer._task is None)
        group = bridge.stack_viewer.frame.source.display_group
        assert len(group.pages) == 3
        bridge.beginScrub()
        for index in (2,1,0,2):
            assert bridge.requestPage(index)
            pyramid = bridge.stack_viewer.frame.source.display_pyramid
            pixels, _x, _y, factor = pyramid.region(1,10,20,100,100)
            assert factor == 1
            np.testing.assert_array_equal(pixels,raw[index,20:120,10:110])
            assert not pyramid.closed
        bridge.clearImage()
        assert group.closed and not group.pages
    finally:
        bridge.waitForLoads()


def test_lut_is_display_only_and_raw_values_survive(imagej, tmp_path):
    path=tmp_path/'gray-lut.tif'
    raw=np.arange(256,dtype=np.uint8).reshape(16,16)
    tifffile.imwrite(path,raw)
    stack=open_stack(path)
    try:
        result=imagej.run(stack.frame(0),command='Fire')
        derived=open_stack(result['path'])
        try:
            frame=derived.frame(0,(0,255))
            np.testing.assert_array_equal(frame.pixels,raw)
            assert frame.preview.image.pixelColor(12,12).red() != int(raw[12,12])
        finally:
            derived.close()
    finally:
        stack.close()
    path = tmp_path/'gray16-lut.tif'
    raw = (raw.astype(np.uint16) * 15)
    tifffile.imwrite(path,raw,imagej=True,metadata={'min':0,'max':4000})
    stack = open_stack(path)
    try:
        result = imagej.run(stack.frame(0), command='Fire')
        derived = open_stack(result['path'])
        try:
            frame = derived.frame(0)
            np.testing.assert_array_equal(frame.pixels,raw)
            assert (frame.low,frame.high) == (0,4000)
            assert frame.source.display_palette.shape == (3,256)
            assert frame.preview.image.pixelColor(12,12).red() != round(int(raw[12,12])*255/4000)
        finally:
            derived.close()
    finally:
        stack.close()


def test_brush_fill_and_line_profile_use_working_pixels(imagej, tmp_path):
    path = tmp_path/'drawing.tif'
    raw = np.zeros((32,32), np.uint8)
    tifffile.imwrite(path, raw)
    original = path.read_bytes()
    stack = open_stack(path)
    try:
        frame = stack.frame(0)
        result = imagej.run(frame, edit=('Brush', [[5,5],[20,5]], '#ffffff', 1, '', 0))
        pixels = tifffile.imread(result['path'])
        assert pixels[5,10] == 255 and pixels[10,10] == 0
        result = imagej.run(frame, edit=('Fill', [[10,10]], '#ff0000', 1, '', 0))
        pixels = tifffile.imread(result['path'])
        assert 0 < pixels[10,10] < 255 and pixels[5,10] == 255
        record = __import__('sic_xrt_analyzer.imaging.imagej_roi', fromlist=['ImportedRoi']).ImportedRoi(
            'line', 'line', 'line', (((5,5),(20,5)),), '#ffffff', (5,5,16,1), None, 'Line')
        profile = imagej.statistics(frame, record, 'Profile')
        assert len(profile['plot']) >= 15 and all(v == 255 for v in profile['plot'])
    finally:
        stack.close()
    assert path.read_bytes() == original


def test_running_macro_can_be_cancelled_and_engine_restarted(imagej, tmp_path):
    client = ImageJClient()
    path = tmp_path/'cancel-source.tif'
    tifffile.imwrite(path, np.zeros((16,16), np.uint8))
    stack = open_stack(path)
    try:
        assert len(client.commands()) >= 400
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client.run, stack.frame(0), macro='while(true) {}')
            time.sleep(.2)
            client.abort()
            with pytest.raises(RuntimeError):
                future.result(timeout=5)
        assert len(client.commands()) >= 400
    finally:
        client.close(); stack.close()


def test_closing_stack_during_preparation_releases_late_pyramid(tmp_path, monkeypatch):
    path = tmp_path/'closing-stack.tif'
    tifffile.imwrite(path, np.zeros((2,1100,1100), np.uint16), photometric='minisblack')
    stack = open_stack(path, browse_enabled=True)
    frame = stack.frame(0)
    entered, finish = Event(), Event()
    original_prepare = DisplayPyramid.prepare
    directories = []
    def paused(pyramid, *args, **kwargs):
        ready = original_prepare(pyramid, *args, **kwargs)
        directories.append(Path(pyramid.directory.name))
        entered.set()
        assert finish.wait(5)
        return ready
    monkeypatch.setattr(DisplayPyramid, 'prepare', paused)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(stack.prepare_browse, 1, (frame.low,frame.high))
            assert entered.wait(5)
            stack.display_group.close()
            finish.set()
            future.result(timeout=5)
        assert stack.display_group.closed and not stack.display_group.pages
        assert all(not directory.exists() for directory in directories)
    finally:
        finish.set(); stack.close()
