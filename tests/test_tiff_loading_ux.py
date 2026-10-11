"""Real first-frame readiness, conservative request gates and data integrity."""
import hashlib
from threading import Event, Timer

import numpy as np
import pytest
import tifffile
from PIL import Image
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from roifile import ImagejRoi
from test_analysis_pipeline import TestAdapter, spin
from test_context_panel import choose
from test_roi_ux import draw, scene
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack

pytest_plugins = ('test_toolbar',)


@pytest.fixture
def load_case(workbench, monkeypatch):
    w = workbench
    path = w.path.parent/'progressive-frames.tif'
    raw = (np.arange(8*320*320, dtype=np.uint32).reshape(8, 320, 320) % 40000 + 1000).astype(np.uint16)
    tifffile.imwrite(path, raw, imagej=True, metadata={'axes': 'TYX', 'min': 1000, 'max': 60000})
    first, tail, first_entered, tail_entered = Event(), Event(), Event(), Event()
    actual = TiffStack.read_page

    class Case:
        tail_index = 1
        fail = False

        def start(self):
            invoke(w.window, 'selectImagePath', str(path))
            spin(w.app, first_entered.is_set)

        def first_frame(self):
            first.set()
            spin(w.app, tail_entered.is_set)
            QTest.qWait(20)

        def finish(self):
            first.set()
            tail.set()
            spin(w.app, lambda: w.bridge.stack_viewer.preload_state['ready'] and not w.bridge.stack_viewer.initial_loading)

    case = Case()
    case.w, case.path, case.raw = w, path, raw
    case.first, case.tail = first, tail

    def controlled(stack, index):
        if stack.path == str(path.resolve()):
            if index == 0:
                first_entered.set()
                assert first.wait(15)
            if index == case.tail_index:
                tail_entered.set()
                assert tail.wait(15)
                if case.fail:
                    raise ValueError('synthetic private decode diagnostic /page-path')
        return actual(stack, index)

    monkeypatch.setattr(TiffStack, 'read_page', controlled)
    yield case
    first.set()
    tail.set()


def phase(w):
    return w.item('tiffLoadState').property('phase')


def test_empty_opening_first_frame_and_ready_with_live_event_loop(load_case):
    c, w = load_case, load_case.w
    invoke(w.window, 'closeImage')
    assert phase(w) == 'EMPTY'
    c.start()
    assert phase(w) == 'OPENING' and w.state.property('loading')
    assert not w.item('viewerMouseArea').property('enabled')
    ticks = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: ticks.append(1))
    heartbeat.start(5)
    QTest.qWait(170)
    heartbeat.stop()
    assert ticks and w.item('initialLoadingOverlay').property('visible')
    assert '파일 여는 중' in w.item('initialLoadingText').property('text')
    c.first_frame()
    assert phase(w) == 'FIRST_FRAME_READY'
    assert w.state.property('hasLoadedImage') and not w.state.property('loading')
    assert w.item('viewerMouseArea').property('enabled')
    assert not w.item('initialLoadingOverlay').property('visible')
    assert not w.window.grabWindow().isNull()  # Real render while the tail worker is held.
    assert w.bridge.stack_viewer.initial_loading  # Original full-browse gate remains.
    assert not w.item('pageSlider').property('enabled')
    c.finish()
    assert phase(w) == 'READY' and w.item('pageSlider').property('enabled')


