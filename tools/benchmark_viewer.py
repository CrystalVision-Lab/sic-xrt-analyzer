"""Reproducible display-path benchmark; results/images belong in ignored artifacts.

QPainter timings are CPU measurements, not input-to-photon or GPU timings.
--window additionally measures programmatic command-to-frameSwapped on Qt's
actual platform. It does not claim physical mouse or Native Dialog acceptance.
"""
import argparse
import ast
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import imagecodecs
import numpy as np
import tifffile
from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt, QUrl, qVersion
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtQml import (
    QQmlAbstractUrlInterceptor,
    QQmlApplicationEngine,
    QQmlExpression,
)
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.imaging.display_pyramid import DisplayPyramid
from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.ui import prepared_view
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def summary(values):
    return {'median': statistics.median(values), 'p95': float(np.percentile(values, 95)),
            'max': max(values), 'n': len(values)} if values else None


def rss():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        return None


class ObservedPainter:
    """Time only the existing raster draw/scaling call, preserving its arguments."""
    def __init__(self, painter, calls, stages):
        self.painter, self.calls, self.stages = painter, calls, stages

    def setRenderHint(self, *args):
        self.painter.setRenderHint(*args)

    def drawImage(self, *args):
        start = time.perf_counter()
        try:
            self.painter.drawImage(*args)
        finally:
            self.calls['raster_scaling_draw'] = self.calls.get('raster_scaling_draw', 0)+1
            self.stages.setdefault('raster_scaling_draw', []).append((time.perf_counter()-start)*1000)


def pixels(image):
    image = image.convertToFormat(QImage.Format_RGB888)
    return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*3].reshape(image.height(), image.width(), 3).copy()


def spin(app, predicate, timeout=180):
    start = time.perf_counter()
    while not predicate():
        app.processEvents()
        time.sleep(.001)
        if time.perf_counter()-start > timeout:
            raise TimeoutError('Viewer benchmark wait timed out')


def reference(source, x, y, w, h):
    # Independent decoder, never the viewer's display samples/pyramid.
    if source.metadata.format == 'JPEG':
        encoded = np.memmap(source.path, mode='r', dtype='uint8')
        try:
            full = imagecodecs.jpeg8_decode(encoded, outcolorspace='RGB')
            return full[y:y+h, x:x+w].copy()
        finally:
            encoded._mmap.close()
    try:
        mapped = tifffile.memmap(source.path, page=source.page_index, mode='r')
    except ValueError:
        # ImageJ virtual frames may share one contiguous first IFD.
        mapped = tifffile.memmap(source.path, mode='r')
    try:
        m = source.metadata
        page = mapped.reshape((m.page_count, m.height, m.width) + (() if m.channels == 1 else (m.channels,)))[source.page_index] if mapped.ndim > (2 if m.channels == 1 else 3) else mapped
        return page[y:y+h, x:x+w].copy()
    finally:
        mapped._mmap.close()


