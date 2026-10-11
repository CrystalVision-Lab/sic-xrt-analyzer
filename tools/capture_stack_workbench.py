"""Capture stack-only controls and calibration using synthetic read-only inputs."""
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault('QSG_RENDER_LOOP', 'basic')

import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui.bridge import FileBridge


def main():
    output=Path('docs/screenshots/stack-workbench')
    output.mkdir(parents=True,exist_ok=True)
    app=QGuiApplication([]);QQuickStyle.setStyle('Basic')
    with TemporaryDirectory() as temporary:
        folder=Path(temporary)
        engine=QQmlApplicationEngine()
        bridge=FileBridge(parent=engine,settings=QSettings(str(folder/'prefs.ini'),QSettings.IniFormat))
        engine.addImageProvider('tiff',bridge.provider)
        engine.rootContext().setContextProperty('fileBridge',bridge)
        warnings=[]
        engine.warnings.connect(lambda items:warnings.extend(i.toString() for i in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
        window=engine.rootObjects()[0];state=window.findChild(QObject,'uiState')
        window.resize(1100,700)
        def invoke(method,*args):
            assert QMetaObject.invokeMethod(window,method,*(Q_ARG('QVariant',a) for a in args))
        def wait(predicate):
            deadline=time.monotonic()+30
            while not predicate():
                if time.monotonic()>deadline:
                    raise TimeoutError('Capture preparation timeout')
                QTest.qWait(20)
        def capture(name):
            QTest.qWait(120)
            assert window.grabWindow().save(str(output/(name+'.png')))
        try:
            pixels=np.random.default_rng(36).integers(0,4000,(3,512,512),np.uint16)
            path=folder/'synthetic-frames.tif'
            tifffile.imwrite(path,pixels,imagej=True,metadata={'axes':'TYX','min':0,'max':4000})
            invoke('selectImagePath',str(path));wait(lambda:not state.property('loading'))
            capture('stack-1100')
            bridge.workbench.gesture('Line',[[100,100],[420,100]])
            bridge.measurements.useReferenceLine();bridge.measurements.setScale(320,18,'mm',1)
            bridge.measurements.measure()
            bridge.workbench.gesture('Rectangle',[[100,130],[420,300]])
            bridge.measurements.measure();invoke('stackMeasurement')
            capture('calibration-measurement')
            window.findChild(QObject,'stackMeasurementDialog').close()
            bridge.roi_manager.clear()
            path=folder/'synthetic-2d.tif';tifffile.imwrite(path,pixels[0])
            invoke('selectImagePath',str(path));wait(lambda:not state.property('loading'))
            capture('single-1100')
            assert not warnings,'\n'.join(warnings)
        finally:
            window.setProperty('allowQuit',True);window.close();bridge.waitForLoads();engine.deleteLater();app.processEvents()
    print('Captured synthetic stack/measurement/single-image screens:',output)


if __name__ == '__main__':
    main()
