"""Local desktop integration and persisted, applicable UI preferences."""
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QSettings,
    QSize,
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
from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.ui.detail_reader import DetailReader
from sic_xrt_analyzer.ui.pixel_reader import PixelReader
from sic_xrt_analyzer.ui.roi_manager import RoiManager
from sic_xrt_analyzer.ui.stack_controller import StackController

DEFAULTS = {
    "smoothImages": True,
    "viewerBackground": "#111518",
    "defaultView": "fit",
    "roiVisible": True,
    "rememberRecentFiles": True,
    "recentFileLimit": 10,
    "startupDemo": False,
}


class TiffImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage()
        self.detail_image = QImage()

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        return self.detail_image if image_id.startswith('detail') else self.image


class FileBridge(QObject):
    recentFilesChanged = Signal()
    imageOpened = Signal("QVariantMap")
    pageChanged = Signal("QVariantMap")
    stackChanged = Signal()
    analysisChanged = Signal()
    roisChanged = Signal()
    roiImportFinished = Signal("QVariantMap")
    detailChanged = Signal()

    def __init__(self, provider=None, parent=None, settings=None):
        super().__init__(parent)
        self.provider = provider or TiffImageProvider()
        self.revision = 0
        self.stack_viewer = StackController(self)
        self.stack_viewer.changed.connect(self.stackChanged)
        self.stack_viewer.frameReady.connect(self._on_frame)
        self.stack_viewer.failed.connect(self._on_stack_error)
        self.original_source = None
        self.pixel_reader = PixelReader(self)
        self.pixel_reader.changed.connect(self.stackChanged)
        self.detail_reader = DetailReader(self)
        self.detail_reader.changed.connect(self._on_detail_changed)
        self.roi_manager = RoiManager(self)
        self.roi_manager.changed.connect(self.roisChanged)
        self.roi_manager.reader.ready.connect(self._on_roi_imported)
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

    @property
    def _task(self):
        return self.stack_viewer._task

    @Property("QVariantMap", notify=stackChanged)
    def stackState(self):
        s, f = self.stack_viewer, self.stack_viewer.frame
        low, high = s.window or (0.0, 65535.0)
        return {
            "busy": s.busy, "error": s.error, "revision": self.revision,
            "initialLoading": s.initial_loading,
            "preload": s.preload_state, "preloadError": s.preload_error,
            "detailBusy": s.detail_busy, "rawReady": f is not None and f.pixels is not None,
            "browsePreview": f is not None and f.pixels is None and f.source.metadata.page_count > 1,
            "cursorRevision": self.pixel_reader.revision, "pixelError": self.pixel_reader.error,
            "format": f.source.metadata.format if f else "",
            "requestedPage": s.requested_page, "currentPage": f.source.page_index if f else 0,
            "pageCount": f.source.metadata.page_count if f else 0,
            "dtype": f.source.metadata.dtype if f else "",
            "low": low, "high": high,
            "defaultLow": f.default_low if f else 0.0, "defaultHigh": f.default_high if f else 65535.0,
            "rangeMin": f.range_min if f else 0.0, "rangeMax": f.range_max if f else 65535.0,
            "rangeOrigin": f.range_origin if f else "",
            "frames": f.imagej_frames or 0 if f else 0,
            "slices": f.imagej_slices or 0 if f else 0,
        }

    @Slot(int, result=bool)
    def requestPage(self, page):
        if self.stack_viewer.frame is None or not 0 <= page < self.stack_viewer.frame.source.metadata.page_count:
            return False
        if page != self.stack_viewer.frame.source.page_index:
            self.pipeline.invalidate()
        return self.stack_viewer.page(page)

    @Slot()
    def beginScrub(self):
        self.stack_viewer.begin_scrub()

    @Slot()
    def endScrub(self):
        self.stack_viewer.end_scrub()

    @Slot()
    def retryPreload(self):
        self.stack_viewer.retry_preload()

    @Slot(float, float, result=bool)
    def setDisplayRange(self, low, high):
        return self.stack_viewer.display_range(low, high)

    @Slot()
    def autoDisplayRange(self):
        self.stack_viewer.display_range(0, 1, automatic=True)

    @Slot()
    def resetDisplayRange(self):
        f = self.stack_viewer.frame
        if f:
            self.stack_viewer.display_range(f.default_low, f.default_high)

    @Slot(int, int, result=str)
    def pixelValue(self, x, y):
        f = self.stack_viewer.frame
        if f is not None and f.pixels is None and f.source.metadata.page_count == 1 and not self.stack_viewer.initial_loading:
            return self.pixel_reader.value(f.source, x, y)
        return self.stack_viewer.pixel_value(x, y)

    @Property("QVariantMap", notify=roisChanged)
    def roiState(self):
        return {"items": self.roi_manager.view(self.stack_viewer.frame), "busy": self.roi_manager.busy,
                "errors": list(self.roi_manager.errors), "selected": self.roi_manager.selected}

    @Property("QVariantMap", notify=detailChanged)
    def detailState(self):
        reader = self.detail_reader
        key = reader.result[0] if reader.result else None
        return {'ready': key is not None, 'busy': reader.busy, 'error': reader.error,
                'x': key[1] if key else 0, 'y': key[2] if key else 0,
                'width': key[3] if key else 0, 'height': key[4] if key else 0,
                'source': f'image://tiff/detail?revision={reader.revision}' if key else ''}

    @Slot()
    def _on_detail_changed(self):
        result = self.detail_reader.result
        self.provider.detail_image = result[1] if result else QImage()
        self.detailChanged.emit()

    @Slot(int, int, int, int)
    def requestDetail(self, x, y, width, height):
        frame = self.stack_viewer.frame
        if frame is None or self.stack_viewer.initial_loading or frame.source.metadata.page_count != 1:
            self.detail_reader.clear()
            return
        try:
            frame.source.validate_region(x, y, width, height)
        except ValueError:
            self.detail_reader.clear()
            return
        self.detail_reader.request(frame, x, y, width, height)

    @Slot()
    def clearDetail(self):
        self.detail_reader.clear()

    @Slot("QVariantList", result=bool)
    def importRois(self, urls):
        frame = self.stack_viewer.frame
        if frame is None or self.stack_viewer.initial_loading:
            return False
        paths = [u.toLocalFile() if isinstance(u, QUrl) else self.localPath(u) for u in urls]
        if not paths or any(not p for p in paths):
            return False
        self.roi_manager.load(paths, frame)
        return True

    @Slot(object, str)
    def _on_roi_imported(self, result, error):
        self.roiImportFinished.emit({"count": len(self.roi_manager.records), "errors": self.roi_manager.errors})

    @Slot(str, bool)
    def setImportedRoiVisible(self, roi_id, visible):
        if visible:
            self.roi_manager.hidden.discard(roi_id)
        else:
            self.roi_manager.hidden.add(roi_id)
        self.roisChanged.emit()

    @Slot(str)
    def selectImportedRoi(self, roi_id):
        if any(r.id == roi_id for r in self.roi_manager.records):
            self.roi_manager.selected = roi_id
            self.roisChanged.emit()

    @Slot(str)
    def removeImportedRoi(self, roi_id):
        self.roi_manager.records = [r for r in self.roi_manager.records if r.id != roi_id]
        self.roi_manager.hidden.discard(roi_id)
        if self.roi_manager.selected == roi_id:
            self.roi_manager.selected = ''
        self.roisChanged.emit()

    @Slot()
    def clearImportedRois(self):
        self.roi_manager.clear()

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
            return {"ok": False, "error": "접근 가능한 로컬 TIFF/JPG 파일을 선택하세요"}
        try:
            stack = open_stack(path)
            try:
                frame = stack.frame(0)
            finally:
                stack.close()
        except Exception as exc:  # noqa: BLE001
            # A damaged file or an unavailable decoder must not terminate the UI.
            return {"ok": False, "error": str(exc)}
        self.stack_viewer.frame = frame
        self.stack_viewer.initial_loading = False
        self.stack_viewer.window = (frame.low, frame.high)
        self.stack_viewer.requested_page = 0
        result = self._publish(path, frame.preview, frame.source)
        self.stackChanged.emit()
        return result

    @Slot(str)
    def requestImage(self, url):
        self.pipeline.invalidate()
        self.pixel_reader.clear()
        self.detail_reader.clear()
        self.roi_manager.invalidate_pending()
        path = self.localPath(url)
        # Filesystem/header/decode errors occur in the worker, with latest-request semantics.
        self.stack_viewer.open(path)

    @Slot(object, bool)
    def _on_frame(self, frame, opening):
        result = self._publish(frame.source.path, frame.preview, frame.source, record_recent=opening)
        result["browsePreview"] = frame.pixels is None and frame.source.metadata.page_count > 1
        (self.imageOpened if opening else self.pageChanged).emit(result)
        self.roisChanged.emit()

    @Slot(str, bool)
    def _on_stack_error(self, error, opening):
        (self.imageOpened if opening else self.pageChanged).emit({"ok": False, "error": error})

    def _publish(self, path, preview, original, *, record_recent=True):
        self.detail_reader.clear()
        if self.original_source is None or self.original_source.identity != original.identity:
            self.pixel_reader.clear()
        if record_recent:
            self.roi_manager.clear()
        self.original_source = original
        if not isinstance(original, OriginalImageSource):
            self.pipeline.set_source(None)
        elif self.pipeline.source is None or self.pipeline.source.identity != original.identity:
            self.pipeline.set_source(original)
        self.provider.image = preview.image
        self.revision += 1
        if record_recent:
            self.recordRecentFile(path)
        return {
            "ok": True, "path": path, "name": self.fileName(path),
            "source": f"image://tiff/current?revision={self.revision}",
            "width": original.metadata.width, "height": original.metadata.height,
            "bitDepth": original.metadata.bit_depth, "pageCount": original.metadata.page_count,
            "dtype": original.metadata.dtype, "channels": original.metadata.channels,
            "format": original.metadata.format,
            "pageIndex": original.page_index,
            "previewWidth": preview.image.width(), "previewHeight": preview.image.height(),
            "sampled": preview.sampled,
        }

    @Slot()
    def clearImage(self):
        self.stack_viewer.clear()
        self.pixel_reader.clear()
        self.roi_manager.clear()
        self.detail_reader.clear()
        self.original_source = None
        self.pipeline.set_source(None)
        self.provider.image = QImage()

    @Slot()
    def waitForLoads(self):
        # Keep worker signal objects alive until decoding ends during shutdown.
        self.stack_viewer.shutdown()
        self.pixel_reader.shutdown()
        self.detail_reader.shutdown()
        self.roi_manager.shutdown()
        self.pipeline.shutdown()

    @Slot(str)
    def copyText(self, value):
        QGuiApplication.clipboard().setText(value)

    @Slot(result=bool)
    def openIssueTracker(self):
        return QDesktopServices.openUrl(QUrl("https://github.com/CrystalVision-Lab/sic-xrt-analyzer/issues"))
