"""Read-only RC checks with real local inputs; reports stay in ignored artifacts.

QTest interactions exercise Qt controls, not the Windows native file picker.
No model, source image, result pixels or local absolute paths enter the report.
"""
import argparse
import csv
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np
import psutil
from PySide6.QtCore import (
    Q_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPointF,
    QSettings,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from validate_stack_workbench import validate

from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import load_rois
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.ui import stack_controller
from sic_xrt_analyzer.ui.bridge import FileBridge


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def memory():
    info = psutil.Process().memory_info()
    return {'rss': info.rss, 'os_process_peak': getattr(info, 'peak_wset', None)}


class Session:
    def __init__(self, app, output, qml):
        self.app, self.output = app, output
        self.engine = QQmlApplicationEngine()
        self.bridge = FileBridge(parent=self.engine, settings=QSettings(str(output/'prefs.ini'), QSettings.IniFormat))
        self.engine.addImageProvider('tiff', self.bridge.provider)
        self.engine.rootContext().setContextProperty('fileBridge', self.bridge)
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(qml/'Main.qml')))
        assert len(self.engine.rootObjects()) == 1, self.warnings
        self.window = self.engine.rootObjects()[0]
        self.window.resize(1100, 700)
        QTest.qWait(40)
        self.state = self.item('uiState')
        self.panel = self.item('inspectorPanel')
        assert not self.state.property('hasImage')
        assert not self.bridge.research.state['points'] and not self.bridge.roi_manager.records
        self.transitions = []
        self.bridge.pipeline.changed.connect(lambda: self.transitions.append(self.bridge.analysis['state']))

    def item(self, name):
        value = self.window.findChild(QObject, name)
        if value is not None:
            return value
        pending = [self.window.contentItem()]
        for popup in self.window.findChildren(QObject):
            if popup.inherits('QQuickPopup') and popup.property('contentItem') is not None:
                pending.append(popup.property('contentItem'))
        while pending:
            value = pending.pop()
            if value.objectName() == name:
                return value
            pending.extend(value.childItems())
        raise AssertionError(name)

    def invoke(self, name, *args):
        assert QMetaObject.invokeMethod(self.window, name, *[Q_ARG('QVariant', a) for a in args]), name

    def wait(self, predicate, timeout=600):
        deadline = time.monotonic()+timeout
        while not predicate():
            assert time.monotonic() < deadline, self.bridge.analysis
            self.app.processEvents()
            # Release the Python GIL so Python QRunnable work can advance.
            # Keep the same polling interval; do not extend a failing deadline.
            time.sleep(.002)
        QTest.qWait(20)

    def click(self, name):
        node = self.item(name)
        assert node.property('visible') and node.property('enabled'), name
        position = node.mapToScene(QPointF(node.property('width')/2, node.property('height')/2))
        assert 0 <= position.x() < self.window.width() and 0 <= position.y() < self.window.height(), name
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, position.toPoint())
        QTest.qWait(30)

    def choose(self, context):
        self.click('contextSwitcher')
        self.click('contextChoice'+str(('image','analysis','result','viewer','roi').index(context)))
        assert self.panel.property('requestedContext') == context

    def open(self, path):
        self.invoke('selectImagePath', str(path))
        self.wait(lambda: not self.state.property('opening') and not self.bridge.stack_viewer.initial_loading)
        assert not self.state.property('loadError'), self.state.property('loadError')
        assert self.bridge.original_source.path == str(path.resolve())
        assert self.panel.property('requestedContext') == 'image'

    def point(self, x, y):
        viewer, frame = self.item('imageViewer'), self.item('imageFrame')
        scale = viewer.property('displayScale')
        return self.item('viewerMouseArea').mapToScene(QPointF(frame.property('x')+x*scale, frame.property('y')+y*scale)).toPoint()

    def drag(self, start, end):
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, self.point(*start))
        QTest.mouseMove(self.window, self.point(*end), 20)
        QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, self.point(*end))
        QTest.qWait(40)

    def save_capture(self, label):
        QTest.qWait(60)
        assert self.window.grabWindow().save(str(self.output/(label+'.png')))

    def close(self):
        self.window.setProperty('allowQuit', True)
        self.window.close()
        started = time.monotonic()
        self.bridge.waitForLoads()
        elapsed = time.monotonic()-started
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        assert not self.warnings, self.warnings
        return elapsed


