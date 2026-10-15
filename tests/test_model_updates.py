"""Signed updater failure paths, real ONNX loading, and Qt controller integration."""

import copy
import threading

import httpx
import pytest
from model_update_fixtures import bundle, signing
from PySide6.QtCore import QSettings
from test_analysis_pipeline import spin

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.model_updates.client import UpdateClient
from sic_xrt_analyzer.model_updates.contracts import canonical, verify_release
from sic_xrt_analyzer.model_updates.store import ModelStore
from sic_xrt_analyzer.model_updates.validation import validate_bundle


@pytest.fixture
def release(tmp_path):
    root = tmp_path / "candidate"
    bundle(root)
    envelope, trust, key = signing(root)
    return root, envelope, trust, key


def client(release, cancel=None, fault=None):
    root, envelope, _trust, _ = release
    rid = envelope["metadata"]["release_id"]

    def handler(request):
        assert request.headers["Authorization"] == "Bearer xrt_synthetic_only"
        route = request.url.path
        if fault == "redirect":
            return httpx.Response(
                302, headers={"Location": "https://other.invalid/leak"}
            )
        if fault == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        if route.endswith("/download"):
            content = (root / "model.onnx").read_bytes()
            if fault == "truncated":
                content = content[:-1]
            if fault == "corrupt":
                content = b"x" * len(content)
            if fault == "cancel":
                cancel.set()
            return httpx.Response(200, content=content)
        if route.endswith("/manifest"):
            return httpx.Response(200, content=(root / "manifest.json").read_bytes())
        if route.endswith(rid):
            return httpx.Response(
                200,
                json={
                    "release": envelope,
                    "status": "REVOKED" if fault == "revoked" else "AVAILABLE",
                },
            )
        return httpx.Response(200, json=[{"release": envelope, "status": "AVAILABLE"}])

    return UpdateClient(
        "http://127.0.0.1:18766",
        "xrt_synthetic_only",
        cancel,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "field",
    [
        "model_sha256",
        "manifest_sha256",
        "channel",
        "model_version",
        "release_sequence",
        "minimum_app_version",
        "release_status",
        "artifact_identity",
    ],
)
def test_signed_field_tamper(release, field):
    _, envelope, trust, _ = release
    e = copy.deepcopy(envelope)
    e["metadata"][field] = 99 if field == "release_sequence" else "tampered"
    with pytest.raises(ValueError, match="RELEASE_SIGNATURE"):
        verify_release(e, trust, "http://127.0.0.1:18766")


def test_rotation_revocation_downgrade_and_expiry(release):
    _, e, t, _ = release
    origin = "http://127.0.0.1:18766"
    verify_release(e, t, origin)
    with pytest.raises(ValueError):
        verify_release(e, t, origin, minimum_sequence=2)
    t["origins"][origin]["keys"]["qa-key"]["status"] = "REVOKED"
    with pytest.raises(ValueError):
        verify_release(e, t, origin)
    with pytest.raises(ValueError):
        verify_release(e, {"origins": {}}, origin)


@pytest.mark.parametrize(
    "fault", ["truncated", "corrupt", "redirect", "timeout", "cancel", "revoked"]
)
def test_download_failure_preserves_current(release, tmp_path, fault):
    store = ModelStore(tmp_path / "models")
    before = store.state()
    cancel = threading.Event()
    c = client(release, cancel, fault)
    try:
        with pytest.raises((ValueError, httpx.HTTPError)):
            store.install(c, release[1], release[2])
    finally:
        c.close()
    assert store.state() == before and store.installed() == []
    assert not list(store.root.glob(".staging-*"))


def test_real_download_verify_atomic_install_activation_rollback(release, tmp_path):
    store = ModelStore(tmp_path / "models")
    c = client(release)
    try:
        record = store.install(c, release[1], release[2])
        assert store.state()["current"] is None
        assert store.install(c, release[1], release[2]) == record
    finally:
        c.close()
    root = store.verify_installed(record, release[2])
    validate_bundle(root)
    store.activate(
        record,
        {
            "legacy_bundle": str(release[0]),
            "model_hash": release[1]["metadata"]["model_sha256"],
        },
    )
    assert store.rollback_record()["legacy_bundle"] == str(release[0])
    assert store.recover_record(release[2]) == record
    (root / "model.onnx").write_bytes(b"corrupted")
    assert store.recover_record(release[2]) == store.rollback_record()


