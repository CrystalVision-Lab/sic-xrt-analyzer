"""App update trust boundary, streamed integrity, cancellation and real QML close guards."""

import hashlib
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from PySide6.QtCore import QObject, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from sic_xrt_analyzer.application_updates import AppUpdateClient, normalize_origin
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


@pytest.fixture
def release():
    data = b"MZ" + b"test-installer-not-a-real-program" * 100

    def row(v, channel="BETA"):
        return {
            "id": str(uuid4()),
            "state": {"status": "PUBLISHED", "channel": channel},
            "manifest": {
                "schema": "xrt_app_release/v1",
                "version": v,
                "platform": "windows-x64",
                "model_included": False,
                "license": "GPL-3.0-only",
                "signature": "UNSIGNED",
                "distribution_clearance": {"status": "APPROVED"},
                "source_revision": "a" * 40,
                "source_archive": {"source_revision": "a" * 40, "sha256": "b" * 64},
                "filename": f"SiCXrtAnalyzer-{v}-windows-x64-setup.exe",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "notes": "연구용 앱 업데이트",
            },
        }

    return row, data


def client(rows, data=b"", requests=None, cancel=None, download_status=200):
    requests = requests if requests is not None else []

    def serve(request):
        requests.append(str(request.url))
        assert not request.headers.get("Authorization")
        if request.url.path == "/portal-api/releases":
            return httpx.Response(200, json=rows)
        return httpx.Response(
            download_status,
            content=data,
            headers={"Location": "https://evil.example/installer.exe"},
        )

    return AppUpdateClient(
        "https://research.example", cancel, httpx.MockTransport(serve)
    )


@pytest.mark.parametrize(
    "bad",
    [
        "http://example.com",
        "https://u:pw@example.com",
        "https://example.com/path",
        "https://example.com?key=secret",
        "https://example.com:8888",
        "file:///C:/evil.exe",
    ],
)
def test_reject_unapproved_origin_forms(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)


def test_newest_version_and_channel_without_download(release):
    row, _ = release
    same, old, stable, beta = (
        row("0.1.1"),
        row("0.0.9"),
        row("0.1.2", "STABLE"),
        row("0.1.3"),
    )
    requests = []
    c = client([same, old, stable, beta], requests=requests)
    assert c.latest("0.1.1") == beta
    assert c.latest("0.1.1", False) == stable
    assert c.latest("0.1.3") is None
    assert len(requests) == 3 and all(
        u.endswith("/portal-api/releases") for u in requests
    )


@pytest.mark.parametrize(
    "mutation", ["path", "hash", "size", "source", "platform", "draft"]
)
def test_bad_manifest_never_downloads(release, mutation):
    row, _ = release
    r = row("0.1.2")
    m = r["manifest"]
    if mutation == "path":
        m["filename"] = "../../evil.exe"
    if mutation == "hash":
        m["sha256"] = "no-hash"
    if mutation == "size":
        m["size"] = 10 * 1024**3
    if mutation == "source":
        m["source_archive"]["source_revision"] = "c" * 40
    if mutation == "platform":
        m["platform"] = "linux"
    if mutation == "draft":
        r["state"]["status"] = "DRAFT"
    with pytest.raises(ValueError, match="INVALID_RELEASE"):
        client([r]).latest("0.1.1")


def test_stream_hash_cache_reuse_and_corrupt_cache_repair(release, tmp_path):
    row, data = release
    r = row("0.1.2")
    requests, progress = [], []
    c = client([r], data, requests)
    p = c.download(r, tmp_path, lambda done, total: progress.append((done, total)))
    assert p.read_bytes() == data and progress[-1] == (len(data), len(data))
    assert not list(tmp_path.glob("*.part"))
    before = len([u for u in requests if u.endswith("/download")])
    assert c.download(r, tmp_path) == p
    assert len([u for u in requests if u.endswith("/download")]) == before
    p.write_bytes(b"MZ" + b"x" * (len(data) - 2))
    assert c.download(r, tmp_path).read_bytes() == data


@pytest.mark.parametrize(
    "case",
    [
        "truncated",
        "tampered",
        "not-exe",
        "too-long",
        "redirect",
        "withdrawn",
        "cancelled",
    ],
)
def test_unverified_download_cannot_survive(release, tmp_path, case):
    row, data = release
    r = row("0.1.2")
    cancel = threading.Event()
    rows, status = [r], 200
    if case == "truncated":
        data = data[:100]
    if case == "tampered":
        data = b"MZ" + b"x" * (len(data) - 2)
    if case == "not-exe":
        data = b"NO" + data[2:]
        r["manifest"]["sha256"] = hashlib.sha256(data).hexdigest()
    if case == "too-long":
        data += b"x"
    if case == "redirect":
        status = 302
    if case == "withdrawn":
        rows = []
    c = client(rows, data, cancel=cancel, download_status=status)
    progress = lambda done, total: cancel.set() if case == "cancelled" else None
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        c.download(r, tmp_path, progress)
    assert not list(tmp_path.iterdir())


