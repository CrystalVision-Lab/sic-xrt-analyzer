"""Display-cache fidelity, pan reuse, invalidation and bounded ownership."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from PySide6.QtGui import QImage, QPainter

from sic_xrt_analyzer.imaging.display_pyramid import DisplayPyramid
from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def rgb(image):
    image = image.convertToFormat(QImage.Format_RGB888)
    return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*3].reshape(image.height(), image.width(), 3).copy()


def draw(view, x, y, scale):
    view.viewTransform = [-x*scale, -y*scale, scale]
    image = QImage(128, 96, QImage.Format_RGB32)
    image.fill(0xff000000)
    painter = QPainter(image)
    view.paint(painter)
    painter.end()
    return rgb(image)


@pytest.fixture
def native_view(qt_app, tmp_path):
    y, x = np.indices((600, 800))
    raw = ((x*97+y*131) % 65536).astype(np.uint16)
    path = tmp_path/'native.tif'
    tifffile.imwrite(path, raw)
    stack = open_stack(path)
    frame = stack.frame(0, (100, 60000))
    pyramid = DisplayPyramid(frame.source, raw)
    assert pyramid.prepare()
    object.__setattr__(frame.source, 'display_pyramid', pyramid)
    bridge = SimpleNamespace(stack_viewer=SimpleNamespace(frame=frame, error='', changed=SimpleNamespace(emit=lambda: None)))
    view = PreparedView()
    view.setWidth(128); view.setHeight(96); view.bridge = bridge
    try:
        yield view, bridge, pyramid, raw, path
    finally:
        pyramid.close(); stack.close()


def expected(raw, x, y, scale, low=100, high=60000):
    gray = np.clip((raw[y:y+96, x:x+128].astype(np.float64)-low)*(255/(high-low)), 0, 255).astype(np.uint8)
    gray = np.repeat(np.repeat(gray, scale, axis=0), scale, axis=1)[:96, :128]
    return np.repeat(gray[..., None], 3, axis=2)


def test_native_pixels_pan_zoom_reuse_and_boundary_refill(native_view, monkeypatch):
    view, _, pyramid, raw, _ = native_view
    calls = []
    region = pyramid.region
    def observed(*args):
        calls.append(args)
        return region(*args)
    monkeypatch.setattr(pyramid, 'region', observed)
    for scale in [1, 2, 4, 8, 4, 2, 1]:
        np.testing.assert_array_equal(draw(view, 250, 200, scale), expected(raw, 250, 200, scale))
    assert len(calls) == 1  # Same level/native rectangle across zoom commands.
    for x in range(250, 290):
        np.testing.assert_array_equal(draw(view, x, 220, 1), expected(raw, x, 220, 1))
    assert len(calls) == 1
    np.testing.assert_array_equal(draw(view, 620, 470, 1), expected(raw, 620, 470, 1))
    assert len(calls) == 2
    assert view._display_cache[5].sizeInBytes() <= view._display_cache_limit


def test_window_level_source_palette_and_closed_cache_invalidation(native_view):
    view, bridge, pyramid, raw, _ = native_view
    first = draw(view, 250, 200, 1)
    bridge.stack_viewer.frame = replace(bridge.stack_viewer.frame, low=1000, high=30000)
    np.testing.assert_array_equal(draw(view, 250, 200, 1), expected(raw, 250, 200, 1, 1000, 30000))
    assert not np.array_equal(first, draw(view, 250, 200, 1))
    palette = np.vstack([np.arange(256)*257, np.zeros(256), np.zeros(256)]).astype(np.uint16)
    object.__setattr__(pyramid.source, 'display_palette', palette)
    colored = draw(view, 250, 200, 1)
    assert np.any(colored[..., 0]) and not np.any(colored[..., 1:])
    palette[:] = palette[::-1].copy()  # Cache key detects even an in-place LUT change.
    recolored = draw(view, 250, 200, 1)
    assert not np.any(recolored[..., :2]) and np.any(recolored[..., 2])
    pyramid.close()
    assert not np.any(draw(view, 250, 200, 1))
    assert view._display_cache is None


def test_source_change_is_checked_on_a_cache_hit_and_cache_limit(native_view):
    view, bridge, _, raw, path = native_view
    view._display_cache_limit = 32
    np.testing.assert_array_equal(draw(view, 250, 200, 1), expected(raw, 250, 200, 1))
    assert view._display_cache is None
    view._display_cache_limit = 32*1024**2
    draw(view, 250, 200, 1)
    assert view._display_cache is not None
    # Test-owned synthetic fixture, never an actual XRT source.
    with path.open('ab') as file:
        file.write(b'changed')
    assert not np.any(draw(view, 250, 200, 1))
    assert 'changed' in bridge.stack_viewer.error
    assert view._display_cache is None


def test_file_switch_and_alpha_coverage_are_preserved(native_view, tmp_path):
    view, bridge, _, _, _ = native_view
    draw(view, 250, 200, 1)
    raw = np.empty((600,800,4), dtype=np.uint8)
    raw[..., :3] = [200,30,80]
    raw[..., 3] = np.arange(800, dtype=np.uint16) % 256
    path = tmp_path/'rgba.tif'
    tifffile.imwrite(path, raw, photometric='rgb', extrasamples=['unassalpha'])
    stack = open_stack(path)
    frame = stack.frame(0, (0,255))
    pyramid = DisplayPyramid(frame.source, raw)
    assert pyramid.prepare()
    object.__setattr__(frame.source, 'display_pyramid', pyramid)
    try:
        bridge.stack_viewer.frame = frame
        actual = draw(view, 250, 200, 2)
        crop = np.ascontiguousarray(raw[200:248,250:314])
        native = QImage(crop.data, 64,48,crop.strides[0],QImage.Format_RGBA8888).copy()
        expected_image = QImage(128,96,QImage.Format_RGB32); expected_image.fill(0xff000000)
        from PySide6.QtCore import QRectF
        painter = QPainter(expected_image); painter.drawImage(QRectF(0,0,128,96),native); painter.end()
        np.testing.assert_array_equal(actual, rgb(expected_image))
        assert view._display_cache[0][0] is pyramid
    finally:
        pyramid.close(); stack.close()


def test_real_image_has_no_demo_canvas_and_demo_still_loads(qt_app, tmp_path):
    from pathlib import Path

    from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
    from PySide6.QtQuickControls2 import QQuickStyle

    from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider

    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path/'prefs.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window = engine.rootObjects()[0]
    loader = window.findChild(QObject, 'demoImageLoader')
    try:
        def has_demo():
            # Inspect in QML: temporary Python wrappers for Loader-owned items
            # must not take ownership of the dynamically constructed demo.
            return QQmlExpression(engine.rootContext(), loader, 'item !== null && item.children.length > 0').evaluate()[0]
        assert not loader.property('active') and not has_demo()
        assert QMetaObject.invokeMethod(window, 'showDemo')
        qt_app.processEvents()
        assert loader.property('active') and has_demo()
        path = tmp_path/'real.tif'
        tifffile.imwrite(path, np.zeros((600,800), dtype=np.uint16))
        assert QMetaObject.invokeMethod(window, 'selectImagePath', Q_ARG('QVariant', str(path)))
        import time
        end = time.monotonic()+10
        while bridge.stack_viewer.busy and time.monotonic() < end:
            qt_app.processEvents(); time.sleep(.001)
        qt_app.processEvents()
        assert bridge.stack_viewer.frame is not None
        assert not loader.property('active') and not has_demo()
        ui = window.findChild(QObject, 'uiState')
        for scale in [1.,2.,4.,8.,16.]:
            ui.setProperty('fitMode', False); ui.setProperty('zoom', scale)
            qt_app.processEvents()
            assert not has_demo()
        assert not warnings, warnings
    finally:
        window.setProperty('allowQuit', True); window.close()
        bridge.waitForLoads(); engine.deleteLater(); qt_app.processEvents()
