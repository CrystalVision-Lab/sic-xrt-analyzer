"""Real Fiji selection commands: geometry, calibration, page scope and endian fidelity."""
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QUrl
from test_analysis_pipeline import spin

from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_roi import ImportedRoi
from sic_xrt_analyzer.imaging.imagej_runtime import runtime_directory

FIJI = Path(os.environ.get('SIC_XRT_FIJI_HOME', 'artifacts/fiji-runtime')).resolve()
MULTIPLY = 'net.imagej.plugins.commands.assign.MultiplyDataValuesBy'


@pytest.fixture
def fiji_client():
    if not (FIJI/'jars').is_dir():
        pytest.skip('Install Fiji libraries with tools/setup_fiji.py')
    client = ImageJClient()
    client.configure(False, str(FIJI))
    yield client
    client.close()


def selection(tool='Rectangle', kind='polygon', points=((3,2),(9,2),(9,7),(3,7)), page=None):
    return ImportedRoi('test', 'selected region', kind, (points,), '#45c3cf', (3,2,6,5), page, tool)


def test_shipped_fiji_roi_command_preserves_outside_and_current_frame(tmp_path, fiji_client):
    path = tmp_path/'big-endian.tif'
    raw = np.full((3,12,16), 40000, dtype=np.uint16)
    raw[:,3,4] = 40001
    tifffile.imwrite(path, raw, photometric='minisblack', byteorder='>')
    before = path.read_bytes()
    stack = open_stack(path)
    client = fiji_client
    try:
        roi = selection(page=1)
        result = client.run(stack.frame(1), modern=MULTIPLY, record=roi,
                            options='{"value":0.5,"preview":false,"allPlanes":false}')
        expected = raw[1].copy()
        expected[2:7,3:9] = (expected[2:7,3:9].astype(np.uint32)+1)//2
        np.testing.assert_array_equal(tifffile.imread(result['path']), expected)
        assert '선택 ROI' in result['log']
        # Virtual source -> bounded editable Dataset; page order is frames, not Z.
        client.session += 1
        result = client.run(stack.frame(1), modern=MULTIPLY, record=roi, whole_stack=True,
                            options='{"value":0.5,"preview":false,"allPlanes":false}')
        expected_stack = raw.copy()
        expected_stack[1,2:7,3:9] = (expected_stack[1,2:7,3:9].astype(np.uint32)+1)//2
        np.testing.assert_array_equal(tifffile.imread(result['path']), expected_stack)
        client.session += 1
        result = client.run(stack.frame(1), modern=MULTIPLY, record=roi, whole_stack=True,
                            options='{"value":0.5,"preview":false,"allPlanes":true}')
        expected_stack = raw.copy()
        expected_stack[:,2:7,3:9] = (expected_stack[:,2:7,3:9].astype(np.uint32)+1)//2
        np.testing.assert_array_equal(tifffile.imread(result['path']), expected_stack)
        # Deselecting must clear the prior Overlay, including when the engine is reused.
        client.session += 1
        result = client.run(stack.frame(0), modern=MULTIPLY,
                            options='{"value":0.5,"preview":false,"allPlanes":false}')
        np.testing.assert_array_equal(tifffile.imread(result['path']), (raw[0].astype(np.uint32)+1)//2)
        # IJ1 reads the same big endian original without byte-swapping intensities.
        client.session += 1
        result = client.run(stack.frame(0), macro='')
        np.testing.assert_array_equal(tifffile.imread(result['path']), raw[0])
    finally:
        stack.close()
    assert path.read_bytes() == before


def test_workbench_passes_drawn_roi_and_retains_selection_on_result(qt_app, tmp_path, bridge_factory):
    if not (FIJI/'jars').is_dir():
        pytest.skip('Install Fiji libraries with tools/setup_fiji.py')
    path = tmp_path/'source.tif'
    raw = np.full((2,30,40),40001,np.uint16)
    tifffile.imwrite(path,raw,photometric='minisblack',byteorder='>')
    before = path.read_bytes()
    bridge = bridge_factory()
    bridge.workbench.resultReady.connect(bridge.requestWorkingCopy)
    bridge.requestImage(QUrl.fromLocalFile(str(path)).toString())
    spin(qt_app,lambda:not bridge.stack_viewer.initial_loading and bridge.stack_viewer.frame is not None)
    bridge.workbench.configureRuntime(False,str(FIJI))
    bridge.workbench.gesture('Rectangle',[[3,2],[9,7]])
    roi = bridge.roi_manager.selected_record(bridge.stack_viewer.frame)
    bridge.workbench.execute('modern',MULTIPLY,'{"value":0.5,"preview":false,"allPlanes":false}',False)
    spin(qt_app,lambda:not bridge.workbench.busy and not bridge.stack_viewer.initial_loading
         and bridge.stack_viewer.frame.source.path != str(path),timeout=60)
    assert not bridge.workbench.error
    result = bridge.stack_viewer.frame
    expected = raw[0].copy()
    expected[2:7,3:9] = 20001
    np.testing.assert_array_equal(result.pixels,expected)
    assert result.source.path != str(path) and bridge._stack_context
    assert bridge.roi_manager.selected_record(result) == roi
    bridge.roi_manager.records = [replace(roi,paths=(roi.paths[0],roi.paths[0]),page_index=None)]
    result_path = result.source.path
    bridge.workbench.execute('modern',MULTIPLY,'{"value":0.5}',False)
    assert not bridge.workbench.busy and '복합 경로' in bridge.workbench.error
    assert bridge.stack_viewer.frame.source.path == result_path
    assert path.read_bytes() == before


def test_fiji_overlay_geometry_measurement_and_required_input(tmp_path, fiji_client):
    directory = tmp_path/'plugin'
    directory.mkdir()
    code = directory/'Test_Overlay_Measurement.java'
    code.write_text('''
import org.scijava.command.Command;
import org.scijava.plugin.Plugin;
import org.scijava.plugin.Parameter;
import org.scijava.ItemIO;
import net.imagej.Dataset;
import net.imagej.overlay.Overlay;
import net.imagej.display.ImageDisplay;
import net.imagej.display.OverlayService;
import net.imglib2.roi.RegionOfInterest;
@Plugin(type=Command.class, name="Selection measurement test")
public class Test_Overlay_Measurement implements Command {
 @Parameter private Dataset image;
 @Parameter private ImageDisplay display;
 @Parameter private Overlay overlay;
 @Parameter private OverlayService overlays;
 @Parameter(type=ItemIO.OUTPUT) private String result;
 public void run() {
  if (overlays.getActiveOverlay(display) != overlay)
   throw new IllegalStateException("Selection is not active");
  RegionOfInterest region = overlay.getRegionOfInterest();
  int count = 0;
  for (int y=0;y<image.dimension(1);y++) for (int x=0;x<image.dimension(0);x++)
   if (region.contains(new double[]{x,y})) count++;
  result = overlay.getClass().getSimpleName()+";"+count+";"+
   image.axis(0).averageScale(0,1)+";"+image.axis(1).averageScale(0,1)+";"+
   image.axis(0).unit()+";"+overlay.getName();
 }
}''', encoding='utf8')
    classpath = os.pathsep.join([str(runtime_directory()/'ij-1.54p.jar'), str(FIJI/'jars'/'*')])
    subprocess.run(['javac','-cp',classpath,'-processor','org.scijava.annotations.AnnotationProcessor',
                    '-d',directory.as_posix(),code.as_posix()],check=True,capture_output=True)
    client = fiji_client
    client.add_classpath(str(directory))
    client.calibration = {'pixelWidth':0.25,'pixelHeight':0.5,'unit':'mm'}
    path = tmp_path/'frames.tif'
    raw = np.full((2,12,16),40000,np.uint16)
    tifffile.imwrite(path, raw, photometric='minisblack')
    before = path.read_bytes()
    stack = open_stack(path)
    try:
        cases = [
            (selection(), 'RectangleOverlay',30),
            (selection('Oval'), 'EllipseOverlay',None),
            (selection('', points=((3,2),(9,2),(3,7))), 'PolygonOverlay',None),
            (selection('Freehand'), 'PolygonOverlay',None),
            (selection('Line','line',((3,2),(8,2))), 'LineOverlay',None),
            (selection('FreeLine','line',((3,2),(8,2),(8,6))), 'CompositeOverlay',None),
            (selection('','point',((3,2),(8,6))), 'PointOverlay',None),
        ]
        for roi, overlay_type, expected_count in cases:
            client.session += 1
            result = client.run(stack.frame(0),modern='Test_Overlay_Measurement',record=roi,options='{}')
            fields = json.loads(result['log'].strip())['result'].split(';')
            assert fields[0] == overlay_type
            if expected_count is not None:
                assert int(fields[1]) == expected_count
            assert fields[2:] == ['0.25','0.5','mm',roi.name]
            np.testing.assert_array_equal(tifffile.imread(result['path']),raw[0])
        client.session += 1
        with pytest.raises(RuntimeError,match='선택 ROI'):
            client.run(stack.frame(0),modern='Test_Overlay_Measurement',options='{}')
        for roi in [selection('Text'), replace(selection(),paths=(selection().paths[0],selection().paths[0]))]:
            with pytest.raises(RuntimeError,match='단일 경로'):
                client.run(stack.frame(0),modern=MULTIPLY,record=roi,options='{"value":0.5}')
    finally:
        stack.close()
    assert path.read_bytes() == before
