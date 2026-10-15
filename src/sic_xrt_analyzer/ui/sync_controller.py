"""Opt-in sync worker, isolated from inference/project writes and stale UI results."""

import os
import sqlite3
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot

from sic_xrt_analyzer.results.persistence import ProjectStore
from sic_xrt_analyzer.sync.client import (
    Outbox,
    SyncError,
    Transport,
    endpoint_url,
    make_crop,
    synchronize,
)
from sic_xrt_analyzer.sync.credentials import CredentialVault
from sic_xrt_analyzer.sync.protocol import digest, project_projection

from .latest_reader import LatestReader


class SyncController(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.settings = bridge._settings
        self.endpoint = str(self.settings.value("syncServer", ""))
        default = (
            Path(self.settings.fileName()).parent / "sync"
            if self.settings.format() == QSettings.IniFormat
            else Path(
                QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            )
            / "sync"
        )
        self.outbox = Outbox(
            Path(os.getenv("SIC_XRT_SYNC_DIR", str(default))) / "outbox.sqlite3"
        )
        self.vault = CredentialVault()
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._done)
        self.cancel_token = threading.Event()
        self.busy = False
        self.status = "UNCONFIGURED" if not self.endpoint else "DISCONNECTED"
        self.error = ""
        self.last_sync = ""
        self.pending_reviews = -1
        self.pending_batches = 0
        self.pending_crops = 0
        self.client_id = self.outbox.client_id
        self.context = None
        bridge.project_controller.changed.connect(self._project_changed)

    def fingerprint(self):
        c = self.bridge.project_controller
        p = c.project
        return (p.project_id, p.revision, c.path, c.dirty) if p else None

    def _project_changed(self):
        current = self.fingerprint()
        if current != self.context:
            self.cancel()
            self.context = current
            self.last_sync = ""
            self.pending_reviews = -1
            self.pending_batches = 0
            self.pending_crops = 0
            if self.endpoint and not self.busy:
                self.status = "DISCONNECTED"
        self.changed.emit()

    def require_saved(self):
        c = self.bridge.project_controller
        if (
            not c.project
            or not c.path
            or c.dirty
            or c.busy
            or c.read_only
            or self.bridge.review_controller.pending
        ):
            raise SyncError("SAVE_PROJECT_BEFORE_SYNC")
        return c.project, c.path

    def token(self):
        return self.vault.get(self.endpoint, self.outbox.client_id)

    @Slot(str, str, str, result=bool)
    def configure(self, endpoint, client_id, credential):
        if self.busy:
            return False
        try:
            origin = endpoint_url(endpoint)
            if client_id != self.outbox.client_id:
                self.outbox.set_client_id(client_id)
            if credential:
                if not credential.startswith("xrt_") or len(credential) > 200:
                    raise SyncError("INVALID_CREDENTIAL")
                self.vault.set(origin, client_id, credential)
            self.client_id = self.outbox.client_id
            self.endpoint = origin
            self.settings.setValue("syncServer", origin)
            self.settings.sync()
            self.status = "DISCONNECTED"
            self.error = ""
            self.changed.emit()
            return True
        except Exception as exc:  # noqa: BLE001 -- contain OS vault/worker errors without secret details
            self.error = (
                str(exc)
                if isinstance(exc, SyncError)
                else "OS_CREDENTIAL_VAULT_UNAVAILABLE"
            )
            self.changed.emit()
            return False

    @Slot()
    def forgetCredential(self):
        if self.busy:
            return
        try:
            self.vault.delete(self.endpoint, self.outbox.client_id)
            self.status = "DISCONNECTED"
            self.error = ""
        except Exception:  # noqa: BLE001 -- OS credential backend errors must remain contained
            self.error = "OS_CREDENTIAL_VAULT_UNAVAILABLE"
        self.changed.emit()

    def _start(self, function):
        if self.busy:
            return
        self.cancel_token = threading.Event()
        token = self.cancel_token
        context = self.fingerprint()
        self.context = context
        self.busy = True
        self.status = "SYNCING"
        self.error = ""
        self.changed.emit()

        def run():
            try:
                return {"context": context, "value": function(token)}
            except Exception as exc:  # noqa: BLE001 -- contain OS vault/worker errors without secret details
                queues = {}
                if context and self.endpoint:
                    try:
                        queues = {
                            "batches": self.outbox.pending_count(
                                self.endpoint, context[0]
                            ),
                            "crops": self.outbox.pending_count(
                                self.endpoint, context[0], "crop"
                            ),
                        }
                    except sqlite3.Error:
                        pass
                return {
                    "context": context,
                    "queues": queues,
                    "error": str(exc)
                    if isinstance(exc, SyncError)
                    else "SYNC_OPERATION_FAILED",
                }

        self.reader.submit(run)

    def _transport(self, cancel):
        return Transport(self.endpoint, self.token(), cancel)

    @Slot()
    def testConnection(self):
        if not self.endpoint:
            self.error = "SERVER_NOT_CONFIGURED"
            self.changed.emit()
            return
        client_id = self.outbox.client_id

        def work(cancel):
            value = self._transport(cancel).request("GET", "/api/v1/health")
            if value.get("client_id") != client_id:
                raise SyncError("DEVICE_MISMATCH")
            return {"status": "CONNECTED"}

        self._start(work)

    @Slot()
    def refresh(self):
        if self.busy or not self.endpoint:
            return
        try:
            project, _ = self.require_saved()
        except SyncError:
            return
        endpoint = self.endpoint
        previous_status = self.status

        def work(cancel):
            _root, entities = project_projection(project)
            receipt = self.outbox.receipt(endpoint, project.project_id)
            known = receipt.get("inventory", {}).get("review_events", {})
            return {
                "status": previous_status,
                "last": receipt.get("received_at", ""),
                "pending": sum(
                    known.get(i) != digest(e)
                    for i, e in entities["review_events"].items()
                ),
                "batches": self.outbox.pending_count(endpoint, project.project_id),
                "crops": self.outbox.pending_count(
                    endpoint, project.project_id, "crop"
                ),
            }

        self._start(work)

    @Slot()
    def synchronize(self):
        try:
            project, path = self.require_saved()
        except SyncError as exc:
            self.error = str(exc)
            self.changed.emit()
            return

        def work(cancel):
            saved = ProjectStore().load(path)
            if saved != project:
                raise SyncError("DISK_SNAPSHOT_CHANGED")
            receipt = synchronize(self.outbox, saved, self._transport(cancel))
            if not receipt:
                raise SyncError("ACK_MISSING")
            return {
                "status": "ACKNOWLEDGED",
                "last": receipt["received_at"],
                "pending": 0,
                "batches": 0,
            }

        self._start(work)

    @Slot(str, str, str, str, int, int, int, int, bool)
    def uploadCrop(
        self, source_id, run_id, target_type, target_id, x, y, width, height, consent
    ):
        try:
            project, path = self.require_saved()
        except SyncError as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        endpoint = self.endpoint

        def work(cancel):
            saved = ProjectStore().load(path)
            if saved != project:
                raise SyncError("DISK_SNAPSHOT_CHANGED")
            if not self.outbox.receipt(endpoint, project.project_id):
                raise SyncError("SYNC_METADATA_FIRST")
            body = make_crop(
                saved,
                source_id,
                run_id,
                target_type,
                target_id,
                (x, y, width, height),
                consent=consent,
                cancel=cancel,
            )
            known = (
                self.outbox.receipt(endpoint, project.project_id)
                .get("inventory", {})
                .get("review_events", {})
            )
            if any(
                ident not in known for ident in body["metadata"]["linked_review_ids"]
            ):
                raise SyncError("SYNC_METADATA_FIRST")
            ident = self.outbox.stage_crop(endpoint, project.project_id, body)
            self.outbox.attempt(ident)
            try:
                ack = self._transport(cancel).request(
                    "POST", "/api/v1/projects/" + project.project_id + "/crops", body
                )
                self.outbox.acknowledge(ident, ack)
            except SyncError as exc:
                self.outbox.failed(ident, str(exc))
                raise
            return {"status": "CROP_ACKNOWLEDGED"}

        self._start(work)

    @Slot(bool)
    def retryCrops(self, consent):
        try:
            project, _path = self.require_saved()
            if consent is not True:
                raise SyncError("EXPLICIT_CROP_CONSENT_REQUIRED")
        except SyncError as exc:
            self.error = str(exc)
            self.changed.emit()
            return
        endpoint = self.endpoint

        def work(cancel):
            transport = self._transport(cancel)
            known = (
                self.outbox.receipt(endpoint, project.project_id)
                .get("inventory", {})
                .get("review_events", {})
            )
            for ident, body in self.outbox.pending(
                endpoint, project.project_id, "crop"
            ):
                if any(
                    review not in known
                    for review in body["metadata"]["linked_review_ids"]
                ):
                    raise SyncError("SYNC_METADATA_FIRST")
                self.outbox.attempt(ident)
                try:
                    ack = transport.request(
                        "POST",
                        "/api/v1/projects/" + project.project_id + "/crops",
                        body,
                    )
                    self.outbox.acknowledge(ident, ack)
                except SyncError as exc:
                    self.outbox.failed(ident, str(exc))
                    raise
            left = self.outbox.pending_count(endpoint, project.project_id, "crop")
            if left:
                raise SyncError("MORE_PENDING_CROPS_RETRY")
            return {"status": "CROP_ACKNOWLEDGED", "crops": left}

        self._start(work)

    def _done(self, value, error):
        self.busy = False
        if not value or value.get("context") != self.fingerprint():
            self.changed.emit()
            return
        code = value.get("error") or error
        if code:
            self.pending_batches = value.get("queues", {}).get(
                "batches", self.pending_batches
            )
            self.pending_crops = value.get("queues", {}).get(
                "crops", self.pending_crops
            )
            self.error = code
            self.status = {
                "AUTHENTICATION_FAILED": "AUTH_FAILED",
                "SYNC_CONFLICT": "CONFLICT",
                "OFFLINE": "OFFLINE",
                "TIMEOUT": "OFFLINE",
                "CANCELED": "RETRY",
            }.get(code, "RETRY")
        else:
            result = value["value"]
            self.status = result["status"]
            self.error = ""
            self.last_sync = result.get("last", self.last_sync)
            self.pending_reviews = result.get("pending", self.pending_reviews)
            self.pending_batches = result.get("batches", self.pending_batches)
            self.pending_crops = result.get("crops", self.pending_crops)
        self.changed.emit()

    @Slot()
    def cancel(self):
        self.cancel_token.set()
        self.reader.invalidate()
        self.busy = False
        if self.status == "SYNCING":
            self.status = "RETRY"
        self.changed.emit()

    def shutdown(self):
        self.cancel()
        self.reader.shutdown()

    @Property("QVariantMap", notify=changed)
    def state(self):
        c = self.bridge.project_controller
        return {
            "endpoint": self.endpoint,
            "clientId": self.client_id,
            "status": self.status,
            "busy": self.busy,
            "error": self.error,
            "last": self.last_sync,
            "pendingReviews": self.pending_reviews,
            "pendingBatches": self.pending_batches,
            "pendingCrops": self.pending_crops,
            "canSync": bool(
                c.project
                and c.path
                and not c.dirty
                and not c.busy
                and not c.read_only
                and not self.bridge.review_controller.pending
                and not self.busy
                and self.endpoint
            ),
            "automaticUpload": False,
        }
