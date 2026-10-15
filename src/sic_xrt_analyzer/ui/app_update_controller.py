"""GUI-safe application updates. Install is armed only after existing close guards."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, Signal, Slot

from sic_xrt_analyzer import __version__
from sic_xrt_analyzer.application_updates import (
    DEFAULT_ORIGIN,
    AppUpdateClient,
    preferred_origin,
    release_highlights,
    update_command,
)

from .latest_reader import LatestReader

ERRORS = {
    "INVALID_ORIGIN": "HTTPS 배포 사이트 주소만 입력하세요. 경로·인증값은 넣지 마세요.",
    "INVALID_RELEASE": "서버의 버전 정보를 확인할 수 없습니다.",
    "CANCELLED": "작업을 취소했습니다.",
    "INTEGRITY_FAILED": "설치 파일 검증에 실패했습니다. 다시 다운로드하세요.",
    "RELEASE_UNAVAILABLE": "이 버전은 현재 배포 중이 아닙니다. 새로 확인하세요.",
    "NO_DISK_SPACE": "업데이트 폴더의 디스크 공간이 부족합니다.",
    "CACHE_UNAVAILABLE": "업데이트 폴더를 사용할 수 없습니다.",
}


class AppUpdateController(QObject):
    changed = Signal()
    progressChanged = Signal(int)
    updateAvailable = Signal()
    installVerified = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._done)
        self.progressChanged.connect(self._progress)
        self.cancel_token = threading.Event()
        self.busy = False
        self.status = "새 버전을 확인합니다."
        self.operation = ""
        self._startup_checked = False
        self.error = ""
        self.release = None
        self.path = self.verified = self.armed = None
        self.progress = 0
        stored_origin = bridge._settings.value(
            "applicationUpdates/origin", DEFAULT_ORIGIN
        )
        try:
            self.origin = preferred_origin(stored_origin)
        except (ValueError, TypeError, AttributeError):
            # Keep invalid explicit preferences visible for correction.
            self.origin = stored_origin
        if self.origin != stored_origin:
            bridge._settings.setValue("applicationUpdates/origin", self.origin)
            bridge._settings.sync()
        # Startup discovery is a product behavior, including installations with
        # the previous optional check disabled. Download/install still needs a click.
        self.startup = True
        bridge._settings.setValue("applicationUpdates/startup", True)
        bridge._settings.sync()
        self.beta = bridge._settings.value("applicationUpdates/beta", True, type=bool)
        default = (
            Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
            / "app-updates"
        )
        if bridge._settings.format() == QSettings.IniFormat:
            default = Path(bridge._settings.fileName()).parent / "app-updates"
        self.directory = Path(os.getenv("SIC_XRT_APP_UPDATE_DIR", str(default)))
        self.launch_error = ""
        self.install_after_download = False

    @Property("QVariantMap", notify=changed)
    def state(self):
        m = self.release["manifest"] if self.release else {}
        return {
            "currentVersion": __version__,
            "origin": self.origin,
            "startup": self.startup,
            "beta": self.beta,
            "busy": self.busy,
            "operation": self.operation,
            "status": self.status,
            "error": self.error,
            "progress": self.progress,
            "version": m.get("version", ""),
            "notes": m.get("notes", ""),
            "highlights": release_highlights(m.get("notes", "")),
            "sizeMiB": round(m.get("size", 0) / 1024**2, 1),
            "downloaded": self.path is not None,
            "canInstall": self.path is not None
            and sys.platform == "win32"
            and bool(getattr(sys, "frozen", False)),
            "frozen": bool(getattr(sys, "frozen", False)),
        }

    @Slot(str, bool, bool)
    def configure(self, origin, startup, beta):
        if self.busy:
            return
        try:
            self.origin = preferred_origin(origin)
        except ValueError:
            self.error = ERRORS["INVALID_ORIGIN"]
            self.changed.emit()
            return
        self.startup, self.beta = True, beta
        self.release = self.path = self.verified = self.armed = None
        for key, value in (
            ("origin", self.origin),
            ("startup", True),
            ("beta", beta),
        ):
            self.bridge._settings.setValue("applicationUpdates/" + key, value)
        self.error = ""
        self.changed.emit()
        self.checkUpdates()

    def _start(self, kind, work):
        if self.busy:
            return
        self.cancel_token = threading.Event()
        cancel = self.cancel_token
        origin = self.origin
        self.busy, self.error, self.progress = True, "", 0
        self.operation = kind
        self.verified = None
        self.changed.emit()

        def run():
            try:
                return {
                    "kind": kind,
                    "value": work(AppUpdateClient(origin, cancel)),
                    "cancel": cancel,
                }
            except Exception as exc:  # noqa: BLE001 -- never display network payloads or secrets
                code = str(exc) if isinstance(exc, ValueError) else "NETWORK_FAILED"
                return {
                    "kind": kind,
                    "error": ERRORS.get(
                        code,
                        "업데이트 서버에 연결할 수 없습니다. 나중에 다시 시도하세요.",
                    ),
                    "cancel": cancel,
                }

        self.reader.submit(run)

    @Slot()
    def checkOnStartup(self):
        """Check once after the first window is ready; never block initial rendering."""
        if self._startup_checked:
            return
        self._startup_checked = True
        self.checkUpdates()

    @Slot()
    def checkUpdates(self):
        if self.busy:
            return
        self.install_after_download = False
        self.status = "새 버전 확인 중…"
        self.release = self.path = None
        self._start("check", lambda c: c.latest(__version__, self.beta))

    @Slot()
    def download(self):
        if self.busy or self.release is None:
            return
        release = self.release
        # Only our previous recorded installer is removed; never scan user files.
        old = self.bridge._settings.value("applicationUpdates/cached", "")
        old_path = self.directory / old if old else None
        if (
            old_path
            and len(old) == 68
            and old.endswith(".exe")
            and old[:-4].isalnum()
            and old != release["manifest"]["sha256"] + ".exe"
        ):
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                self.install_after_download = False
                self.error = "이전 업데이트 캐시를 정리할 수 없습니다."
                self.changed.emit()
                return
        self.status = "설치 파일 다운로드·SHA-256 확인 중…"
        last = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] >= 0.1 or done == total:
                last[0] = now
                self.progressChanged.emit(round(100 * done / total))

        self._start("download", lambda c: c.download(release, self.directory, progress))

    @Slot()
    def update(self):
        if self.busy or self.release is None:
            return
        self.install_after_download = True
        if self.path:
            self.verifyInstall()
        else:
            self.download()

    @Slot()
    def verifyInstall(self):
        if self.busy or not self.state["canInstall"]:
            return
        release, path = self.release, self.path
        self.install_after_download = False
        self.status = "배포 상태·설치 파일 다시 확인 중…"

        def verify(client):
            client.ensure_published(release)
            client.verify(path, release)
            return path

        self._start("verify", verify)

    @Slot(result=bool)
    def armInstall(self):
        if not self.verified or self.busy or self._working():
            self.status = "진행 중인 분석·동기화·파일 작업을 마친 뒤 설치하세요."
            self.changed.emit()
            return False
        self.armed = self.verified
        self.verified = None
        return True

    def _working(self):
        b = self.bridge
        return (
            b.pipeline.state.value == "RUNNING"
            or b.research.loading
            or b.project_controller.busy
            or b.sync_controller.busy
            or b.stack_viewer.busy
            or b.stack3d_controller.busy
            or b.defect3d_controller.busy
            or b.folder_map.busy
            or b.workbench.busy
            or b.model_update_controller.busy
            or b.registration_controller.busy
            or b.wafer_map_controller.busy
            or b.research_controller.experiments.loading
            or b.stack3d_controller.manual_pending
        )

    @Slot()
    def cancel(self):
        self.cancel_token.set()
        self.install_after_download = False
        self.verified = self.armed = None

    def _progress(self, value):
        self.progress = value
        self.changed.emit()

    def _done(self, result, error):
        self.busy = False
        self.operation = ""
        if error or not result or result["cancel"].is_set():
            self.install_after_download = False
            self.error = (
                ERRORS["CANCELLED"]
                if self.cancel_token.is_set()
                else (result or {}).get("error", "업데이트 작업에 실패했습니다.")
            )
        elif "error" in result:
            self.install_after_download = False
            self.error = result["error"]
        elif result["kind"] == "check":
            self.release = result["value"]
            self.status = (
                "새 버전을 다운로드할 수 있습니다."
                if self.release
                else "현재 사용할 수 있는 새 버전이 없습니다."
            )
            if self.release:
                self.updateAvailable.emit()
        elif result["kind"] == "download":
            self.path = result["value"]
            self.bridge._settings.setValue("applicationUpdates/cached", self.path.name)
            self.status = "다운로드·SHA-256 확인 완료. 설치하면 프로그램을 종료합니다."
            self.progress = 100
            if self.install_after_download:
                self.install_after_download = False
                self.verifyInstall()
        elif result["kind"] == "verify":
            self.verified = result["value"]
            self.status = "설치 준비 완료. 저장하지 않은 작업을 확인합니다."
            self.installVerified.emit()
        self.changed.emit()

    def shutdown(self):
        self.cancel_token.set()
        self.reader.shutdown()

    def launch_after_exit(self):
        if not self.armed:
            return
        try:
            AppUpdateClient(self.origin).verify(self.armed, self.release)
            command = update_command(self.armed, sys.executable)
            subprocess.Popen(
                command,
                cwd=str(self.directory),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, ValueError):
            self.launch_error = "설치 프로그램을 실행할 수 없습니다. 다운로드 사이트에서 직접 설치하세요."
