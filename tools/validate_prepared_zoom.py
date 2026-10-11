"""Read-only real-image zoom painting and pixel-fidelity timing, not a GPU FPS claim."""
import argparse
import json
import statistics
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.ui.bridge import FileBridge
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    app = QGuiApplication([])
    before = args.path.stat()
    stack = open_stack(args.path)
    bridge = FileBridge(settings=QSettings(str(args.output.with_suffix('.ini')), QSettings.IniFormat))
    view = PreparedView()
    result = {'paint_size': [1200,800], 'zoom': []}
    try:
        started = time.monotonic()
        assert stack.prepare_native()
        frame = stack.frame(0)
        result['prepare_seconds'] = time.monotonic() - started
        bridge.stack_viewer.frame = frame
        view.bridge = bridge
        view.setWidth(1200); view.setHeight(800)
        meta = frame.source.metadata
        cx, cy = meta.width // 2, meta.height // 2
        expected = frame.source.read_region(cx,cy,1,1)[0,0].tolist()
        result['size'] = [meta.width,meta.height]
        result['temporary_level_bytes'] = frame.source.display_pyramid.cache_bytes
        for scale in (.05,.1,.25,.5,1,2,4):
            timings=[]
            view.viewTransform=[600-cx*scale,400-cy*scale,scale]
            for _ in range(10):
                image=QImage(1200,800,QImage.Format_RGB32)
                image.fill(Qt.black)
                painter=QPainter(image)
                started=time.perf_counter()
                view.paint(painter)
                timings.append((time.perf_counter()-started)*1000)
                painter.end()
            color=image.pixelColor(600,400)
            if scale >= 1:
                assert [color.red(),color.green(),color.blue()] == expected
            result['zoom'].append({'scale':scale,'paint_median_ms':statistics.median(timings), 'paint_max_ms':max(timings), 'native_center_exact':scale>=1})
        after=args.path.stat()
        assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        result['source_unchanged']=True
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(result,ensure_ascii=False))
    finally:
        bridge.waitForLoads();stack.close();app.processEvents()


if __name__=='__main__':
    main()
