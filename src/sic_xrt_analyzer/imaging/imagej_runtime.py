"""ImageJ 1.x embedded JVM; pixels belong to a working copy, never a source file."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, RLock, Thread

import numpy as np
import tifffile

ENGINE_LOCK = RLock()

JARS = {
    'ij-1.54p.jar': ('net/imagej/ij/1.54p', '2e1a09961dfb41cee66ddc821b2577a41a072566ce45a49bae69267099741e20'),
    'ij1-patcher-2.0.0.jar': ('net/imagej/ij1-patcher/2.0.0', 'b68810263f9521ddb34bac272816613ebb71607775c1fc337079a0476c2b581a'),
    'javassist-3.30.2-GA.jar': ('org/javassist/javassist/3.30.2-GA', 'eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf'),
    'classgraph-4.8.162.jar': ('io/github/classgraph/classgraph/4.8.162', 'ea30b2d5e29e89d52706bcecf7a6ae3b44682d4a1566a5f22b9453f9be2a970c'),
    'jna-5.16.0.jar': ('net/java/dev/jna/jna/5.16.0', '3f5233589a799eb66dc2969afa3433fb56859d3d787c58b9bc7dd9e86f0a250c'),
}


def runtime_directory():
    return Path(os.environ.get('SIC_XRT_IMAGEJ_HOME', str(Path.cwd() / 'artifacts/imagej-runtime'))).resolve()


def initialize():
    import jpype
    directory = runtime_directory()
    files = [directory / name for name in JARS]
    for path in files:
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != JARS[path.name][1]:
            raise RuntimeError('ImageJ 실행 파일이 없습니다. tools/setup_imagej.py를 실행하세요: ' + str(path))
    if not jpype.isJVMStarted():
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(['java', '-XshowSettings:properties', '-version'], capture_output=True, text=True,
                                creationflags=flags, timeout=10, check=True)
        home = next((line.split('=', 1)[1].strip() for line in result.stderr.splitlines() if 'java.home =' in line), '')
        if not home:
            raise RuntimeError('Java 17 이상 설치 및 PATH/JAVA_HOME 설정이 필요합니다')
        if os.environ.get('SIC_XRT_FIJI_HOME'):
            version = next((line.split('=', 1)[1].strip() for line in result.stderr.splitlines() if 'java.specification.version =' in line), '0')
            if int(version) < 21:
                raise RuntimeError('이 Fiji 라이브러리에는 Java 21 이상이 필요합니다')
        candidates = [Path(home) / 'bin/server/jvm.dll', Path(home) / 'lib/server/libjvm.so', Path(home) / 'lib/server/libjvm.dylib']
        jvm = next((p for p in candidates if p.is_file()), None)
        extra = json.loads(os.environ.get('SIC_XRT_IMAGEJ_EXTRA_PATHS', '[]'))
        gui = os.environ.get('SIC_XRT_IMAGEJ_GUI') == '1'
        jpype.startJVM('-Xmx3g', f'-Djava.awt.headless={str(not gui).lower()}', '--add-opens=java.base/java.lang=ALL-UNNAMED',
                      '-Dimagej.updater.disableAutocheck=true',
                      jvmpath=str(jvm) if jvm else None, classpath=[str(p) for p in files] + extra, convertStrings=True)
        jpype.JClass('net.imagej.patcher.LegacyInjector').preinit()
    return jpype


class ImageJRuntime:
    """One serialized embedded ImageJ session; arbitrary plugins have normal user privileges."""
    def __init__(self, window_sink=None):
        self.directory = TemporaryDirectory(prefix='sic-xrt-imagej-', dir=os.environ.get('SIC_XRT_IMAGEJ_TMP'))
        self.lock = ENGINE_LOCK
        self.jp = None
        self.image = None
        self.identity = None
        self.outputs = set()
        self.active_output = None
        self.sequence = 0
        self.gui = os.environ.get('SIC_XRT_IMAGEJ_GUI') == '1'
        self.window_sink = window_sink
        self.window_stop = Event()
        self.window_thread = None
        self.modern = None

    def start(self):
        if self.jp is None:
            self.jp = initialize()
            self.IJ = self.jp.JClass('ij.IJ')
            self.WM = self.jp.JClass('ij.WindowManager')
            self.Interpreter = self.jp.JClass('ij.macro.Interpreter')
            self.IJ.runMacro('setBatchMode(true);')
            if self.gui and self.window_sink:
                self.window_thread = Thread(target=self.watch_windows, daemon=True)
                self.window_thread.start()
        return self.jp

    def watch_windows(self):
        """Publish native AWT/Swing handles while a modal plugin blocks its execution thread."""
        window_class = self.jp.JClass('java.awt.Window')
        native = self.jp.JClass('com.sun.jna.Native')
        previous = None
        initial_sizes = {}
        while not self.window_stop.wait(.08):
            windows = []
            for window in window_class.getWindows():
                if window.isVisible() and window.isDisplayable():
                    try:
                        handle = int(native.getWindowID(window))
                        size = initial_sizes.setdefault(handle, (int(window.getWidth()), int(window.getHeight())))
                        windows.append({'id': handle,
                                        'title': str(window.getTitle()) if hasattr(window, 'getTitle') else window.getClass().getSimpleName(),
                                        'width': size[0], 'height': size[1]})
                    except (self.jp.JException, OSError):
                        # A window may disappear between enumeration and handle lookup.
                        continue
            if windows != previous:
                self.window_sink({'windows': windows})
                previous = windows
            initial_sizes = {w['id']: initial_sizes[w['id']] for w in windows}

    def load(self, frame, whole_stack=False):
        jp = self.start()
        source = frame.source
        if (self.image is not None and (source.identity == self.identity or source.path == self.active_output)
                and (not whole_stack or self.image.getStackSize() == source.metadata.page_count)):
            if self.image.getStackSize() == source.metadata.page_count:
                self.image.setSlice(source.page_index + 1)
            self.WM.setTempCurrentImage(self.image)
            self.apply_calibration(frame)
            return
        if self.image is not None:
            self.image.changes = False
            self.Interpreter.removeBatchModeImage(self.image)
        meta = source.metadata
        if (meta.channels in (3,4) and meta.dtype != 'uint8') or (meta.channels == 1 and meta.dtype not in ('uint8','uint16','float32')):
            raise ValueError('ImageJ 작업은 회색조 uint8/uint16/float32 및 RGB uint8 입력을 지원합니다')
        if whole_stack:
            if meta.format != 'TIFF' or meta.page_count <= 1:
                raise ValueError('전체 스택은 다중 페이지 TIFF에서 사용하세요')
            self.image = self.IJ.openVirtual(self.virtual_path(source))
            if (self.image is None or self.image.getStackSize() != meta.page_count
                    or self.image.getProcessor() is None):
                raise ValueError('ImageJ 가상 스택 읽기 실패')
            self.image.setSlice(source.page_index + 1)
        else:
            if meta.width * meta.height > 200_000_000:
                raise ValueError('ImageJ 작업 복사본은 페이지당 2억 픽셀까지 지원합니다')
            processor_type, element = ('ColorProcessor', jp.JInt) if meta.channels in (3,4) else ('ShortProcessor', jp.JShort) if meta.dtype == 'uint16' else ('ByteProcessor', jp.JByte) if meta.dtype == 'uint8' else ('FloatProcessor', jp.JFloat)
            processor = jp.JClass('ij.process.' + processor_type)(meta.width, meta.height)
            target = processor.getPixels()
            system = jp.JClass('java.lang.System')
            for y in range(0, meta.height, 64):
                pixels = source.read_region(0, y, meta.width, min(64, meta.height - y))
                if meta.channels in (3,4):
                    a = pixels.astype(np.int32)
                    flat = ((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]).reshape(-1)
                else:
                    flat = pixels.reshape(-1)
                    if meta.dtype == 'uint16':
                        flat = flat.view(np.int16)
                    elif meta.dtype == 'uint8':
                        flat = flat.view(np.int8)
                    else:
                        flat = flat.astype(np.float32)
                values = jp.JArray(element)(flat)
                system.arraycopy(values, 0, target, y * meta.width, len(flat))
            self.image = jp.JClass('ij.ImagePlus')(Path(source.path).name + ' [작업 복사본]', processor)
        self.image.setFileInfo(None)
        self.image.setDisplayRange(frame.low, frame.high)
        palette = getattr(source, 'display_palette', None)
        if palette is not None and len(palette[0]) == 256:
            channels = [jp.JArray(jp.JByte)((c // 257).astype(np.uint8).view(np.int8)) for c in palette]
            self.image.getProcessor().setColorModel(jp.JClass('java.awt.image.IndexColorModel')(8, 256, *channels))
        self.Interpreter.addBatchModeImage(self.image)
        self.WM.setTempCurrentImage(self.image)
        self.identity = source.identity
        self.apply_calibration(frame)
        source.validate_identity()

    def apply_calibration(self, frame):
        calibration = getattr(frame, 'calibration', {})
        if calibration:
            native = self.image.getCalibration()
            native.pixelWidth = float(calibration.get('pixelWidth',1))
            native.pixelHeight = float(calibration.get('pixelHeight',1))
            native.setUnit(str(calibration.get('unit','pixel')))

    def virtual_path(self, source):
        """ImageJ 1's TIFF decoder needs classic TIFF; normalize BigTIFF in private storage."""
        with tifffile.TiffFile(source.path) as tif:
            if not tif.is_bigtiff:
                return source.path
        meta = source.metadata
        page_bytes = meta.width * meta.height * meta.channels * np.dtype(meta.dtype).itemsize
        estimate = page_bytes * meta.page_count
        if estimate >= 4 * 1024**3 - 64 * 1024**2:
            raise ValueError('4 GiB 이상 BigTIFF 전체 스택은 ImageJ 1 엔진에서 지원하지 않습니다. 현재 페이지 처리를 사용하세요')
        if shutil.disk_usage(self.directory.name).free < estimate + 64 * 1024**2:
            raise ValueError('BigTIFF 스택 작업 복사본을 만들 임시 디스크 공간이 부족합니다')
        from .original_source import OriginalImageSource
        path = Path(self.directory.name) / 'virtual-input.tif'
        shape = (meta.height, meta.width, meta.channels) if meta.channels > 1 else (meta.height, meta.width)
        with tifffile.TiffWriter(path) as writer:
            for index in range(meta.page_count):
                page = OriginalImageSource(source.path, index)
                if (page.metadata.width, page.metadata.height, page.metadata.dtype, page.metadata.channels) != (meta.width, meta.height, meta.dtype, meta.channels):
                    raise ValueError('전체 스택 처리에는 같은 크기·데이터 타입의 페이지가 필요합니다')
                def strips(page=page):
                    for y in range(0, meta.height, 64):
                        yield page.read_region(0, y, meta.width, min(64, meta.height-y))
                writer.write(strips(), shape=shape, dtype=meta.dtype, rowsperstrip=64,
                             photometric='rgb' if meta.channels > 1 else 'minisblack', metadata=None)
        source.validate_identity()
        return str(path)

    def roi(self, record):
        if record is None:
            self.image.deleteRoi()
            return
        from .roi_edit import encode_roi
        data = encode_roi(record)
        raw = self.jp.JArray(self.jp.JByte)(np.frombuffer(data, dtype=np.int8))
        roi = self.jp.JClass('ij.io.RoiDecoder')(raw, record.name).getRoi()
        self.image.setRoi(roi)

    def run(self, frame, *, macro='', command='', options='', plugin='', modern='', record=None, whole_stack=False, edit=None):
        with self.lock:
            self.load(frame, whole_stack)
            self.roi(record)
            before_images = set(self.Interpreter.getBatchModeImageIDs())
            before_log = self.IJ.getLog() or ''
            modern_outputs = {}
            if modern:
                modern_outputs = self.run_modern(modern, options)
            elif edit:
                self.edit(*edit)
            elif plugin:
                instance = self.jp.JClass(plugin)()
                plug_in = self.jp.JClass('ij.plugin.PlugIn')
                if isinstance(instance, plug_in):
                    instance.run(options)
                else:
                    self.jp.JClass('ij.plugin.filter.PlugInFilterRunner')(instance, plugin, options)
            elif command:
                if whole_stack and command == 'Z Project...':
                    # Explicit page-axis operation on a new wrapper; no spatial calibration is inferred.
                    wrapper = self.jp.JClass('ij.ImagePlus')('페이지 축 투영 · 공간 Z 미확정', self.image.getStack())
                    wrapper.setDimensions(1, self.image.getStackSize(), 1)
                    self.image = wrapper
                    self.Interpreter.addBatchModeImage(wrapper)
                    self.WM.setTempCurrentImage(wrapper)
                if self.gui and not options:
                    self.IJ.run(self.image, command, None)
                else:
                    self.IJ.run(self.image, command, options)
            else:
                interpreter = self.Interpreter()
                self.WM.setTempCurrentImage(None)
                try:
                    result_image = interpreter.runBatchMacro(macro, self.image)
                except self.jp.JException as exc:
                    raise RuntimeError(interpreter.getErrorMessage() or str(exc)) from exc
                if interpreter.wasError():
                    raise RuntimeError(interpreter.getErrorMessage() or 'ImageJ 매크로 실행 실패')
                if result_image is not None:
                    self.image = result_image
            if command or plugin:
                created = [self.Interpreter.getBatchModeImage(i) for i in self.Interpreter.getBatchModeImageIDs() if i not in before_images]
                if created:
                    self.image = created[-1]
            self.WM.setTempCurrentImage(self.image)
            rt = self.jp.JClass('ij.measure.ResultsTable').getResultsTable()
            rows = [rt.getRowAsString(i) for i in range(rt.size())]
            log = self.IJ.getLog() or ''
            self.sequence += 1
            path = Path(self.directory.name) / f'ImageJ_result_{self.sequence}.tif'
            self.save_stack(path)
            self.outputs.add(str(path))
            self.active_output = str(path)
            for image_id in self.Interpreter.getBatchModeImageIDs():
                if image_id != self.image.getID():
                    old = self.Interpreter.getBatchModeImage(image_id)
                    old.changes = False
                    self.Interpreter.removeBatchModeImage(old)
            for old_path in tuple(self.outputs):
                if old_path not in (str(path), frame.source.path):
                    try:
                        Path(old_path).unlink(missing_ok=True)
                        self.outputs.remove(old_path)
                    except OSError:
                        pass  # A still displayed mmap will be released by the Qt owner.
            return {'path': str(path), 'version': self.IJ.getVersion(), 'headings': rt.getColumnHeadings(), 'rows': rows,
                    'log': log.removeprefix(before_log) + (json.dumps(modern_outputs, ensure_ascii=False) + '\n' if modern_outputs else ''),
                    'pages': self.image.getStackSize(), 'publish': command not in ('Measure', 'Set Scale...', 'Set Measurements...', 'Properties...')}

    def edit(self, tool, points, color, size, text, tolerance):
        jp = self.jp
        processor = self.image.getProcessor()
        if tool != 'Undo':
            processor.snapshot()
            jp.JClass('ij.Undo').setup(jp.JClass('ij.Undo').FILTER, self.image)
        awt_color = jp.JClass('java.awt.Color')(int(color.lstrip('#'), 16))
        processor.setColor(awt_color)
        processor.setLineWidth(int(size))
        if tool == 'Brush':
            processor.moveTo(round(points[0][0]), round(points[0][1]))
            for x, y in points[1:]:
                processor.lineTo(round(x), round(y))
        elif tool == 'Fill':
            jp.JClass('ij.process.FloodFiller')(processor).fill(round(points[0][0]), round(points[0][1]))
        elif tool == 'Text':
            processor.setFont(jp.JClass('java.awt.Font')('SansSerif', 0, int(size)))
            processor.drawString(text, round(points[0][0]), round(points[0][1]))
        elif tool == 'Arrow':
            roi = jp.JClass('ij.gui.Arrow')(*points[0], *points[-1])
            roi.setStrokeColor(awt_color)
            roi.setStrokeWidth(size)
            roi.drawPixels(processor)
        elif tool == 'Undo':
            processor.reset()

    def wand(self, frame, x, y, tolerance):
        with self.lock:
            self.load(frame)
            wand = self.jp.JClass('ij.gui.Wand')(self.image.getProcessor())
            wand.autoOutline(int(x), int(y), float(tolerance), 4)
            return [[float(wand.xpoints[i]), float(wand.ypoints[i])] for i in range(wand.npoints)]

    def statistics(self, frame, record, kind):
        with self.lock:
            self.load(frame)
            self.roi(record)
            if kind == 'Profile':
                profile = self.jp.JClass('ij.gui.ProfilePlot')(self.image).getProfile()
                if profile is None:
                    raise ValueError('직선 / 분할선 ROI를 선택하세요')
                values = [float(x) for x in profile]
                return {'headings': 'Distance (px)\tValue', 'rows': [f'{i}\t{x}' for i, x in enumerate(values)], 'plot': values}
            stats = self.image.getStatistics()
            histogram = np.asarray(stats.histogram16 if self.image.getBitDepth() == 16 else stats.histogram).astype(np.int64)
            step = max(1, len(histogram) // 256)
            counts = histogram.reshape(-1, step).sum(axis=1) if len(histogram) % step == 0 else histogram
            return {'headings': 'Bin start\tBin end\tCount', 'rows': [f'{i*step}\t{(i+1)*step-1}\t{x}' for i, x in enumerate(counts)], 'plot': counts.tolist()}

    def save_stack(self, path):
        """Write each processed page in strips, preserving raw values and LUTs."""
        image = self.image
        bytes_per_pixel = 3 if image.getBitDepth() == 24 else image.getBitDepth() // 8
        estimated_bytes = image.getWidth() * image.getHeight() * bytes_per_pixel * image.getStackSize()
        with tifffile.TiffWriter(path, byteorder='<', bigtiff=estimated_bytes >= 4 * 1024**3 - 64 * 1024**2) as writer:
            for index in range(1, self.image.getStackSize() + 1):
                processor = self.image.getStack().getProcessor(index)
                width, height = processor.getWidth(), processor.getHeight()
                depth = processor.getBitDepth()
                raw = np.asarray(processor.getPixels()).reshape(height, width)
                dtype = 'uint8' if depth in (8, 24) else 'uint16' if depth == 16 else 'float32'
                shape = (height, width, 3) if depth == 24 else (height, width)
                def strips(raw=raw, height=height, depth=depth, dtype=dtype):
                    for y in range(0, height, 64):
                        part = raw[y:y + 64]
                        if depth == 24:
                            yield np.stack(((part >> 16) & 255, (part >> 8) & 255, part & 255), axis=-1).astype(np.uint8)
                        else:
                            yield part.view(np.dtype(dtype))
                color_map = None
                display_lut = None
                if depth != 24 and (processor.isColorLut() or processor.isInvertedLut()):
                    model = processor.getColorModel()
                    display_lut = np.array([[getattr(model, name)(self.jp.JInt(i)) for i in range(256)] for name in ('getRed', 'getGreen', 'getBlue')], dtype=np.uint8)
                if depth == 8 and (processor.isColorLut() or processor.isInvertedLut()):
                    color_map = display_lut.astype(np.uint16) * 257
                description = None
                tags = ()
                if index == 1:
                    low, high = float(processor.getMin()), float(processor.getMax())
                    description = f'ImageJ={self.IJ.getVersion()}\nimages={image.getStackSize()}\nframes={image.getStackSize()}\nmin={low}\nmax={high}\n'
                    if display_lut is not None:
                        tags = tifffile.imagej_metadata_tag({'LUTs': [display_lut]}, '<')
                writer.write(strips(), shape=shape, dtype=dtype, rowsperstrip=64,
                             photometric='rgb' if depth == 24 else 'palette' if color_map is not None else 'minisblack',
                             colormap=color_map, metadata=None, description=description, extratags=tags)

    def commands(self):
        with self.lock:
            self.start()
            self.IJ.runMacro('setBatchMode(true);')
            return sorted(str(x) for x in self.jp.JClass('ij.Menus').getCommands().keySet())

    def close(self):
        self.window_stop.set()
        if self.window_thread:
            self.window_thread.join(timeout=2)
        with self.lock:
            if self.image is not None:
                self.image.changes = False
                self.Interpreter.removeBatchModeImage(self.image)
                self.WM.setTempCurrentImage(None)
                self.image = None
            if self.jp and self.gui:
                for window in self.jp.JClass('java.awt.Window').getWindows():
                    window.dispose()
            if self.modern is not None:
                self.modern.context().dispose()
            self.directory.cleanup()

    def modern_engine(self):
        self.start()
        if self.modern is None:
            try:
                self.modern = self.jp.JClass('net.imagej.ImageJ')()
            except Exception as exc:
                raise ValueError('Fiji/ImageJ2 라이브러리를 등록하세요. tools/setup_fiji.py로 설치할 수 있습니다: ' + str(exc)) from exc
        return self.modern

    def modern_commands(self):
        with self.lock:
            engine = self.modern_engine()
            return sorted([{'class': str(info.getClassName()), 'label': str(info.getLabel() or info.getClassName()),
                            'inputs': ', '.join(f'{item.getName()}: {item.getType().getSimpleName()}' for item in info.inputs())}
                           for info in engine.command().getCommands()], key=lambda c:c['label'].lower())

    def run_modern(self, class_name, options):
        engine = self.modern_engine()
        args = json.loads(options or '{}')
        if not isinstance(args, dict):
            raise TypeError('ImageJ2 인수는 JSON 객체 형식으로 입력하세요')
        info = engine.command().getCommand(self.jp.JClass(class_name))
        if info is None:
            raise ValueError('등록된 SciJava Command 클래스를 지정하세요')
        unknown = set(args) - {str(item.getName()) for item in info.inputs()}
        if unknown:
            raise ValueError('알 수 없는 ImageJ2 인수: ' + ', '.join(sorted(unknown)))
        values = self.jp.JClass('java.util.HashMap')()
        dataset_type = self.jp.JClass('net.imagej.Dataset')
        dataset = None
        display = None
        if self.image.getStackSize() > 1:
            # ImageJ needs C/Z/T dimensions. Use frames solely as a page-order
            # interoperability axis, without assigning physical Z or time spacing.
            self.image.setDimensions(1, 1, self.image.getStackSize())
        try:
            for item in info.inputs():
                name, type_name = str(item.getName()), str(item.getType().getName())
                if type_name == 'ij.ImagePlus':
                    values.put(name, self.image)
                elif type_name in ('net.imagej.Dataset', 'net.imagej.display.ImageDisplay'):
                    if dataset is None:
                        dataset = engine.convert().convert(self.image, dataset_type.class_)
                        if dataset is not None and self.image.getStack().isVirtual():
                            size = self.image.getWidth()*self.image.getHeight()*self.image.getStackSize()*max(1,self.image.getBitDepth()//8)
                            if size > 512*1024**2:
                                raise ValueError('Fiji 전체 스택 작업 복사본은 512 MiB까지 지원합니다. 큰 XRT 스택은 현재 페이지를 처리하세요')
                            # A virtual ImagePlus reloads pages; writes through its adapter
                            # would disappear. Materialize an explicit bounded working copy.
                            dataset = dataset.duplicate()
                    if dataset is None:
                        raise ValueError('ImagePlus를 ImageJ2 Dataset으로 변환할 수 없습니다')
                    if type_name == 'net.imagej.display.ImageDisplay':
                        if display is None:
                            display = engine.imageDisplay().createImageDisplay(dataset)
                        values.put(name, display)
                    else:
                        values.put(name, dataset)
                elif name in args:
                    value = args[name]
                    if type_name in ('boolean','java.lang.Boolean') and type(value) is not bool:
                        raise TypeError(name + ': JSON true/false를 입력하세요')
                    if type_name in ('int','java.lang.Integer','long','java.lang.Long') and type(value) is not int:
                        raise TypeError(name + ': JSON 정수를 입력하세요')
                    if type_name in ('double','java.lang.Double','float','java.lang.Float') and (type(value) not in (int,float) or not np.isfinite(value)):
                        raise ValueError(name + ': 유한한 JSON 숫자를 입력하세요')
                    if type_name in ('double','java.lang.Double'):
                        value = self.jp.JDouble(value)
                    elif type_name in ('float','java.lang.Float'):
                        value = self.jp.JFloat(value)
                    elif type_name in ('int','java.lang.Integer'):
                        value = self.jp.JInt(value)
                    elif type_name in ('long','java.lang.Long'):
                        value = self.jp.JLong(value)
                    elif type_name in ('boolean','java.lang.Boolean'):
                        value = self.jp.JBoolean(value)
                    elif type_name == 'java.io.File':
                        value = self.jp.JClass('java.io.File')(str(value))
                    values.put(name, value)
            # Inject services, initialize defaults and validate typed inputs. Output display
            # is handled by Qt, so SciJava's display postprocessors are not invoked.
            pre_type = self.jp.JClass('org.scijava.module.process.PreprocessorPlugin')
            preprocessors = engine.plugin().createInstancesOfType(pre_type.class_)
            postprocessors = self.jp.JClass('java.util.ArrayList')()
            module = engine.module().run(info, preprocessors, postprocessors, values).get()
        finally:
            if display is not None:
                display.close()
        if module.isCanceled():
            raise ValueError('ImageJ2 명령이 취소되었습니다: ' + str(module.getCancelReason()))
        outputs = {}
        image_output = False
        for name in module.getOutputs().keySet():
            output = module.getOutput(name)
            if isinstance(output, self.jp.JClass('ij.ImagePlus')):
                self.image = output
                image_output = True
            elif isinstance(output, dataset_type):
                converted = engine.convert().convert(output, self.jp.JClass('ij.ImagePlus').class_)
                if converted is not None:
                    self.image = converted
                    image_output = True
                else:
                    raise ValueError('ImageJ2 출력 Dataset을 내부 뷰어 이미지로 변환하지 못했습니다')
            elif output is not None:
                outputs[str(name)] = str(output)
        if dataset is not None and not image_output:
            converted = engine.convert().convert(dataset, self.jp.JClass('ij.ImagePlus').class_)
            if converted is None:
                raise ValueError('수정된 ImageJ2 Dataset을 내부 뷰어로 반환할 수 없습니다')
            self.image = converted
        return outputs

    def invalidate(self):
        """An exception cannot leave hidden partial edits active for the next command."""
        with self.lock:
            if self.jp is not None:
                for image_id in self.Interpreter.getBatchModeImageIDs():
                    image = self.Interpreter.getBatchModeImage(image_id)
                    if image is not None:
                        image.changes = False
                        self.Interpreter.removeBatchModeImage(image)
                self.WM.setTempCurrentImage(None)
            self.image = self.identity = None
            self.active_output = None
