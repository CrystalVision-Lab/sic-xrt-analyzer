"""ImageJ 1.x embedded JVM; pixels belong to a working copy, never a source file."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

import numpy as np
import tifffile

ENGINE_LOCK = RLock()

JARS = {
    'ij-1.54p.jar': ('net/imagej/ij/1.54p', '2e1a09961dfb41cee66ddc821b2577a41a072566ce45a49bae69267099741e20'),
    'ij1-patcher-2.0.0.jar': ('net/imagej/ij1-patcher/2.0.0', 'b68810263f9521ddb34bac272816613ebb71607775c1fc337079a0476c2b581a'),
    'javassist-3.30.2-GA.jar': ('org/javassist/javassist/3.30.2-GA', 'eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf'),
    'classgraph-4.8.162.jar': ('io/github/classgraph/classgraph/4.8.162', 'ea30b2d5e29e89d52706bcecf7a6ae3b44682d4a1566a5f22b9453f9be2a970c'),
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
        candidates = [Path(home) / 'bin/server/jvm.dll', Path(home) / 'lib/server/libjvm.so', Path(home) / 'lib/server/libjvm.dylib']
        jvm = next((p for p in candidates if p.is_file()), None)
        jpype.startJVM('-Xmx3g', '-Djava.awt.headless=true', '--add-opens=java.base/java.lang=ALL-UNNAMED',
                      jvmpath=str(jvm) if jvm else None, classpath=[str(p) for p in files], convertStrings=True)
        jpype.JClass('net.imagej.patcher.LegacyInjector').preinit()
    return jpype


class ImageJRuntime:
    """One serialized embedded ImageJ session; arbitrary plugins have normal user privileges."""
    def __init__(self):
        self.directory = TemporaryDirectory(prefix='sic-xrt-imagej-', dir=os.environ.get('SIC_XRT_IMAGEJ_TMP'))
        self.lock = ENGINE_LOCK
        self.jp = None
        self.image = None
        self.identity = None
        self.outputs = set()
        self.active_output = None
        self.sequence = 0

    def start(self):
        if self.jp is None:
            self.jp = initialize()
            self.IJ = self.jp.JClass('ij.IJ')
            self.WM = self.jp.JClass('ij.WindowManager')
            self.Interpreter = self.jp.JClass('ij.macro.Interpreter')
            self.IJ.runMacro('setBatchMode(true);')
        return self.jp

    def load(self, frame, whole_stack=False):
        jp = self.start()
        source = frame.source
        if (self.image is not None and (source.identity == self.identity or source.path == self.active_output)
                and (not whole_stack or self.image.getStackSize() == source.metadata.page_count)):
            if self.image.getStackSize() == source.metadata.page_count:
                self.image.setSlice(source.page_index + 1)
            self.WM.setTempCurrentImage(self.image)
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
        source.validate_identity()

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

    def run(self, frame, *, macro='', command='', options='', plugin='', record=None, whole_stack=False, edit=None):
        with self.lock:
            self.load(frame, whole_stack)
            self.roi(record)
            before_images = set(self.Interpreter.getBatchModeImageIDs())
            before_log = self.IJ.getLog() or ''
            if edit:
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
                    'log': log.removeprefix(before_log),
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
        with self.lock:
            if self.image is not None:
                self.image.changes = False
                self.Interpreter.removeBatchModeImage(self.image)
                self.WM.setTempCurrentImage(None)
                self.image = None
            self.directory.cleanup()

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
