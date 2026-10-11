"""All-page preparation and live pressed-slider navigation; synthetic data only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

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

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.stack_controller import StackController


def spin(app, predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.002)
    raise AssertionError("Stack preparation timed out")


@pytest.fixture
def browse_file(tmp_path):
    path = tmp_path / "synthetic_browse.tif"
    raw = (np.arange(20 * 64 * 96).reshape(20, 64, 96) % 50000 + 1000).astype(np.uint16)
    tifffile.imwrite(path, raw, imagej=True, metadata={"axes": "TYX", "min": 1000, "max": 60000})
    return path, raw


@pytest.mark.parametrize("budget", [1000, 8000, 256000])
def test_all_page_cache_scales_to_budget_and_keeps_samples_readonly(browse_file, budget):
    path, raw = browse_file
    original = path.read_bytes()
    stack = TiffStack(path, browse_enabled=True, browse_max_bytes=budget)
    try:
        template = stack.frame(0)
        for index in range(stack.page_count):
            stack.prepare_browse(index, (template.low, template.high))
        cache = stack.browse
        assert len(cache.indices) == 20 and cache.bytes <= budget
        assert len(stack.cache) <= 3 and stack.cache_bytes <= stack.max_cache_bytes
        assert cache.bytes == sum(e.samples.nbytes + e.preview.image.sizeInBytes() for e in cache._pages.values())
        for index in (0, 11, 19):
            entry = cache._pages[index]
            np.testing.assert_array_equal(entry.samples, raw[index, ::cache.step, ::cache.step])
            assert not entry.samples.flags.writeable and entry.samples.dtype == np.uint16
        first = stack.browse_frame(11, template, (1000, 60000))
        changed = stack.browse_frame(11, template, (1000, 30000))
        assert first.pixels is changed.pixels is None
        assert first.preview.image.pixelColor(0, 0) != changed.preview.image.pixelColor(0, 0)
        assert stack.browse_frame(11, template, (1000, 30000)).preview.image == changed.preview.image
        assert cache.bytes <= budget
        assert path.read_bytes() == original
    finally:
        stack.close()
    assert cache.closed and cache.bytes == 0 and not cache.indices


def test_all_pages_scrub_immediately_without_reads_and_release_restores_raw(qt_app, browse_file, monkeypatch):
    path, raw = browse_file
    controller = StackController()
    try:
        controller.open(str(path))
        spin(qt_app, lambda: controller.preload_state["ready"] and controller._task is None)
        stack = controller._reader.stack
        reads = []
        actual = TiffStack.read_page
        def counted(stack, index):
            reads.append(index)
            return actual(stack, index)
        monkeypatch.setattr(TiffStack, "read_page", counted)
        controller.begin_scrub()
        for index in [19, 3, 15, 7, 2, 18, *range(19, -1, -1), 11]:
            assert controller.page(index)
            assert not controller.busy and controller.frame.source.page_index == index
            assert controller.frame.pixels is None and controller.pixel_value(0, 0) == ""
            expected = int(np.clip((int(raw[index, 0, 0]) - 1000) * (255 / 59000), 0, 255))
            assert controller.frame.preview.image.pixelColor(0, 0).red() == expected
            qt_app.processEvents()
        assert reads == []
        controller.end_scrub()
        spin(qt_app, lambda: controller.frame.pixels is not None and not controller.detail_busy)
        assert reads == [11]
        np.testing.assert_array_equal(controller.frame.pixels, raw[11])
        assert controller.pixel_value(0, 0) == str(raw[11, 0, 0])
        count = len(stack.browse.indices)
        controller.display_range(1000, 30000)
        spin(qt_app, lambda: not controller.busy)
        controller.begin_scrub()
        controller.page(1)
        assert (controller.frame.low, controller.frame.high) == (1000, 30000)
        assert len(stack.browse.indices) == count  # Contrast keeps every cached page.
        expected = int(np.clip((int(raw[1, 0, 0]) - 1000) * (255 / 29000), 0, 255))
        assert controller.frame.preview.image.pixelColor(0, 0).red() == expected
    finally:
        controller.shutdown()
    assert stack.browse.bytes == stack.cache_bytes == 0


def test_new_drag_discards_previous_detail_read(qt_app, browse_file, monkeypatch):
    path, raw = browse_file
    controller = StackController()
    gate, entered = Event(), Event()
    originals = []
    controller.frameReady.connect(lambda f, opening: originals.append(f.source.page_index) if f.pixels is not None else None)
    try:
        controller.open(str(path))
        spin(qt_app, lambda: controller.preload_state["ready"] and controller._task is None)
        actual = TiffStack.read_page
        def block(stack, index):
            if index == 2:
                entered.set()
                assert gate.wait(5)
            return actual(stack, index)
        monkeypatch.setattr(TiffStack, "read_page", block)
        controller.begin_scrub()
        controller.page(2)
        controller.end_scrub()
        spin(qt_app, entered.is_set)
        controller.begin_scrub()
        controller.page(17)
        assert controller.frame.source.page_index == 17 and controller.frame.pixels is None
        controller.end_scrub()
        gate.set()
        spin(qt_app, lambda: not controller.detail_busy)
        assert originals == [0, 17]
        np.testing.assert_array_equal(controller.frame.pixels, raw[17])
    finally:
        gate.set()
        controller.shutdown()


def test_preload_error_is_visible_and_retry_continues(qt_app, browse_file, monkeypatch):
    path, _ = browse_file
    controller = StackController()
    actual = TiffStack.read_page
    fail = True
    def interrupted(stack, index):
        if index == 4 and fail:
            raise ValueError("Synthetic read error")
        return actual(stack, index)
    monkeypatch.setattr(TiffStack, "read_page", interrupted)
    try:
        controller.open(str(path))
        spin(qt_app, lambda: bool(controller.preload_error) and controller._task is None)
        assert controller.preload_state["prepared"] == 4
        assert controller.frame.source.page_index == 0 and not controller.busy
        fail = False
        controller.retry_preload()
        spin(qt_app, lambda: controller.preload_state["ready"])
        assert controller.preload_error == ""
    finally:
        controller.shutdown()


def test_changed_source_during_scrub_never_reports_old_raw(qt_app, browse_file):
    path, _ = browse_file
    controller = StackController()
    try:
        controller.open(str(path))
        spin(qt_app, lambda: controller.preload_state["ready"] and controller._task is None)
        controller.begin_scrub()
        controller.page(9)
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        controller.end_scrub()
        spin(qt_app, lambda: bool(controller.error) and not controller.detail_busy)
        assert controller.frame.source.page_index == 9 and controller.frame.pixels is None
        assert controller.pixel_value(0, 0) == ""
    finally:
        controller.shutdown()


def test_whole_stack_benchmark_cli_reports_no_reads_during_scrub(browse_file):
    path, _ = browse_file
    script = Path(__file__).parents[1] / "tools/benchmark_tiff_scroll.py"
    result = subprocess.run([sys.executable, str(script), "--path", str(path), "--all-pages", "--repeats", "1"],
                            capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["pages"] == 20 and report["scrub_additional_decodes"] == 0
    assert report["all_page_scrub_publication_ms"]["samples"] == 40
    assert report["browse_cache_bytes"] <= report["browse_cache_limit_bytes"]
    assert report["released_page_raw_restored"] and report["source_stat_unchanged"]


def test_file_switch_during_whole_preload_clears_samples(qt_app, browse_file, tmp_path, monkeypatch):
    path, _ = browse_file
    other = tmp_path / "other.tif"
    tifffile.imwrite(other, np.full((3, 16, 24), 4321, np.uint16), photometric="minisblack")
    controller = StackController()
    gate, entered = Event(), Event()
    actual = TiffStack.read_page
    def block(stack, index):
        if stack.path == str(path.resolve()) and index == 4:
            entered.set()
            assert gate.wait(5)
        return actual(stack, index)
    monkeypatch.setattr(TiffStack, "read_page", block)
    try:
        controller.open(str(path))
        spin(qt_app, entered.is_set)
        old_stack = controller._reader.stack
        assert old_stack.browse.bytes > 0
        controller.begin_scrub()
        assert not controller.page(2) and not controller.scrubbing
        assert controller.initial_loading and controller.frame.source.page_index == 0
        controller.open(str(other))
        assert controller.initial_loading and controller.preload_state["prepared"] == 0
        controller.end_scrub()  # Disabling the pressed slider must not reopen the old file.
        gate.set()
        spin(qt_app, lambda: controller.frame.source.path == str(other.resolve()) and controller.preload_state["ready"])
        spin(qt_app, lambda: not controller.initial_loading)
        assert old_stack.closed and old_stack.browse.bytes == old_stack.cache_bytes == 0
        assert not old_stack.browse.indices
        assert controller.pixel_value(0, 0) == "4321"
        controller.clear()
        spin(qt_app, lambda: controller._reader.stack is None)
        assert controller.preload_state["prepared"] == 0
    finally:
        gate.set()
        controller.shutdown()


def test_qml_pressed_drag_updates_each_page_before_release(qt_app, browse_file, tmp_path, monkeypatch):
    path, raw = browse_file
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "drag.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    controller = bridge.stack_viewer
    try:
        assert QMetaObject.invokeMethod(window, "selectImagePath", Q_ARG("QVariant", str(path)))
        spin(qt_app, lambda: controller.preload_state["ready"] and controller._task is None)
        # TD-03 opens image information first; page controls are explicit settings.
        assert QMetaObject.invokeMethod(window.findChild(QObject, "viewerSettingsAction"), "trigger")
        QTest.qWait(35)
        status = window.findChild(QObject, "preloadStatus")
        assert "Stack 준비 완료" in status.property("text")
        slider = window.findChild(QObject, "pageSlider")
        slider_origin = slider.mapToScene(QPoint(0, 0))
        def position(fraction):
            return QPoint(int(slider_origin.x() + slider.property("leftPadding") + slider.property("availableWidth") * fraction),
                          int(slider_origin.y() + slider.property("height") / 2))
        reads = []
        actual = TiffStack.read_page
        def counted(stack, index):
            reads.append(index)
            return actual(stack, index)
        monkeypatch.setattr(TiffStack, "read_page", counted)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, position(.005))
        assert slider.property("pressed") and controller.scrubbing
        seen = []
        for fraction in (.15, .45, .8, .35, .95, .25):
            QTest.mouseMove(window, position(fraction))
            qt_app.processEvents()
            assert slider.property("pressed") and controller.scrubbing
            index = state.property("pageIndex")
            assert index == round(slider.property("value")) == controller.requested_page
            assert controller.frame.pixels is None and not controller.busy
            assert bridge.stackState["browsePreview"] and not bridge.stackState["rawReady"]
            seen.append(index)
        assert len(set(seen)) >= 5 and seen[2] > seen[3] and reads == []
        final = seen[-1]
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, position(.25))
        assert not controller.scrubbing
        spin(qt_app, lambda: bridge.stackState["rawReady"] and not controller.detail_busy)
        assert reads == [final] and state.property("pageIndex") == final
        np.testing.assert_array_equal(controller.frame.pixels, raw[final])
        assert not warnings, "\n".join(warnings)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()


@pytest.mark.parametrize("outcome", ["complete", "cancel", "retry"])
def test_qml_first_frame_usable_while_navigation_waits_for_whole_stack(qt_app, browse_file, tmp_path, monkeypatch, outcome):
    path, _ = browse_file
    gate, entered = Event(), Event()
    fail = outcome == "retry"
    actual = TiffStack.read_page
    def block(stack, index):
        if index == 4:
            entered.set()
            assert gate.wait(5)
            if fail:
                raise ValueError("Synthetic preload failure")
        return actual(stack, index)
    monkeypatch.setattr(TiffStack, "read_page", block)
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(tmp_path / "loading.ini"), QSettings.IniFormat))
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
    window = engine.rootObjects()[0]
    state = window.findChild(QObject, "uiState")
    controller = bridge.stack_viewer
    try:
        assert QMetaObject.invokeMethod(window, "selectImagePath", Q_ARG("QVariant", str(path)))
        spin(qt_app, entered.is_set)
        old_stack = controller._reader.stack
        overlay = window.findChild(QObject, "initialLoadingOverlay")
        slider = window.findChild(QObject, "pageSlider")
        assert controller.preload_state["prepared"] == 4
        assert not state.property("loading") and not overlay.property("visible")
        assert "4 / 20" in window.findChild(QObject, "preloadStatus").property("text")
        assert not slider.property("enabled")
        assert window.findChild(QObject, "viewerMouseArea").property("enabled")
        assert not window.findChild(QObject, "displayLowSlider").property("enabled")
        assert window.findChild(QObject, "zoomInAction").property("enabled")
        assert window.findChild(QObject, "closeImageAction").property("enabled")
        assert not bridge.requestPage(2)  # Already cached, but the whole stack is not ready.
        assert not bridge.setDisplayRange(0, 50000)
        bridge.beginScrub()
        assert not controller.scrubbing
        QTest.keyClick(window, Qt.Key_Right)
        viewport = window.findChild(QObject, "viewerViewport")
        origin = viewport.mapToScene(QPointF(0, 0))
        pos = QPointF(origin.x() + viewport.property("width") / 2, origin.y() + viewport.property("height") / 2)
        wheel = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        qt_app.sendEvent(window, wheel)
        assert controller.requested_page == state.property("pageIndex") == 0
        if outcome == "cancel":
            assert QMetaObject.invokeMethod(window.findChild(QObject, "viewerSettingsAction"), "trigger")
            QTest.qWait(30)
            cancel = window.findChild(QObject, "cancelStackPreparation")
            cancel_pos = cancel.mapToScene(QPointF(cancel.property("width") / 2, cancel.property("height") / 2))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, cancel_pos.toPoint())
            assert not state.property("loading") and not overlay.property("visible")
            assert not state.property("hasImage")
            gate.set()
            spin(qt_app, lambda: controller._reader.stack is None)
            assert old_stack.browse.bytes == 0
        else:
            gate.set()
            if outcome == "retry":
                spin(qt_app, lambda: bool(controller.preload_error))
                assert not state.property("loading") and not slider.property("enabled")
                assert "실패" in window.findChild(QObject, "preloadStatus").property("text")
                fail = False
                bridge.retryPreload()
            spin(qt_app, lambda: controller.preload_state["ready"] and not controller.initial_loading)
            assert controller.preload_state["ready"] and not controller.initial_loading
            assert not overlay.property("visible") and slider.property("enabled")
            qt_app.sendEvent(window, wheel)
            assert state.property("pageIndex") == 1 and not state.property("loading")
        assert not warnings, "\n".join(warnings)
    finally:
        gate.set()
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        qt_app.processEvents()
