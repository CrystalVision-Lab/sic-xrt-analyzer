import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QGuiApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    # One GUI application for workers and existing QML tests, never a QCoreApplication.
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
    app.processEvents()
