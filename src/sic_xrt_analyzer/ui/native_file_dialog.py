"""Keep Windows native dialogs on the GUI STA until their modal call returns.

Qt Quick's Windows helper uses an asynchronous dialog thread. Logical reject
can precede native completion; reusing that helper can receive stale completion
signals. QFileDialog.exec uses the same native Windows picker synchronously.
QML callbacks are delivered only after the native modal call returns.
Other platforms continue to use the original Qt Quick dialog.
"""

import threading

import shiboken6
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QDir,
    QEvent,
    QMetaObject,
    QObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QJSValue
from PySide6.QtWidgets import QApplication, QFileDialog


class NativeFileDialogs(QObject):
    executing = Signal(QObject)  # Lifecycle observation; emitted on the GUI thread.

    def __init__(self, parent=None):
        super().__init__(parent)
        self._request = self._widget = self._owner = None
        self._widgets = {}
        self._cancelled = self._stopping = False
        self._destroyed_callback = None
        self._gui_thread_id = threading.get_ident()
        app = QGuiApplication.instance()
        self._enabled = (
            isinstance(app, QApplication) and app.platformName() == "windows"
        )

    @Property(bool, constant=True)
    def enabled(self):
        return self._enabled

    def _gui_thread(self):
        if threading.get_ident() != self._gui_thread_id:
            raise RuntimeError(
                "Native file dialogs must be called on the Qt GUI thread"
            )

    @staticmethod
    def _find_owner(dialog, explicit):
        owner = explicit or dialog.parent()
        while owner is not None:
            if isinstance(owner, QWindow):
                return owner
            owner = owner.parent()
        raise RuntimeError("Native file dialog requires a live owner window")

    @Slot(QObject, QObject, result=bool)
    def open(self, dialog, owner=None):
        self._gui_thread()
        if self._stopping or self._request is not None:
            return False
        self._owner = self._find_owner(dialog, owner)
        self._request, self._cancelled = dialog, False
        self._destroyed_callback = lambda *_: self.reject(dialog)
        dialog.destroyed.connect(self._destroyed_callback)
        self._owner.destroyed.connect(self._destroyed_callback)
        dialog.setProperty("visible", True)
        # Leave the QML Action/signal stack before entering the modal Windows
        # call. This is queued dispatch, not a timer used to wait out a race.
        QTimer.singleShot(0, self._execute)
        return True

    @Slot(QObject)
    def reject(self, dialog):
        self._gui_thread()
        if self._request is dialog:
            self._cancelled = True
            if self._widget is not None:
                self._widget.reject()

    @Slot()
    def shutdown(self):
        self._stopping = True
        if self._request is not None:
            self._gui_thread()
            self.reject(self._request)
        elif self._widgets:
            self._gui_thread()
            self._dispose_widgets()

    def _dispose_widgets(self):
        for widget in self._widgets.values():
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)
        self._widgets.clear()

    @Slot()
    def _execute(self):
        self._gui_thread()
        root, owner = self._request, self._owner
        if root is None:
            return
        accepted, files = False, []
        widget = None
        try:
            if (
                not self._cancelled
                and shiboken6.isValid(root)
                and shiboken6.isValid(owner)
            ):
                folder, mode = (
                    bool(root.property("folderMode")),
                    root.property("fileMode"),
                )
                if not folder and mode not in (0, 1, 2):
                    raise ValueError("Unsupported native file dialog mode")
                key = "folder" if folder else mode
                if key not in self._widgets:
                    self._widgets[key] = QFileDialog()
                widget = self._widget = self._widgets[key]
                widget.setObjectName("windowsNativeFileDialog")
                widget.setAttribute(Qt.WA_DeleteOnClose, False)
                widget.setWindowTitle(root.property("title"))
                widget.setWindowModality(Qt.WindowModal)
                widget.winId()
                widget.windowHandle().setTransientParent(owner)
                widget.setAcceptMode(
                    QFileDialog.AcceptSave
                    if mode == 2 and not folder
                    else QFileDialog.AcceptOpen
                )
                widget.setFileMode(
                    QFileDialog.Directory
                    if folder
                    else QFileDialog.AnyFile
                    if mode == 2
                    else QFileDialog.ExistingFiles
                    if mode == 1
                    else QFileDialog.ExistingFile
                )
                widget.setOptions(QFileDialog.Option(root.property("options")))
                if folder:
                    widget.setOption(QFileDialog.ShowDirsOnly, True)
                else:
                    filters = root.property("nameFilters")
                    widget.setNameFilters(
                        filters.toVariant()
                        if isinstance(filters, QJSValue)
                        else filters
                    )
                    widget.setDefaultSuffix(root.property("defaultSuffix"))
                directory = root.property("currentFolder")
                if not isinstance(directory, QUrl) or directory.isEmpty():
                    directory = QUrl.fromLocalFile(QDir.homePath())
                widget.setDirectoryUrl(directory)
                self.executing.emit(root)
                accepted = (
                    widget.exec() == QFileDialog.Accepted
                    and not self._cancelled
                    and not self._stopping
                )
                if accepted:
                    files = widget.selectedUrls()
                if shiboken6.isValid(root):
                    root.setProperty("currentFolder", widget.directoryUrl())
        finally:
            # Never destroy the native host, reset its owner, or emit a QML
            # completion while Windows Show()/Qt helper exec is on the stack.
            callback, self._destroyed_callback = self._destroyed_callback, None
            if shiboken6.isValid(root):
                root.destroyed.disconnect(callback)
            if shiboken6.isValid(owner):
                owner.destroyed.disconnect(callback)
            self._widget = self._request = self._owner = None
            if self._stopping:
                self._dispose_widgets()
            if shiboken6.isValid(root):
                root.setProperty("visible", False)
        if not shiboken6.isValid(root):
            return
        if accepted and files:
            root.setProperty("selectedFiles", files)
            root.setProperty("selectedFile", files[0])
            root.setProperty("selectedFolder", files[0])
        QMetaObject.invokeMethod(root, "accepted" if accepted and files else "rejected")
