"""Integration tests for calibrated measurements, Fiji services and GUI workers."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

import numpy as np
import pytest
import tifffile
from PySide6.QtCore import QObject, QPointF, QRect, QSettings, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import isValid
from test_analysis_pipeline import spin
from test_prepared_roi_editor import invoke

from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_client import ImageJClient
from sic_xrt_analyzer.imaging.imagej_runtime import runtime_directory
from sic_xrt_analyzer.ui.bridge import FileBridge
from sic_xrt_analyzer.ui.native_plugin_window import (
    NativePluginWindow,
    native_windows_supported,
)

FIJI = Path(os.environ.get('SIC_XRT_FIJI_HOME', 'artifacts/fiji-runtime')).resolve()


def test_fiji_dataset_command_injects_services_and_preserves_unsigned_pixels(tmp_path):
    if not (FIJI / 'jars').is_dir():
        pytest.skip('Install Fiji libraries with tools/setup_fiji.py')
    directory = tmp_path / 'plugins'
    directory.mkdir()
    code = directory / 'Test_Dataset_Command.java'
    code.write_text('''
import org.scijava.command.Command;
import org.scijava.plugin.Plugin;
import org.scijava.plugin.Parameter;
import org.scijava.ItemIO;
import org.scijava.log.LogService;
import net.imagej.Dataset;
import net.imglib2.type.numeric.RealType;
@Plugin(type=Command.class, name="Native Dataset Test")
public class Test_Dataset_Command implements Command {
 @Parameter(type=ItemIO.BOTH) private Dataset image;
 @Parameter private int delta = 5;
 @Parameter private boolean enabled = true;
 @Parameter private LogService log;
 @Parameter(type=ItemIO.OUTPUT) private String result;
 public void run() {
  if (log == null) throw new IllegalStateException("No injected LogService");
  if (enabled) for (Object p : image.getImgPlus()) {
   RealType value = (RealType)p; value.setReal(value.getRealDouble()+delta);
  }
  result = "services injected; " + image.dimension(0) + "x" + image.dimension(1);
  for (int d=2; d<image.numDimensions(); d++)
   if (image.axis(d).type().toString().equals("Z"))
    throw new IllegalStateException("Page axis misidentified as spatial Z");
 }
}''', encoding='utf8')
    classpath = os.pathsep.join([str(runtime_directory()/'ij-1.54p.jar'), str(FIJI/'jars'/'*')])
    subprocess.run(['javac', '-cp', classpath, '-processor', 'org.scijava.annotations.AnnotationProcessor',
                    '-d', directory.as_posix(), code.as_posix()], check=True, capture_output=True)
    path = tmp_path / 'original.tif'
    raw = np.full((2,16,24), 40000, np.uint16)
    tifffile.imwrite(path, raw, photometric='minisblack')
    before = path.read_bytes()
    stack = open_stack(path)
    client = ImageJClient()
    client.classpaths.append(str(directory))
    client.configure(False, str(FIJI))
    try:
        commands = client.modern_commands()
        assert len(commands) > 100
        assert any(c['class'] == 'Test_Dataset_Command' for c in commands)
        result = client.run(stack.frame(0), modern='Test_Dataset_Command', options='{"delta": 7, "enabled": true}')
        np.testing.assert_array_equal(tifffile.imread(result['path']), raw[0]+7)
        assert 'services injected; 24x16' in result['log']
        result = client.run(stack.frame(1), modern='Test_Dataset_Command', options='{"delta": 17, "enabled": false}')
        np.testing.assert_array_equal(tifffile.imread(result['path']), raw[1])
        # SciJava may remember a previous boolean through its input preprocessors;
        # explicitly select the operation whose pixel result this assertion checks.
        result = client.run(stack.frame(0), modern='Test_Dataset_Command', options='{"delta": 3, "enabled": true}',whole_stack=True)
        with tifffile.TiffFile(result['path']) as out:
            assert len(out.pages) == 2
            values = [np.unique(page.asarray()).tolist() for page in out.pages]
            assert values == [[40003], [40003]], values
        # A shipped Fiji command needs an ImageDisplay and injected services.
        client.session += 1
        result = client.run(stack.frame(0), modern='net.imagej.plugins.commands.assign.MultiplyDataValuesBy',
                            options='{"value": 0.5, "preview": false, "allPlanes": true}')
        np.testing.assert_array_equal(tifffile.imread(result['path']), raw[0]//2)
        with pytest.raises(RuntimeError,match='unknown_delta'):
            client.run(stack.frame(0),modern='Test_Dataset_Command',options='{"unknown_delta":7}')
        with pytest.raises(RuntimeError,match='JSON'):
            client.run(stack.frame(0),modern='Test_Dataset_Command',options='{"enabled":"false"}')
    finally:
        client.close(); stack.close()
    assert path.read_bytes() == before


def test_gui_plugin_dialog_in_real_qml_workbench(qt_app,tmp_path):
    if not native_windows_supported():
        pytest.skip('Desktop foreign window embedding requires windows/xcb')
    QQuickStyle.setStyle('Basic')
    directory=tmp_path/'plugin'
    directory.mkdir()
    code=directory/'Test_QML_Plugin.java'
    code.write_text('''
import ij.IJ; import ij.plugin.PlugIn; import java.awt.*; import javax.swing.*;
public class Test_QML_Plugin implements PlugIn {
 public void run(String arg) {
  JDialog dialog = new JDialog((Frame)null,"Embedded Swing plugin",true);
  JTextField field = new JTextField("5",8);
  JButton button = new JButton("Apply");
  dialog.setLayout(new FlowLayout()); dialog.add(new JLabel("Add value:"));
  dialog.add(field); dialog.add(button); dialog.setSize(360,160);
  button.addActionListener(e -> dialog.dispose());
  Timer timer = new Timer(2500,e -> {field.setText("7"); dialog.dispose();});
  timer.setRepeats(false); timer.start(); dialog.setVisible(true);
  IJ.getImage().getProcessor().add(Integer.parseInt(field.getText()));
 }
}''',encoding='utf8')
    subprocess.run(['javac','-cp',str(runtime_directory()/'ij-1.54p.jar'),str(code)],check=True,capture_output=True)
    path=tmp_path/'frames.tif'
    tifffile.imwrite(path,np.full((2,100,100),100,np.uint16),photometric='minisblack')
    before=path.read_bytes()
    engine=QQmlApplicationEngine()
    bridge=FileBridge(parent=engine,settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.IniFormat))
    engine.addImageProvider('tiff',bridge.provider)
    engine.rootContext().setContextProperty('fileBridge',bridge)
    warnings=[]
    engine.warnings.connect(lambda items:warnings.extend(x.toString() for x in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window=engine.rootObjects()[0];state=window.findChild(QObject,'uiState')
    try:
        invoke(window,'selectImagePath',str(path));spin(qt_app,lambda:not state.property('loading'))
        bridge.workbench.configureRuntime(True,'')
        assert not bridge.workbench.error
        bridge.workbench.runtime.classpaths.append(str(directory))
        bridge.workbench.execute('plugin','Test_QML_Plugin','',False)
        spin(qt_app,lambda:bool(bridge.workbench.windows) or not bridge.workbench.busy,timeout=30)
        assert bridge.workbench.windows,bridge.workbench.error
        dialog=window.findChild(QObject,'pluginWindowsDialog')
        assert dialog.property('visible')
        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)
        # Keep wrappers from scene traversal alive through the Qt event loop.
        scene=list(items(window.contentItem()))
        host=next(i for i in scene if i.objectName()=='nativePluginHost')
        spin(qt_app,lambda:host.foreign.geometry().width() > 300)
        assert host.foreign.parent() == window and host.foreign.geometry().width() > 300
        assert host.foreign.type() == Qt.ForeignWindow
        native=qt_app.primaryScreen().grabWindow(int(host.nativeId))
        assert not native.isNull() and native.save(str(tmp_path/'embedded-plugin.png'))
        spin(qt_app,lambda:not bridge.workbench.busy and not state.property('loading') and not dialog.property('visible'),timeout=30)
        assert not bridge.workbench.error
        np.testing.assert_array_equal(tifffile.imread(bridge.stack_viewer.frame.source.path),np.full((100,100),107,np.uint16))
        assert state.property('stackFeaturesVisible') and not dialog.property('visible')
        assert not warnings,'\n'.join(warnings)
    finally:
        if isValid(window):
            window.setProperty('allowQuit',True);window.close()
        bridge.waitForLoads()
        engine.deleteLater();qt_app.processEvents()
    assert path.read_bytes() == before


def test_qml_processing_result_keeps_window_and_stack_context(qt_app,tmp_path):
    QQuickStyle.setStyle('Basic')
    path=tmp_path/'frames.tif'
    tifffile.imwrite(path,np.full((2,100,100),100,np.uint16),photometric='minisblack')
    engine=QQmlApplicationEngine()
    bridge=FileBridge(parent=engine,settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.IniFormat))
    engine.addImageProvider('tiff',bridge.provider)
    engine.rootContext().setContextProperty('fileBridge',bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window=engine.rootObjects()[0];state=window.findChild(QObject,'uiState')
    try:
        invoke(window,'selectImagePath',str(path));spin(qt_app,lambda:not state.property('loading'))
        bridge.workbench.execute('command','Invert','',False)
        spin(qt_app,lambda:not bridge.workbench.busy and not state.property('loading'),timeout=30)
        assert state.property('stackFeaturesVisible') and not bridge.workbench.error
    finally:
        if isValid(window):
            window.setProperty('allowQuit',True);window.close()
        bridge.waitForLoads();engine.deleteLater();qt_app.processEvents()


def test_scale_length_area_count_and_source_readonly(qt_app, tmp_path):
    path = tmp_path/'frames.tif'
    tifffile.imwrite(path, np.zeros((3,100,100),np.uint16),imagej=True,metadata={'axes':'TYX'})
    before = path.read_bytes()
    stack = open_stack(path)
    bridge = FileBridge(settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.IniFormat))
    bridge.stack_viewer.frame = stack.frame(1)
    m, tools = bridge.measurements, bridge.workbench
    try:
        tools.gesture('Line', [[10,10],[28,10]])
        m.useReferenceLine()
        assert not m.error and m.reference == 18
        m.setScale(m.reference, 1, 'mm', 1)
        m.measure()
        assert m.rows[-1]['value'] == 1 and m.rows[-1]['page'] == 2
        tools.gesture('Rectangle', [[10,10],[28,46]])
        m.measure()
        assert m.rows[-1]['value'] == pytest.approx(2) and m.rows[-1]['unit'] == 'mm²'
        tools.gesture('Oval', [[10,10],[28,46]])
        m.measure()
        assert m.rows[-1]['value'] == pytest.approx(np.pi/2)
        tools.gesture('Point', [[10,10]])
        tools.gesture('Point', [[15,10]])
        m.measure()
        assert m.rows[-1]['value'] == 2 and m.rows[-1]['metric'] == 'Count'
        tools.gesture('Angle', [[10,10],[28,10],[28,46]])
        m.measure()
        assert m.rows[-1]['value'] == pytest.approx(90)
        m.setScale(18,1,'mm',2)
        tools.gesture('Polyline', [[10,10],[28,10],[28,28]])
        m.measure()
        assert m.rows[-1]['value'] == pytest.approx(3)
        m.setScale(float('nan'),1,'mm',1)
        assert m.error and m.pixel_height == pytest.approx(2/18)
        m.setScale(1e-300,1e300,'mm',1)
        assert m.error and m.pixel_height == pytest.approx(2/18)
        saved=tmp_path/'measurements.tsv'
        m.saveResults(bridge.localUrl(str(saved)))
        assert not m.error and 'Raw pixels' in saved.read_text(encoding='utf-8-sig')
        first=saved.read_bytes()
        m.saveResults(bridge.localUrl(str(saved)))
        assert m.error and saved.read_bytes() == first
        m.reset()
        assert m.pixel_width == 1 and m.unit == 'pixel'
    finally:
        bridge.waitForLoads(); stack.close()
    assert path.read_bytes() == before


def test_advanced_backend_rejects_single_page_tiff(qt_app,tmp_path):
    path=tmp_path/'single.tif'
    tifffile.imwrite(path,np.zeros((16,16),np.uint16))
    stack=open_stack(path)
    bridge=FileBridge(settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.IniFormat))
    bridge.stack_viewer.frame=stack.frame(0)
    try:
        bridge.workbench.execute('command','Invert','',False)
        assert bridge.workbench.error and bridge.workbench.runtime.process is None
        bridge.measurements.setScale(100,1,'mm',1)
        assert bridge.measurements.error and bridge.measurements.pixel_width == 1
        bridge.workbench.gesture('Brush',[[0,0],[1,1]])
        assert bridge.workbench.error and bridge.workbench.runtime.process is None
        bridge.workbench.gesture('Rectangle',[[1,1],[10,10]])
        assert not bridge.workbench.error and bridge.roi_manager.records
    finally:
        bridge.waitForLoads();stack.close()


def test_stack_only_menu_and_measurement_dialog_reset(qt_app,tmp_path):
    QQuickStyle.setStyle('Basic')
    engine=QQmlApplicationEngine()
    bridge=FileBridge(parent=engine,settings=QSettings(str(tmp_path/'qml.ini'),QSettings.IniFormat))
    engine.addImageProvider('tiff',bridge.provider)
    engine.rootContext().setContextProperty('fileBridge',bridge)
    warnings=[]
    engine.warnings.connect(lambda items:warnings.extend(x.toString() for x in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window=engine.rootObjects()[0]
    state=window.findChild(QObject,'uiState')
    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)
    try:
        assert not state.property('stackFeaturesVisible')
        for count in (1,3):
            path=tmp_path/f'input-{count}.tif'
            raw=np.zeros((count,100,100),np.uint16)
            tifffile.imwrite(path,raw if count>1 else raw[0],photometric='minisblack')
            invoke(window,'selectImagePath',str(path))
            spin(qt_app,lambda: not state.property('loading'))
            assert state.property('stackFeaturesVisible') == (count>1)
            menus=list(visual_items(window.contentItem()))
            process=next(i for i in menus if i.property('text') == '처리 (Process)')
            plugins=next(i for i in menus if i.property('text') == '플러그인 (Plugins)')
            assert process.isVisible() == plugins.isVisible() == (count>1)
        bridge.workbench.gesture('Line',[[10,10],[28,10]])
        invoke(window,'stackMeasurement')
        QTest.qWait(40)
        dialog=window.findChild(QObject,'stackMeasurementDialog')
        assert dialog.property('visible')
        bridge.measurements.useReferenceLine();bridge.measurements.setScale(18,1,'mm',1)
        bridge.measurements.measure()
        assert bridge.measurements.rows[-1]['value'] == 1
        # A derived single page retains its explicit stack provenance. Opening an
        # unrelated single image removes advanced menus and resets calibration.
        path=tmp_path/'derived.tif'
        tifffile.imwrite(path,np.zeros((100,100),np.uint16))
        bridge.requestWorkingCopy(str(path))
        spin(qt_app,lambda:not state.property('loading'))
        assert state.property('stackFeaturesVisible') and bridge.workbench.require_stack()
        invoke(window,'selectImagePath',str(tmp_path/'missing.tif'))
        spin(qt_app,lambda:not state.property('loading'))
        assert state.property('stackFeaturesVisible') and bridge.workbench.require_stack()
        assert bridge.measurements.unit == 'mm'
        bridge.roi_manager.clear()
        invoke(window,'selectImagePath',str(tmp_path/'input-1.tif'))
        spin(qt_app,lambda:not state.property('loading'))
        assert not state.property('stackFeaturesVisible') and not dialog.property('visible')
        assert bridge.measurements.unit == 'pixel'
        assert not warnings,'\n'.join(warnings)
    finally:
        window.setProperty('allowQuit',True);window.close();bridge.waitForLoads();engine.deleteLater();qt_app.processEvents()


@pytest.mark.parametrize('window_type', ['AWT', 'Swing', 'ImageJ'])
def test_gui_plugin_window_is_hosted_and_settings_return_pixels(qt_app,tmp_path,window_type):
    if not native_windows_supported():
        pytest.skip('Run with QT_QPA_PLATFORM=windows or xcb under Xvfb')
    directory=tmp_path/'gui-plugin'
    directory.mkdir()
    code=directory/'Test_GUI_Plugin.java'
    code.write_text('''
import ij.IJ; import ij.plugin.PlugIn;
import java.awt.*; import javax.swing.*; import ij.gui.GenericDialog;
public class Test_GUI_Plugin implements PlugIn {
 public void run(String arg) {
  if (arg.equals("ImageJ")) {
   GenericDialog gd = new GenericDialog("Native plugin settings");
   gd.addNumericField("Add value",5,0);
   Timer timer = new Timer(2500,e -> {((TextField)gd.getNumericFields().get(0)).setText("7"); gd.dispose();});
   timer.setRepeats(false); timer.start(); gd.showDialog();
   IJ.getImage().getProcessor().add(gd.getNextNumber()); return;
  }
  if (arg.equals("Swing")) {
   JDialog dialog = new JDialog((Frame)null,"Native plugin settings",true);
   JTextField field = new JTextField("5",8);
   JButton button = new JButton("Apply");
   dialog.setLayout(new FlowLayout()); dialog.add(new JLabel("Add value:"));
   dialog.add(field); dialog.add(button); dialog.setSize(360,150);
   button.addActionListener(e -> dialog.dispose());
   Timer timer = new Timer(2500,e -> {field.setText("7"); dialog.dispose();});
   timer.setRepeats(false); timer.start(); dialog.setVisible(true);
   IJ.getImage().getProcessor().add(Integer.parseInt(field.getText())); return;
  }
  Dialog dialog = new Dialog((Frame)null,"Native plugin settings",true);
  TextField field = new TextField("5",8);
  Button button = new Button("Apply");
  dialog.setLayout(new FlowLayout()); dialog.add(new Label("Add value:"));
  dialog.add(field); dialog.add(button); dialog.setSize(360,150);
  button.addActionListener(e -> dialog.dispose());
  Timer timer = new Timer(2500,e -> {field.setText("7"); dialog.dispose();});
  timer.setRepeats(false); timer.start(); dialog.setVisible(true);
  IJ.getImage().getProcessor().add(Integer.parseInt(field.getText()));
 }
}''',encoding='utf8')
    subprocess.run(['javac','-cp',str(runtime_directory()/'ij-1.54p.jar'),str(code)],check=True,capture_output=True)
    client=ImageJClient();client.configure(True);client.classpaths.append(str(directory))
    events=Queue();client.window_event=events.put
    path=tmp_path/'gui-source.tif'
    raw=np.full((2,16,16),40000,np.uint16)
    tifffile.imwrite(path,raw,photometric='minisblack');before=path.read_bytes()
    stack=open_stack(path)
    window=QQuickWindow();window.resize(600,400)
    host=NativePluginWindow(window.contentItem());host.setPosition(QPointF(30,40));host.setSize(__import__('PySide6.QtCore',fromlist=['QSizeF']).QSizeF(360,150))
    window.show()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            try:
                future=executor.submit(client.run,stack.frame(0),plugin='Test_GUI_Plugin',options=window_type)
                event=events.get(timeout=30)
                while not event.get('windows'):
                    event=events.get(timeout=10)
                native=next(w for w in event['windows'] if w['title']=='Native plugin settings')
                host.nativeId=str(native['id']);QTest.qWait(100)
                assert host.foreign is not None and host.foreign.parent() == window
                assert host.foreign.geometry() == QRect(30,40,360,150)
                host.parentItem().setX(20);QTest.qWait(100)
                assert host.foreign.geometry().x() == 50
                spin(qt_app,future.done)
                result=future.result(timeout=1)
                np.testing.assert_array_equal(tifffile.imread(result['path']),raw[0]+7)
            finally:
                host.nativeId='';client.abort()
    finally:
        host.nativeId='';client.close();stack.close();window.close();window.deleteLater()
    assert path.read_bytes() == before