@pytest.mark.parametrize('context', ['analysis', 'roi'])
def test_first_frame_pan_zoom_fit_pixel_roi_and_original_analysis(load_case, context):
    c, w = load_case, load_case.w
    analysis_gate = Event()
    adapter = TestAdapter(gate=analysis_gate)
    w.bridge.pipeline.adapter = adapter
    try:
        c.start()
        c.first_frame()
        choose(w, context)
        invoke(w.item('zoomInAction'), 'trigger')
        viewer = w.item('imageViewer')
        start, end = scene(w, 60, 70), scene(w, 80, 90)
        QTest.mousePress(w.window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(w.window, end, 10)
        QTest.mouseRelease(w.window, Qt.LeftButton, Qt.NoModifier, end)
        assert abs(viewer.property('panX')) > 0 and not w.state.property('fitMode')
        invoke(w.item('fitAction'), 'trigger')
        assert w.state.property('fitMode') and viewer.property('panX') == 0
        assert w.bridge.pixelValue(40, 50) == str(c.raw[0, 50, 40])
        invoke(w.item('roiAction'), 'trigger')
        draw(w, start=(40, 50), end=(140, 150))
        assert w.state.property('hasRoi') and w.state.property('roiX') == pytest.approx(40, abs=1)
        w.state.setProperty('analysisScope', 'ROI')
        assert w.state.property('canAnalyze') and w.bridge.pipeline.source is w.bridge.original_source
        invoke(w.item('runAction'), 'trigger')
        spin(w.app, adapter.entered.is_set)
        assert adapter.image.dtype == np.uint16
        region = adapter.request.roi
        np.testing.assert_array_equal(adapter.image, c.raw[0, region.y:region.y+region.height, region.x:region.x+region.width])
        # Even programmatic rejected navigation must not invalidate an analysis.
        analysis_id = adapter.request.analysis_id
        assert not w.bridge.requestPage(7)
        QTest.keyClick(w.window, Qt.Key_End)
        assert w.bridge.analysis['state'] == 'RUNNING'
        assert w.bridge.pipeline._active.request.analysis_id == analysis_id
        assert w.state.property('pageIndex') == 0
    finally:
        analysis_gate.set()


def test_stack_progress_labels_context_and_original_record_gates(load_case):
    c, w = load_case, load_case.w
    c.tail_index = 4
    c.start()
    c.first_frame()
    choose(w, 'viewer')
    assert phase(w) == 'STACK_PREPARING'
    assert '현재 페이지 1 / 8' == w.item('currentPageLabel').property('text')
    assert '4 / 8 페이지 준비' in w.item('preloadStatus').property('text')
    assert '전체 페이지 준비 후' in w.item('navigationReadyReason').property('text')
    for name in ('nextPageButton', 'pageSlider', 'displayLowSlider', 'importRoisAction', 'toolRectangleAction', 'advancedMacroAction', 'imagejRunButton'):
        assert not w.item(name).property('enabled'), name
    assert w.item('roiAction').property('enabled')
    c.finish()
    assert w.panel.property('requestedContext') == 'viewer'
    assert w.item('toolRectangleAction').property('enabled')


@pytest.mark.parametrize('suffix', ['jpg', 'tif'])
def test_single_images_have_no_stack_progress_or_lingering_indicator(workbench, suffix):
    w = workbench
    pixels = np.full((64, 96, 3), 120, np.uint8)
    path = w.path.parent/('single.'+suffix)
    if suffix == 'jpg':
        Image.fromarray(pixels).save(path)
    else:
        tifffile.imwrite(path, pixels, photometric='rgb')
    w.open(path)
    assert phase(w) == 'READY'
    assert w.item('tiffLoadState').property('stackLabel') == ''
    assert not w.item('preloadStatus').property('visible')
    assert not w.item('initialLoadingOverlay').property('visible')


def test_partial_prepare_error_retains_frame_and_can_retry(load_case):
    c, w = load_case, load_case.w
    c.fail = True
    c.start()
    c.first_frame()
    first_frame = w.bridge.stack_viewer.frame
    c.tail.set()
    spin(w.app, lambda: bool(w.bridge.stack_viewer.preload_error))
    assert phase(w) == 'ERROR' and w.bridge.stack_viewer.frame is first_frame
    assert w.state.property('canNavigateImage') and not w.item('pageSlider').property('enabled')
    assert 'synthetic' not in w.item('loadingStatus').property('text')
    assert 'synthetic private' in w.item('tiffLoadState').property('errorDetails')
    w.click('loadingErrorDetails')
    assert w.item('loadingErrorDialog').property('visible')
    w.item('loadingErrorDialog').close()
    c.fail = False
    w.click('retryPreparationNotice')
    spin(w.app, lambda: phase(w) == 'READY')
    assert w.bridge.stack_viewer.preload_state['ready']


@pytest.mark.parametrize('keep_previous', [True, False])
def test_open_failure_preserves_previous_pixels_and_recovers(workbench, keep_previous):
    w = workbench
    if not keep_previous:
        invoke(w.window, 'closeImage')
    old = w.bridge.stack_viewer.frame
    broken = w.path.parent/'corrupt.tif'
    broken.write_bytes(b'II*\x00broken')
    invoke(w.window, 'selectImagePath', str(broken))
    spin(w.app, lambda: phase(w) == 'ERROR')
    assert not w.state.property('loading') and w.bridge.stack_viewer.frame is old
    assert w.item('viewerMouseArea').property('enabled') == keep_previous
    assert w.item('initialLoadingOverlay').property('visible') != keep_previous
    assert 'broken' not in w.item('initialLoadingText').property('text')
    w.open(w.path)
    assert phase(w) == 'READY'
    assert w.item('tiffLoadState').property('errorDetails') == ''


@pytest.mark.parametrize('stage', ['opening', 'preparing'])
def test_new_file_replaces_old_generation_without_old_completion(load_case, stage):
    c, w = load_case, load_case.w
    c.start()
    if stage == 'preparing':
        c.first_frame()
    other = w.path.parent/'replacement.tif'
    tifffile.imwrite(other, np.full((80, 100), 51000, np.uint16))
    opened = []
    w.bridge.imageOpened.connect(lambda result: opened.append(result.get('path')))
    invoke(w.window, 'selectImagePath', str(other))
    assert phase(w) == 'OPENING'
    assert w.item('tiffLoadState').property('openingName') == 'replacement.tif'
    assert not w.state.property('canAnalyze')
    c.first.set()
    c.tail.set()
    spin(w.app, lambda: w.state.property('filePath') == str(other.resolve()) and phase(w) == 'READY')
    assert opened == [str(other.resolve())]
    assert w.bridge.pixelValue(20, 30) == '51000'
    assert w.state.property('pageCount') == 1


def test_page_order_range_hashes_and_roi_page_semantics(load_case):
    c, w = load_case, load_case.w
    before = hashlib.sha256(c.path.read_bytes()).hexdigest()
    c.start()
    c.finish()
    assert (w.state.property('imageWidth'), w.state.property('imageHeight'), w.state.property('bitDepth'), w.state.property('pageCount')) == (320, 320, 16, 8)
    assert w.bridge.setDisplayRange(1300, 45000)
    spin(w.app, lambda: not w.bridge.stack_viewer.busy)
    w.bridge.workbench.gesture('Rectangle', [[10, 20], [50, 60]])
    page_record = w.bridge.roi_manager.records[0]
    global_path = w.path.parent/'global.roi'
    ImagejRoi.frompoints(np.array([[30, 40], [60, 80], [90, 50]], dtype=np.float32)).tofile(global_path)
    assert w.bridge.importRois([w.bridge.localUrl(str(global_path))])
    spin(w.app, lambda: not w.bridge.roiState['busy'])
    w.state.setProperty('hasRoi', True)
    for index in (1, 4, 7, 0):
        assert w.bridge.requestPage(index)
        spin(w.app, lambda index=index: w.state.property('pageIndex') == index and w.bridge.stackState['rawReady'] and not w.bridge.stack_viewer.busy and not w.bridge.stack_viewer.detail_busy)
        frame = w.bridge.stack_viewer.frame
        assert frame.pixels.dtype == np.uint16
        np.testing.assert_array_equal(frame.pixels, c.raw[index])
        assert (frame.low, frame.high) == (1300, 45000)
        assert not w.state.property('hasRoi')
        records = w.bridge.roiState['items']
        assert next(r for r in records if r['id'] == page_record.id)['active'] == (index == 0)
        assert any(r['page'] == 0 and r['active'] for r in records)
    assert hashlib.sha256(c.path.read_bytes()).hexdigest() == before
    stack = w.bridge.stack_viewer._reader.stack
    assert stack.cache_bytes <= stack.max_cache_bytes and stack.display_bytes <= stack.max_display_bytes
    assert stack.browse.bytes <= stack.browse.max_bytes


@pytest.mark.parametrize('size', [(1100, 700), (1440, 900)])
def test_progressive_layout_keeps_viewer_and_status_in_bounds(load_case, size):
    c, w = load_case, load_case.w
    c.start()
    c.first_frame()
    w.window.resize(*size)
    QTest.qWait(40)
    choose(w, 'viewer')
    for name in ('viewerHeader', 'loadingStatus', 'pageSlider', 'currentPageLabel', 'preloadStatus', 'cancelStackPreparation'):
        item = w.item(name)
        origin = item.mapToScene(QPointF())
        assert origin.x() >= 0 and origin.y() >= 0
        assert origin.x()+item.property('width') <= size[0]+1
        assert origin.y()+item.property('height') <= size[1]+1
    assert not w.item('initialLoadingOverlay').property('visible')


def test_shutdown_cancels_active_tiff_worker(load_case):
    c, w = load_case, load_case.w
    c.start()
    release = Timer(.05, c.first.set)
    release.start()
    try:
        w.window.setProperty('allowQuit', True)
        w.window.close()
        w.bridge.waitForLoads()
        controller = w.bridge.stack_viewer
        assert controller._pool.activeThreadCount() == 0 and controller._reader.stack is None
        assert controller.frame is None
    finally:
        release.join()