def spin(app, predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("worker did not settle")


def test_controller_background_check_download_and_no_automatic_install(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    from sic_xrt_analyzer.ui import app_update_controller as module

    row, data = release
    r = row("0.1.2")
    requests = []
    c = client([r], data, requests)
    monkeypatch.setattr(module, "AppUpdateClient", lambda *args: c)
    monkeypatch.setattr(module, "__version__", "0.1.1")  # Simulate the previous installed app.
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    u = b.appUpdates
    u.checkUpdates()
    assert u.busy
    spin(qt_app, lambda: not u.busy)
    assert u.state["version"] == "0.1.2" and u.path is None and u.armed is None
    assert len(requests) == 1
    u.download()
    spin(qt_app, lambda: not u.busy)
    assert u.path.read_bytes() == data and u.progress == 100 and u.armed is None
    u.verified = u.path
    b.sync_controller.busy = True
    assert not u.armInstall()
    b.sync_controller.busy = False
    assert u.armInstall()
    u.armed = None


def test_install_shutdown_only_and_tamper_recheck(
    release, tmp_path, bridge_factory, monkeypatch
):
    import sic_xrt_analyzer.ui.app_update_controller as module

    row, data = release
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    u = b.appUpdates
    u.release = row("0.1.2")
    u.directory.mkdir()
    p = u.directory / (u.release["manifest"]["sha256"] + ".exe")
    p.write_bytes(data)
    u.path = u.verified = p
    app_executable=tmp_path / "installed" / "SiCXrtAnalyzer.exe"
    app_executable.parent.mkdir();app_executable.write_bytes(b"MZ-existing-install")
    monkeypatch.setattr(module.sys,"executable",str(app_executable))
    calls = []
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **k: calls.append((a, k))
    )
    assert u.armInstall() and calls == []
    u.shutdown()
    u.launch_after_exit()
    command=calls[0][0][0]
    assert command[0]==str(p) and '/VERYSILENT' in command and '/XRTUPDATE=1' in command
    assert '/DIR='+str(app_executable.parent) in command
    assert '/NORESTARTAPPLICATIONS' in command
    assert calls[0][1]['creationflags']==module.subprocess.CREATE_NO_WINDOW
    calls.clear()
    p.write_bytes(b"tampered")
    u.launch_after_exit()
    assert not calls and u.launch_error


def test_offline_is_nonfatal_and_releases_stay_empty(
    tmp_path, bridge_factory, qt_app, monkeypatch
):
    import sic_xrt_analyzer.ui.app_update_controller as module

    def failure(request):
        raise httpx.ConnectError("private-error-detail", request=request)

    c = AppUpdateClient(
        "https://research.example", transport=httpx.MockTransport(failure)
    )
    monkeypatch.setattr(module, "AppUpdateClient", lambda *args: c)
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    b.appUpdates.checkUpdates()
    spin(qt_app, lambda: not b.appUpdates.busy)
    assert (
        b.appUpdates.release is None
        and "private-error-detail" not in b.appUpdates.error
    )
    assert b.appUpdates.error and not b.appUpdates.armed


def test_qml_dirty_project_and_review_guard_cancel_do_not_arm(tmp_path, qt_app):
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    bridge = FileBridge(
        provider, engine, QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    engine.addImageProvider("tiff", provider)
    engine.rootContext().setContextProperty("fileBridge", bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(
        QUrl.fromLocalFile(
            str(Path(__file__).parents[1] / "src/sic_xrt_analyzer/ui/Main.qml")
        )
    )
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    qt_app.processEvents()
    bridge.project_controller.dirty = True
    bridge.project_controller.changed.emit()
    bridge.appUpdates.verified = tmp_path / "unexecuted.exe"
    bridge.appUpdates.installVerified.emit()
    qt_app.processEvents()
    assert window.findChild(QObject, "projectDirtyDialog").property("visible")
    window.findChild(QObject, "projectDirtyCancel").clicked.emit()
    qt_app.processEvents()
    assert bridge.appUpdates.armed is None and window.isVisible()
    bridge.project_controller.dirty = False
    bridge.project_controller.changed.emit()
    bridge.review_controller.pending = True
    bridge.review_controller.changed.emit()
    bridge.appUpdates.installVerified.emit()
    qt_app.processEvents()
    assert window.findChild(QObject, "reviewDiscardDialog").property("visible")
    window.findChild(QObject, "reviewDiscardCancel").clicked.emit()
    qt_app.processEvents()
    assert bridge.appUpdates.armed is None and window.isVisible()
    bridge.review_controller.pending = False
    bridge.review_controller.changed.emit()
    assert not warnings
    bridge.waitForLoads()
    window.close()
    engine.deleteLater()
