"""Opt-in native Qt benchmark (QTest inputs, never physical mouse acceptance).

Run each backend/DPI in a fresh process. Outputs and raw captures stay in an
ignored directory. frameSwapped means Qt submission, not input-to-photon. No
product defaults, source pixels, cache policy or model parameters are changed.
"""
import argparse
import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

import imagecodecs
import numpy as np
import psutil
from benchmark_viewer import digest, pixels, reference, spin
from PySide6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QSettings,
    Qt,
    QTimer,
    QUrl,
    qVersion,
)
from PySide6.QtQml import QQmlAbstractUrlInterceptor, QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sic_xrt_analyzer.imaging.display_pyramid import DisplayPyramid
from sic_xrt_analyzer.ui import prepared_view
from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def stats(values):
    return {"n": len(values), "median": statistics.median(values),
            "p95": float(np.percentile(values, 95)), "max": max(values),
            "min": min(values), "over_50ms": sum(v > 50 for v in values),
            "over_100ms": sum(v > 100 for v in values)} if values else None


class EventTrace(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.events = []
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            self.events.append((time.perf_counter(), str(event.type())))
        return False


class Session:
    def __init__(self, app, output, baseline_viewer=False):
        self.app, self.output = app, output
        self.engine = QQmlApplicationEngine()
        self.interceptor = None
        if baseline_viewer:
            ui_dir = Path(prepared_view.__file__).parent
            ref = baseline_viewer if isinstance(baseline_viewer, str) else '18b9b9cdc27332ada788097866507d05851aa012'
            baseline = subprocess.check_output(['git','show',ref+':src/sic_xrt_analyzer/ui/ImageViewer.qml'],text=True,encoding='utf8')
            baseline_path = output/'TD01ImageViewer.qml'
            baseline_path.write_text('import "'+ui_dir.as_uri()+'"\n'+baseline,encoding='utf8')
            class BaselineUrl(QQmlAbstractUrlInterceptor):
                def intercept(self, url, kind):
                    if kind == QQmlAbstractUrlInterceptor.QmlFile and Path(url.toLocalFile()) == ui_dir/'ImageViewer.qml':
                        return QUrl.fromLocalFile(str(baseline_path.resolve()))
                    return url
            self.interceptor = BaselineUrl()
            self.engine.addUrlInterceptor(self.interceptor)
        provider = TiffImageProvider()
        self.bridge = FileBridge(provider, self.engine, QSettings(str(output / 'prefs.ini'), QSettings.IniFormat))
        self.engine.addImageProvider('tiff', provider)
        self.engine.rootContext().setContextProperty('fileBridge', self.bridge)
        self.warnings = []
        self.engine.warnings.connect(lambda items: self.warnings.extend(i.toString() for i in items))
        self.frames, self.paints, self.syncs, self.renders, self.beats = [], [], [], [], []
        self.calls, self.stages, self.phase = Counter(), {}, {}
        self.state_events, self.region_events = [], []
        self.paint_threads = set()
        self.engine.load(QUrl.fromLocalFile(str(Path(prepared_view.__file__).with_name('Main.qml'))))
        assert self.engine.rootObjects(), self.warnings
        self.window = self.engine.rootObjects()[0]
        self.window.setTitle('XRT-PERF-TD-02 automated benchmark')
        self.window.resize(1440, 900)
        self.ui = self.item('uiState')
        self.viewer, self.viewport, self.view = [self.item(n) for n in ('imageViewer', 'viewerViewport', 'preparedImageView')]
        self.overlay = self.item('analysisOverlay')
        for obj, signal in [(self.viewer,'panXChanged'), (self.viewer,'panYChanged'),
                            (self.ui,'zoomChanged'), (self.ui,'fitModeChanged')]:
            getattr(obj,signal).connect(lambda: self.state_events.append(time.perf_counter()))
        self.events = EventTrace(self.window)
        self.window.frameSwapped.connect(lambda: self.frames.append((time.perf_counter(), len(self.paints))))
        for prefix, start, end, dest in [('sync', 'beforeSynchronizing', 'afterSynchronizing', self.syncs),
                                       ('render', 'beforeRendering', 'afterRendering', self.renders)]:
            getattr(self.window, start).connect(lambda p=prefix: self.phase.update({p: time.perf_counter()}))
            getattr(self.window, end).connect(lambda p=prefix, d=dest: d.append((time.perf_counter() - self.phase.get(p, time.perf_counter())) * 1000))
        self.timer = QTimer()
        self.timer.setInterval(5)
        self.timer.timeout.connect(lambda: self.beats.append(time.perf_counter()))
        self.timer.start()

    def item(self, name):
        found = self.window.findChild(QObject, name)
        assert found is not None, name
        return found

    def timed(self, name, function):
        def run(*args, **kwargs):
            start = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                end = time.perf_counter()
                self.calls[name] += 1
                self.stages.setdefault(name, []).append((end - start) * 1000)
                if name == 'region':
                    self.region_events.append((start,end))
        return run

    def paint(self, original, item, painter):
        start, cache = time.perf_counter(), item._display_cache
        before = self.calls['region']
        transform = list(item.viewTransform)
        self.paint_threads.add(threading.get_ident())
        original(item, painter)
        self.paints.append({'start': start, 'end': time.perf_counter(), 'transform': transform,
                            'hit': cache is not None and self.calls['region'] == before,
                            'cache_bytes': item._display_cache[5].sizeInBytes() if item._display_cache else 0})

    def open(self, path):
        self.capture_prefix = path.stem
        self.ui.setProperty('opening', True)
        start = time.perf_counter()
        self.bridge.requestImage(self.bridge.localUrl(str(path)))
        spin(self.app, lambda: not self.bridge.stack_viewer.initial_loading and self.bridge.original_source is not None, 600)
        assert Path(self.bridge.original_source.path) == path, self.bridge.stack_viewer.error
        assert not self.bridge.stack_viewer.error
        self.app.processEvents()
        self.window.grabWindow()
        return time.perf_counter() - start

    def set_zoom(self, scale):
        self.ui.setProperty('fitMode', scale is None)
        if scale is not None:
            self.ui.setProperty('zoom', float(scale))

    def settle(self):
        self.app.processEvents()
        self.window.grabWindow()

    def command(self, action):
        first_frame, first_paint, first_event = len(self.frames), len(self.paints), len(self.events.events)
        first_state, first_region = len(self.state_events), len(self.region_events)
        start = time.perf_counter()
        action()
        self.app.processEvents()
        state = time.perf_counter()
        target = list(self.view.viewTransform)
        self.view.update()
        self.window.update()
        def completed():
            return any(p['start'] >= start and p['transform'] == target for p in self.paints[first_paint:]) and len(self.frames) > first_frame and self.frames[-1][1] > first_paint
        try:
            spin(self.app, completed, 5)
        except TimeoutError:
            (self.output/'timeout.json').write_text(json.dumps({'frames':len(self.frames), 'first_frame':first_frame,
                'paints':self.paints[first_paint:], 'target':target, 'exposed':self.window.isExposed(),
                'visible':self.view.isVisible(), 'calls':dict(self.calls)}),encoding='utf8')
            raise
        paint = next(p for p in self.paints[first_paint:] if p['start'] >= start and p['transform'] == target)
        swapped = next(f for f in self.frames[first_frame:] if f[0] >= paint['end'])
        received = self.events.events[first_event:]
        states, regions = self.state_events[first_state:], self.region_events[first_region:]
        return {'state_ms': (states[0]-start)*1000 if states else None,
                'dispatch_process_ms': (state-start)*1000,
                'region_ready_ms': (regions[-1][1]-start)*1000 if regions else 0.,
                'event_ms': (received[0][0]-start)*1000 if received else None,
                'paint_ms': (paint['end']-paint['start'])*1000,
                'prepared_ms': (paint['end']-start)*1000, 'swap_ms': (swapped[0]-start)*1000,
                'swap': swapped[0], 'hit': paint['hit']}

    def case(self, scale, kind, repeats):
        research = self.bridge.research
        research.setFilter('ALL' if kind in ('OFF', 'ALL', 'SELECTED') else kind, False, '')
        self.ui.setProperty('analysisLayerVisible', kind != 'OFF')
        if kind == 'SELECTED':
            research.selectCandidate(research.rows[0]['id'])
            spin(self.app, lambda: not self.item('candidateFocusAnimation').property('running'), 5)
        else:
            research._clear_selection()
            research.changed.emit()
        self.set_zoom(scale)
        self.viewer.setProperty('panX', 0.)
        self.viewer.setProperty('panY', 0.)
        self.settle()
        self.view._display_cache = None  # Diagnostic cold-display-cache sample only.
        cold = self.command(lambda: None)
        # GUI/QTest event dispatch rather than only assigning pan properties.
        self.ui.setProperty('activeTool', 'Pan')
        point = self.item('viewerMouseArea').mapToScene(QPointF(self.viewport.width()/2, self.viewport.height()/2))
        anchor = QPoint(round(point.x()), round(point.y()))
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, anchor)
        self.app.processEvents()
        pans, zooms = [], []
        calls_before, paint_before = self.calls.copy(), len(self.paints)
        beat_before, sync_before, render_before = len(self.beats), len(self.syncs), len(self.renders)
        cpu, tick = time.process_time(), time.perf_counter()
        for i in range(repeats):
            # Alternating directions and small/large moves; no forced sleeps.
            offset = QPoint(12+(i % 5)*3 if i % 2 else 72 - (i % 5)*12, (i % 4)*2)
            pans.append(self.command(lambda p=anchor+offset: QTest.mouseMove(self.window, p, 0)))
        QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, anchor+offset)
        fit = self.viewer.property('fitScale') * self.ui.property('displayPixelRatio')
        target = scale or fit
        for i in range(repeats):
            zooms.append(self.command(lambda z=target*(1 if i % 2 else .8): self.set_zoom(z)))
        elapsed = time.perf_counter() - tick
        row = {'scale': scale or 'Fit', 'overlay': kind,
               'candidate_count': len(research.filtered) if kind != 'OFF' else 0,
               'cold_display_cache': cold,
               'pan': {name: stats([p[name] for p in pans if p[name] is not None]) for name in ('event_ms', 'state_ms', 'dispatch_process_ms', 'region_ready_ms', 'paint_ms', 'prepared_ms', 'swap_ms')},
               'zoom': {name: stats([p[name] for p in zooms if p[name] is not None]) for name in ('state_ms', 'dispatch_process_ms', 'region_ready_ms', 'paint_ms', 'prepared_ms', 'swap_ms')},
               'frame_interval_ms': stats([1000*(b['swap']-a['swap']) for a,b in pairwise(pans)]),
               'cpu_one_core_percent': (time.process_time()-cpu)/elapsed*100,
               'system_available_memory': psutil.virtual_memory().available,
               'rss': psutil.Process().memory_info().rss,
               'gui_timer_gap_ms': stats([1000*(b-a) for a,b in pairwise(self.beats[beat_before:])]),
               'cpu_scene_sync_ms': stats(self.syncs[sync_before:]),
               'cpu_render_submit_ms': stats(self.renders[render_before:]),
               'command_requests': repeats*2, 'command_completions': len(pans)+len(zooms),
               'first_pan_cold_or_transition': pans[0]['swap_ms'],
               'remaining_pan_ms': stats([p['swap_ms'] for p in pans[1:]]),
               'calls': dict(self.calls - calls_before), 'paint_requests': len(self.paints)-paint_before,
               'pan_cache_hits': sum(p['hit'] for p in pans), 'zoom_cache_hits': sum(p['hit'] for p in zooms)}
        assert max((p['cache_bytes'] for p in self.paints[paint_before:]), default=0) <= 32*1024**2
        return row

    def quality(self, label):
        self.ui.setProperty('analysisLayerVisible', False)
        self.ui.setProperty('roiLayerVisible', False)
        source = self.bridge.original_source
        frame = self.bridge.stack_viewer.frame
        x, y, w, h = 1003, 1011, 128, 96
        raw = reference(source, x, y, w, h)
        np.testing.assert_array_equal(source.read_region(x,y,w,h), raw)
        expected = np.clip((raw.astype(np.float64)-frame.low)*(255/(frame.high-frame.low)),0,255).astype(np.uint8)
        if getattr(source.display_pyramid, 'invert', False):
            expected = 255-expected
        if expected.ndim == 2:
            expected = np.repeat(expected[..., None],3,axis=2)
        dpr = self.window.devicePixelRatio()
        rows = []
        for zoom in (1,2,4,8):
            self.set_zoom(zoom)
            self.app.processEvents()
            scale = self.viewer.property('displayScale')
            # Align to physical pixels at fractional DPI. Zoom=physical pixels/original pixel.
            self.viewer.setProperty('panX', -x*scale-(self.viewport.width()-source.metadata.width*scale)/2)
            self.viewer.setProperty('panY', -y*scale-(self.viewport.height()-source.metadata.height*scale)/2)
            self.settle()
            # A queued animation must not silently replace the requested scale.
            assert abs(self.viewer.property('displayScale') * dpr - zoom) < 1e-8
            captured = self.window.grabWindow()
            pos = self.viewport.mapToScene(QPointF())
            actual = pixels(captured.copy(round(pos.x()*dpr), round(pos.y()*dpr),w,h))
            target = np.ascontiguousarray(np.repeat(np.repeat(expected,zoom,axis=0),zoom,axis=1)[:h,:w])
            actual_image = captured.copy(round(pos.x()*dpr), round(pos.y()*dpr),w,h)
            actual_image.save(str(self.output/f'{self.capture_prefix}-{label}-{zoom}-screen.png'))
            from PySide6.QtGui import QImage
            expected_image = QImage(target.data,w,h,target.strides[0],QImage.Format_RGB888).copy()
            expected_image.save(str(self.output/f'{self.capture_prefix}-{label}-{zoom}-expected.png'))
            # Exclude the viewport clip boundary (fractional-DPI half pixel).
            # Interior still maps to the same original crop; no error tolerance.
            diff = np.abs(actual[2:-2,2:-2].astype(np.int16)-target[2:-2,2:-2].astype(np.int16))
            rows.append({'label': label, 'zoom': zoom, 'logical_scale': scale, 'dpr': dpr,
                         'max_error': int(diff.max()), 'different_values': int(np.count_nonzero(diff)),
                         'exact': not np.any(diff), 'raw_pixel_exact': True,
                         'compared_physical_pixels': [w-4,h-4], 'excluded_clip_border': 2,
                         'low': frame.low, 'high': frame.high,
                         'viewport_physical_origin': [pos.x()*dpr,pos.y()*dpr],
                         'texture_smooth': self.view.smooth(),
                         'pyramid_level': self.view._display_cache[0][-1] if self.view._display_cache else None})
        return rows

    def interactions(self):
        result = {}
        research = self.bridge.research
        if research.rows:
            original = self.bridge.pipeline.result
            research.setFilter('ALL',False,'')
            self.ui.setProperty('autoCandidateRoi', False)
            self.ui.setProperty('analysisLayerVisible', True)
            chosen = research.rows[0]
            research.selectCandidate(chosen['id'])
            spin(self.app, lambda: bool(research.thumbnail_source or research.thumbnail_error), 20)
            assert not research.thumbnail_error
            self.settle()
            time_start = time.perf_counter()
            research.focusRequested.emit(chosen['x'],chosen['y'])
            animation = self.item('candidateFocusAnimation')
            spin(self.app, lambda: not animation.property('running'), 5)
            self.settle()
            frame = self.item('imageFrame')
            center = [frame.x()+chosen['x']*self.viewer.property('displayScale'), frame.y()+chosen['y']*self.viewer.property('displayScale')]
            assert abs(center[0]-self.viewport.width()/2)<1 and abs(center[1]-self.viewport.height()/2)<1
            scene = self.viewport.mapToScene(QPointF(*center))
            QTest.mouseClick(self.window,Qt.LeftButton,Qt.NoModifier,QPoint(round(scene.x()),round(scene.y())))
            self.app.processEvents()
            assert research.selected_id == chosen['id']
            assert self.bridge.pipeline.result is original
            # Clicking the same candidate starts another valid Focus animation.
            # Wait for that animation before the unrelated burst/quality test.
            spin(self.app, lambda: not animation.property('running'), 5)
            self.settle()
            result['candidate_focus_hit_test'] = {'passed': True, 'ms': (time.perf_counter()-time_start)*1000}
        self.ui.setProperty('analysisLayerVisible',False)
        self.ui.setProperty('roiLayerVisible',False)
        # Rapid queued moves/zooms; only latest transform must be painted, no async viewport queue.
        self.paints.clear()
        for i in range(60):
            self.set_zoom((1,2,4,8)[i%4])
            self.viewer.setProperty('panX',float(i*3))
        final = list(self.view.viewTransform)
        self.settle()
        assert self.paints[-1]['transform'] == final
        result['latest_transform'] = True
        result['burst_paints'] = len(self.paints)
        result['quality_after_burst'] = self.quality('after-burst')
        return result

    def close(self):
        self.timer.stop()
        self.window.setProperty('allowQuit',True)
        self.window.close()
        self.bridge.waitForLoads()
        self.engine.deleteLater()
        self.app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--repeats',type=int,default=30)
    parser.add_argument('--model',type=Path)
    parser.add_argument('--reference-result',type=Path)
    parser.add_argument('--pages',action='store_true')
    parser.add_argument('--quality-only',action='store_true')
    parser.add_argument('--diagnostic-nearest-texture',action='store_true',help='Test-only ablation, never a product default')
    parser.add_argument('--baseline-viewer',action='store_true',help='Exact TD-01 final viewer via test URL interceptor')
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error('--repeats must be >= 2')
    args.output.mkdir(parents=True,exist_ok=True)
    # Match the product entry point, including QWidget native-dialog infrastructure.
    os.environ.setdefault('QSG_RENDER_LOOP','basic')
    app = QApplication([])
    QQuickStyle.setStyle('Basic')
    report = {'start_head': '18b9b9cdc27332ada788097866507d05851aa012',
              'tool_sha256': digest(Path(__file__)),
              'baseline_viewer': args.baseline_viewer,
              'environment': {'os': platform.platform(), 'qt': qVersion(), 'qpa': app.platformName(),
                              'quick_backend': os.getenv('QT_QUICK_BACKEND'), 'rhi': os.getenv('QSG_RHI_BACKEND'),
                              'render_loop': os.getenv('QSG_RENDER_LOOP'), 'scale_factor': os.getenv('QT_SCALE_FACTOR'),
                              'main_thread': threading.get_ident()},
              'physical_mouse': 'PENDING', 'input_kind': 'QTest + programmatic zoom',
              'gpu_upload_ms': 'NOT MEASURED', 'gpu_usage': 'NOT MEASURED', 'gpu_memory': 'NOT MEASURED',
              'files': []}
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(lambda kind, context, message: print(f'{context.category}: {message}',file=sys.stderr,flush=True))
    s = Session.__new__(Session)
    original_paint = PreparedView.paint
    try:
        with patch.object(PreparedView,'paint',lambda item,painter: s.paint(original_paint,item,painter)), \
             patch.object(DisplayPyramid,'region',s.timed('region',DisplayPyramid.region)), \
             patch.object(prepared_view,'render_samples',s.timed('conversion',prepared_view.render_samples)), \
             patch.object(imagecodecs,'jpeg8_decode',s.timed('jpeg_decode',imagecodecs.jpeg8_decode)):
            s.__init__(app,args.output,args.baseline_viewer)
            if args.diagnostic_nearest_texture:
                s.view.setSmooth(False)
            previous_pyramid = None
            for file_number, path in enumerate(args.paths):
                before = digest(path)
                row = {'file':path.name,'sha_before':before,'rss_before_open':psutil.Process().memory_info().rss}
                report['files'].append(row)
                row['open_seconds'] = s.open(path)
                if previous_pyramid is not None:
                    assert previous_pyramid.closed
                    assert s.view._display_cache is None or s.view._display_cache[0][0] is s.bridge.original_source.display_pyramid
                    assert not s.bridge.research.rows
                    row['previous_source_cache_overlay_cleared'] = True
                report['environment'].update(graphics_api=str(s.window.rendererInterface().graphicsApi()),
                    dpr=s.window.devicePixelRatio(), ui_dpr=s.ui.property('displayPixelRatio'),
                    viewport=[s.viewport.width(),s.viewport.height()], render_target=str(s.view.renderTarget()))
                source = s.bridge.original_source
                row['meta'] = {'width':source.metadata.width,'height':source.metadata.height,
                               'dtype':source.metadata.dtype,'pages':source.metadata.page_count}
                kinds = ['OFF']
                if args.model and source.metadata.format == 'JPEG':
                    s.bridge.research.loadModel(str(args.model))
                    spin(app,lambda: not s.bridge.research.loading,120)
                    assert not s.bridge.research.error
                    assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{'point_mode':'contrast_proposals'})
                    spin(app,lambda: s.bridge.analysis['state'] != 'RUNNING',180)
                    assert s.bridge.analysis['hasResult'], s.bridge.analysis
                    counts=Counter(p['type'] for p in s.bridge.research.rows)
                    assert dict(counts) == {'BPD':245,'TED':1398,'TSD':1303}, counts
                    row['counts'] = dict(counts)
                    if args.reference_result:
                        saved = json.loads(args.reference_result.read_text(encoding='utf8'))
                        assert s.bridge.research.rows == saved['predictions'], 'Inference candidate values differ'
                        row['unchanged_predictions'] = True
                    kinds += ['ALL','BPD','TED','TSD','SELECTED']
                row['rows']=[]
                for scale in ([] if args.quality_only else [None,1,2,4,8]):
                    for kind in kinds:
                        case=s.case(scale,kind,args.repeats)
                        row['rows'].append(case)
                        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
                        print(json.dumps({'file':path.name,'scale':scale,'kind':kind,'pan':case['pan']['swap_ms'],'zoom':case['zoom']['swap_ms']}),flush=True)
                row['quality']=s.quality('first')
                if kinds != ['OFF']:
                    assert s.bridge.research.rows == saved['predictions'] if args.reference_result else len(s.bridge.research.rows)==2946
                    row['predictions_after_interactions_unchanged'] = True
                row['interaction']=s.interactions()
                if not args.baseline_viewer:
                    assert all(q['exact'] for q in row['quality'] + row['interaction']['quality_after_burst']), 'Completed viewport differs from original crop'
                if args.pages and source.metadata.page_count>1:
                    row['page_quality']=[]
                    for page in [source.metadata.page_count//2,source.metadata.page_count-1,0]:
                        assert s.bridge.stack_viewer.page(page)
                        spin(app,lambda p=page: s.bridge.original_source.page_index==p and not s.bridge.stack_viewer.busy,120)
                        s.settle()
                        assert s.ui.property('pageIndex')==page
                        row['page_quality'].extend(s.quality(f'page-{page}'))
                    for page in [source.metadata.page_count-1,source.metadata.page_count//2,0]:
                        assert s.bridge.stack_viewer.page(page)
                    spin(app,lambda: s.bridge.original_source.page_index==0 and not s.bridge.stack_viewer.busy,120)
                    s.settle()
                    assert s.ui.property('pageIndex')==0
                    row['latest_page_request']=True
                    assert all(q['exact'] for q in row['page_quality']), 'Completed TIFF viewport differs from original crop'
                row['sha_after']=digest(path)
                assert before==row['sha_after']
                row['unchanged']=True
                row['stages']={k:stats(v) for k,v in s.stages.items()}
                row['cache_bytes']=s.view._display_cache[5].sizeInBytes() if s.view._display_cache else 0
                row['decode_calls']=dict(s.calls)
                s.ui.setProperty('hasRoi',False)
                if file_number+1 < len(args.paths):
                    previous_pyramid = s.bridge.original_source.display_pyramid
                    s.set_zoom(4)
                    s.settle()
                else:
                    s.bridge.clearImage()
                    s.view.update()
                    s.settle()
                # A closed/invisible item's display cache clears on next paint (<=32MiB).
                gc.collect()
                row['rss_after_clear']=psutil.Process().memory_info().rss
                row['cache_after_clear']=s.view._display_cache[5].sizeInBytes() if s.view._display_cache else 0
                (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        report['paint_threads']=list(s.paint_threads)
        report['gui_timer_gap_ms']=stats([1000*(b-a) for a,b in pairwise(s.beats)])
        report['cpu_scene_sync_ms']=stats(s.syncs)
        report['cpu_render_submit_ms']=stats(s.renders)
        report['qml_warnings']=s.warnings
    except Exception as exc:
        report['error']=repr(exc)
        raise
    finally:
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        s.close()


if __name__=='__main__':
    main()
