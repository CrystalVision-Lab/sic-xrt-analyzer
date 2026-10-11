"""Native Qt captures of generated JPEG and ImageJ ROI data only."""
import argparse
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from roifile import ROI_TYPE, ImagejRoi

from sic_xrt_analyzer.ui.bridge import FileBridge, TiffImageProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', action='store_true', help='Capture the ROI editor with generated data')
    args = parser.parse_args()
    app = QGuiApplication([])
    QQuickStyle.setStyle('Basic')
    output = Path(__file__).resolve().parents[1] / ('docs/screenshots/roi-editor' if args.editor else 'docs/screenshots/2d-roi')
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        x, y = np.meshgrid(np.linspace(-1, 1, 3200), np.linspace(-1, 1, 3000))
        gray = np.clip(140 + 55 * np.cos(x * 2) + 20 * np.sin(y * 4) + 18 * np.sin(x * 28 + y * 10), 0, 255).astype(np.uint8)
        rgb = np.stack([gray, gray, gray], axis=-1)
        image = QImage(rgb.data, 3200, 3000, rgb.strides[0], QImage.Format_RGB888).copy()
        path = folder / 'SYNTHETIC_TEST_2D_RGB.jpg'
        assert image.save(str(path), 'JPEG', 95)
        points = ImagejRoi.frompoints([[1400, 1350], [1450, 1500], [1600, 1520], [1740, 1480], [1680, 1620]])
        points.roitype = ROI_TYPE.POINT; points.name = 'SYNTHETIC · points'
        points.stroke_color = b'\xff\x45\xff\x80'
        polygon = ImagejRoi.frompoints([[1250, 1200], [1830, 1180], [1900, 1700], [1300, 1760]])
        polygon.roitype = ROI_TYPE.POLYGON; polygon.name = 'SYNTHETIC · polygon'
        polygon.stroke_color = b'\xff\xff\xc5\x62'
        line = ImagejRoi.frompoints([[1200, 1400], [1600, 1700], [1950, 1300]])
        line.roitype = ROI_TYPE.POLYLINE; line.name = 'SYNTHETIC · polyline'
        line.stroke_color = b'\xff\x5a\xbb\xff'
        archive = folder / 'SYNTHETIC_RoiSet.zip'
        with ZipFile(archive, 'w') as zip_file:
            for i, roi in enumerate([points, polygon, line]):
                zip_file.writestr(f'{i}.roi', roi.tobytes())
        engine = QQmlApplicationEngine()
        provider = TiffImageProvider()
        bridge = FileBridge(provider, engine, QSettings(str(folder / 'ui.ini'), QSettings.IniFormat))
        engine.addImageProvider('tiff', provider)
        engine.rootContext().setContextProperty('fileBridge', bridge)
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / 'src/sic_xrt_analyzer/ui/Main.qml')))
        window = engine.rootObjects()[0]
        state = window.findChild(QObject, 'uiState')
        def invoke(obj, name, *args):
            assert QMetaObject.invokeMethod(obj, name, *(Q_ARG('QVariant', a) for a in args))
        def wait(predicate):
            for _ in range(300):
                app.processEvents(); QTest.qWait(20); time.sleep(.005)
                if predicate():
                    return
            raise AssertionError('Synthetic capture timed out')
        def capture(name):
            QTest.qWait(150)
            assert window.grabWindow().save(str(output / f'{name}.png'))
        try:
            invoke(window, 'selectImagePath', str(path))
            wait(lambda: not state.property('loading'))
            assert bridge.importRois([bridge.localUrl(str(archive))])
            wait(lambda: len(bridge.roiState['items']) == 3)
            if args.editor:
                state.setProperty('roiEditMode', True)
                bridge.selectRoiVertex(1)
                bridge.moveRoiVertex(1490, 1495)
            capture('jpeg-roi-fit')
            invoke(window.findChild(QObject, 'actualSizeAction'), 'trigger')
            wait(lambda: bridge.detailState['ready'])
            viewport = window.findChild(QObject, 'viewerViewport')
            origin = viewport.mapToScene(QPoint(0, 0))
            QTest.mouseMove(window, QPoint(int(origin.x() + viewport.width() / 2), int(origin.y() + viewport.height() / 2)))
            wait(lambda: bool(state.property('cursorValue')))
            capture('jpeg-roi-100-detail')
            invoke(window.findChild(QObject, 'fitAction'), 'trigger')
            window.resize(1100, 700)
            capture('jpeg-roi-1100')
            assert not warnings, '\n'.join(warnings)
        finally:
            bridge.waitForLoads()
            window.setProperty('allowQuit', True)
            window.close()
            engine.deleteLater()
            app.processEvents()
    print('Synthetic JPEG/ROI and native-detail screenshots captured; no QML warnings.')


if __name__ == '__main__':
    main()