def benchmark(session, path, client, full):
    controller = session.bridge.stack_viewer
    before = digest(path)
    metadata = OriginalImageSource(path).metadata
    baseline = time.perf_counter()
    measured = {'T0': 0, 'memory_open': memory()}
    heartbeat, rss = [], []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: (heartbeat.append(time.perf_counter()), rss.append(memory()['rss'])))
    actual_open = stack_controller.open_stack

    def now():
        return round(time.perf_counter()-baseline, 6)

    def opened(*a, **kw):
        stack = actual_open(*a, **kw)
        measured.setdefault('T1_metadata', now())
        return stack

    def first(frame, opening):
        if opening and 'T2_source_frame' not in measured:
            measured.update(T2_source_frame=now(), memory_first=memory())

    def ready():
        if controller.preload_state['ready'] and 'T2_source_frame' in measured and 'T4_full_stack' not in measured:
            measured.update(T4_full_stack=now(), memory_ready=memory())
            timer.stop()

    def swapped():
        if ('T2_source_frame' in measured and session.state.property('hasLoadedImage')
                and not session.item('initialLoadingOverlay').property('visible')):
            measured.setdefault('T3_viewer_visible', now())

    stack_controller.open_stack = opened
    controller.frameReady.connect(first)
    controller.changed.connect(ready)
    session.window.frameSwapped.connect(swapped)
    timer.start()
    try:
        if full:
            row = validate(session.app, session.window, session.bridge, path, client)
        else:
            session.open(path)
            session.wait(lambda: 'T3_viewer_visible' in measured)
            meta = session.bridge.original_source.metadata
            row = {'file': path.name, 'width': meta.width, 'height': meta.height,
                   'pages': meta.page_count, 'dtype': meta.dtype}
            session.bridge.clearImage()
            session.wait(lambda: controller._task is None and controller._reader.stack is None)
        assert 'T3_viewer_visible' in measured, measured
        assert before == digest(path)
        row.update(measured, width=metadata.width,height=metadata.height,dtype=metadata.dtype,
                   bit_depth=metadata.bit_depth,page_count=metadata.page_count,size_bytes=path.stat().st_size,
                   sha256_before=before, sha256_after=before,
                   sampled_peak_rss=max(rss, default=0), heartbeat_samples=len(heartbeat),
                   heartbeat_max_gap_ms=round(max(np.diff(heartbeat), default=0)*1000, 3),
                   memory_after=memory(), iterations=1)
        return row
    finally:
        timer.stop()
        stack_controller.open_stack = actual_open
        controller.frameReady.disconnect(first)
        controller.changed.disconnect(ready)
        session.window.frameSwapped.disconnect(swapped)


