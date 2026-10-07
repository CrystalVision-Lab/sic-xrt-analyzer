"""Windows dialog lifecycle diagnosis; Qt calls only, no native mouse input.

Run each case in a separate process. Raw logs and reports belong in artifacts.
psutil is an optional validation dependency, not a production dependency.
"""

import argparse
import ctypes
import faulthandler
import json
import os
import threading
import time
from pathlib import Path

import psutil
import shiboken6
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from validate_rc_session import Session


def resources():
    process = psutil.Process()
    result = {
        "rss": process.memory_info().rss,
        "handles": process.num_handles(),
        "threads": process.num_threads(),
    }
    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    user.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    handle = kernel.GetCurrentProcess()
    result.update(
        user=user.GetGuiResources(handle, 1), gdi=user.GetGuiResources(handle, 0)
    )
    apartment, qualifier = ctypes.c_int(), ctypes.c_int()
    hr = ctypes.windll.ole32.CoGetApartmentType(
        ctypes.byref(apartment), ctypes.byref(qualifier)
    )
    result["com"] = {
        "hresult": hex(hr & 0xFFFFFFFF),
        "apartment": apartment.value,
        "qualifier": qualifier.value,
    }
    return result


def native_windows():
    """Read-only native HWND evidence. This never sends Windows input/messages."""
    user = ctypes.windll.user32
    user.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user.GetWindow.restype = ctypes.c_void_p
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    def inspect(hwnd, _):
        pid, name = ctypes.c_ulong(), ctypes.create_unicode_buffer(256)
        tid = user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        user.GetClassNameW(hwnd, name, len(name))
        if (
            pid.value == os.getpid()
            and user.IsWindowVisible(hwnd)
            and name.value == "#32770"
        ):
            found.append(
                {
                    "hwnd": hex(hwnd),
                    "owner": hex(user.GetWindow(hwnd, 4) or 0),
                    "thread": tid,
                }
            )
        return 1

    user.EnumWindows(callback_type(inspect), 0)
    return found


class Trace:
    def __init__(self, path):
        self.stream = path.open("w", encoding="utf8")
        self.started = time.monotonic()
        self.cycle = 0

    def emit(self, event, **details):
        value = {
            "seconds": round(time.monotonic() - self.started, 6),
            "cycle": self.cycle,
            "event": event,
            "pid": os.getpid(),
            "thread": threading.get_native_id(),
            **details,
        }
        self.stream.write(json.dumps(value) + "\n")
        self.stream.flush()


