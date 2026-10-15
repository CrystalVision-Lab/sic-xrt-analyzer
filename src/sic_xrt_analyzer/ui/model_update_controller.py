"""Model management worker; shares Sync origin/vault, never edits historical runs."""

import os
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.model_updates.client import UpdateClient
from sic_xrt_analyzer.model_updates.contracts import (
    read_json,
    safe_name,
    safe_path,
    verify_release,
)
from sic_xrt_analyzer.model_updates.store import ModelStore

from .latest_reader import LatestReader


class ModelUpdateController(QObject):
    changed = Signal()
    progressChanged = Signal(int, int)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        default = (
            Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
            / "models"
        )
        if bridge._settings.format() == QSettings.IniFormat:
            default = Path(bridge._settings.fileName()).parent / "models"
        self.store_error = ""
        try:
            self.store = ModelStore(os.getenv("SIC_XRT_MODEL_DIR", str(default)))
        except (OSError, ValueError):
            self.store = None
            self.store_error = "모델 저장 폴더를 사용할 수 없습니다."
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._done)
        self.progressChanged.connect(self._progress)
        self.cancel_token = threading.Event()
        self.busy = False
        self.status = "업데이트를 확인하세요."
        self.error = ""
        self.available = None
        self.installed_record = None
        self.progress = 0
        self.channel = "STABLE"
        self.context = None
        self.origin_context = None
        bridge.project_controller.changed.connect(self._context_changed)
        bridge.sync_controller.changed.connect(self._context_changed)

    def trust(self):
        default = (
            Path(__file__).resolve().parents[1] / "model_updates/trusted-keys.json"
        )
        path = Path(os.getenv("SIC_XRT_MODEL_TRUST_FILE", str(default)))
        value = read_json(path.read_bytes())
        if (
            not isinstance(value, dict)
            or value.get("schema") != "xrt_release_trust/v1"
            or not isinstance(value.get("origins"), dict)
        ):
            raise ValueError("INVALID_TRUST_FILE")
        return value

    def fingerprint(self):
        sync = self.bridge.sync_controller
        p = self.bridge.project_controller
        return (
            sync.endpoint,
            sync.client_id,
            p.project.project_id if p.project else "",
            p.project.revision if p.project else 0,
            p.path,
        )

    def _context_changed(self):
        if self.context is not None and self.context != self.fingerprint():
            self.cancel_token.set()
            self.available = None
            self.changed.emit()

    def protected(self):
        b = self.bridge
        return (
            b.pipeline.state == AnalysisState.RUNNING
            or b.research.loading
            or b.project_controller.busy
            or b.project_controller.dirty
            or b.review_controller.pending
            or b.review_controller.draft is not None
            or b.roi_manager.dirty
        )

    def _start(self, work):
        if self.store is None:
            self.error = self.store_error
            self.changed.emit()
            return
        if self.busy:
            return
        self.cancel_token = threading.Event()
        cancel = self.cancel_token
        self.context = self.fingerprint()
        context = self.context
        self.busy = True
        self.error = ""
        self.changed.emit()

        def run():
            try:
                return {"context": context, "value": work(cancel)}
            except Exception as exc:  # noqa: BLE001 -- never show network credentials or raw runtime failures
                return {
                    "context": context,
                    "error": str(exc)
                    if isinstance(exc, ValueError)
                    else "MODEL_UPDATE_FAILED",
                }

        self.reader.submit(run)

    def _client(self, cancel):
        sync = self.bridge.sync_controller
        if not sync.endpoint:
            raise ValueError("SERVER_NOT_CONFIGURED")
        return UpdateClient(sync.endpoint, sync.token(), cancel)

    @Slot()
    def checkUpdates(self):
        channel = self.channel

        def work(cancel):
            trust = self.trust()
            client = self._client(cancel)
            try:
                rows = client.listing(channel)
                if not isinstance(rows, list) or len(rows) > 100:
                    raise ValueError("RELEASE_LIST_SIZE")
                chosen = None
                unavailable = []
                rejected = 0
                minimum = self.store.state()["sequences"].get(
                    client.origin + "|" + channel, 0
                )
                for row in rows:
                    envelope = row["release"]
                    try:
                        m = verify_release(
                            envelope,
                            trust,
                            client.origin,
                            channel=channel,
                            minimum_sequence=0,
                            allow_expired=row["status"] != "AVAILABLE",
                        )
                    except ValueError:
                        # Retired keys/incompatible historical entries cannot block a newer trusted release.
                        rejected += 1
                        continue
                    if row["status"] != "AVAILABLE":
                        unavailable.append(m["release_id"])
                        self.store.remember(
                            client.origin, channel, envelope, revoked=True
                        )
                        continue
                    if m["release_sequence"] < minimum:
                        continue
                    if (
                        chosen is None
                        or m["release_sequence"]
                        > chosen["metadata"]["release_sequence"]
                    ):
                        chosen = envelope
                if chosen:
                    self.store.remember(client.origin, channel, chosen)
                current = self.store.state()["current"]
                current_invalid = False
                if current:
                    try:
                        self.store.verify_installed(current, trust)
                    except (OSError, ValueError, KeyError):
                        current_invalid = True
                return {
                    "operation": "check",
                    "release": chosen,
                    "unavailable": unavailable,
                    "rejected": rejected,
                    "current_invalid": current_invalid,
                }
            finally:
                client.close()

        self._start(work)

    @Slot(bool)
    def selectBeta(self, enabled):
        if self.busy:
            return
        self.channel = "BETA" if enabled else "STABLE"
        self.available = None
        self.changed.emit()

    @Slot()
    def download(self):
        if not self.available:
            return
        envelope = self.available
        channel = self.channel

        def work(cancel):
            trust = self.trust()
            client = self._client(cancel)
            try:
                record = self.store.install(
                    client,
                    envelope,
                    trust,
                    channel,
                    lambda done, total: self.progressChanged.emit(done, total),
                )
                return {"operation": "download", "record": record}
            finally:
                client.close()

        self._start(work)

    @Slot()
    def cancel(self):
        self.cancel_token.set()

    @Slot()
    def activate(self):
        if self.installed_record:
            self._activate(self.installed_record)

    @Slot(str)
    def activateInstalled(self, release_id):
        if self.store is None:
            return
        try:
            root = safe_path(self.store.root / safe_name(release_id))
            e = read_json((root / "release.json").read_bytes())
            origin = self.bridge.sync_controller.endpoint
            verify_release(
                e,
                self.trust(),
                origin,
                channel=e["metadata"]["channel"],
                allow_expired=True,
            )
            self._activate(
                {
                    "release_id": release_id,
                    "origin": origin,
                    "channel": e["metadata"]["channel"],
                }
            )
        except (OSError, ValueError, KeyError):
            self.error = "INSTALLED_MODEL_UNAVAILABLE"
            self.changed.emit()

    @Slot()
    def rollback(self):
        if self.store is None:
            return
        record = self.store.rollback_record()
        if record:
            self._activate(record)

    def _activate(self, record):
        if self.protected():
            self.error = (
                "분석·검수·편집을 마치고 프로젝트를 저장한 뒤 모델을 변경하세요."
            )
            self.changed.emit()
            return
        if os.getenv("SIC_XRT_MODEL_BUNDLE"):
            self.error = "개발용 모델 환경변수 Override가 활성화되어 있습니다."
            self.changed.emit()
            return

        def work(cancel):
            trust = self.trust()
            root = self.store.verify_installed(record, trust)
            state = self.store.state()
            if "legacy_bundle" not in record and record not in (
                state["current"],
                state["previous"],
            ):
                envelope = read_json((root / "release.json").read_bytes())
                verify_release(
                    envelope,
                    trust,
                    record["origin"],
                    channel=record["channel"],
                    minimum_sequence=state["sequences"].get(
                        record["origin"] + "|" + record["channel"], 0
                    ),
                    allow_expired=True,
                )
            from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter

            adapter = DesktopResearchAdapter(root)
            if cancel.is_set():
                raise ValueError("UPDATE_CANCELED")
            return {
                "operation": "activate",
                "record": record,
                "adapter": adapter,
                "bundle": str(root),
            }

        self._start(work)

    def startup_bundle(self):
        if self.store is None:
            return None
        try:
            record = self.store.recover_record(self.trust())
            if record:
                self.status = "설치된 승인 모델 복원"
                return str(self.store.verify_installed(record, self.trust()))
        except (OSError, ValueError, KeyError):
            self.error = "모델 설치 상태를 읽지 못했습니다. 번들 모델로 복구합니다."
        return None

    def startup_fallback(self, failed):
        if self.store is None:
            return None
        try:
            record = self.store.rollback_record()
            if record:
                path = str(self.store.verify_installed(record, self.trust()))
                if path != failed:
                    return path
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _progress(self, done, total):
        self.progress = int(100 * done / total) if total else 0
        self.changed.emit()

    def _done(self, result, error):
        self.busy = False
        if error or not result:
            self.error = "MODEL_UPDATE_FAILED"
            self.changed.emit()
            return
        if result["context"] != self.fingerprint():
            self.error = "작업 대상이 바뀌어 업데이트 응답을 폐기했습니다."
            self.changed.emit()
            return
        if "error" in result:
            self.error = result["error"]
            self.status = "현재 모델을 유지합니다."
            self.changed.emit()
            return
        if self.cancel_token.is_set():
            self.error = "UPDATE_CANCELED"
            self.status = "현재 모델을 유지합니다."
            self.changed.emit()
            return
        value = result["value"]
        operation = value["operation"]
        if operation == "check":
            self.available = value["release"]
            self.status = (
                "승인된 새 모델이 있습니다."
                if self.available
                else "최신 승인 모델이 없습니다. 현재 모델을 유지합니다."
            )
            if not self.available and value.get("rejected"):
                self.error = "모델 목록의 서명·신뢰키·호환성을 확인하지 못했습니다. 현재 모델을 유지합니다."
            if value.get("current_invalid"):
                self.error = "현재 설치 모델의 서명·상태·파일을 확인할 수 없습니다. 작업을 저장한 뒤 이전 모델을 복원하세요."
            current = self.store.state()["current"]
            if current and current.get("release_id") in value.get("unavailable", []):
                self.error = "현재 모델의 배포 승인이 철회되었거나 재검토 중입니다. 작업을 저장한 뒤 이전 모델을 복원하세요."
        elif operation == "download":
            self.installed_record = value["record"]
            self.status = "설치 완료. 적용 버튼을 누르면 새 분석부터 사용합니다."
        elif operation == "activate":
            if self.protected():
                self.error = "작업 상태가 바뀌었습니다. 저장 후 다시 적용하세요."
            else:
                try:
                    adapter = self.bridge.pipeline.adapter
                    old_bundle = self.bridge.research.bundle
                    previous_legacy = (
                        {
                            "legacy_bundle": old_bundle,
                            "model_hash": adapter.model_version,
                        }
                        if adapter and old_bundle
                        else None
                    )
                    settings = self.bridge._settings
                    direct = settings.value("researchModelBundle", "")
                    settings.remove("researchModelBundle")
                    settings.sync()
                    if settings.status() != QSettings.NoError:
                        if direct:
                            settings.setValue("researchModelBundle", direct)
                        raise OSError("Settings could not be persisted")
                    try:
                        self.store.activate(value["record"], previous_legacy)
                    except (OSError, ValueError):
                        if direct:
                            settings.setValue("researchModelBundle", direct)
                            settings.sync()
                        raise
                except (OSError, ValueError):
                    self.error = (
                        "모델 상태 저장에 실패했습니다. 현재 모델을 유지합니다."
                    )
                    self.changed.emit()
                    return
                # Adapter is ready before changing the active reference. Completed results stay untouched.
                b = self.bridge
                b.pipeline.adapter = value["adapter"]
                b.research.bundle = value["bundle"]
                b.research.changed.emit()
                b.analysisChanged.emit()
                self.status = "새 모델을 다음 분석부터 사용합니다."
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        adapter = self.bridge.pipeline.adapter
        try:
            installed = self.store.installed() if self.store else []
            can_rollback = bool(self.store and self.store.rollback_record())
        except (OSError, ValueError, KeyError):
            installed = []
            can_rollback = False
        messages = {
            "UNTRUSTED_SIGNING_KEY": "모델 서명 검증키가 등록되지 않았습니다. 관리자에게 확인하세요.",
            "UPDATE_SERVER_UNAVAILABLE": "업데이트 서버에 연결할 수 없습니다.",
            "MODEL_UPDATE_FAILED": "모델 업데이트를 완료하지 못했습니다. 현재 모델을 유지합니다.",
            "INSUFFICIENT_MODEL_DISK": "모델 설치 공간이 부족합니다.",
            "UPDATE_CANCELED": "모델 업데이트를 취소했습니다.",
            "RELEASE_SIGNATURE": "모델 서명을 검증하지 못했습니다.",
            "SERVER_NOT_CONFIGURED": "중앙 서버 연결을 먼저 설정하세요.",
        }
        friendly_error = messages.get(
            self.error,
            self.error
            if any("가" <= c <= "힣" for c in self.error)
            else "모델 검증 또는 업데이트에 실패했습니다. 현재 모델을 유지합니다."
            if self.error
            else "",
        )
        return {
            "busy": self.busy,
            "status": self.status,
            "error": friendly_error,
            "progress": self.progress,
            "modelId": adapter.model_id if adapter else "",
            "modelHash": adapter.model_version if adapter else "",
            "source": "환경변수 Override"
            if os.getenv("SIC_XRT_MODEL_BUNDLE")
            else "직접 선택"
            if self.bridge._settings.value("researchModelBundle", "")
            else "승인 설치/번들",
            "release": self.available["metadata"] if self.available else {},
            "installed": installed,
            "canActivate": bool(self.installed_record) and not self.protected(),
            "canRollback": can_rollback and not self.protected(),
        }

    def shutdown(self):
        self.cancel_token.set()
        self.reader.shutdown()
