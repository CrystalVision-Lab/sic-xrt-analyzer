"""Measure synthetic TIFF open events and the first unobscured Qt render.

Run from the repository in a graphical Qt session. Fixtures/results remain in
ignored artifacts/. Timings are observations, never test pass thresholds.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from sic_xrt_analyzer.ui import stack_controller
from sic_xrt_analyzer.ui.bridge import FileBridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, default=Path('artifacts/td07-benchmark'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    bridge = FileBridge(parent=engine, settings=QSettings(str(args.output/'prefs.ini'), QSettings.IniFormat))
    engine.addImageProvider('tiff', bridge.provider)
    engine.rootContext().setContextProperty('fileBridge', bridge)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'src/sic_xrt_analyzer/ui/Main.qml')))
    window = engine.rootObjects()[0]
    window.resize(1100, 700)
    state = window.findChild(QObject, 'uiState')
    controller = bridge.stack_viewer
    measured = {}
    baseline = [0.0]
    original_open = stack_controller.open_stack

    def now():
        return round(time.perf_counter() - baseline[0], 6)

    def opened(*a, **kw):
        stack = original_open(*a, **kw)
        measured['T1_metadata'] = now()
        return stack

    def first_frame(frame, opening):
        if opening:
            measured['T2_frame'] = now()

    def ready():
        if controller.preload_state['ready']:
            measured.setdefault('T4_stack', now())

    def rendered():
        # Both old and new presentations use the same full-overlay object.
        overlay = window.findChild(QObject, 'initialLoadingOverlay')
        if measured.get('T2_frame') is not None and state.property('hasLoadedImage') and not overlay.property('visible'):
            measured.setdefault('T3_render', now())

    stack_controller.open_stack = opened
    controller.frameReady.connect(first_frame)
    controller.changed.connect(ready)
    window.frameSwapped.connect(rendered)
    results = []
    try:
        for count, edge in [(3, 512), (32, 1024), (158, 256)]:
            path = args.output/f'generated-{count}-{edge}.tif'
            if not path.exists():
                grid = np.arange(edge*edge, dtype=np.uint16).reshape(edge, edge)
                with tifffile.TiffWriter(path) as writer:
                    for index in range(count):
                        writer.write(grid + np.uint16(index), photometric='minisblack', contiguous=True)
            measured.clear()
            QTest.qWait(40)
            baseline[0] = time.perf_counter()
            assert QMetaObject.invokeMethod(window, 'selectImagePath', Q_ARG('QVariant', str(path.resolve())))
            deadline = time.monotonic() + 600
            while 'T4_stack' not in measured or 'T3_render' not in measured:
                if time.monotonic() > deadline:
                    raise TimeoutError(f'No complete Qt render for {count}: {measured}')
                QTest.qWait(1)
            stack = controller._reader.stack
            results.append({'pages': count, 'width': edge, 'height': edge,
                            'dtype': stack.first_source.metadata.dtype,
                            **measured, 'browse_bytes': stack.browse.bytes,
                            'raw_cache_bytes': stack.cache_bytes,
                            'display_cache_bytes': stack.display_bytes,
                            'decode_count': stack.decode_count})
            print(json.dumps(results[-1]), flush=True)
        assert not warnings, warnings
    finally:
        stack_controller.open_stack = original_open
        window.setProperty('allowQuit', True)
        window.close()
        bridge.waitForLoads()
        engine.deleteLater()
        app.processEvents()
    result = {'label': args.label, 'platform': 'Qt '+app.platformName(),
              'units': 'seconds since open request; cache bytes', 'results': results}
    (args.output/f'{args.label}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
