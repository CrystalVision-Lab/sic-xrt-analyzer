"""Real QML pointer events must preserve the original source anchor."""
import math
import time
from pathlib import Path

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
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def invoke(obj, method, *args):
    assert QMetaObject.invokeMethod(obj, method, *(Q_ARG("QVariant", a) for a in args))


class Viewer:
    def __init__(self, app, tmp_path):
        self.app = app
        QQuickStyle.setStyle("Basic")
        self.engine = QQmlApplicationEngine()
        provider = TiffImageProvider()
        self.bridge = FileBridge(provider, self.engine, QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat))
        self.engine.addImageProvider("tiff", provider)
        self.engine.rootContext().setContextProperty("fileBridge", self.bridge)
        self.warnings = []
        self.engine.warnings.connect(lambda items: self.warnings.extend(i.toString() for i in items))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")))
        assert self.engine.rootObjects(), self.warnings
        self.window = self.engine.rootObjects()[0]
        self.window.resize(1280, 900)
        self.ui = self.item("uiState")
        self.viewer = self.item("imageViewer")
        self.viewport = self.item("viewerViewport")
        self.frame = self.item("imageFrame")
        # Multi-page uint16 file: wheel also exercises the existing page policy.
        path = tmp_path / "stack.tif"
        tifffile.imwrite(path, np.arange(3 * 480 * 640, dtype=np.uint16).reshape(3, 480, 640), photometric="minisblack")
        self.bridge.requestImage(QUrl.fromLocalFile(str(path)).toString())
        self.wait(lambda: self.ui.property("canNavigateImage") and self.bridge.stack_viewer.preload_state["ready"])
        invoke(self.viewer, "setActualZoom", 2.)
        self.settle()

    def item(self, name):
        obj = self.window.findChild(QObject, name)
        assert obj is not None, name
        return obj

    def wait(self, predicate):
        until = time.monotonic() + 20
        while not predicate():
            assert time.monotonic() < until, (self.bridge.stackState, self.warnings)
            QTest.qWait(10)
        self.settle()

    def settle(self):
        self.app.processEvents()
        QTest.qWait(20)

    def local_anchor(self, fx, fy):
        point = self.viewport.mapToScene(QPointF(self.viewport.width() * fx, self.viewport.height() * fy))
        scene = QPoint(round(point.x()), round(point.y()))
        local = self.viewport.mapFromScene(QPointF(scene))
        return scene, local

    def source(self, p):
        s = self.viewer.property("displayScale")
        return ((p.x() - self.frame.x()) / s, (p.y() - self.frame.y()) / s)

    def wheel(self, scene, delta=120, modifiers=Qt.ControlModifier):
        QTest.wheelEvent(self.window, scene, QPoint(0, delta), stateKey=modifiers)
        self.settle()

    def close(self):
        self.window.setProperty("allowQuit", True)
        self.window.close()
        self.bridge.waitForLoads()
        self.engine.deleteLater()
        self.app.processEvents()


@pytest.fixture
def viewer(qt_app, tmp_path):
    v = Viewer(qt_app, tmp_path)
    try:
        yield v
        assert not v.warnings
    finally:
        v.close()


def assert_anchor(before, after):
    # No pan clamp exists in the product; all local points obey the affine map.
    assert math.dist(before, after) < 1e-7, (before, after, math.dist(before, after))


@pytest.mark.parametrize("location", [(0.5, 0.5), (0.1, 0.1), (0.9, 0.9)])
@pytest.mark.parametrize("tool", ["wheel", "Zoom"])
def test_pointer_zoom_and_round_trip(viewer, location, tool):
    v = viewer
    v.viewer.setProperty("panX", 73.)
    v.viewer.setProperty("panY", -61.)
    v.ui.setProperty("activeTool", "Zoom" if tool == "Zoom" else "Pan")
    scene, local = v.local_anchor(*location)
    before, scale = v.source(local), v.viewer.property("displayScale")
    for delta in [120, -120]:
        if tool == "Zoom":
            QTest.mouseClick(v.window, Qt.LeftButton, Qt.AltModifier if delta < 0 else Qt.NoModifier, scene)
            v.settle()
        else:
            v.wheel(scene, delta)
        assert_anchor(before, v.source(local))
    assert v.viewer.property("displayScale") == pytest.approx(scale)
    assert v.viewer.property("panX") == pytest.approx(73.)
    assert v.viewer.property("panY") == pytest.approx(-61.)


def test_toolbar_zoom_preserves_viewport_center_after_pan(viewer):
    v = viewer
    v.viewer.setProperty("panX", 123.)
    v.viewer.setProperty("panY", -74.)
    _, local = v.local_anchor(.5, .5)
    before = v.source(local)
    invoke(v.item("zoomInAction"), "trigger")
    v.settle()
    assert_anchor(before, v.source(local))


