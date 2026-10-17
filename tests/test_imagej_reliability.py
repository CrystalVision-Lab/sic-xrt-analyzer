"""#159/#180: whole-stack edits persist, per-run results, preconditions and worker isolation."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QPointF, QRect, QSizeF
from PySide6.QtGui import QWindow
from PySide6.QtQuick import QQuickItem, QQuickWindow

from sic_xrt_analyzer.imaging import imagej_runtime
from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import ImportedRoi
from sic_xrt_analyzer.imaging.imagej_runtime import (
    java_executable,
    java_major,
    runtime_directory,
)
from sic_xrt_analyzer.imaging.imagej_service import PREFIX, WINDOW_PREFIX
from sic_xrt_analyzer.ui.native_plugin_window import NativePluginWindow


def require_runtime():
    pytest.importorskip('jpype')
    if not (runtime_directory() / 'ij-1.54p.jar').is_file():
        pytest.skip('Run tools/setup_imagej.py')


class RecordingClient(ImageJClient):
    """Keeps every worker stdout line to prove only protocol lines use it."""
    def __init__(self):
        super().__init__()
        self.lines = []

    def consume(self, process, responses):
        stream, lines = process.stdout, self.lines

        class Tee:
            def __iter__(self):
                for line in stream:
                    lines.append(line)
                    yield line
        process.stdout = Tee()
        try:
            super().consume(process, responses)
        finally:
            process.stdout = stream


@pytest.fixture(scope='module')
def engine():
    require_runtime()
    client = RecordingClient()
    yield client
    client.close()


def pages():
    y, x = np.mgrid[:40, :48]
    stack = np.stack([(x * 20 + y * 5 + 300 * (i + 1)) for i in range(3)]).astype(np.uint16)
    for i, value in enumerate((1000, 10000, 60000)):
        stack[i, 20, 24] = value
    return stack


def read_pages(path):
    data = tifffile.imread(path)
    return data if data.ndim == 3 else data[None]


@pytest.mark.parametrize('kind,content,options', [
    ('command', 'Gaussian Blur...', 'sigma=1 stack'),
    ('command', 'Invert', 'stack'),
    ('command', 'Subtract Background...', 'rolling=5 stack'),
    ('macro', 'run("Gaussian Blur...", "sigma=1 stack");', ''),
])
def test_whole_stack_pixel_changes_are_saved(engine, tmp_path, kind, content, options):
    raw = pages()
    path = tmp_path / 'stack.tif'
    tifffile.imwrite(path, raw, photometric='minisblack')
    before = path.read_bytes()
    stack = open_stack(path)
    try:
        result = engine.run(stack.frame(1), **{kind: content}, options=options, whole_stack=True)
        saved = read_pages(result['path'])
        assert result['pages'] == 3 and saved.shape == raw.shape
        reread = open_stack(result['path'])
        try:
            np.testing.assert_array_equal(reread.frame(2).source.read_full(), saved[2])
        finally:
            reread.close()
        for index in range(3):
            assert not np.array_equal(saved[index], raw[index])
            # Oracle: the same ImageJ operation on an in-memory single page.
            page_options = options.replace('stack', '').strip()
            expected = engine.run(stack.frame(index), **{kind: content.replace(' stack', '')}, options=page_options)
            np.testing.assert_array_equal(saved[index], tifffile.imread(expected['path']))
    finally:
        stack.close()
    assert path.read_bytes() == before


def test_over_budget_virtual_stack_refuses_pixel_changes(tmp_path, monkeypatch):
    require_runtime()
    monkeypatch.setenv('SIC_XRT_IMAGEJ_STACK_BUDGET', '1')
    raw = pages()
    path = tmp_path / 'large.tif'
    tifffile.imwrite(path, raw, photometric='minisblack')
    client, stack = ImageJClient(), open_stack(path)
    try:
        for args in ({'command': 'Gaussian Blur...', 'options': 'sigma=1 stack'},
                     {'macro': 'run("Invert", "stack");'}):
            with pytest.raises(RuntimeError, match='보존할 수 없습니다'):
                client.run(stack.frame(0), whole_stack=True, **args)
        projection = client.run(stack.frame(0), command='Z Project...', options='projection=[Max Intensity]',
                                whole_stack=True)
        np.testing.assert_array_equal(tifffile.imread(projection['path']), raw.max(axis=0))
        # A cached virtual stack is never reused for a page edit (writes would be lost).
        page = client.run(stack.frame(2), command='Add...', options='value=7')
        np.testing.assert_array_equal(tifffile.imread(page['path']), raw[2] + 7)
    finally:
        stack.close()
        client.close()


def test_results_reset_per_run_and_table_stays_off_protocol(engine, tmp_path):
    path = tmp_path / 'measure.tif'
    tifffile.imwrite(path, np.arange(64, dtype=np.uint8).reshape(8, 8))
    stack = open_stack(path)
    try:
        for _ in range(3):
            result = engine.run(stack.frame(0), command='Measure')
            assert len(result['rows']) == 1
        assert engine.run(stack.frame(0), command='Add...', options='value=1')['rows'] == []
    finally:
        stack.close()
    assert engine.lines and all(line.startswith((PREFIX, WINDOW_PREFIX)) for line in engine.lines)


@pytest.mark.parametrize('command,message', [
    ('Crop', '면적 ROI'), ('Clear Outside', '면적 ROI'), ('Fill', '선택 ROI'), ('Draw', '선택 ROI'),
    ('Plot Profile', '직선'), ('Erode', '이진'), ('Skeletonize', '이진'), ('Watershed', '이진'),
])
def test_commands_explain_missing_roi_or_binary_input(engine, tmp_path, command, message):
    path = tmp_path / 'gray.tif'
    tifffile.imwrite(path, np.arange(256, dtype=np.uint8).reshape(16, 16))
    stack = open_stack(path)
    try:
        with pytest.raises(RuntimeError, match=message) as error:
            engine.run(stack.frame(0), command=command)
        assert 'Macro canceled' not in str(error.value)
    finally:
        stack.close()


def test_binary_and_roi_commands_still_run_when_preconditions_hold(engine, tmp_path):
    raw = np.zeros((16, 16), np.uint8)
    raw[4:12, 4:12] = 255
    path = tmp_path / 'mask.tif'
    tifffile.imwrite(path, raw)
    rectangle = ImportedRoi('r', 'Rectangle', 'polygon', (((2, 2), (10, 2), (10, 10), (2, 10)),),
                            '#ffff00', (2, 2, 8, 8), None, 'Rectangle')
    stack = open_stack(path)
    try:
        eroded = tifffile.imread(engine.run(stack.frame(0), command='Erode')['path'])
        assert 0 < int((eroded == 255).sum()) < int((raw == 255).sum())
        cropped = engine.run(stack.frame(0), command='Crop', record=rectangle)
        assert tifffile.imread(cropped['path']).shape == (8, 8)
    finally:
        stack.close()


def test_java_discovery_prefers_java_home_and_parses_versions(tmp_path, monkeypatch):
    assert [java_major(v) for v in ('1.8', '17', '21.0.2', '24', 'x')] == [8, 17, 21, 24, 0]
    java = tmp_path / 'jdk' / 'bin' / ('java.exe' if sys.platform == 'win32' else 'java')
    java.parent.mkdir(parents=True)
    java.write_bytes(b'')
    monkeypatch.setenv('JAVA_HOME', str(tmp_path / 'jdk'))
    assert java_executable() == str(java)
    monkeypatch.setenv('JAVA_HOME', str(tmp_path / 'missing'))
    assert java_executable() == 'java'


@pytest.mark.parametrize('version,flag', [('21', False), ('24', True)])
def test_native_access_flag_for_java_22_and_newer(monkeypatch, version, flag):
    require_runtime()
    started = {}
    fake = SimpleNamespace(isJVMStarted=lambda: False,
                           startJVM=lambda *args, **kwargs: started.update(args=args, kwargs=kwargs),
                           JClass=lambda name: SimpleNamespace(preinit=lambda: None))
    monkeypatch.setitem(sys.modules, 'jpype', fake)
    monkeypatch.setenv('JAVA_HOME', '')
    monkeypatch.delenv('SIC_XRT_FIJI_HOME', raising=False)
    properties = f'    java.home = {runtime_directory()}\n    java.specification.version = {version}\n'
    monkeypatch.setattr(imagej_runtime.subprocess, 'run', lambda *a, **k: SimpleNamespace(stderr=properties))
    imagej_runtime.initialize()
    assert ('--enable-native-access=ALL-UNNAMED' in started['args']) is flag


def test_runtime_directory_env_override_and_repository_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('SIC_XRT_IMAGEJ_HOME', str(tmp_path / 'custom'))
    assert runtime_directory() == (tmp_path / 'custom').resolve()
    monkeypatch.delenv('SIC_XRT_IMAGEJ_HOME')
    monkeypatch.chdir(tmp_path)
    directory = runtime_directory()
    assert directory.name == 'imagej-runtime' and directory.parent.name == 'artifacts'


def test_plugin_host_follows_ancestor_moves_without_polling(qt_app):
    window = QQuickWindow()
    window.resize(400, 300)
    outer = QQuickItem(window.contentItem())
    middle = QQuickItem(outer)
    host = NativePluginWindow(middle)
    host.setPosition(QPointF(30, 40))
    host.setSize(QSizeF(120, 80))
    host.foreign = QWindow()
    try:
        host.sync_geometry()
        host.timer.stop()
        assert host.container.geometry() == QRect(30, 40, 120, 80)
        outer.setX(20)
        middle.setY(5)
        assert host.container.geometry().topLeft().toTuple() == (50, 45)
        # Reparenting re-subscribes to the new ancestor chain.
        other = QQuickItem(window.contentItem())
        other.setX(100)
        host.setParentItem(other)
        assert host.container.geometry().x() == 130
        middle.setX(300)
        assert host.container.geometry().x() == 130
    finally:
        host.release()
        window.close()
        window.deleteLater()