def window_bench(app, path, output, repeats, suppress_demo=False, baseline_viewer=False):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    interceptor = None
    if baseline_viewer:
        ui_dir = Path(prepared_view.__file__).parent
        original = subprocess.check_output(['git', 'show', 'e9cad2b07027675225a6b4f89a57b0774eb22cb2:src/sic_xrt_analyzer/ui/ImageViewer.qml'], text=True, encoding='utf8')
        baseline_file = output/'TD12ImageViewer.qml'
        baseline_file.write_text('import "'+ui_dir.as_uri()+'"\n'+original, encoding='utf8')
        class BaselineViewerUrl(QQmlAbstractUrlInterceptor):
            def intercept(self, url, data_type):
                if data_type == QQmlAbstractUrlInterceptor.QmlFile and Path(url.toLocalFile()) == ui_dir/'ImageViewer.qml':
                    return QUrl.fromLocalFile(str(baseline_file.resolve()))
                return url
        interceptor = BaselineViewerUrl()
        engine.addUrlInterceptor(interceptor)
    provider = TiffImageProvider()
    bridge = FileBridge(provider, engine, QSettings(str(output/'window.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(prepared_view.__file__).with_name('Main.qml'))))
    window = engine.rootObjects()[0]
    window.setTitle('XRT Viewer performance benchmark')
    if suppress_demo:
        demos = [obj for obj in window.findChildren(QObject) if obj.metaObject().className().startswith('DemoImage_')]
        for demo in demos:
            for canvas in demo.findChildren(QObject):
                if canvas.metaObject().className() == 'QQuickCanvasItem':
                    expression = QQmlExpression(engine.rootContext(), canvas, 'anchors.fill = null; width = 0; height = 0')
                    expression.evaluate()
                    assert not expression.hasError(), expression.error().toString()
    ui = window.findChild(QObject, 'uiState')
    viewer = window.findChild(QObject, 'imageViewer')
    painted = window.findChild(QObject, 'preparedImageView')
    viewport = window.findChild(QObject, 'viewerViewport')
    frames, heartbeats, render_times, sync_times = [], [], [], []
    phase_start = {}
    window.beforeSynchronizing.connect(lambda: phase_start.update(sync=time.perf_counter()))
    window.afterSynchronizing.connect(lambda: sync_times.append((time.perf_counter()-phase_start.get('sync',time.perf_counter()))*1000))
    window.beforeRendering.connect(lambda: phase_start.update(render=time.perf_counter()))
    window.afterRendering.connect(lambda: render_times.append((time.perf_counter()-phase_start.get('render',time.perf_counter()))*1000))
    window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: heartbeats.append(time.perf_counter()))
    try:
        # Test harness ingress, explicitly not Native Open acceptance.
        ui.setProperty('opening', True)
        bridge.requestImage(bridge.localUrl(str(path)))
        spin(app, lambda: bridge.stack_viewer.frame is not None and not bridge.stack_viewer.initial_loading)
        spin(app, lambda: painted.isVisible() and len(frames)>0)
        timer.start()
        rows = []
        for scale in [None, 1., 2., 4., 8.]:
            ui.setProperty('fitMode', scale is None)
            if scale is not None:
                ui.setProperty('zoom', scale)
            app.processEvents()
            # Flush layout/render before timing commands.
            window.grabWindow()
            for overlay in [False, True]:
                ui.setProperty('hasRoi', overlay)
                ui.setProperty('roiStartX', .3); ui.setProperty('roiStartY', .3)
                ui.setProperty('roiEndX', .7); ui.setProperty('roiEndY', .7)
                samples, zooms, pan_frames = [], [], []
                cpu_start, start = time.process_time(), time.perf_counter()
                for i in range(repeats):
                    frame_count = len(frames)
                    viewer.setProperty('panX', i*3.)
                    painted.update(); window.update()
                    try:
                        spin(app, lambda count=frame_count: len(frames)>count, 10)
                    except TimeoutError:
                        (output/'timeout.json').write_text(json.dumps({'scale': scale, 'overlay': overlay, 'phase': 'continuous_pan', 'iteration': i,
                            'active': window.isActive(), 'exposed': window.isExposed(), 'visible': window.isVisible(),
                            'painted_visible': painted.isVisible(), 'frames': len(frames), 'rows': rows}), encoding='utf8')
                        raise
                    pan_frames.append(frames[-1])
                for i in range(repeats):
                    frame_count = len(frames)
                    command = time.perf_counter()
                    viewer.setProperty('panX', (i%7)*3.)
                    viewer.setProperty('panY', (i%5)*2.)
                    window.update()
                    painted.update()
                    try:
                        spin(app, lambda count=frame_count: len(frames)>count, 10)
                    except TimeoutError:
                        (output/'timeout.json').write_text(json.dumps({'scale': scale, 'overlay': overlay, 'phase': 'pan', 'iteration': i,
                            'active': window.isActive(), 'exposed': window.isExposed(), 'visible': window.isVisible(),
                            'painted_visible': painted.isVisible(), 'frames': len(frames), 'rows': rows}), encoding='utf8')
                        raise
                    samples.append((frames[-1]-command)*1000)
                    frame_count = len(frames)
                    command = time.perf_counter()
                    if scale is None:
                        ui.setProperty('fitMode', False); ui.setProperty('zoom', viewer.property('fitScale')*(1.001 if i%2 else 1.))
                    else:
                        ui.setProperty('zoom', scale*(1.001 if i%2 else 1.))
                    window.update()
                    painted.update()
                    try:
                        spin(app, lambda count=frame_count: len(frames)>count, 10)
                    except TimeoutError:
                        (output/'timeout.json').write_text(json.dumps({'scale': scale, 'overlay': overlay, 'phase': 'zoom', 'iteration': i,
                            'active': window.isActive(), 'exposed': window.isExposed(), 'visible': window.isVisible(),
                            'painted_visible': painted.isVisible(), 'frames': len(frames), 'rows': rows}), encoding='utf8')
                        raise
                    zooms.append((frames[-1]-command)*1000)
                elapsed = time.perf_counter()-start
                rows.append({'scale': scale or 'Fit', 'roi_overlay': overlay, 'pan_command_to_swap_ms': summary(samples),
                             'zoom_command_to_swap_ms': summary(zooms), 'cpu_one_core_percent': (time.process_time()-cpu_start)/elapsed*100,
                             'continuous_pan_frame_ms': summary([1000*(b-a) for a,b in pairwise(pan_frames)]),
                             'rss': rss(), 'viewport': [viewport.width(), viewport.height()]})
        ui.setProperty('activeTool', 'Pan')
        viewer_mouse = window.findChild(QObject, 'viewerMouseArea')
        scene = viewer_mouse.mapToScene(QPointF(100,100))
        press = QPoint(round(scene.x()), round(scene.y()))
        mouse_handler = []
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, press)
        start_pan = viewer.property('panX')
        for i in range(repeats):
            tick = time.perf_counter()
            QTest.mouseMove(window, press+QPoint(i+1,i+1), 0)
            app.processEvents()
            mouse_handler.append((time.perf_counter()-tick)*1000)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, press+QPoint(repeats,repeats))
        mouse_pan_changed = viewer.property('panX') != start_pan
        timer.stop()
        measured_heartbeats = heartbeats.copy()
        ui.setProperty('hasRoi', False)
        quality = []
        frame = bridge.stack_viewer.frame
        x, y = 1003, 1011
        raw = reference(frame.source, x, y, 128, 96)
        display = np.clip((raw.astype(np.float64)-frame.low)*(255/(frame.high-frame.low)), 0, 255).astype(np.uint8)
        if getattr(frame.source.display_pyramid, 'invert', False):
            display = 255-display
        if display.ndim == 2:
            display = np.repeat(display[...,None], 3, axis=2)
        for scale in [1, 2, 4]:
            ui.setProperty('fitMode', False); ui.setProperty('zoom', scale)
            viewer.setProperty('panX', -x*scale-(viewport.width()-frame.source.metadata.width*scale)/2)
            viewer.setProperty('panY', -y*scale-(viewport.height()-frame.source.metadata.height*scale)/2)
            app.processEvents(); painted.update()
            captured = window.grabWindow()
            position = viewport.mapToScene(QPointF(0,0))
            actual = pixels(captured.copy(round(position.x()), round(position.y()), 128, 96))
            expected = np.repeat(np.repeat(display, scale, axis=0), scale, axis=1)[:96,:128]
            diff = np.abs(actual.astype(np.int16)-expected.astype(np.int16))
            quality.append({'scale': scale, 'max_error': int(diff.max()), 'different_channel_values': int(np.count_nonzero(diff)), 'exact': not np.any(diff)})
            captured.save(str(output/f'window-{path.stem}-{scale*100}.png'))
        return {'rows': rows, 'window_quality': quality, 'qml_warnings': warnings, 'gui_timer_gap_ms': summary([1000*(b-a) for a,b in pairwise(measured_heartbeats)]),
                'qt_cpu_sync_ms': summary(sync_times), 'qt_cpu_render_submit_ms': summary(render_times),
                'synthetic_mouse_dispatch_and_process_events_ms': summary(mouse_handler), 'synthetic_pan_changed': mouse_pan_changed,
                'graphics_api': str(window.rendererInterface().graphicsApi()), 'dpr': window.devicePixelRatio(),
                'physical_input': False, 'gpu_upload_separately_measured': False}
    finally:
        timer.stop()
        window.setProperty('allowQuit', True)
        window.close()
        bridge.waitForLoads()
        engine.deleteLater(); app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeats', type=int, default=30)
    parser.add_argument('--page', choices=['first', 'middle', 'last'], default='first',
                        help='Page used for the CPU/raw-pixel comparison (window mode starts at page one)')
    parser.add_argument('--window', action='store_true')
    parser.add_argument('--window-only', action='store_true')
    parser.add_argument('--baseline', action='store_true', help='Use TD-12 paint method from its exact Git blob')
    parser.add_argument('--suppress-demo-canvas', action='store_true', help='Diagnostic ablation, no production UI changes')
    parser.add_argument('--baseline-viewer', action='store_true', help='Load the exact TD-12 ImageViewer.qml through a test URL interceptor')
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error('--repeats must be at least 2')
    args.output.mkdir(parents=True, exist_ok=True)
    code = Path(prepared_view.__file__).read_text(encoding='utf8')
    if args.baseline:
        code = subprocess.check_output(['git', 'show', 'e9cad2b07027675225a6b4f89a57b0774eb22cb2:src/sic_xrt_analyzer/ui/prepared_view.py'], text=True, encoding='utf8')
        cls = next(node for node in ast.parse(code).body if isinstance(node, ast.ClassDef) and node.name == 'PreparedView')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'paint')
        namespace = vars(prepared_view)
        # Fixed, user-requested Git baseline, not arbitrary downloaded code.
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<TD12 baseline paint>', 'exec'), namespace)  # noqa: S102
        PreparedView.paint = namespace['paint']
    app = QGuiApplication.instance() or QGuiApplication([])
    results = {'environment': {'os': platform.platform(), 'python': platform.python_version(), 'qt': qVersion(),
                              'qpa': app.platformName(), 'render_loop': os.getenv('QSG_RENDER_LOOP'),
                              'quick_backend': os.getenv('QT_QUICK_BACKEND'), 'rhi_backend': os.getenv('QSG_RHI_BACKEND')}, 'files': []}
    results['environment']['paint_code_sha256'] = hashlib.sha256(code.encode()).hexdigest()
    results['environment']['baseline'] = args.baseline
    results['environment']['suppress_demo_canvas'] = args.suppress_demo_canvas
    results['environment']['baseline_viewer'] = args.baseline_viewer
    for number, path in enumerate(args.paths):
        if args.window_only:
            row = {'file': path.name, 'window': window_bench(app, path, args.output, args.repeats, args.suppress_demo_canvas, args.baseline_viewer)}
            results['files'].append(row)
            (args.output/'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({'file': path.name, 'window_rows': len(row['window']['rows'])}), flush=True)
            continue
        before = digest(path)
        stack = open_stack(path, browse_enabled=True)
        calls, stages = {}, {}
        def timed(label, function, calls=calls, stages=stages):
            def run(*a, **kw):
                start = time.perf_counter()
                try:
                    return function(*a, **kw)
                finally:
                    calls[label] = calls.get(label, 0)+1
                    stages.setdefault(label, []).append((time.perf_counter()-start)*1000)
            return run
        try:
            start = time.perf_counter()
            with patch.object(imagecodecs, 'jpeg8_decode', timed('jpeg_decode', imagecodecs.jpeg8_decode)):
                if hasattr(stack, 'prepare_native'):
                    assert stack.prepare_native()
                page = {'first': 0, 'middle': stack.page_count // 2, 'last': stack.page_count - 1}[args.page]
                frame = stack.frame(page)
            row = {'file': path.name, 'prepare_seconds': time.perf_counter()-start, 'sha256_before': before,
                   'dimensions': [frame.source.metadata.width, frame.source.metadata.height], 'dtype': frame.source.metadata.dtype,
                   'page_count': frame.source.metadata.page_count, 'page_index': page,
                   'preparation_calls': dict(calls), 'tiff_page_reads_preparation': getattr(stack, 'decode_count', None),
                   'paint': [], 'quality': []}
            assert getattr(frame.source, 'display_pyramid', None) is not None
            view = PreparedView()
            view.bridge = SimpleNamespace(stack_viewer=SimpleNamespace(frame=frame))
            view.setWidth(1200); view.setHeight(800)
            source = frame.source
            x, y = min(1003, source.metadata.width-1200), min(1011, source.metadata.height-800)
            raw = reference(source, x, y, 1200, 800)
            expected = np.clip((raw.astype(np.float64)-frame.low)*(255/(frame.high-frame.low)), 0, 255).astype(np.uint8)
            if getattr(source.display_pyramid, 'invert', False):
                expected = 255-expected
            if expected.ndim == 2:
                expected = np.repeat(expected[...,None], 3, axis=2)
            QImage(expected.data, 1200, 800, expected.strides[0], QImage.Format_RGB888).save(str(args.output/f'{number}-direct-crop.png'))
            stages.clear(); calls.clear()
            with patch.object(DisplayPyramid, 'region', timed('region_copy', DisplayPyramid.region)), \
                 patch.object(prepared_view, 'render_samples', timed('display_conversion', prepared_view.render_samples)), \
                 patch.object(type(source), 'validate_identity', timed('identity_stat', source.validate_identity.__func__)), \
                 patch.object(imagecodecs, 'jpeg8_decode', timed('jpeg_decode', imagecodecs.jpeg8_decode)):
                for scale in [min(1200/source.metadata.width, 800/source.metadata.height), 1., 2., 4., 8.]:
                    for motion in ['stationary', 'pan', 'zoom']:
                        times = []; start_calls = dict(calls)
                        cpu_start, start = time.process_time(), time.perf_counter()
                        for i in range(args.repeats):
                            s = scale*(1+(i%2)*.001) if motion=='zoom' else scale
                            dx, dy = ((i%7)*3, (i%5)*2) if motion=='pan' else (0,0)
                            view.viewTransform = [-x*s+dx, -y*s+dy, s]
                            image = QImage(1200, 800, QImage.Format_RGB32); image.fill(0xff000000)
                            painter = QPainter(image)
                            tick = time.perf_counter(); view.paint(ObservedPainter(painter, calls, stages))
                            times.append((time.perf_counter()-tick)*1000); painter.end()
                        elapsed = time.perf_counter()-start
                        row['paint'].append({'scale': scale, 'motion': motion, 'cpu_paint_ms': summary(times), 'rss': rss(),
                                             'cpu_one_core_percent': (time.process_time()-cpu_start)/elapsed*100,
                                             'calls': {k:v-start_calls.get(k,0) for k,v in calls.items()}})
                    if scale >= 1:
                        view.viewTransform = [-x*scale, -y*scale, scale]
                        image = QImage(1200, 800, QImage.Format_RGB32); image.fill(0xff000000)
                        painter = QPainter(image); view.paint(painter); painter.end()
                        target = np.repeat(np.repeat(expected, int(scale), axis=0), int(scale), axis=1)[:800,:1200]
                        actual = pixels(image)
                        diff = np.abs(actual.astype(np.int16)-target.astype(np.int16))
                        row['quality'].append({'scale': scale, 'different_channel_values': int(np.count_nonzero(diff)), 'max_error': int(diff.max()), 'exact': not np.any(diff)})
                        image.save(str(args.output/f'{number}-viewer-{int(scale*100)}.png'))
            row['stages_ms'] = {k: summary(v) for k,v in stages.items()}
            row['paint_calls'] = calls
            row['tiff_page_reads_during_paint'] = (stack.decode_count - row['tiff_page_reads_preparation']) if hasattr(stack, 'decode_count') else None
        finally:
            stack.close()
        row['sha256_after'] = digest(path)
        row['original_unchanged'] = before == row['sha256_after']
        results['files'].append(row)
        (args.output/'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
        if args.window:
            row['window'] = window_bench(app, path, args.output, args.repeats, args.suppress_demo_canvas, args.baseline_viewer)
        (args.output/'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps({'file': path.name, 'quality': row['quality'], 'unchanged': row['original_unchanged']}), flush=True)


if __name__ == '__main__':
    main()