def test_fit_then_pointer_zoom_preserves_small_image_anchor(viewer):
    v = viewer
    invoke(v.viewer, "fitView")
    v.settle()
    assert v.frame.x() == pytest.approx((v.viewport.width() - v.frame.width()) / 2)
    assert v.frame.y() == pytest.approx((v.viewport.height() - v.frame.height()) / 2)
    scene, local = v.local_anchor(.4, .6)
    before = v.source(local)
    v.wheel(scene)
    assert_anchor(before, v.source(local))


def test_single_wheel_one_step_and_normal_wheel_changes_page(viewer):
    v = viewer
    scene, local = v.local_anchor(.3, .7)
    before = v.source(local)
    old = v.ui.property("effectiveZoom")
    v.wheel(scene)
    assert v.ui.property("effectiveZoom") == pytest.approx(old * 1.25)
    assert_anchor(before, v.source(local))
    old_zoom, old_pan = v.ui.property("effectiveZoom"), (v.viewer.property("panX"), v.viewer.property("panY"))
    v.wheel(scene, -120, Qt.NoModifier)
    v.wait(lambda: v.ui.property("pageIndex") == 1 and not v.ui.property("pageLoading"))
    assert v.ui.property("effectiveZoom") == old_zoom
    assert (v.viewer.property("panX"), v.viewer.property("panY")) == old_pan


@pytest.mark.parametrize("dimensions", [(320, 240), (1920, 240), (320, 1920), (1920, 1440)])
def test_small_wide_tall_and_large_alignment_and_repeated_zoom(viewer, dimensions):
    v = viewer
    # Geometry-only ablation: actual source fidelity is verified separately.
    v.ui.setProperty("imageWidth", dimensions[0])
    v.ui.setProperty("imageHeight", dimensions[1])
    invoke(v.viewer, "setActualZoom", .285)
    v.settle()
    scene, local = v.local_anchor(.35, .65)
    before = v.source(local)
    for _ in range(3):
        v.wheel(scene)
        assert_anchor(before, v.source(local))
    assert v.ui.property("effectiveZoom") == pytest.approx(.285 * 1.25**3)
    for _ in range(3):
        v.wheel(scene, -120)
        assert_anchor(before, v.source(local))
    assert v.ui.property("effectiveZoom") == pytest.approx(.285)
    invoke(v.viewer, "fitView")
    v.settle()
    assert v.viewer.property("panX") == v.viewer.property("panY") == 0
    assert v.frame.width() <= v.viewport.width()
    assert v.frame.height() <= v.viewport.height()
    assert v.frame.x() == pytest.approx((v.viewport.width() - v.frame.width()) / 2)
    assert v.frame.y() == pytest.approx((v.viewport.height() - v.frame.height()) / 2)


def test_high_zoom_pan_zoom_shortcuts_and_roi_invariants(viewer):
    v = viewer
    roi = [.2, .3, .4, .5]
    for name, value in zip(("roiStartX", "roiStartY", "roiEndX", "roiEndY"), roi, strict=True):
        v.ui.setProperty(name, value)
    v.ui.setProperty("hasRoi", True)
    geometry = [v.ui.property(n) for n in ("roiX", "roiY", "roiWidth", "roiHeight")]
    invoke(v.viewer, "setActualZoom", 1.)
    scene, local = v.local_anchor(.35, .65)
    for _ in range(10):
        before = v.source(local)
        v.wheel(scene)
        assert_anchor(before, v.source(local))
    v.ui.setProperty("activeTool", "Pan")
    QTest.mousePress(v.window, Qt.LeftButton, Qt.NoModifier, scene)
    QTest.mouseMove(v.window, scene + QPoint(41, -33))
    QTest.mouseRelease(v.window, Qt.LeftButton, Qt.NoModifier, scene + QPoint(41, -33))
    v.settle()
    before = v.source(local)
    v.wheel(scene, -120)
    assert_anchor(before, v.source(local))
    assert geometry == [v.ui.property(n) for n in ("roiX", "roiY", "roiWidth", "roiHeight")]
    QTest.keyClick(v.window, Qt.Key_0, Qt.ControlModifier)
    v.settle()
    assert v.ui.property("fitMode")
    QTest.keyClick(v.window, Qt.Key_1, Qt.ControlModifier)
    v.settle()
    assert v.ui.property("effectiveZoom") == 1
    assert v.viewer.property("panX") == v.viewer.property("panY") == 0


def test_source_point_agrees_with_prepared_transform_and_roi(viewer):
    v = viewer
    scene, local = v.local_anchor(.4, .6)
    v.wheel(scene)
    transform = v.item("preparedImageView").viewTransform
    assert list(transform) == pytest.approx([v.frame.x(), v.frame.y(), v.viewer.property("displayScale")])
    expression = QQmlExpression(v.engine.rootContext(), v.viewer, f"imagePoint({local.x()}, {local.y()})")
    p = expression.evaluate()[0]
    source = v.source(local)
    assert p.x() == pytest.approx(max(0, min(1, source[0] / v.ui.property("contentWidth"))))
    assert p.y() == pytest.approx(max(0, min(1, source[1] / v.ui.property("contentHeight"))))