def real_model_flow(s, jpeg, model):
    b, result = s.bridge, {}
    before = digest(jpeg)
    b.research.loadModel(str(s.output/'missing-model'))
    s.wait(lambda: not b.research.state['loading'])
    assert b.research.state['error'] and not b.analysis['modelAvailable']
    result['invalid_model_recovery'] = 'PASS'
    b.research.loadModel(str(model))
    s.wait(lambda: not b.research.state['loading'])
    assert b.analysis['modelAvailable'], b.research.state['error']
    result['model'] = {'id': b.pipeline.adapter.model_id, 'hash': b.pipeline.adapter.model_version,
                       'device': b.pipeline.adapter.device}
    s.open(jpeg)
    print(json.dumps({'stage':'model-image-open','prepared':b.original_source.prepared is not None,
                      'pipeline_uses_display_source':b.pipeline.source is b.original_source}),flush=True)
    assert not s.state.property('stackFeaturesVisible')
    result['image'] = {'file': jpeg.name, 'width': b.original_source.metadata.width,
                       'height': b.original_source.metadata.height, 'dtype': b.original_source.metadata.dtype}
    s.click('toolbarPan'); s.click('toolbarZoom'); s.click('toolbarFit')
    s.click('imagePrepareAnalysis')
    assert s.state.property('canAnalyze')
    s.save_capture('analysis-ready-1100')
    started = time.monotonic()
    s.click('contextRunAnalysis')
    if b.analysis['state'] == 'RUNNING':
        s.save_capture('analysis-running-1100')
    s.wait(lambda: b.analysis['state'] != 'RUNNING')
    assert b.analysis['hasResult'], b.analysis
    assert s.panel.property('requestedContext') == 'result'
    result.update(full_seconds=round(time.monotonic()-started,3), counts=b.research.state['counts'],
                  total=b.research.state['total'], running_seen='RUNNING' in s.transitions)
    print(json.dumps({'stage':'real-full-completed',**result}),flush=True)
    original = b.pipeline.result
    assert b.research.exportResult(str(s.output))
    initial = json.loads((Path(b.research.export_path)/'result.json').read_text(encoding='utf8'))
    latencies = []
    for kind in ('ALL','BPD','TED','TSD'):
        start = time.perf_counter()
        s.click('resultFilter'+kind)
        research = b.research.state
        expected = research['total'] if kind == 'ALL' else research['counts'].get(kind,0)
        assert research['filteredTotal'] == expected
        assert len(s.item('analysisOverlay').property('points')) == expected
        if expected:
            s.click('nextCandidate')
            s.click('nextCandidate')
            s.click('previousCandidate')
            s.wait(lambda: bool(b.research.state['thumbnailSource']) or bool(b.research.state['thumbnailError']))
            assert not b.research.state['thumbnailError']
        latencies.append((time.perf_counter()-start)*1000)
        assert b.pipeline.result is original
        print(json.dumps({'stage':'real-filter','kind':kind,'count':expected}),flush=True)
    assert b.research.exportResult(str(s.output))
    export = Path(b.research.export_path)
    final = json.loads((export/'result.json').read_text(encoding='utf8'))
    assert initial == final
    with (export/'predictions.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert len(list(csv.DictReader(stream))) == result['total']
    result.update(export_integrity=True, filter_median_ms=round(statistics.median(latencies),3),
                  filter_max_ms=round(max(latencies),3))
    for width,height in ((1100,700),(1440,900),(1920,1080)):
        s.window.resize(width,height); QTest.qWait(50)
        for name in ('resultTotal','candidateList','analysisExportButton'):
            node = s.item(name)
            origin = node.mapToScene(QPointF())
            assert origin.x() >= 0 and origin.y()+node.property('height') <= height-28+1
        s.save_capture('real-result-'+str(width))
    s.window.resize(1100,700)
    s.wait(lambda: s.panel.x()+s.panel.width() <= s.window.width()+1)
    s.click('toolbarFit')
    s.choose('roi'); s.click('roiSpecifyArea'); s.drag((1000,1000),(2500,2500))
    region = b.pipeline.current_roi
    assert region and region.width > 1000 and region.height > 1000
    crop = b.original_source.read_region(region.x,region.y,region.width,region.height)
    assert crop.shape == (region.height,region.width,3)
    result['roi'] = {'x':region.x,'y':region.y,'width':region.width,'height':region.height,'shape':list(crop.shape)}
    del crop
    s.choose('analysis'); s.state.setProperty('analysisScope','ROI')
    s.click('contextRunAnalysis'); s.wait(lambda: b.analysis['state'] != 'RUNNING')
    assert b.analysis['hasResult'], b.analysis
    assert b.pipeline.result.roi == region
    assert all(region.x <= d.geometry.points[0][0] < region.x+region.width
               and region.y <= d.geometry.points[0][1] < region.y+region.height for d in b.pipeline.result.detections)
    result['roi_inference_count'] = len(b.pipeline.result.detections)
    print(json.dumps({'stage':'real-roi-completed', 'roi':result['roi'],
                      'count':result['roi_inference_count']}),flush=True)
    s.choose('analysis'); s.state.setProperty('analysisScope','FULL_IMAGE')
    s.click('contextRunAnalysis')
    if b.analysis['state'] == 'RUNNING':
        s.click('contextCancelAnalysis')
        s.wait(lambda: not b.pipeline._tasks)
        assert b.analysis['state'] == 'CANCELED' and not b.research.state['points']
        result['cancel'] = 'PASS'
    else:
        result['cancel'] = 'NOT OBSERVABLE'
    s.click('contextRunAnalysis'); s.wait(lambda: b.analysis['state'] != 'RUNNING')
    assert b.analysis['hasResult']
    result['rerun'] = 'PASS'
    print(json.dumps({'stage':'real-rerun-completed','cancel':result['cancel']}),flush=True)
    copy = s.output/'image-copy.jpg'
    b.imagej.saveImageCopy(b.localUrl(str(copy))); s.wait(lambda: not b.imagej.state['busy'])
    assert not b.imagej.state['error'], b.imagej.state['error']
    assert digest(copy) == before
    result.update(image_copy_exact=True, sha256_before=before, sha256_after=digest(jpeg))
    assert result['sha256_after'] == before
    return result


def stack_flow(s, path):
    b, row = s.bridge, {}
    before = digest(path)
    s.open(path)
    s.choose('analysis')
    row['run_enabled_for_uint16'] = s.state.property('canAnalyze')
    if row['run_enabled_for_uint16']:
        s.click('contextRunAnalysis')
        s.wait(lambda: b.analysis['state'] != 'RUNNING')
        row['uint16_analysis'] = {'state': b.analysis['state'],'error_code': b.analysis['errorCode']}
        assert b.analysis['errorCode'] == 'INVALID_INPUT'
    s.choose('viewer')
    slider = s.item('pageSlider')
    count = s.state.property('pageCount')
    def slider_point(index):
        x = slider.property('leftPadding')+6+index/(count-1)*(slider.property('availableWidth')-12)
        return slider.mapToScene(QPointF(x,slider.height()/2)).toPoint()
    s.wait(lambda: slider.property('visible') and slider.property('enabled'))
    QTest.mousePress(s.window,Qt.LeftButton,Qt.NoModifier,slider_point(0))
    for index in (9,29,count-1,count//2):
        QTest.mouseMove(s.window,slider_point(index),10)
    QTest.mouseRelease(s.window,Qt.LeftButton,Qt.NoModifier,slider_point(count//2))
    s.wait(lambda: not b.stack_viewer.busy and not b.stack_viewer.detail_busy)
    assert s.state.property('pageIndex') == count//2
    s.click('nextPageButton'); s.click('previousPageButton')
    s.wait(lambda: not b.stack_viewer.busy and not b.stack_viewer.detail_busy)
    assert s.state.property('pageIndex') == count//2
    row['ui_page_navigation'] = 'Slider drag / next / previous PASS (QTest)'
    b.requestPage(0)
    s.wait(lambda: not b.stack_viewer.busy and not b.stack_viewer.detail_busy)
    s.choose('roi')
    for tool, points in [('Rectangle',[(100,100),(400,400)]),('Polygon',[(500,100),(800,100),(650,400)]),
                         ('Freehand',[(900,100),(1100,250),(950,400)]),('Point',[(1200,200)])]:
        s.click('roiToolDropdown'); s.click('tool'+tool)
        if tool == 'Rectangle':
            s.drag(points[0],points[-1])
        elif tool == 'Freehand':
            QTest.mousePress(s.window, Qt.LeftButton, Qt.NoModifier, s.point(*points[0]))
            for point in points[1:]:
                QTest.mouseMove(s.window, s.point(*point), 20)
            QTest.mouseRelease(s.window, Qt.LeftButton, Qt.NoModifier, s.point(*points[-1]))
        else:
            for point in points:
                QTest.mouseClick(s.window, Qt.LeftButton, Qt.NoModifier, s.point(*point))
            if tool == 'Polygon':
                QTest.keyClick(s.window, Qt.Key_Return)
        QTest.qWait(30)
    assert len(b.roi_manager.records) == 4
    s.click('roiEditButton')
    assert s.state.property('roiEditMode')
    selected = b.roi_manager.records[-1]
    b.translateRoi(10,10)
    assert b.roi_manager.records[-1].paths != selected.paths
    zip_path = s.output/'roi-copy.zip'
    b.saveRoiCopy(b.localUrl(str(zip_path)))
    s.wait(lambda: b.roi_exporter.task is None and b.roi_exporter.pending is None)
    assert zip_path.exists() and not b.roi_manager.dirty
    imported, errors = load_rois([zip_path], b.original_source.metadata)
    assert not errors and len(imported) == 4
    quantization = []
    for loaded, original in zip(imported,b.roi_manager.records,strict=True):
        assert (loaded.name,loaded.kind,loaded.page_index,loaded.color) == (
            original.name,original.kind,original.page_index,original.color)
        if original.tool == 'Rectangle':
            # Existing ImageJ RECT writer stores integer enclosing bounds and
            # its reader adds a closing vertex; path order is not preserved.
            assert loaded.tool == 'Rectangle' and loaded.bbox == original.bbox
            points = np.asarray(original.paths[0])
            x,y,w,h = loaded.bbox
            delta = max(abs(points.min(axis=0)-[x,y]).max(),
                        abs(points.max(axis=0)-[x+w,y+h]).max())
            assert delta < 1
        else:
            assert len(loaded.paths) == len(original.paths) == 1
            expected = np.asarray(original.paths[0],dtype=np.float32).astype(np.float64)
            np.testing.assert_array_equal(loaded.paths[0],expected)
            delta = np.abs(np.asarray(loaded.paths[0])-original.paths[0]).max()
        quantization.append({'tool':original.tool,'max_source_delta_pixels':float(delta)})
    row['roi_export_precision'] = quantization
    s.save_capture('real-roi-1100')
    for index in (0,9,29,s.state.property('pageCount')-1,s.state.property('pageCount')//2):
        b.requestPage(index)
    s.wait(lambda: not b.stack_viewer.busy and not b.stack_viewer.detail_busy)
    assert s.state.property('pageIndex') == s.state.property('pageCount')//2
    assert not s.state.property('hasRoi')
    row.update(roi_geometry_roundtrip=True, rapid_last_page_wins=True,
               page_tags=[r.page_index for r in b.roi_manager.records])
    for end in ('escape','pan','page'):
        s.click('roiToolDropdown'); s.click('toolPolygon')
        QTest.mouseClick(s.window, Qt.LeftButton, Qt.NoModifier, s.point(100,100))
        assert s.item('imageViewer').property('toolPoints').toVariant()
        if end == 'escape':
            QTest.keyClick(s.window, Qt.Key_Escape)
        elif end == 'pan':
            QTest.keyClick(s.window, Qt.Key_H)
        else:
            b.requestPage(1)
            s.wait(lambda: not b.stack_viewer.busy and not b.stack_viewer.detail_busy)
        assert not s.item('imageViewer').property('toolPoints').toVariant()
        assert len(b.roi_manager.records) == 4
    row['unfinished_polygon'] = 'Esc/Pan/page PASS (QTest, not human mouse)'
    b.workbench.execute('macro','print("RC current page");','',False)
    s.wait(lambda: not b.workbench.busy and not s.state.property('opening')
           and not b.stack_viewer.initial_loading)
    assert not b.workbench.error
    row['macro'] = 'PASS'
    s.click('toolbarPan')
    # Saving makes the existing discard guard unnecessary on the next Open.
    assert not b.roi_manager.dirty
    row['source_sha256_before'] = before
    row['source_sha256_after'] = digest(path)
    assert row['source_sha256_after'] == before
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--file',help='Optional single filename in folder')
    parser.add_argument('--jpeg',type=Path)
    parser.add_argument('--model',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--qml-root',type=Path,default=Path('src/sic_xrt_analyzer/ui'))
    parser.add_argument('--benchmark-only',action='store_true')
    parser.add_argument('--session-only',action='store_true',help='Run real model/ROI flow without repeating TIFF benchmarks')
    parser.add_argument('--fiji-home',type=Path)
    parser.add_argument('--shutdown-case',choices=('idle','loading','analysis'))
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.is_relative_to(args.folder.resolve()) or (args.model and args.output.is_relative_to(args.model.resolve())):
        parser.error('Output must be separate from read-only source and model directories')
    args.output.mkdir(parents=True,exist_ok=True)
    app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
    s = Session(app,args.output,args.qml_root.resolve())
    if args.shutdown_case:
        row = {'case':args.shutdown_case,'platform':app.platformName()}
        if args.shutdown_case == 'loading':
            path = args.folder/args.file if args.file else next(args.folder.glob('*.tif'))
            s.invoke('selectImagePath',str(path))
            s.wait(lambda: s.bridge.stack_viewer.frame is not None)
            assert s.bridge.stack_viewer.initial_loading
            group = s.bridge.stack_viewer._reader.stack.display_group
            directories = [Path(p.directory.name) for p in group.pages.values()]
            row['preparing_observed'] = True
            s.save_capture('real-stack-preparing-1100')
        elif args.shutdown_case == 'analysis':
            assert args.model and args.jpeg
            s.bridge.research.loadModel(str(args.model))
            s.wait(lambda: not s.bridge.research.state['loading'])
            s.open(args.jpeg); s.click('imagePrepareAnalysis'); s.click('contextRunAnalysis')
            assert s.bridge.analysis['state'] == 'RUNNING'
            row['running_observed'] = True
        row['memory_before'] = memory()
        row['shutdown_seconds'] = round(s.close(),3)
        row['memory_after'] = memory()
        if args.shutdown_case == 'loading':
            assert group.closed and all(not p.exists() for p in directories)
            row['known_temp_directories_removed'] = True
        row['qml_warnings'] = s.warnings
        (args.output/'report.json').write_text(json.dumps(row,indent=2),encoding='utf8')
        print(json.dumps(row),flush=True)
        return
    client = ImageJClient() if args.fiji_home else None
    if client:
        client.configure(False,str(args.fiji_home.resolve()))
    screen = app.primaryScreen()
    report = {'platform':app.platformName(),'dpr':s.window.devicePixelRatio(),'files':[],'startup_empty':True,
              'screen': {'width':screen.size().width(),'height':screen.size().height(),
                         'logical_dpi':screen.logicalDotsPerInch()}}
    try:
        paths = [args.folder/args.file] if args.file else sorted(p for p in args.folder.iterdir() if p.suffix.lower() in ('.tif','.tiff'))
        assert paths
        for path in ([] if args.session_only else paths):
            report['files'].append(benchmark(s,path,client,not args.benchmark_only))
            print(json.dumps(report['files'][-1],ensure_ascii=False),flush=True)
        if args.jpeg and args.model:
            report['model_flow'] = real_model_flow(s,args.jpeg,args.model)
            report['stack_flow'] = stack_flow(s,paths[-1])
            s.open(args.jpeg)
            assert not s.bridge.research.state['points'] and not s.bridge.roi_manager.records
            assert not s.state.property('stackFeaturesVisible')
            report['file_switch_clears_state'] = True
    finally:
        if client:
            client.close()
        report['shutdown_seconds'] = round(s.close(),3)
        report['qml_warnings'] = s.warnings
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    restarted = Session(app,args.output/'restart',args.qml_root.resolve())
    report['restart_empty'] = True
    report['restart_shutdown_seconds'] = round(restarted.close(),3)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__ == '__main__':
    main()
