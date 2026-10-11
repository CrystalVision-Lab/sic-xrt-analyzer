"""Decoder-driven TIFF/JPEG context routing without changing source semantics."""
import hashlib

import numpy as np
import pytest
import tifffile
from PIL import Image
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_ui_analysis_contract import invoke

pytest_plugins = ('test_toolbar',)


@pytest.mark.parametrize('suffix,format_,pages', [
    ('.tif', 'TIFF', 1), ('.TIFF', 'TIFF', 3), ('.tiff', 'TIFF', 1),
    ('.JPG', 'JPEG', 1), ('.jpeg', 'JPEG', 1),
    ('.jpg', 'TIFF', 3), ('.tif', 'JPEG', 1),
])
def test_actual_format_routes_after_successful_open(workbench, suffix, format_, pages):
    w = workbench
    path = w.path.parent / ('routing' + suffix)
    if format_ == 'TIFF':
        shape = (300, 400) if pages == 1 else (pages, 300, 400)
        tifffile.imwrite(path, np.arange(np.prod(shape), dtype=np.uint16).reshape(shape), photometric='minisblack')
    else:
        Image.fromarray(np.full((300, 400, 3), 120, np.uint8)).save(path, format='JPEG')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    choose(w, 'result')
    w.open(path)
    QTest.qWait(35)
    assert w.state.property('workspaceIndex') == 0
    assert w.state.property('imageFormat') == format_ and w.state.property('pageCount') == pages
    if format_ == 'TIFF':
        assert w.panel.property('requestedContext') == 'viewer'
        assert w.panel.property('lastReason') == 'OPEN_TIFF' and not w.panel.property('visible')
        choose(w, 'viewer')
        assert w.item('displayLowSlider').property('visible')
        assert w.item('pageSlider').property('visible') == (pages > 1)
        assert w.state.property('stackFeaturesVisible') == (pages > 1)
    else:
        assert w.panel.property('requestedContext') == 'image'
        assert w.panel.property('lastReason') == 'OPEN_IMAGE' and not w.panel.property('visible')
    assert not w.state.property('analysisRunning') and not w.bridge.analysis['hasResult']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_page_and_failed_open_do_not_override_manual_context(workbench):
    w = workbench
    assert w.panel.property('requestedContext') == 'viewer' and not w.panel.property('visible')
    choose(w, 'result')
    w.click('closeContextPanel')
    w.bridge.requestPage(1)
    spin(w.app, lambda: w.state.property('pageIndex') == 1 and not w.state.property('pageLoading'))
    assert w.panel.property('requestedContext') == 'result' and not w.panel.property('visible')
    source = w.bridge.original_source
    broken = w.path.parent / 'broken.jpg'
    broken.write_bytes(b'not an image')
    invoke(w.window, 'selectImagePath', str(broken))
    spin(w.app, lambda: not w.state.property('opening'))
    assert w.state.property('loadError') and w.bridge.original_source is source
    assert w.panel.property('requestedContext') == 'result' and not w.panel.property('visible')
