"""Local desktop integration and persisted, applicable UI preferences."""
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QRunnable,
    QSettings,
    QSize,
    QThreadPool,
    QUrl,
    Signal,
    Slot,
    qVersion,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage
from PySide6.QtQuick import QQuickImageProvider

from sic_xrt_analyzer.analysis.contracts import (
    AnalysisError,
    AnalysisRequest,
    AnalysisScope,
    AnalysisState,
    Region,
)
from sic_xrt_analyzer.analysis.pipeline import AnalysisPipeline
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.imaging.tiff_preview import load_tiff_preview

DEFAULTS = {
    "smoothImages": True,
    "viewerBackground": "#111518",
    "defaultView": "fit",
    "roiVisible": True,
    "rememberRecentFiles": True,
    "recentFileLimit": 10,
    "startupDemo": False,
}


class _LoadSignals(QObject):
    finished = Signal(object)


class _LoadTask(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _LoadSignals()

    def run(self):
        try:
            original = OriginalImageSource(self.path)
            preview = load_tiff_preview(self.path)
            original.validate_identity()
            payload = (self.path, preview, original, "")
        except Exception as exc:  # noqa: BLE001
            payload = (self.path, None, None, str(exc))
        self.signals.finished.emit(payload)


class TiffImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage()

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        return self.image


class FileBridge(QObject):
    recentFilesChanged = Signal()
    imageOpened = Signal("QVariantMap")
    analysisChanged = Signal()

    def __init__(self, provider=None, parent=None, settings=None):
        super().__init__(parent)
        self.provider = provider or TiffImageProvider()
        self.revision = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._task = None
        self.original_source = None
        self.pipeline = AnalysisPipeline(parent=self)
        self.pipeline.changed.connect(self.analysisChanged)
        self._settings = settings or QSettings("CrystalVision-Lab", "sic-xrt-analyzer")
        stored = self._settings.value("preferences", {})
        self._preferences = self._validated(stored if isinstance(stored, dict) else {})
        recent = self._settings.value("recentFiles", [])
        candidates = recent if isinstance(recent, list) else [recent]
        self._recent_files = list(dict.fromkeys(x for x in candidates if isinstance(x, str)))[:self._preferences["recentFileLimit"]]
        if not self._preferences["rememberRecentFiles"]:
            self._recent_files = []

    @staticmethod
    def _validated(values):
        output = dict(DEFAULTS)
        for key in ("smoothImages", "roiVisible", "rememberRecentFiles", "startupDemo"):
            if isinstance(values.get(key), bool):
                output[key] = values[key]
        if values.get("viewerBackground") in ("#111518", "#080b0e"):
            output["viewerBackground"] = values["viewerBackground"]
        # Legacy fit-relative defaultZoom cannot describe a true pixel scale.
        # Keep other preferences and migrate legacy views to the safe fit default.
        if values.get("defaultView") in ("fit", "actual", "125", "200"):
            output["defaultView"] = values["defaultView"]
        limit = values.get("recentFileLimit")
        if isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 10:
            output["recentFileLimit"] = limit
        return output

    @Property("QStringList", notify=recentFilesChanged)
    def recentFiles(self):
        return self._recent_files

    @Property(str, constant=True)
    def appVersion(self):
        try:
            return version("sic-xrt-analyzer")
        except PackageNotFoundError:
            return "설치된 버전 없음"

    @Property(str, constant=True)
    def systemInfo(self):
        return f"{platform.system()} {platform.release()} · Python {platform.python_version()} · Qt {qVersion()}"

    @Property("QVariantMap", notify=analysisChanged)
    def analysis(self):
        p = self.pipeline
        adapter = p.adapter
        # Detailed adapter errors stay in Python/logs, never in ordinary UI text.
        messages = {
            "CANCELED": "분석이 취소되었습니다",
            "SOURCE_CHANGED": "원본 파일이 변경되었습니다. 파일을 다시 여세요",
            "UNSUPPORTED_SCOPE": "모델이 선택한 분석 범위를 지원하지 않습니다",
            "INVALID_INPUT": "원본 이미지와 분석 입력 조건을 확인하세요",
            "MODEL_NOT_AVAILABLE": "승인된 모델이 연결되지 않았습니다",
        }
        labels = {AnalysisState.UNAVAILABLE: "사용 불가", AnalysisState.READY: "준비 완료",
                  AnalysisState.RUNNING: "분석 중", AnalysisState.COMPLETED: "완료",
                  AnalysisState.FAILED: "실패", AnalysisState.CANCELED: "취소됨"}
        return {
            "state": p.state.value, "statusLabel": labels[p.state],
            "modelAvailable": bool(adapter and adapter.available),
            "modelName": adapter.model_name if adapter else "",
            "modelVersion": adapter.model_version if adapter else "",
            "device": (adapter.device or "") if adapter else "",
            "supportedScopes": [s.value for s in adapter.input_contract.supported_scopes] if adapter else [],
            "sourceReady": p.source is not None,
            "inputSource": "Original TIFF" if p.source else "",
            "scope": p.result.scope.value if p.result else "",
            "analysisId": p.result.analysis_id if p.result else "",
            "hasResult": bool(p.result and p.result.status == AnalysisState.COMPLETED),
            "resultRoiMismatch": p.result_roi_mismatch,
            "errorCode": p.error.code if p.error else "",
            "errorMessage": messages.get(p.error.code, "분석에 실패했습니다. 진단 로그를 확인하세요") if p.error else "",
        }

    @Slot(bool, int, int, int, int)
    def setCurrentRoi(self, selected, x, y, width, height):
        self.pipeline.set_current_roi(Region(x, y, width, height) if selected else None)

    @Slot(str, int, int, int, int, "QVariantMap", result=bool)
    def requestAnalysis(self, scope, x, y, width, height, parameters):
        # Caller must choose scope explicitly. Presence of a viewer ROI never chooses it.
        if self.pipeline.adapter is None or not self.pipeline.adapter.available:
            return self.pipeline.reject(AnalysisError("MODEL_NOT_AVAILABLE", "승인된 모델이 연결되지 않았습니다"))
        if self.pipeline.source is None:
            return self.pipeline.reject(AnalysisError("INVALID_INPUT", "원본 TIFF를 여세요"))
        try:
            explicit_scope = AnalysisScope(scope)
            request = AnalysisRequest(self.pipeline.source, explicit_scope,
                                      self.pipeline.adapter.model_id, self.pipeline.adapter.model_version,
                                      Region(x, y, width, height) if explicit_scope == AnalysisScope.ROI else None,
                                      parameters)
        except (TypeError, ValueError) as exc:
            return self.pipeline.reject(AnalysisError("INVALID_INPUT", "분석 범위와 입력을 확인하세요", str(exc)))
        return self.pipeline.start(request)

    @Slot()
    def cancelAnalysis(self):
        self.pipeline.cancel()

    @Slot(result="QVariantMap")
    def preferences(self):
        return dict(self._preferences)

    @Slot(result="QVariantMap")
    def defaultPreferences(self):
        return dict(DEFAULTS)

    @Slot("QVariantMap", result="QVariantMap")
    def applyPreferences(self, values):
        self._preferences = self._validated(values)
        self._settings.setValue("preferences", self._preferences)
        self._recent_files = self._recent_files[:self._preferences["recentFileLimit"]]
        self._save_recent()
        self._settings.sync()
        self.recentFilesChanged.emit()
        return dict(self._preferences)

    def _save_recent(self):
        if self._preferences["rememberRecentFiles"]:
            self._settings.setValue("recentFiles", self._recent_files)
        else:
            self._settings.remove("recentFiles")

    @Slot(str)
    def recordRecentFile(self, path):
        normalized = str(Path(path).resolve())
        self._recent_files = [normalized, *(old for old in self._recent_files if os.path.normcase(old) != os.path.normcase(normalized))][:self._preferences["recentFileLimit"]]
        self._save_recent()
        self.recentFilesChanged.emit()

    @Slot()
    def clearRecentFiles(self):
        self._recent_files = []
        self._settings.remove("recentFiles")
        self.recentFilesChanged.emit()

    @Slot(str, result=bool)
    def isAccessible(self, path):
        return Path(path).is_file() and os.access(path, os.R_OK)

    @Slot(str, result=str)
    def localPath(self, url):
        return QUrl(url).toLocalFile()

    @Slot(str, result=str)
    def localUrl(self, path):
        return QUrl.fromLocalFile(path).toString()

    @Slot(str, result=str)
    def fileName(self, path):
        return Path(path).name

    @Slot(str, result="QVariantMap")
    def openImage(self, url):
        self.pipeline.invalidate()
        path = self.localPath(url)
        if not path or not self.isAccessible(path):
            return {"ok": False, "error": "접근 가능한 로컬 TIFF 파일을 선택하세요"}
        try:
            original = OriginalImageSource(path)
            preview = load_tiff_preview(path)
            original.validate_identity()
        except Exception as exc:  # noqa: BLE001
            # A damaged file or an unavailable decoder must not terminate the UI.
            return {"ok": False, "error": str(exc)}
        return self._publish(path, preview, original)

    @Slot(str)
    def requestImage(self, url):
        if self._task is not None:
            return
        self.pipeline.invalidate()
        path = self.localPath(url)
        if not path or not self.isAccessible(path):
            self.imageOpened.emit({"ok": False, "error": "접근 가능한 로컬 TIFF 파일을 선택하세요"})
            return
        self._task = _LoadTask(path)
        self._task.signals.finished.connect(self._finish_load)
        self._pool.start(self._task)

    @Slot(object)
    def _finish_load(self, payload):
        path, preview, original, error = payload
        self._task = None
        result = {"ok": False, "error": error} if error else self._publish(path, preview, original)
        self.imageOpened.emit(result)

    def _publish(self, path, preview, original):
        self.original_source = original
        self.pipeline.set_source(original)
        self.provider.image = preview.image
        self.revision += 1
        self.recordRecentFile(path)
        return {
            "ok": True, "path": path, "name": self.fileName(path),
            "source": f"image://tiff/current?revision={self.revision}",
            "width": original.metadata.width, "height": original.metadata.height,
            "bitDepth": original.metadata.bit_depth, "pageCount": original.metadata.page_count,
            "dtype": original.metadata.dtype, "channels": original.metadata.channels,
            "previewWidth": preview.image.width(), "previewHeight": preview.image.height(),
            "sampled": preview.sampled,
        }

    @Slot()
    def clearImage(self):
        self.original_source = None
        self.pipeline.set_source(None)
        self.provider.image = QImage()

    @Slot()
    def waitForLoads(self):
        # Keep worker signal objects alive until decoding ends during shutdown.
        self._pool.waitForDone()
        self.pipeline.shutdown()

    @Slot(str)
    def copyText(self, value):
        QGuiApplication.clipboard().setText(value)

    @Slot(result=bool)
    def openIssueTracker(self):
        return QDesktopServices.openUrl(QUrl("https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues"))
