"""Read-only real-stack QML/preparation/zoom/Fiji ROI checks; no source image exports."""
import argparse
import ctypes
import json
import os
import statistics
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import ImportedRoi
from sic_xrt_analyzer.imaging.tiff_stack import render_samples
from sic_xrt_analyzer.ui.bridge import FileBridge
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def memory():
    """Working set includes resident file mappings; it is not heap or cache size."""
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [
            (name,ctypes.c_size_t) for name in ('peak','current','pp','p','np','n','pf','peakpf')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'working_set_bytes':counters.current,'process_peak_working_set_bytes':counters.peak}


def wait(app, controller, predicate, timeout=600):
    started = time.monotonic()
    while not predicate():
        app.processEvents()
        if controller.error or controller.preload_error:
            raise RuntimeError(controller.error or controller.preload_error)
        if time.monotonic()-started > timeout:
            raise TimeoutError('Stack preparation did not finish')
        time.sleep(.002)
    app.processEvents()


def validate(app, window, bridge, path, client):
    before = path.stat()
    controller = bridge.stack_viewer
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda:ticks.append(time.monotonic()))
    timer.start()
    started = time.monotonic()
    assert QMetaObject.invokeMethod(window,'selectImagePath',Q_ARG('QVariant',str(path)))
    wait(app,controller,lambda:not controller.initial_loading and controller.frame is not None)
    elapsed = time.monotonic()-started
    timer.stop()
    assert len(ticks) > 1, 'No Qt heartbeat while reading'
    stack = controller._reader.stack
    group = stack.display_group
    directories = [Path(p.directory.name) for p in group.pages.values()]
    assert controller.preload_state['ready']
    assert window.findChild(QObject,'uiState').property('stackFeaturesVisible')
    row = {'file':path.name,'prepare_seconds':round(elapsed,3),
           'heartbeat_max_gap_ms':round(max(np.diff(ticks))*1000,3),
           'memory_ready':memory(),'browse_cache_bytes':stack.browse.bytes,
           'raw_cache_bytes':stack.cache_bytes,'display_disk_bytes':group.cache_bytes,'pages':[]}
    view = PreparedView()
    view.bridge = bridge
    view.setWidth(800)
    view.setHeight(600)
    count = stack.page_count
    # Slider scrubbing requests must publish immediately on each GUI event.
    bridge.beginScrub()
    timings = []
    for index in list(range(count))+list(range(count-1,-1,-1)):
        start = time.perf_counter()
        assert bridge.requestPage(index)
        assert controller.frame.source.page_index == index
        timings.append((time.perf_counter()-start)*1000)
    bridge.endScrub()
    wait(app,controller,lambda:not controller.busy and not controller.detail_busy)
    row['scrub_requests'] = len(timings)
    row['scrub_median_ms'] = round(statistics.median(timings),3)
    row['scrub_max_ms'] = round(max(timings),3)
    for index in sorted({0,count//2,count-1}):
        assert bridge.requestPage(index)
        wait(app,controller,lambda:not controller.busy and not controller.detail_busy)
        frame = controller.frame
        with tifffile.TiffFile(path) as tif:
            if len(tif.pages) == count:
                oracle = tif.pages[index].asarray(maxworkers=1)
            else:
                mapped = tifffile.memmap(path,series=0,mode='r')
                try:
                    oracle = mapped.reshape(count,frame.source.metadata.height,frame.source.metadata.width)[index].copy()
                finally:
                    mapped._mmap.close()
        np.testing.assert_array_equal(frame.pixels,oracle)
        height,width = oracle.shape
        original_image = frame.preview.image
        assert bridge.setDisplayRange(0,1000)
        wait(app,controller,lambda:not controller.busy)
        assert controller.frame.preview.image != original_image
        np.testing.assert_array_equal(controller.frame.pixels,oracle)
        bridge.resetDisplayRange()
        wait(app,controller,lambda:not controller.busy)
        frame = controller.frame
        painting = []
        # Native zoom and pan use prepared grids. Check displayed values exactly.
        for x,y in [(width//2,height//2),(width//3,height//3)]:
            for scale in (min(800/width,600/height),1,2,4):
                view.viewTransform = [400-x*scale,300-y*scale,scale]
                image = QImage(800,600,QImage.Format_RGB32)
                image.fill(0)
                painter = QPainter(image)
                start = time.perf_counter()
                view.paint(painter)
                painting.append((time.perf_counter()-start)*1000)
                painter.end()
                if scale >= 1:
                    expected = render_samples(oracle[y:y+1,x:x+1],frame.source,frame.low,frame.high,
                                              getattr(frame.source.display_pyramid,'invert',False)).image.pixelColor(0,0)
                    assert image.pixelColor(400,300) == expected
        if client is not None:
            roi = ImportedRoi('validation','ROI', 'polygon',
                              (((10,10),(42,10),(42,42),(10,42)),),'#45c3cf',(10,10,32,32),index,'Rectangle')
            client.session += 1
            result = client.run(frame,modern='net.imagej.plugins.commands.assign.MultiplyDataValuesBy',
                                record=roi,options='{"value":0.5,"preview":false,"allPlanes":false}')
            processed = tifffile.imread(result['path'])
            expected = oracle.astype(np.uint16,copy=True)
            # ImgLib2 UnsignedShortType.setReal rounds half up, rather than truncating.
            expected[10:42,10:42] = (expected[10:42,10:42].astype(np.uint32)+1)//2
            np.testing.assert_array_equal(processed,expected)
        row['pages'].append({'page':index+1,'raw_equal':True,'contrast':True,'zoom_pan_exact':True,
                             'paint_max_ms':round(max(painting),3),'fiji_roi':client is not None})
        del oracle
    # A full reopen must release all old mappings and rebuild safely.
    started = time.monotonic()
    assert QMetaObject.invokeMethod(window,'selectImagePath',Q_ARG('QVariant',str(path)))
    wait(app,controller,lambda:not controller.initial_loading and controller.frame is not None)
    assert group.closed and all(not p.exists() for p in directories)
    row['reopen_seconds'] = round(time.monotonic()-started,3)
    new_group = controller._reader.stack.display_group
    new_dirs = [Path(p.directory.name) for p in new_group.pages.values()]
    bridge.clearImage()
    wait(app,controller,lambda:controller._task is None and controller._reader.stack is None)
    assert new_group.closed and all(not p.exists() for p in new_dirs)
    after = path.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    row.update(status='PASS',source_stat_unchanged=True,cache_cleanup=True,memory_after_close=memory())
    view.deleteLater()
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--fiji-home',type=Path)
    args = parser.parse_args()
    app = QGuiApplication([])
    QQuickStyle.setStyle('Basic')
    client = ImageJClient() if args.fiji_home else None
    if client:
        client.configure(False,str(args.fiji_home.resolve()))
    with TemporaryDirectory(prefix='sic-xrt-validation-') as directory:
        engine = QQmlApplicationEngine()
        bridge = FileBridge(parent=engine,settings=QSettings(str(Path(directory)/'prefs.ini'),QSettings.IniFormat))
        engine.addImageProvider('tiff',bridge.provider)
        engine.rootContext().setContextProperty('fileBridge',bridge)
        warnings = []
        engine.warnings.connect(lambda items:warnings.extend(x.toString() for x in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
        window = engine.rootObjects()[0]
        try:
            paths = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in ('.tif','.tiff'))
            if not paths:
                raise ValueError('No TIFF files found')
            for path in paths:
                print(json.dumps(validate(app,window,bridge,path,client),ensure_ascii=False),flush=True)
            assert not warnings,'\n'.join(warnings)
        finally:
            window.setProperty('allowQuit',True)
            window.close()
            bridge.waitForLoads()
            if client:
                client.close()
            engine.deleteLater()
            app.processEvents()


if __name__ == '__main__':
    main()