def test_pointer_failure_does_not_change_state(release, tmp_path, monkeypatch):
    from sic_xrt_analyzer.model_updates import store as module

    store = ModelStore(tmp_path / "models")
    before = store.state()

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(module, "atomic_json", fail)
    with pytest.raises(OSError):
        store.activate({"release_id": "a"})
    assert store.state() == before


def test_onnx_corruption_and_manifest_contract_rejected(release):
    root = release[0]
    m = __import__("json").loads((root / "manifest.json").read_bytes())
    m["classes"].reverse()
    (root / "manifest.json").write_bytes(canonical(m))
    with pytest.raises(ValueError):
        validate_bundle(root)


def test_controller_no_release_offline_and_protected_state(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    bridge = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    controller = bridge.modelUpdates
    monkeypatch.setattr(controller, "trust", lambda: release[2])
    bridge.centralSync.endpoint = "http://127.0.0.1:18766"

    def empty(cancel):
        return UpdateClient(
            bridge.centralSync.endpoint,
            "xrt_synthetic_only",
            cancel,
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
        )

    monkeypatch.setattr(controller, "_client", empty)
    controller.checkUpdates()
    spin(qt_app, lambda: not controller.busy)
    assert not controller.available and "최신 승인 모델" in controller.status
    before = bridge.pipeline.adapter
    bridge.pipeline.state = AnalysisState.RUNNING
    controller._activate({"release_id": "fake"})
    assert bridge.pipeline.adapter is before and controller.error
    bridge.pipeline.state = AnalysisState.UNAVAILABLE
    monkeypatch.setattr(
        controller, "_client", lambda cancel: client(release, cancel, "timeout")
    )
    controller.checkUpdates()
    spin(qt_app, lambda: not controller.busy)
    assert bridge.pipeline.adapter is before and controller.error


def test_controller_download_apply_and_legacy_rollback(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter

    bridge = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = bridge.modelUpdates
    old = DesktopResearchAdapter(release[0])
    bridge.pipeline.adapter = old
    bridge.research.bundle = str(release[0])
    before = bridge.pipeline.result
    bridge.centralSync.endpoint = "http://127.0.0.1:18766"
    monkeypatch.setattr(c, "trust", lambda: release[2])
    monkeypatch.setattr(c, "_client", lambda cancel: client(release, cancel))
    c.checkUpdates()
    spin(qt_app, lambda: not c.busy)
    assert c.available
    c.download()
    spin(qt_app, lambda: not c.busy)
    assert c.installed_record and bridge.pipeline.adapter is old
    c.activate()
    spin(qt_app, lambda: not c.busy)
    assert (
        not c.error
        and bridge.pipeline.adapter is not old
        and bridge.pipeline.result is before
    )
    assert c.store.rollback_record()["legacy_bundle"] == str(release[0])
    c.rollback()
    spin(qt_app, lambda: not c.busy)
    assert (
        not c.error
        and bridge.research.bundle == str(release[0])
        and bridge.pipeline.result is before
    )


def test_rotated_key_wrong_key_expiry_and_status_replay(release):
    from datetime import UTC, datetime, timedelta

    from model_update_fixtures import signing

    from sic_xrt_analyzer.model_updates.contracts import sign_release

    root, envelope, trust, raw = release
    origin = "http://127.0.0.1:18766"
    rotated, second_trust, second_key = signing(root, key_id="rotated-key", sequence=2)
    trust["origins"][origin]["keys"].update(second_trust["origins"][origin]["keys"])
    assert verify_release(rotated, trust, origin, minimum_sequence=2)
    with pytest.raises(ValueError, match="RELEASE_SIGNATURE"):
        verify_release(sign_release(envelope["metadata"], second_key), trust, origin)
    m = copy.deepcopy(envelope["metadata"])
    m["created_at"] = (datetime.now(UTC) - timedelta(days=16)).isoformat()
    m["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    expired = sign_release(m, raw)
    with pytest.raises(ValueError):
        verify_release(expired, trust, origin)
    assert verify_release(expired, trust, origin, allow_expired=True)


@pytest.mark.parametrize("failure", ["disk", "permission", "concurrent", "runtime"])
def test_install_local_resource_failure_and_retry(
    release, tmp_path, monkeypatch, failure
):
    from collections import namedtuple

    from sic_xrt_analyzer.model_updates import store as module

    store = ModelStore(tmp_path / "models")
    before = store.state()
    c = client(release)
    with monkeypatch.context() as patch:
        if failure == "disk":
            patch.setattr(
                module.shutil, "disk_usage", lambda _: namedtuple("Disk", "free")(0)
            )
        elif failure == "permission":
            patch.setattr(
                c,
                "download",
                lambda *a, **k: (_ for _ in ()).throw(PermissionError("QA")),
            )
        elif failure == "runtime":
            patch.setattr(
                module,
                "validate_bundle",
                lambda *a, **k: (_ for _ in ()).throw(ValueError("QA runtime failure")),
            )
        if failure == "concurrent":
            with store.exclusive(), pytest.raises(OSError):
                store.install(c, release[1], release[2])
        else:
            with pytest.raises((OSError, ValueError)):
                store.install(
                    c, release[1], release[2], validator=module.validate_bundle
                )
    assert store.state() == before and store.installed() == []
    assert not list(store.root.glob(".staging-*"))
    assert store.install(c, release[1], release[2])
    c.close()


@pytest.mark.parametrize("field", ["dirty", "pending", "geometry", "loading"])
def test_controller_protects_unsaved_work(
    release, tmp_path, bridge_factory, qt_app, monkeypatch, field
):
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = b.modelUpdates
    if field == "dirty":
        b.project_controller.dirty = True
    elif field == "pending":
        b.review_controller.pending = True
    elif field == "geometry":
        b.review_controller.draft = {"qa": True}
    else:
        b.research.loading = True
    before = b.pipeline.adapter
    c._activate({"release_id": "qa"})
    assert not c.busy and c.error and b.pipeline.adapter is before
    b.research.loading = False
    b.review_controller.draft = None
    b.review_controller.pending = False
    b.project_controller.dirty = False


def test_controller_discards_response_after_project_context_change(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = b.modelUpdates
    entered, finish = threading.Event(), threading.Event()

    def work(cancel):
        entered.set()
        assert finish.wait(5)
        return {"operation": "check", "release": release[1]}

    c._start(work)
    spin(qt_app, entered.is_set)
    b.centralSync.endpoint = "http://127.0.0.1:18766"
    c._context_changed()
    finish.set()
    spin(qt_app, lambda: not c.busy)
    assert c.available is None and c.error and c.cancel_token.is_set()


def test_qml_update_buttons_install_activate_restart_rollback(
    release, tmp_path, qt_app, monkeypatch
):
    from pathlib import Path

    from PySide6.QtCore import QMetaObject, QObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
    from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider

    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    provider = TiffImageProvider()
    settings = QSettings(str(tmp_path / "qml.ini"), QSettings.IniFormat)
    bridge = FileBridge(provider, engine, settings)
    c = bridge.modelUpdates
    old = DesktopResearchAdapter(release[0])
    bridge.pipeline.adapter = old
    bridge.research.bundle = str(release[0])
    bridge.centralSync.endpoint = "http://127.0.0.1:18766"
    monkeypatch.setattr(c, "trust", lambda: release[2])
    monkeypatch.setattr(c, "_client", lambda cancel: client(release, cancel))
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

    def click(name):
        button = window.findChild(QObject, name)
        assert button and button.property("enabled")
        assert QMetaObject.invokeMethod(button, "clicked")
        spin(qt_app, lambda: not c.busy)
        assert not c.error, c.error

    try:
        dialog = window.findChild(QObject, "modelUpdatesDialog")
        QMetaObject.invokeMethod(dialog, "open")
        click("checkModelUpdatesButton")
        click("downloadModelButton")
        assert bridge.pipeline.adapter is old
        click("activateModelButton")
        assert bridge.pipeline.adapter is not old
        assert not settings.value("researchModelBundle", "")
        installed = c.startup_bundle()
        assert installed == bridge.research.bundle
        bridge.research.load_saved()
        spin(qt_app, lambda: not bridge.research.loading)
        assert bridge.research.bundle == installed
        assert not settings.value("researchModelBundle", "")
        click("rollbackModelButton")
        assert bridge.research.bundle == str(release[0])
        assert not warnings, "\n".join(warnings)
    finally:
        bridge.waitForLoads()
        window.close()
        engine.deleteLater()
        bridge.deleteLater()
        qt_app.processEvents()


def test_known_revoked_current_warns_and_rejects_next_activation(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = b.modelUpdates
    b.centralSync.endpoint = "http://127.0.0.1:18766"
    monkeypatch.setattr(c, "trust", lambda: release[2])
    network = client(release)
    try:
        record = c.store.install(network, release[1], release[2])
    finally:
        network.close()
    c.store.activate(
        record,
        {
            "legacy_bundle": str(release[0]),
            "model_hash": release[1]["metadata"]["model_sha256"],
        },
    )

    def revoked(cancel):
        return UpdateClient(
            b.centralSync.endpoint,
            "synthetic",
            cancel,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json=[{"release": release[1], "status": "REVOKED"}]
                )
            ),
        )

    monkeypatch.setattr(c, "_client", revoked)
    before = b.pipeline.adapter
    c.checkUpdates()
    spin(qt_app, lambda: not c.busy)
    assert "철회" in c.error and c.available is None and b.pipeline.adapter is before
    with pytest.raises(ValueError, match="REVOKED"):
        c.store.verify_installed(record, release[2])
    assert c.store.recover_record(release[2]) == c.store.rollback_record()


@pytest.mark.parametrize("bad", [None, [], {"current": []}])
def test_corrupt_local_state_falls_back_to_bundle(
    tmp_path, bridge_factory, monkeypatch, bad
):
    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = b.modelUpdates
    (c.store.root / "state.json").write_bytes(canonical(bad))
    assert c.startup_bundle() is None
    assert not c.state["canRollback"]
    # A malformed out-of-band trust file must also be a contained startup error.
    trust = tmp_path / "bad-trust.json"
    trust.write_bytes(canonical([]))
    monkeypatch.setenv("SIC_XRT_MODEL_TRUST_FILE", str(trust))
    assert c.startup_bundle() is None


def test_controller_key_rotation_keeps_latest_trusted_release(
    release, tmp_path, bridge_factory, qt_app, monkeypatch
):
    from model_update_fixtures import signing

    b = bridge_factory(
        settings=QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    )
    c = b.modelUpdates
    origin = "http://127.0.0.1:18766"
    b.centralSync.endpoint = origin
    rotated, trust, _ = signing(release[0], sequence=2, key_id="new-key")
    trust["origins"][origin]["keys"].update(release[2]["origins"][origin]["keys"])
    trust["origins"][origin]["keys"]["qa-key"]["status"] = "REVOKED"
    monkeypatch.setattr(c, "trust", lambda: trust)
    rows = [
        {"release": rotated, "status": "AVAILABLE"},
        {"release": release[1], "status": "KEY_OR_RELEASE_UNAVAILABLE"},
    ]
    monkeypatch.setattr(
        c,
        "_client",
        lambda cancel: UpdateClient(
            origin,
            "qa",
            cancel,
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rows)),
        ),
    )
    c.checkUpdates()
    spin(qt_app, lambda: not c.busy)
    assert (
        not c.error
        and c.available == rotated
        and c.store.state()["sequences"][origin + "|STABLE"] == 2
    )
