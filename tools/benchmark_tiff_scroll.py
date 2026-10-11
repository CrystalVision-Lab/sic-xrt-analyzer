"""Read-only scroll preparation/publication timings; synthetic TIFF by default.

This measures Python/Qt signal publication, not GPU upload or monitor frame latency.
No source pixels or derived inspection images are written to the report.
"""
import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtCore import QCoreApplication

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack, render_page
from sic_xrt_analyzer.ui.stack_controller import StackController


def wait(app, predicate):
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.001)
    raise TimeoutError("Page preparation timed out")


def milliseconds(operation, repeats):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1000)
    return {"median": round(statistics.median(samples), 3), "min": round(min(samples), 3),
            "max": round(max(samples), 3), "samples": len(samples)}


def benchmark(path, repeats):
    app = QCoreApplication.instance() or QCoreApplication([])
    stat = path.stat()
    stack = TiffStack(path)
    try:
        start = time.perf_counter()
        frame = stack.frame(0)
        first_ms = (time.perf_counter() - start) * 1000
        if frame.pixels.dtype != np.uint16 or frame.pixels.ndim != 2 or stack.page_count < 2:
            raise ValueError("Benchmark requires a multi-page uint16 grayscale TIFF")
        window = (frame.low, frame.high)
        report = {"width": frame.source.metadata.width, "height": frame.source.metadata.height,
                  "pages": stack.page_count, "uncached_read_and_render_ms": round(first_ms, 3),
                  "uint16_display_conversion_ms": milliseconds(
                      lambda: render_page(frame.pixels, frame.source, *window), repeats),
                  "prepared_frame_lookup_ms": milliseconds(lambda: stack.frame(0, window), repeats)}
    finally:
        stack.close()
    frame = None
    controller = StackController(preload_enabled=False)
    published = []
    controller.frameReady.connect(lambda frame, opening: published.append(frame.source.page_index))
    try:
        controller.open(str(path.resolve()))
        wait(app, lambda: not controller.busy)
        if controller.error:
            raise ValueError(controller.error)
        stack = controller._reader.stack
        if min(stack.max_cache_pages, stack.max_cache_bytes // controller.frame.pixels.nbytes,
               stack.max_display_bytes // controller.frame.preview.image.sizeInBytes()) < 2:
            raise ValueError("This page size exceeds the two-page prefetch cache capacity")
        wait(app, lambda: stack.cached_frame(1, controller.window) is not None)
        wait(app, lambda: controller._task is None)
        def navigate():
            index = 1 - controller.frame.source.page_index
            count = len(published)
            controller.page(index)
            if controller.busy or len(published) != count + 1 or controller.frame.source.page_index != index:
                raise AssertionError("Prepared page was not published synchronously")
        report["prepared_page_publication_ms"] = milliseconds(navigate, repeats)
        report["raw_cache_bytes"] = stack.cache_bytes
        report["raw_cache_limit_bytes"] = stack.max_cache_bytes
        report["display_cache_bytes"] = stack.display_bytes
        report["display_cache_limit_bytes"] = stack.max_display_bytes
    finally:
        controller.shutdown()
    after = path.stat()
    report["source_stat_unchanged"] = (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    if not report["source_stat_unchanged"]:
        raise ValueError("Source file changed during benchmark")
    return report


def benchmark_scrubbing(path, repeats):
    app = QCoreApplication.instance() or QCoreApplication([])
    stat = path.stat()
    controller = StackController()
    try:
        start = time.perf_counter()
        controller.open(str(path.resolve()))
        def complete():
            if controller.error or controller.preload_error:
                raise ValueError(controller.error or controller.preload_error)
            return controller.preload_state["ready"] and controller._task is None
        wait(app, complete)
        preparation = (time.perf_counter() - start) * 1000
        stack = controller._reader.stack
        before = stack.decode_count
        indices = list(range(stack.page_count)) + list(range(stack.page_count - 1, -1, -1))
        cursor = 0
        controller.begin_scrub()
        def navigate():
            nonlocal cursor
            index = indices[cursor % len(indices)]
            cursor += 1
            if not controller.page(index) or controller.busy or controller.frame.source.page_index != index:
                raise AssertionError("Scrub did not publish the requested page immediately")
            if controller.frame.pixels is not None or controller.pixel_value(0, 0):
                raise AssertionError("Browse samples were reported as original pixels")
        timing = milliseconds(navigate, len(indices) * repeats)
        if stack.decode_count != before:
            raise AssertionError("Scrubbing reread the TIFF")
        m = controller.frame.source.metadata
        report = {"width": m.width, "height": m.height, "pages": m.page_count,
                  "all_page_preparation_ms": round(preparation, 3),
                  "all_page_scrub_publication_ms": timing, "scrub_additional_decodes": 0,
                  "browse_step": stack.browse.step,
                  "browse_cache_bytes": stack.browse.bytes, "browse_cache_limit_bytes": stack.browse.max_bytes,
                  "raw_cache_bytes": stack.cache_bytes, "raw_cache_limit_bytes": stack.max_cache_bytes}
        controller.end_scrub()
        wait(app, lambda: controller.frame.pixels is not None and not controller.detail_busy)
        report["released_page_raw_restored"] = True
    finally:
        controller.shutdown()
    after = path.stat()
    report["source_stat_unchanged"] = (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    if not report["source_stat_unchanged"]:
        raise ValueError("Source file changed during benchmark")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, help="Read-only existing TIFF; default is temporary synthetic data")
    parser.add_argument("--edge", type=int, default=3000, help="Synthetic width/height")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--all-pages", action="store_true", help="Measure whole-stack preparation and continuous scrubbing")
    parser.add_argument("--pages", type=int, default=5, help="Synthetic page count")
    args = parser.parse_args()
    if args.edge < 2 or args.repeats < 1 or args.pages < 2:
        parser.error("edge >= 2, repeats >= 1 and pages >= 2 required")
    measure = benchmark_scrubbing if args.all_pages else benchmark
    if args.path:
        report = measure(args.path, args.repeats)
        report["input"] = "existing read-only file"
    else:
        with tempfile.TemporaryDirectory(prefix="xrt-scroll-benchmark-") as folder:
            path = Path(folder) / "synthetic.tif"
            mapped = tifffile.memmap(path, shape=(args.pages, args.edge, args.edge), dtype=np.uint16,
                                    photometric="minisblack")
            try:
                mapped[:] = (np.arange(args.edge, dtype=np.uint16) * 20)[None, None, :]
                mapped.flush()
            finally:
                mapped._mmap.close()
            report = measure(path, args.repeats)
        report["input"] = "synthetic temporary TIFF"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
