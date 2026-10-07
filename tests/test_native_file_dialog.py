"""Modal completion, GUI affinity, lifetime and cancellation protocol checks.

The double replaces only the OS picker; QML objects/signals and controller are
real. Actual Windows HWND stress is performed by dialog_lifecycle_probe.py.
"""

from pathlib import Path
from threading import Thread
from typing import ClassVar

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QThread, QUrl
from PySide6.QtGui import QWindow
from PySide6.QtQml import QJSValue, QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QFileDialog

from sic_xrt_analyzer.ui import native_file_dialog as native


@pytest.fixture
def picker(qt_app, bridge_factory, monkeypatch):
    bridge = bridge_factory()
    controller = bridge.native_dialogs
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("fileBridge", bridge)
    path = Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/SafeFileDialog.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    assert component.isReady(), component.errors()
    root, other = component.create(), component.create()
    root.setParent(engine)
    other.setParent(engine)
    owner = QWindow()
    calls, completed = [], []

    class Dialog(QObject):
        Accepted = QFileDialog.Accepted
        AcceptSave, AcceptOpen = QFileDialog.AcceptSave, QFileDialog.AcceptOpen
        Directory, AnyFile = QFileDialog.Directory, QFileDialog.AnyFile
        ExistingFiles, ExistingFile = (
            QFileDialog.ExistingFiles,
            QFileDialog.ExistingFile,
        )
        ShowDirsOnly, Option = QFileDialog.ShowDirsOnly, QFileDialog.Option
        instances: ClassVar[list] = []
        response = QFileDialog.Rejected
        on_exec = lambda self: None

        def __init__(self):
            super().__init__()
            self.instances.append(self)
            self.values = {}
            self.files = [
                QUrl.fromLocalFile("/synthetic/first.tif"),
                QUrl.fromLocalFile("/synthetic/second.tif"),
            ]

        def __getattr__(self, key):
            if key.startswith("set"):
                return lambda *args: self.values.update({key: args})
            raise AttributeError(key)

        def winId(self):
            return 1

        def windowHandle(self):
            return self

        def directoryUrl(self):
            return QUrl.fromLocalFile("/synthetic")

        def exec(self):
            assert QThread.isMainThread()
            assert root.property("visible")
            assert not controller.open(other, owner)
            calls.append("native-enter")
            self.on_exec()
            calls.append("native-return")
            return self.response

        def reject(self):
            assert QThread.isMainThread()
            self.response = QFileDialog.Rejected
            calls.append("native-reject")

        def selectedUrls(self):
            return self.files

    monkeypatch.setattr(native, "QFileDialog", Dialog)
    root.accepted.connect(lambda: completed.append("accepted"))
    root.rejected.connect(lambda: completed.append("rejected"))
    yield controller, root, other, owner, Dialog, calls, completed
    controller.shutdown()
    engine.deleteLater()
    if shiboken6.isValid(owner):
        owner.deleteLater()


def test_duplicate_and_cancel_before_dispatch_create_no_native_picker(picker, qt_app):
    controller, root, other, owner, dialog, calls, completed = picker
    assert controller.open(root, owner)
    assert not controller.open(root, owner)
    assert not controller.open(other, owner)
    controller.reject(root)
    qt_app.processEvents()
    assert not dialog.instances and not calls
    assert completed == ["rejected"]
    assert controller._request is None and not root.property("visible")


def test_pending_qml_object_destruction_cancels_without_accessing_deleted_object(
    picker, qt_app
):
    controller, root, _other, owner, dialog, calls, completed = picker
    assert controller.open(root, owner)
    root.deleteLater()
    QCoreApplication.sendPostedEvents(root, QEvent.DeferredDelete)
    assert not shiboken6.isValid(root)
    qt_app.processEvents()
    assert controller._request is None and not dialog.instances
    assert not completed and not calls


def test_selected_urls_are_published_only_after_native_return(picker, qt_app):
    controller, root, _other, owner, dialog, calls, completed = picker
    root.setProperty("fileMode", 1)
    root.setProperty("options", int(QFileDialog.ReadOnly.value))
    dialog.response = QFileDialog.Accepted
    observed = []

    def selected_urls():
        value = root.property("selectedFiles")
        return value.toVariant() if isinstance(value, QJSValue) else value

    root.accepted.connect(
        lambda: observed.append(
            (
                calls[-1],
                controller._request,
                controller._widget,
                root.property("visible"),
                selected_urls(),
                root.property("selectedFile"),
                root.property("currentFolder"),
            )
        )
    )
    assert controller.open(root, owner)
    qt_app.processEvents()
    assert completed == ["accepted"]
    assert observed == [
        (
            "native-return",
            None,
            None,
            False,
            dialog.instances[0].files,
            dialog.instances[0].files[0],
            QUrl.fromLocalFile("/synthetic"),
        )
    ]
    assert dialog.instances[0].values["setFileMode"] == (QFileDialog.ExistingFiles,)
    assert dialog.instances[0].values["setOptions"] == (QFileDialog.ReadOnly,)


def test_worker_thread_cannot_touch_pending_gui_picker(picker, qt_app):
    controller, root, _other, owner, _dialog, _calls, completed = picker
    errors = []
    assert controller.open(root, owner)

    def wrong_thread():
        try:
            controller.reject(root)
        except RuntimeError as error:
            errors.append(str(error))

    worker = Thread(target=wrong_thread)
    worker.start()
    worker.join()
    assert errors == ["Native file dialogs must be called on the Qt GUI thread"]
    assert not controller._cancelled and root.property("visible")
    controller.reject(root)
    qt_app.processEvents()
    assert completed == ["rejected"]


def test_cancel_does_not_publish_a_late_native_selection(picker, qt_app):
    controller, root, _other, owner, dialog, _calls, completed = picker

    def late_accept(self):
        controller.reject(root)
        self.response = QFileDialog.Accepted

    dialog.on_exec = late_accept
    assert controller.open(root, owner)
    qt_app.processEvents()
    assert completed == ["rejected"]
    assert root.property("selectedFile").isEmpty()


@pytest.mark.parametrize("event", ["owner_destroyed", "shutdown"])
def test_owner_loss_or_shutdown_rejects_active_modal_before_disposal(
    picker, qt_app, event
):
    controller, root, other, owner, dialog, calls, completed = picker

    def interrupt(self):
        if event == "shutdown":
            controller.shutdown()
        else:
            owner.deleteLater()
            QCoreApplication.sendPostedEvents(owner, QEvent.DeferredDelete)
        assert calls[-1] == "native-reject"
        assert shiboken6.isValid(self)

    dialog.on_exec = interrupt
    assert controller.open(root, owner)
    qt_app.processEvents()
    assert completed == ["rejected"]
    assert calls == ["native-enter", "native-reject", "native-return"]
    assert controller._request is None
    if event == "shutdown":
        assert not shiboken6.isValid(dialog.instances[0])
        assert not controller.open(other, owner)
