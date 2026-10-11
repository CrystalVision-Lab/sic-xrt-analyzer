"""Pytest plugin: observe existing UI tests without altering input/waits/layout.

Use PYTHONPATH=tools; pytest -p windows_ui_probe ... and TD12_TRACE_DIR.
Artifacts stay local, snapshots are flushed only after the test call finishes.
"""

import json
import os
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QGuiApplication

TRACES = {}


def describe(obj):
    if obj is None:
        return None
    return {"class": obj.metaObject().className(), "name": obj.objectName()}


def point(p):
    return [round(p.x(), 3), round(p.y(), 3)]


class Trace(QObject):
    def __init__(self, w, nodeid):
        super().__init__(w.window)
        self.w, self.nodeid = w, nodeid
        self.started = time.perf_counter()
        self.rows = []
        self.menu = w.item("analysisMenu")
        self.run = w.item("menuRunAnalysis")
        self.action = w.item("runAction")
        self.window = w.window
        self.window.installEventFilter(self)
        self.connected = set()
        self.items = [self.menu.itemAt(i) for i in range(self.menu.property("count"))]
        for item in self.items:
            if item is None:
                continue
            for signal in (
                "pressedChanged",
                "clicked",
                "triggered",
                "yChanged",
                "heightChanged",
            ):
                if hasattr(item, signal):
                    getattr(item, signal).connect(
                        lambda *args, item=item, signal=signal: self.signal(
                            item, signal
                        )
                    )
        self.action.triggered.connect(lambda *args: self.record("action-triggered"))
        self.window.activeChanged.connect(lambda: self.record("window-active-changed"))
        self.record("call-start", self.geometry())
        self.menu.openedChanged.connect(
            lambda: self.record("opened-changed", self.geometry())
        )
        original_click = w.click

        def observed_click(name):
            if name == "menuRunAnalysis":
                self.record("before-click", self.geometry())
            result = original_click(name)
            if name == "menuRunAnalysis":
                self.record("after-click", self.geometry())
            return result

        w.click = observed_click

    def record(self, event, data=None):
        self.rows.append(
            {
                "seconds": round(time.perf_counter() - self.started, 6),
                "event": event,
                **(data or {}),
            }
        )

    def signal(self, item, signal):
        if self.menu.property("visible"):
            self.record(
                signal,
                {
                    "item": describe(item),
                    "text": item.property("text"),
                    "x": item.property("x"),
                    "y": item.property("y"),
                    "height": item.property("height"),
                    "visible": item.property("visible"),
                    "enabled": item.property("enabled"),
                    "pressed": item.property("pressed"),
                },
            )

    def geometry(self):
        w, menu, obj = self.window, self.menu, self.run
        scene = obj.mapToScene(QPointF(obj.width() / 2, obj.height() / 2))
        global_point = w.mapToGlobal(scene.toPoint())
        content = menu.property("contentItem")
        self.items = [
            i
            for i in menu.findChildren(QObject)
            if i.inherits("QQuickMenuItem") or i.inherits("QQuickMenuSeparator")
        ]
        for item in self.items:
            if item in self.connected:
                continue
            self.connected.add(item)
            for signal in ("pressedChanged", "clicked", "triggered"):
                if hasattr(item, signal):
                    getattr(item, signal).connect(
                        lambda *args, item=item, signal=signal: self.signal(
                            item, signal
                        )
                    )
        return {
            "window": [w.x(), w.y(), w.width(), w.height()],
            "active": w.isActive(),
            "activeWindow": describe(QGuiApplication.focusWindow()),
            "focus": describe(w.activeFocusItem()),
            "dpr": w.devicePixelRatio(),
            "menu": {
                "x": menu.property("x"),
                "y": menu.property("y"),
                "width": menu.property("width"),
                "height": menu.property("height"),
                "visible": menu.property("visible"),
                "opened": menu.property("opened"),
            },
            "run": {
                "x": obj.x(),
                "y": obj.y(),
                "width": obj.width(),
                "height": obj.height(),
                "scene": point(scene),
                "global": point(global_point),
                "enabled": obj.isEnabled(),
                "sameWindow": obj.window() == w,
                "visible": obj.isVisible(),
                "implicitHeight": obj.implicitHeight(),
                "parent": describe(obj.parentItem()),
            },
            "actionEnabled": self.action.property("enabled"),
            "content": {
                "class": content.metaObject().className(),
                "height": content.height(),
                "contentHeight": content.property("contentHeight"),
                "count": content.property("count"),
            },
            "rows": [
                {
                    "name": i.objectName(),
                    "text": i.property("text"),
                    "y": i.property("y"),
                    "height": i.property("height"),
                    "implicitHeight": i.property("implicitHeight"),
                    "visible": i.property("visible"),
                    "enabled": i.property("enabled"),
                }
                for i in self.items
                if i is not None
            ],
        }

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
        ) and self.menu.property("visible"):
            self.record(
                event.type().name,
                {
                    "local": point(event.position()),
                    "global": point(event.globalPosition()),
                    "geometry": self.geometry(),
                },
            )
        return False


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    if "test_toolbar_layout_and_analysis_menu_entry" in item.nodeid:
        TRACES[item.nodeid] = Trace(item.funcargs["workbench"], item.nodeid)
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    trace = TRACES.get(item.nodeid)
    if trace and report.when == "call":
        directory = Path(os.environ["TD12_TRACE_DIR"])
        directory.mkdir(parents=True, exist_ok=True)
        name = item.name.replace("[", "-").replace("]", "")
        trace.record(
            "call-finished", {"outcome": report.outcome, "geometry": trace.geometry()}
        )
        (directory / (name + ".json")).write_text(
            json.dumps(
                {"nodeid": item.nodeid, "rows": trace.rows},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf8",
        )
        if report.failed:
            trace.window.grabWindow().save(
                str(directory / (name + "-after-failure.png"))
            )
        trace.window.removeEventFilter(trace)
    return report
