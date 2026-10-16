"""Native form -> pinned ImageJ fidelity, scope isolation and real QML submission."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QSettings, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import isValid
from test_2d_images_roi import invoke
from test_analysis_pipeline import spin

from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_commands import command_form, command_options
from sic_xrt_analyzer.imaging.imagej_roi import ImportedRoi
from sic_xrt_analyzer.imaging.imagej_runtime import runtime_directory
from sic_xrt_analyzer.ui.bridge import FileBridge

CASES = [
    ('Gaussian Blur...', {'sigma': 1.3}, 'sigma=1.3 slice'),
    ('Median...', {'radius': 2.5}, 'radius=2.5 slice'),
    ('Mean...', {'radius': 2.5}, 'radius=2.5 slice'),
    ('Minimum...', {'radius': 2.5}, 'radius=2.5 slice'),
    ('Maximum...', {'radius': 2.5}, 'radius=2.5 slice'),
    ('Variance...', {'radius': 2.5}, 'radius=2.5 slice'),
    ('Unsharp Mask...', {'radius': 1.5, 'mask': 0.4}, 'radius=1.5 mask=0.4 slice'),
    ('Remove Outliers...', {'radius': 2, 'threshold': 20, 'which': 'Dark'},
     'radius=2 threshold=20 which=Dark slice'),
    ('Subtract Background...', {'rolling': 10, 'light': False, 'sliding': False,
                                'disable': False, 'separate': False}, 'rolling=10 slice'),
]


@pytest.fixture(scope='module')
def engines():
    pytest.importorskip('jpype')
    if not (runtime_directory() / 'ij-1.54p.jar').is_file():
        pytest.skip('Run tools/setup_imagej.py')
    native, reference = ImageJClient(), ImageJClient()
    yield native, reference
    native.close()
    reference.close()


def rectangle():
    return ImportedRoi('test', 'selection', 'polygon', (((6, 7), (26, 7), (26, 27), (6, 27)),),
                       '#ffff00', (6, 7, 20, 20), None, 'Rectangle')


@pytest.mark.parametrize('dtype', ['uint8', 'uint16', 'float32'])
@pytest.mark.parametrize('command,parameters,reference_options', CASES)
def test_native_parameters_match_original_imagej(engines, tmp_path, dtype, command, parameters, reference_options):
    # Independent hard-coded IJ options are the oracle; no native serializer there.
    native, reference = engines
    pixels = np.random.default_rng(158).integers(20, 220, (36, 40)).astype(dtype)
    if dtype == 'uint16':
        pixels *= 200
    path = tmp_path / 'input.tif'
    tifffile.imwrite(path, pixels)
    before = path.read_bytes()
    stack = open_stack(path)
    roi = None if command == 'Subtract Background...' else rectangle()
    try:
        expected = reference.run(stack.frame(0), command=command, options=reference_options, record=roi)
        expected_pixels = tifffile.imread(expected['path'])
        result = native.run(stack.frame(0), native=command, parameters=parameters, record=roi)
        actual = tifffile.imread(result['path'])
        np.testing.assert_array_equal(actual, expected_pixels)
        assert actual.dtype == pixels.dtype and actual.shape == pixels.shape
        if roi:
            outside = np.ones(pixels.shape, dtype=bool)
            outside[7:27, 6:26] = False
            np.testing.assert_array_equal(actual[outside], pixels[outside])
    finally:
        stack.close()
    assert path.read_bytes() == before


def test_background_rgb_flags_and_remembered_state(engines, tmp_path):
    native, reference = engines
    pixels = np.random.default_rng(3).integers(20, 240, (32, 32, 3), dtype=np.uint8)
    paths = [tmp_path / f'rgb-{i}.tif' for i in range(2)]
    for p in paths:
        tifffile.imwrite(p, pixels, photometric='rgb')
    for i, enabled in enumerate((True, False)):
        stack = open_stack(paths[i])
        try:
            values = {'rolling': 8, 'light': enabled, 'sliding': enabled, 'disable': enabled, 'separate': enabled}
            options = 'rolling=8 light sliding disable separate slice' if enabled else 'rolling=8 slice'
            expected = reference.run(stack.frame(0), command='Subtract Background...', options=options)
            expected_pixels = tifffile.imread(expected['path'])
            actual = native.run(stack.frame(0), native='Subtract Background...', parameters=values)
            np.testing.assert_array_equal(tifffile.imread(actual['path']), expected_pixels)
        finally:
            stack.close()


def test_native_isolates_displayed_page_after_cached_stack(engines, tmp_path):
    native, _ = engines
    pixels = np.stack([np.full((20, 22), v, np.uint16) for v in (100, 1000, 10000)])
    path = tmp_path / 'pages.tif'
    tifffile.imwrite(path, pixels, photometric='minisblack')
    before = path.read_bytes()
    stack = open_stack(path)
    try:
        native.run(stack.frame(0), command='Measure', options='slice', whole_stack=True)
        result = native.run(stack.frame(1), native='Gaussian Blur...', parameters={'sigma': 1})
        actual = tifffile.imread(result['path'])
        assert actual.shape == (20, 22) and result['pages'] == 1
        np.testing.assert_array_equal(actual, pixels[1])
        with pytest.raises(RuntimeError, match='현재 페이지'):
            native.run(stack.frame(0), native='Gaussian Blur...', parameters={'sigma': 1}, whole_stack=True)
        with pytest.raises(RuntimeError, match='선택 ROI'):
            native.run(stack.frame(0), native='Subtract Background...', record=rectangle(),
                       parameters=CASES[-1][1])
        for kind, tool in [('line', 'Line'), ('point', 'Point'), ('polygon', 'Text')]:
            with pytest.raises(RuntimeError, match='면적 ROI'):
                native.run(stack.frame(0), native='Gaussian Blur...', parameters={'sigma': 1},
                           record=replace(rectangle(), kind=kind, tool=tool))
    finally:
        stack.close()
    assert path.read_bytes() == before


@pytest.mark.parametrize('value', [True, '', '1 stack', 'NaN', float('inf'), -1, 1001])
def test_invalid_parameters_cannot_become_macro_options(value):
    with pytest.raises(ValueError):
        command_options('Gaussian Blur...', {'sigma': value})


def test_unrepresented_options_stay_in_advanced_mode():
    assert command_form('Gaussian Blur...', 'radius=2') == {}  # Legacy radius is sigma/2.5!
    assert command_form('Gaussian Blur...', 'sigma=2 scaled') == {}
    assert command_form('Gaussian Blur...', 'sigma=2 stack') == {}
    assert command_form('Subtract Background...', 'rolling=50 create') == {}
    assert command_form('Gaussian Blur...', 'sigma=NaN') == {}
    assert command_form('Median...', 'radius=101') == {}
    with pytest.raises(ValueError):
        command_options('Gaussian Blur...', {'sigma': 2, 'stack': True})


def test_qml_native_form_edits_parameters_and_runs_imagej(qt_app, tmp_path):
    if not (runtime_directory() / 'ij-1.54p.jar').is_file():
        pytest.skip('Run tools/setup_imagej.py')
    QQuickStyle.setStyle('Basic')
    pixels = np.zeros((40, 40), np.uint16)
    pixels[20, 20] = 60000
    path = tmp_path / 'single.tif'
    tifffile.imwrite(path, pixels)
    before = path.read_bytes()
    engine = QQmlApplicationEngine()
    bridge = FileBridge(parent=engine, settings=QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', bridge.provider)
    bridge.centralSync.dismissSetup()  # Existing-user workflow; first run is covered separately.
    engine.rootContext().setContextProperty('fileBridge', bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1] / 'src/sic_xrt_analyzer/ui/Main.qml')))
    assert engine.rootObjects()
    window = engine.rootObjects()[0]
    try:
        invoke(window, 'selectImagePath', str(path))
        spin(qt_app, lambda: bridge.stack_viewer.frame is not None and not bridge.stack_viewer.busy
             and not bridge.stack_viewer.initial_loading)
        dialog = window.findChild(QObject, 'imagejDialog')
        invoke(dialog, 'showCommand', 'Gaussian Blur...', 'sigma=2')
        qt_app.processEvents()
        assert dialog.property('nativeControls')
        assert not window.findChild(QObject, 'imagejOptions').property('visible')
        form = window.findChild(QObject, 'imagejNativeForm')
        def descendants(item):
            for child in item.childItems():
                yield child
                yield from descendants(child)
        fields = [f for f in descendants(form) if f.objectName() == 'imagejParameter_sigma']
        assert fields
        field = next((f for f in fields if f.property('visible')), fields[0])
        spin(qt_app, lambda: field.property('visible'))
        field.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for key in (Qt.Key_1, Qt.Key_Period, Qt.Key_3):
            QTest.keyClick(window, key)
        qt_app.processEvents()
        toggle = window.findChild(QObject, 'imagejAdvancedInput')
        invoke(toggle, 'clicked')
        assert not dialog.property('nativeControls')
        assert window.findChild(QObject, 'imagejOptions').property('text') == 'sigma=1.3 slice'
        # A real text edit must retain the return affordance and be parsed on return.
        options = window.findChild(QObject, 'imagejOptions')
        options.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in 'sigma=1.7 slice':
            QTest.keyClick(window, char)
        qt_app.processEvents()
        assert toggle.property('visible')
        invoke(toggle, 'clicked')
        assert dialog.property('nativeControls')
        bridge.workbench.record(True)
        run = window.findChild(QObject, 'imagejRunButton')
        invoke(run, 'clicked')
        spin(qt_app, lambda: not bridge.workbench.busy and bridge.stack_viewer.frame is not None
             and bridge.stack_viewer.frame.source.path != str(path) and not bridge.stack_viewer.busy, timeout=30)
        assert not bridge.workbench.error
        assert 'sigma=1.7 slice' in bridge.workbench.recorded
        result = tifffile.imread(bridge.stack_viewer.frame.source.path)
        assert result[20, 20] < 60000 and result[20, 21] > 0
        invoke(dialog, 'showCommand', 'Subtract Background...', 'rolling=50')
        assert dialog.property('nativeControls')
        # Unknown/advanced options must never be silently rewritten by our form.
        invoke(dialog, 'showCommand', 'Gaussian Blur...', 'sigma=2 scaled')
        assert not dialog.property('nativeControls')
    finally:
        if isValid(window):
            window.setProperty('allowQuit', True)
            window.close()
        bridge.waitForLoads()
        engine.deleteLater()
        qt_app.processEvents()
    assert path.read_bytes() == before
