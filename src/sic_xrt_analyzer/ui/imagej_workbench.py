"""Asynchronous Qt controller for native tools and the embedded ImageJ session."""
import math
import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Property, QObject, Signal, Slot

from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import MAX_POINTS, MAX_ROIS, ImportedRoi
from sic_xrt_analyzer.imaging.imagej_runtime import runtime_directory
from sic_xrt_analyzer.imaging.roi_edit import geometry

from .latest_reader import LatestReader
from .native_plugin_window import native_windows_supported


class ImageJWorkbench(QObject):
    changed = Signal()
    resultReady = Signal(str)
    saveFinished = Signal('QVariantMap')
    windowEvent = Signal(object)
    windowsChanged = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.runtime = ImageJClient()
        self.windows = []
        self.runtime.window_event = self.windowEvent.emit
        self.windowEvent.connect(self._windows)
        self.modern_catalog = []
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.busy = False
        self.error = self.log = self.headings = ''
        self.rows = []
        self.plot = []
        self.catalog = []
        self.color = '#ffff00'
        self.size = 5
        self.tolerance = 0
        self.text = 'Text'
        self.source_key = None
        self.recording = False
        self.recorded = ''
        self.canceled = False

    @Property('QVariantMap', notify=changed)
    def state(self):
        return {'busy': self.busy, 'error': self.error, 'log': self.log, 'headings': self.headings,
                'rows': self.rows, 'commands': self.catalog, 'color': self.color, 'size': self.size,
                'tolerance': self.tolerance, 'text': self.text, 'recording': self.recording,
                'recorded': self.recorded, 'plot': self.plot, 'runtimePath': str(runtime_directory()),
                'gui': self.runtime.gui, 'fijiPath': self.runtime.fiji_home, 'windows': self.windows,
                'nativeWindowsAvailable': native_windows_supported(), 'modernCommands': self.modern_catalog}

    @Slot(object)
    def _windows(self, event):
        process = self.runtime.process
        if 'enginePid' in event and (process is None or process.poll() is not None or event['enginePid'] != process.pid):
            return
        windows = event.get('windows', [])
        if windows == self.windows:
            return
        self.windows = windows
        self.windowsChanged.emit()
        self.changed.emit()

    @Property('QVariantList', notify=windowsChanged)
    def pluginWindows(self):
        return self.windows

    def require_stack(self):
        frame = self.frame()
        working_stack = self.bridge._stack_context and frame.source.path == self.bridge._working_path
        if frame.source.metadata.format != 'TIFF' or (frame.source.metadata.page_count < 2 and not working_stack):
            raise ValueError('이 기능은 여러 페이지가 있는 XRT TIFF 스택에서 사용하세요')
        return frame

    @Slot(bool, str)
    def configureRuntime(self, gui, url):
        try:
            self.require_stack()
            if gui and not native_windows_supported():
                raise ValueError('플러그인 창 연결에는 Windows 또는 Linux X11/XWayland 데스크톱이 필요합니다')
            path = self.bridge.localPath(url) if url.startswith('file:') else url
            if path:
                root = Path(path).resolve(strict=True)
                if not (root/'jars').is_dir() or not list((root/'jars').glob('imagej-*.jar')):
                    raise ValueError('jars/가 있는 Fiji 라이브러리 폴더를 선택하세요')
                path = str(root)
            self.runtime.configure(gui,path)
            self.modern_catalog = []
            self.error = ''
        except (OSError,ValueError) as exc:
            self.error = str(exc)
        self.changed.emit()

    @Slot()
    def loadModernCommands(self):
        try:
            self.require_stack()
            self.submit(lambda:{'modernCommands':self.runtime.modern_commands()})
        except ValueError as exc:
            self.error = str(exc); self.changed.emit()

    @Slot(str, float, float, str)
    def configure(self, color, size, tolerance, text):
        if len(color) != 7 or not color.startswith('#') or any(x not in '0123456789abcdefABCDEF' for x in color[1:]):
            self.error = '색상은 #RRGGBB 형식으로 입력하세요'
        elif not all(math.isfinite(x) for x in (size, tolerance)) or not 1 <= size <= 1024 or not 0 <= tolerance <= 65535:
            self.error = '크기 1–1024, 허용오차 0–65535를 지정하세요'
        else:
            self.color, self.size, self.tolerance, self.text = color, size, tolerance, text[:4096]
            self.error = ''
        self.changed.emit()

    def frame(self):
        frame = self.bridge.stack_viewer.frame
        if frame is None or self.bridge.stack_viewer.initial_loading or self.busy:
            raise ValueError('이미지 준비 및 현재 작업이 끝난 뒤 사용하세요')
        return frame

    def selected(self, frame):
        manager = self.bridge.roi_manager
        if manager.busy:
            raise ValueError('ROI 불러오기가 끝난 뒤 실행하세요')
        selected = next((r for r in manager.records if r.id == manager.selected), None)
        if (selected is not None and selected.id not in manager.hidden
                and selected.page_index in (None, frame.source.page_index) and len(selected.paths) != 1):
            # Never silently replace an unsupported selected shape with no ROI
            # (whole-image processing) or the analysis bounding rectangle.
            raise ValueError('복합 경로 ROI 처리는 아직 지원하지 않습니다. 단일 경로 ROI를 선택하세요')
        try:
            return manager.selected_record(frame)
        except ValueError:
            region = self.bridge.pipeline.current_roi
            roi = (region.x, region.y, region.width, region.height) if region else None
            if roi:
                x, y, w, h = roi
                return ImportedRoi('selection', 'Rectangle', 'polygon', (((x,y),(x+w,y),(x+w,y+h),(x,y+h)),), self.color, roi, None, 'Rectangle')
            return None

    def submit(self, operation, key=None):
        self.canceled = False
        self.busy, self.error = True, ''
        self.source_key = key
        self.reader.submit(operation)
        self.changed.emit()

    @Slot(str, str, str, bool)
    def execute(self, kind, content, options, whole_stack=False):
        try:
            frame = self.require_stack()
            record = self.selected(frame)
            kwargs = {kind: content, 'options': options, 'record': record, 'whole_stack': whole_stack}
            if kind not in ('command', 'macro', 'plugin', 'modern'):
                raise ValueError('알 수 없는 실행 형식')
            if self.recording and kind == 'command':
                import json
                self.recorded += f'run({json.dumps(content)}, {json.dumps(options)});\n'
            self.submit(lambda: self.runtime.run(frame, **kwargs), frame.source.identity)
        except Exception as exc:  # noqa: BLE001 (Qt boundary reports user/Java errors)
            self.error = str(exc)
            self.changed.emit()

    @Slot()
    def loadCommands(self):
        try:
            self.require_stack()
            self.submit(lambda: {'commands': self.runtime.commands()})
        except ValueError as exc:
            self.error = str(exc); self.changed.emit()

    @Slot(bool)
    def record(self, enabled):
        self.recording = enabled
        self.changed.emit()

    @Slot(str, result=str)
    def readMacro(self, url):
        try:
            path = Path(self.bridge.localPath(url))
            if path.suffix.lower() not in ('.ijm', '.txt') or path.stat().st_size > 1024**2:
                raise ValueError('1MiB 이하 .ijm/.txt 파일을 선택하세요')
            code = path.read_text(encoding='utf-8-sig')
            self.error = ''
            return code
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return ''

    @Slot(str)
    def installPlugin(self, url):
        try:
            if self.busy:
                raise ValueError('현재 ImageJ 작업이 끝난 뒤 경로를 등록하세요')
            self.require_stack()
            path = Path(self.bridge.localPath(url)).resolve(strict=True)
            if path.suffix.lower() not in ('.jar', '.class'):
                raise ValueError('Java 플러그인 .jar 또는 .class 파일을 선택하세요')
            # Add an existing JAR (or directory of loose classes), without changing it.
            def register():
                self.runtime.add_classpath(str(path if path.suffix.lower() == '.jar' else path.parent))
                return {'registered': str(path)}
            self.submit(register)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self.changed.emit()

    @Slot(str, 'QVariantList')
    def gesture(self, tool, points):
        try:
            frame = self.require_stack() if tool in ('Wand','Brush','Fill','Picker') else self.frame()
            self.error = ''
            if not points or len(points) > 10000:
                raise ValueError('도구 좌표 수가 유효하지 않습니다')
            points = [[float(p[0]), float(p[1])] for p in points]
            if tool == 'Picker':
                rgb = frame.source.read_region(int(points[0][0]), int(points[0][1]), 1, 1)[0, 0]
                values = rgb.tolist()[:3] if hasattr(rgb, '__len__') else [round((float(rgb)-frame.low) * 255 / max(1, frame.high-frame.low))] * 3
                values = [min(255, max(0, round(v))) for v in values]
                self.color = '#' + ''.join(f'{v:02x}' for v in values)
                self.changed.emit()
            elif tool == 'Wand':
                self.submit(lambda: {'wand': self.runtime.wand(frame, *points[0], self.tolerance)}, frame.source.identity)
            elif tool in ('Brush', 'Fill'):
                edit = (tool, points, self.color, self.size, self.text, self.tolerance)
                self.submit(lambda: self.runtime.run(frame, edit=edit), frame.source.identity)
            else:
                self.add_shape(tool, points, frame)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self.changed.emit()

    def add_shape(self, tool, points, frame):
        meta = frame.source.metadata
        kind = 'point' if tool == 'Point' else 'line' if tool in ('Line', 'Polyline', 'FreeLine', 'Angle', 'Arrow') else 'polygon'
        if tool in ('Rectangle', 'Oval', 'Text'):
            x1, y1 = points[0]
            x2, y2 = points[-1] if tool != 'Text' else (min(meta.width, x1 + max(10, len(self.text)) * self.size * .65), min(meta.height, y1 + self.size * 1.4))
            left, right, top, bottom = min(x1,x2), max(x1,x2), min(y1,y2), max(y1,y2)
            if tool == 'Oval':
                points = [[(left+right)/2 + (right-left)/2 * math.cos(i*math.tau/128), (top+bottom)/2 + (bottom-top)/2 * math.sin(i*math.tau/128)] for i in range(128)]
            else:
                points = [[left,top],[right,top],[right,bottom],[left,bottom]]
        record = ImportedRoi(uuid4().hex, tool, kind, (), self.color, (), frame.source.page_index if meta.page_count > 1 else None,
                             tool, self.text if tool == 'Text' else '', self.size if tool == 'Text' else 1)
        record = geometry(record, [points], meta)
        manager = self.bridge.roi_manager
        if len(manager.records) >= MAX_ROIS or sum(sum(len(p) for p in r.paths) for r in manager.records) + len(points) > MAX_POINTS:
            raise ValueError('ROI 개수/좌표 한도 초과')
        if tool == 'Point' and manager.selected:
            selected = next((r for r in manager.records if r.id == manager.selected), None)
            if selected and selected.kind == 'point':
                manager.add_vertex(*points[0], frame)
                return
        manager.remember(manager.snapshot())
        manager.records.append(record)
        manager.selected, manager.vertex = record.id, 0
        manager.modified.add(record.id)
        manager.changed.emit()

    def _ready(self, result, error):
        self.busy = False
        self.error = error
        if self.canceled:
            self.error = 'ImageJ 작업을 취소했습니다. 다음 실행에서 엔진이 다시 시작됩니다'
            self.changed.emit()
            return
        current = self.bridge.stack_viewer.frame
        if self.source_key is not None and (current is None or current.source.identity != self.source_key):
            self.error = '이미지가 변경되어 이전 작업 결과를 적용하지 않았습니다'
        elif result is not None:
            if self.source_key is not None:
                try:
                    current.source.validate_identity()
                except ValueError as exc:
                    self.error = str(exc)
                    self.changed.emit()
                    return
            if 'commands' in result:
                self.catalog = result['commands']
            elif 'modernCommands' in result:
                self.modern_catalog = result['modernCommands']
            elif 'registered' in result:
                self.modern_catalog = []
                self.log += '\n플러그인 경로 등록: ' + result['registered']
            elif 'saved' in result:
                self.log += '\n복사본 저장: ' + result['saved']
                self.saveFinished.emit({'ok': True, 'path': result['saved']})
            elif 'wand' in result:
                try:
                    self.add_shape('Polygon', result['wand'], current)
                except ValueError as exc:
                    self.error = str(exc)
            elif 'plot' in result:
                self.plot, self.rows, self.headings = result['plot'], result['rows'], result['headings']
            else:
                self.rows, self.headings = result['rows'], result['headings']
                self.log += result['log']
                if result.get('publish', True):
                    self.resultReady.emit(result['path'])
        self.changed.emit()

    @Slot(str)
    def statistics(self, kind):
        try:
            frame = self.require_stack()
            record = self.selected(frame)
            self.submit(lambda: self.runtime.statistics(frame, record, kind), frame.source.identity)
        except ValueError as exc:
            self.error = str(exc)
            self.changed.emit()

    @Slot(str)
    def saveImageCopy(self, url):
        try:
            frame = self.frame()
            source = frame.source
            path = Path(self.bridge.localPath(url))
            extensions = ('.jpg','.jpeg') if source.metadata.format == 'JPEG' else ('.tif','.tiff')
            if path.suffix.lower() not in extensions:
                raise ValueError('현재 이미지와 같은 TIFF/JPEG 형식의 새 파일명을 지정하세요')
            def save():
                source.validate_identity()
                with Path(source.path).open('rb') as original, path.open('xb') as output:
                    shutil.copyfileobj(original, output, 16 * 1024**2)
                source.validate_identity()
                return {'saved': str(path)}
            self.submit(save)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            self.changed.emit()

    @Slot(str)
    def saveResults(self, url):
        try:
            path = Path(self.bridge.localPath(url))
            if path.suffix.lower() != '.tsv' or not self.rows:
                raise ValueError('측정 결과가 있는 상태에서 새 .tsv 파일명을 지정하세요')
            text = self.headings + '\n' + '\n'.join(self.rows) + '\n'
            def save():
                with path.open('x', encoding='utf-8-sig', newline='') as output:
                    output.write(text)
                return {'saved':str(path)}
            self.submit(save)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            self.changed.emit()

    def shutdown(self):
        if self.busy or self.windows:
            self.runtime.abort()
        self.reader.shutdown()
        self.runtime.close()

    @Slot()
    def cancel(self):
        if self.busy or self.windows:
            self.canceled = self.busy
            self.runtime.abort()
            self.windows = []
            self.windowsChanged.emit()
            self.changed.emit()
