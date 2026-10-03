import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    # One GUI application for workers and existing QML tests, never a QCoreApplication.
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def dispose_deferred_qml_windows(qt_app):
    yield
    # These tests manually pump events instead of entering app.exec().
    # processEvents alone does not deliver DeferredDelete: old engines/windows
    # otherwise survive into later tests with already closed mmap owners.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qt_app.processEvents()


@pytest.fixture
def bridge_factory(qt_app):
    """Own even temporary preference-only bridges until their timers are stopped."""
    from sic_xrt_analyzer.ui.bridge import FileBridge
    bridges = []
    def create(**kwargs):
        bridge = FileBridge(**kwargs)
        bridges.append(bridge)
        return bridge
    yield create
    for bridge in bridges:
        bridge.waitForLoads()
        bridge.deleteLater()