def main():
    faulthandler.enable()
    # Match the application entry point: Python-painted items require the GUI
    # render loop to avoid render-thread/GIL waits during QML/Python callbacks.
    os.environ.setdefault("QSG_RENDER_LOOP", "basic")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--case", choices=("open", "save", "mixed", "sequence"), default="open"
    )
    parser.add_argument(
        "--dispatch", choices=("object", "qml", "action"), default="qml"
    )
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--minimal", action="store_true")
    parser.add_argument("--dynamic", action="store_true")
    parser.add_argument("--non-native", action="store_true")
    parser.add_argument(
        "--managed-native",
        action="store_true",
        help="Exercise production QApplication native modal route",
    )
    parser.add_argument(
        "--qml-root", type=Path, default=Path("src/sic_xrt_analyzer/ui")
    )
    args = parser.parse_args()
    assert os.name == "nt" and args.cycles > 0
    args.output.mkdir(parents=True, exist_ok=True)
    trace = Trace(args.output / "events.jsonl")
    app = (QApplication if args.managed_native else QGuiApplication)([])
    QQuickStyle.setStyle("Basic")
    assert app.platformName() == "windows"
    session = None
    if args.minimal:
        engine = QQmlApplicationEngine()
        engine.loadData(b"""import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
ApplicationWindow {
 id: root; objectName: "minimalWindow"; visible: true; width: 600; height: 400
 property bool dynamicDialog: false
 property var chooser: persistent
 Component { id: factory; FileDialog { objectName: "dynamicDialog" } }
 FileDialog { id: persistent; objectName: "persistentDialog" }
 Action { id: request; objectName: "dialogAction"; onTriggered: root.showChooser() }
 Button { text: "Open"; onClicked: request.trigger() }
 function showChooser() {
   chooser.open()
 }
 function prepare(save, nonNative) {
   if (dynamicDialog) chooser = factory.createObject(root)
   chooser.fileMode = save ? FileDialog.SaveFile : FileDialog.OpenFile
   chooser.options = nonNative ? FileDialog.DontUseNativeDialog : 0
 }
 function cleanup() { if (dynamicDialog) chooser.destroy() }
}""")
        window = engine.rootObjects()[0]
        window.setProperty("dynamicDialog", args.dynamic)
        warnings = []
        engine.warnings.connect(
            lambda values: warnings.extend(v.toString() for v in values)
        )
    else:
        assert args.input and not args.dynamic
        session = Session(app, args.output, args.qml_root.resolve())
        engine, window, warnings = session.engine, session.window, session.warnings
        session.open(args.input)
    context = QQmlEngine.contextForObject(window)

    def evaluate(code):
        expression = QQmlExpression(context, window, code)
        value = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value[0] if isinstance(value, tuple) else value

    class CancelRequest(QObject):
        requested = Signal(str)

        @Slot(str)
        def reject(self, key):
            trace.emit("queued-reject-gui", dialog=key)
            assert QThread.isMainThread()
            evaluate(key + ".reject()")

    coordinator = CancelRequest()
    coordinator.requested.connect(coordinator.reject, Qt.QueuedConnection)

    def wait(predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            assert time.monotonic() < deadline, "dialog condition deadline"
            app.processEvents()
            time.sleep(0.002)

    hwnd = int(window.winId())
    gui_thread_id = threading.get_native_id()
    ctypes.windll.user32.IsWindow.argtypes = [ctypes.c_void_p]
    assert ctypes.windll.user32.IsWindow(hwnd)
    trace.emit(
        "startup",
        platform=app.platformName(),
        owner=hex(hwnd),
        resources=resources(),
        app_gui_thread=QThread.isMainThread(),
    )
    app.aboutToQuit.connect(lambda: trace.emit("about-to-quit"))
    app.lastWindowClosed.connect(lambda: trace.emit("last-window-closed"))
    window.destroyed.connect(lambda: trace.emit("window-destroyed"))
    engine.destroyed.connect(lambda: trace.emit("engine-destroyed"))
    if session and hasattr(session.bridge, "native_dialogs"):
        trace.emit(
            "native-controller",
            enabled=session.bridge.native_dialogs.enabled,
            app_type=type(app).__name__,
        )
        session.bridge.native_dialogs.executing.connect(
            lambda root: trace.emit("native-executing", title=root.property("title"))
        )
    summary = {
        "cycles": args.cycles,
        "case": args.case,
        "dispatch": args.dispatch,
        "minimal": args.minimal,
        "dynamic": args.dynamic,
        "non_native": args.non_native,
        "samples": [{"cycle": 0, **resources()}],
        "completed": 0,
    }
    connected = set()
    initial_state = (
        (
            session.bridge.original_source.identity,
            len(session.bridge.roi_manager.records),
            session.bridge.pipeline.result,
        )
        if session
        else None
    )
    for cycle in range(1, args.cycles + 1):
        trace.cycle = cycle
        names = (
            ["openDialog"]
            if args.case == "open"
            else ["imageSaveDialog"]
            if args.case == "save"
            else ["openDialog", "imageSaveDialog"]
        )
        if args.case == "sequence":
            names = ["openDialog", "imageSaveDialog", "roiDialog", "resultsDialog"]
        # A mixed cycle contains both Open and Save; neither count is reduced.
        for name in names:
            if args.minimal:
                evaluate(
                    f"prepare({str(name == 'imageSaveDialog').lower()}, {str(args.non_native).lower()})"
                )
                qml_id = "chooser"
            else:
                qml_id = name
                if args.non_native:
                    evaluate(qml_id + ".options = FileDialog.DontUseNativeDialog")
            dialog = evaluate(qml_id)
            assert dialog is not None
            pointer = shiboken6.getCppPointer(dialog)[0]
            assert QThread.isMainThread()
            if pointer not in connected:
                for signal in ("accepted", "rejected", "visibleChanged", "destroyed"):
                    getattr(dialog, signal).connect(
                        lambda *_, sig=signal, p=pointer: trace.emit(
                            sig, pointer=hex(p)
                        )
                    )
                connected.add(pointer)
            trace.emit(
                "open-request",
                dialog=name,
                pointer=hex(pointer),
                visible=bool(evaluate(qml_id + ".visible")),
                managed=dialog.property("managedNative"),
                owner_python=shiboken6.ownedByPython(window),
            )
            worker = None
            if args.managed_native:
                errors = []

                def cancel_when_native_visible(key=qml_id, problems=errors):
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        windows = native_windows()
                        windows = [
                            w
                            for w in windows
                            if w["owner"] == hex(hwnd) and w["thread"] == gui_thread_id
                        ]
                        if windows:
                            trace.emit("native-visible", windows=windows)
                            coordinator.requested.emit(key)
                            return
                        time.sleep(0.002)
                    problems.append("Native HWND was not observed")
                    trace.emit("native-observation-deadline", windows=native_windows())
                    coordinator.requested.emit(key)

                worker = threading.Thread(target=cancel_when_native_visible)
                worker.start()
            if args.dispatch == "object":
                assert QMetaObject.invokeMethod(dialog, "open")
            elif args.dispatch == "action":
                if args.minimal:
                    action = window.findChild(QObject, "dialogAction")
                    assert action and QMetaObject.invokeMethod(action, "trigger")
                elif name == "openDialog":
                    assert QMetaObject.invokeMethod(window, "openImageDialog")
                else:
                    assert QMetaObject.invokeMethod(window, "saveImageCopy")
            else:
                evaluate(qml_id + ".open()")
            trace.emit(
                "post-dispatch",
                window_valid=shiboken6.isValid(window),
                engine_valid=shiboken6.isValid(engine),
            )
            trace.emit(
                "open-return",
                qml_visible=evaluate(qml_id + ".visible"),
                object_visible=dialog.property("visible"),
                pending=session.bridge.native_dialogs._request is not None
                if session and hasattr(session.bridge, "native_dialogs")
                else False,
            )
            wait(lambda key=qml_id: bool(evaluate(key + ".visible")))
            trace.emit("visible-true", dialog=name)
            if args.managed_native:
                # exec returns only after a real native HWND was observed and
                # the queued Qt reject ran on the GUI thread. No fixed sleep.
                app.processEvents()
                worker.join(10)
                assert not worker.is_alive() and not errors, errors
            else:
                # Preserve TD-09's baseline observation interval, never lengthen.
                QTest.qWait(100)
            trace.emit("reject-request", dialog=name)
            if args.managed_native:
                pass  # The coordinator already rejected on the GUI thread.
            elif args.dispatch == "object":
                assert QMetaObject.invokeMethod(dialog, "reject")
            else:
                evaluate(qml_id + ".reject()")
            wait(lambda key=qml_id: not evaluate(key + ".visible"))
            trace.emit("visible-false", dialog=name)
            # The real outer event loop delivers DeferredDelete between user
            # requests. processEvents() alone does not: flush the completed
            # native helper's deleteLater before the next manually driven cycle.
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
            if args.minimal:
                evaluate("cleanup()")
            if session:
                assert initial_state == (
                    session.bridge.original_source.identity,
                    len(session.bridge.roi_manager.records),
                    session.bridge.pipeline.result,
                )
                assert not session.state.property("loadError")
        summary["completed"] = cycle
        if cycle in (1, 10, 50, 100, args.cycles):
            summary["samples"].append({"cycle": cycle, **resources()})
            trace.emit("resources", **summary["samples"][-1])
        (args.output / "report.json").write_text(
            json.dumps(summary, indent=2), encoding="utf8"
        )
    trace.emit("shutdown-start")
    if session:
        session.close()
    else:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    assert not warnings, warnings
    summary.update(qml_warnings=warnings, after_cleanup=resources())
    trace.emit("shutdown-complete", resources=summary["after_cleanup"])
    (args.output / "report.json").write_text(
        json.dumps(summary, indent=2), encoding="utf8"
    )


if __name__ == "__main__":
    main()
