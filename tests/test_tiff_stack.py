"""Synthetic multi-page and ImageJ frame stacks; no inspection data in Git."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, get_ident

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
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack, imagej_window
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.stack_controller import StackController


def spin(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Stack request timed out")


@pytest.fixture
def stack_file(tmp_path):
    path = tmp_path / "frames.tif"
    pixels = (np.arange(7 * 64 * 96).reshape(7, 64, 96) + 1000).astype(np.uint16)
    tifffile.imwrite(path, pixels, imagej=True, metadata={"axes": "TYX", "min": 1000, "max": 50000})
    return path, pixels


@pytest.mark.parametrize("imagej,truncated,compressed", [(False, False, False), (False, False, True),
                                                        (True, False, False), (True, True, False)])
def test_first_middle_last_raw_pages_and_readonly(tmp_path, imagej, truncated, compressed):
    path = tmp_path / "stack.tif"
    raw = (np.arange(5 * 32 * 48).reshape(5, 32, 48) + 700).astype(np.uint16)
    if imagej:
        tifffile.imwrite(path, raw, imagej=True, truncate=truncated,
                         metadata={"axes": "TYX", "min": 100, "max": 5000})
    else:
        with tifffile.TiffWriter(path, bigtiff=True) as writer:
            for page in raw:
                writer.write(page, compression="deflate" if compressed else None)
    original_bytes, stat = path.read_bytes(), path.stat()
    stack = TiffStack(path)
    try:
        assert stack.page_count == 5
        # A recovered reader may first request the middle page; its default range is still page one.
        middle_first = stack.frame(2)
        if not imagej:
            np.testing.assert_allclose((middle_first.default_low, middle_first.default_high), np.percentile(raw[0], (1, 99)))
        for page in (0, 2, 4):
            frame = stack.frame(page)
            assert frame.source.metadata.dtype == "uint16"
            assert (frame.source.metadata.width, frame.source.metadata.height) == (48, 32)
            np.testing.assert_array_equal(frame.pixels, raw[page])
            assert not frame.pixels.flags.writeable
            np.testing.assert_array_equal(frame.source.read_region(5, 6, 8, 9), raw[page, 6:15, 5:13])
            assert frame.source.identity.page_index == page
            if imagej:
                assert (frame.low, frame.high) == (100, 5000) and frame.imagej_frames == 5
        assert path.read_bytes() == original_bytes
        assert path.stat().st_mtime_ns == stat.st_mtime_ns
        with pytest.raises(ValueError):
            stack.read_page(5)
    finally:
        stack.close()


def test_cache_and_window_never_change_or_redecode_raw(stack_file):
    path, raw = stack_file
    stack = TiffStack(path, max_cache_bytes=raw[0].nbytes * 2, max_cache_pages=3)
    try:
        first = stack.frame(0)
        initial_pixel = first.preview.image.pixelColor(30, 20).red()
        changed = stack.frame(0, (1000, 7000))
        assert changed.preview.image.pixelColor(30, 20).red() != initial_pixel
        np.testing.assert_array_equal(changed.pixels, raw[0])
        assert stack.decode_count == 1
        stack.frame(1)
        stack.frame(2)
        assert list(stack.cache) == [1, 2]
        assert stack.cache_bytes <= raw[0].nbytes * 2
        stack.frame(0)
        assert stack.decode_count == 4
        assert stack.cache_bytes <= stack.max_cache_bytes and len(stack.cache) <= stack.max_cache_pages
    finally:
        stack.close()
    assert stack.closed and not stack.cache and stack.cache_bytes == 0


@pytest.mark.parametrize("metadata,expected", [({"min": "200", "max": "6000"}, (200, 6000)),
                                               ({"Ranges": [123, 456]}, (123, 456)),
                                               ({"Ranges": [[100, 500]]}, (100, 500)),
                                               ({"min": 200, "max": 100}, None),
                                               ({"Ranges": [[1], [2, 3]]}, None),
                                               ({"min": np.nan, "max": 6000}, None)])
def test_imagej_display_range_parsing(metadata, expected):
    assert imagej_window(metadata) == expected


def test_readonly_validation_tool(stack_file):
    path, _ = stack_file
    script = Path(__file__).parents[1] / "tools/validate_tiff_stack.py"
    result = subprocess.run([sys.executable, str(script), "--folder", str(path.parent), "--files", path.name],
                            capture_output=True, text=True, encoding="utf-8", timeout=20,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)["files"][0]
    assert report["status"] == "PASS", report
    assert (report["width"], report["height"], report["pages"]) == (96, 64, 7)
    assert [r["page"] for r in report["checks"]] == [1, 4, 7]
    assert report["source_stat_unchanged"]
    assert all(r["contrast_changed"] and r["raw_equal"] for r in report["checks"])


def test_validation_reports_missing_real_files_without_claiming_pass(tmp_path):
    script = Path(__file__).parents[1] / "tools/validate_tiff_stack.py"
    result = subprocess.run([sys.executable, str(script), "--folder", str(tmp_path)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False)
    assert result.returncode == 1, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "PARTIAL"
    reports = report["files"]
    assert len(reports) == 4 and all(r["status"] == "NOT_RUN" for r in reports)


def test_latest_page_request_only_and_file_cache_cleanup(qt_app, stack_file, tmp_path, monkeypatch):
    path, _ = stack_file
    controller = StackController()
    gate, entered = Event(), Event()
    calls, threads = [], []
    actual = TiffStack.read_page
    def blocked_read(stack, index):
        calls.append(index)
        threads.append(get_ident())
        if index == 1:
            entered.set()
            assert gate.wait(5)
        return actual(stack, index)
    monkeypatch.setattr(TiffStack, "read_page", blocked_read)
    frames = []
    controller.frameReady.connect(lambda f, opening: frames.append(f.source.page_index))
    try:
        controller.open(str(path))
        spin(qt_app, lambda: not controller.busy)
        original_stack = controller._reader.stack
        controller.page(1)
        spin(qt_app, entered.is_set)
        for page in (2, 3, 4, 5, 6):
            controller.page(page)
        # GUI events remain serviceable while the reader is deliberately blocked.
        qt_app.processEvents()
        gate.set()
        spin(qt_app, lambda: not controller.busy)
        assert calls == [0, 1, 6] and frames == [0, 6]
        assert all(t != get_ident() for t in threads)
        other = tmp_path / "other.tif"
        tifffile.imwrite(other, np.ones((32, 32), np.uint16) * 1234)
        controller.open(str(other))
        spin(qt_app, lambda: not controller.busy)
        assert original_stack.closed and original_stack.cache_bytes == 0
        assert controller.frame.source.path == str(other.resolve())
        assert controller.pixel_value(0, 0) == "1234"
        assert controller.pixel_value(-1, 0) == ""
        current_stack = controller._reader.stack
        controller.clear()
        assert controller.frame is None and current_stack.closed
    finally:
        gate.set()
        controller.shutdown()


def test_file_switch_discards_busy_old_frame(qt_app, stack_file, tmp_path, monkeypatch):
    path, _ = stack_file
    controller = StackController()
    gate, entered = Event(), Event()
    actual = TiffStack.read_page
    old_stacks, published = [], []
    def block(stack, page):
        if stack.path == str(path.resolve()):
            old_stacks.append(stack)
            entered.set()
            assert gate.wait(5)
        return actual(stack, page)
    monkeypatch.setattr(TiffStack, "read_page", block)
    controller.frameReady.connect(lambda f, opening: published.append(f.source.path))
    other = tmp_path / "other.tif"
    tifffile.imwrite(other, np.full((16, 20), 4321, np.uint16))
    try:
        controller.open(str(path))
        spin(qt_app, entered.is_set)
        controller.open(str(other))
        gate.set()
        spin(qt_app, lambda: not controller.busy)
        assert published == [str(other.resolve())]
        assert old_stacks[0].closed and not old_stacks[0].cache
        assert controller.pixel_value(0, 0) == "4321"
    finally:
        gate.set()
        controller.shutdown()


def test_error_preserves_display_and_detects_source_change(qt_app, stack_file, tmp_path):
    path, _ = stack_file
    controller = StackController()
    try:
        controller.open(str(path))
        spin(qt_app, lambda: not controller.busy)
        previous = controller.frame
        controller.open(str(tmp_path / "missing.tif"))
        spin(qt_app, lambda: not controller.busy)
        assert controller.error and controller.frame is previous
        assert not controller.display_range(2, 1)
        assert controller.frame is previous
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        with pytest.raises(ValueError):
            previous.source.read_full()
    finally:
        controller.shutdown()


def test_qml_stack_navigation_contrast_pixel_and_view(qt_app, stack_file, tmp_path):
    path, pixels = stack_file
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    errors = []
    engine.warnings.connect(lambda items: errors.extend(item.toString() for item in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    viewer = window.findChild(QObject, "imageViewer")
    def invoke(obj, name, *args):
        assert QMetaObject.invokeMethod(obj, name, *(Q_ARG("QVariant", arg) for arg in args))
    def wait_page(index):
        spin(qt_app, lambda: not bridge.stack_viewer.busy and state.property("pageIndex") == index)
    try:
        invoke(window, "selectImagePath", str(path))
        spin(qt_app, lambda: not state.property("loading"))
        assert state.property("dtype") == "uint16" and state.property("pageCount") == 7
        assert bridge.stackState["frames"] == 7 and bridge.stackState["low"] == 1000
        slider = window.findChild(QObject, "pageSlider")
        slider.setProperty("value", 3)
        invoke(slider, "moved")
        wait_page(3)
        invoke(viewer, "focusView")
        QTest.keyClick(window, Qt.Key_Right)
        wait_page(4)
        QTest.keyClick(window, Qt.Key_End)
        wait_page(6)
        QTest.keyClick(window, Qt.Key_Home)
        wait_page(0)

        viewport = window.findChild(QObject, "viewerViewport")
        frame = window.findChild(QObject, "imageFrame")
        origin = viewport.mapToScene(QPointF(0, 0))
        pos = QPoint(int(origin.x() + viewport.property("width") / 2), int(origin.y() + viewport.property("height") / 2))
        wheel = QWheelEvent(QPointF(pos), QPointF(pos), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        qt_app.sendEvent(window, wheel)
        wait_page(1)
        zoom = state.property("effectiveZoom")
        wheel = QWheelEvent(QPointF(pos), QPointF(pos), QPoint(0, 0), QPoint(0, 120), Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False)
        qt_app.sendEvent(window, wheel)
        assert state.property("effectiveZoom") > zoom
        invoke(viewer, "fitView")
        assert state.property("zoomLabel") == "FIT"
        QTest.mouseMove(window, pos)
        qt_app.processEvents()
        x, y = state.property("cursorX"), state.property("cursorY")
        assert x >= 0 and y >= 0
        assert state.property("cursorValue") == str(pixels[1, y, x])
        value = bridge.pixelValue(x, y)
        before = provider.image.pixelColor(x, y).red()
        low = window.findChild(QObject, "displayLowSlider")
        high = window.findChild(QObject, "displayHighSlider")
        low.setProperty("value", 0)
        invoke(low, "moved")
        high.setProperty("value", 20000)
        invoke(high, "moved")
        spin(qt_app, lambda: not bridge.stack_viewer.busy)
        assert provider.image.pixelColor(x, y).red() != before
        assert bridge.pixelValue(x, y) == value
        np.testing.assert_array_equal(bridge.stack_viewer.frame.pixels, pixels[1])
        assert frame.property("width") > 0
        window.resize(1100, 700)
        qt_app.processEvents()
        assert viewer.property("viewportWidth") > 500
        controls = window.findChild(QObject, "stackControls")
        assert controls.property("width") <= viewer.property("width")
        assert not errors, "\n".join(errors)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()
