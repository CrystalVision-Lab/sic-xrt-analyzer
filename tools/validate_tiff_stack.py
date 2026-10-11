"""Read-only validation of requested real stacks. Writes no TIFF or screenshot files."""
import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import tifffile

from sic_xrt_analyzer.imaging.tiff_stack import TiffStack

EXPECTED = {
    "No22_220_Section_stack_flipped.tif": (2944, 2745, 156),
    "N119_220_Section_stack_flipped.tif": (3072, 3012, 158),
    "No107_SectionTopo-beforeAnnealing.tif": (2922, 2895, 156),
    "No107_SectionTopo-afterAnnealing .tif": (2922, 2895, 156),
}


def display_samples(image):
    # QImage rows may be padded. Return an independent visible grayscale buffer.
    return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()].copy()


def validate(path, expected=None):
    path = Path(path)
    if not path.is_file():
        return {"file": path.name, "status": "NOT_RUN", "reason": "File is not accessible"}
    stat = path.stat()
    stack = None
    try:
        stack = TiffStack(path)
        m = stack.first_source.metadata
        if expected and (m.width, m.height, m.page_count) != expected:
            raise ValueError(f"Expected {expected}; found {(m.width, m.height, m.page_count)}")
        if m.dtype != "uint16" or m.channels != 1:
            raise ValueError("Requested XRT stacks require uint16 single-channel pages")
        records = []
        for index in sorted({0, stack.page_count // 2, stack.page_count - 1}):
            start = perf_counter()
            frame = stack.frame(index)
            # Independent tifffile page oracle; never series.asarray() on the whole stack.
            with tifffile.TiffFile(path) as tif:
                if len(tif.pages) == stack.page_count:
                    oracle = tif.pages[index].asarray(maxworkers=1)
                else:
                    mapped = tifffile.memmap(path, series=0, mode="r")
                    try:
                        oracle = mapped.reshape(stack.page_count, m.height, m.width)[index].copy()
                    finally:
                        mapped._mmap.close()
            np.testing.assert_array_equal(frame.pixels, oracle)
            original_display = display_samples(frame.preview.image)
            center = int(frame.pixels[m.height // 2, m.width // 2])
            changed = stack.frame(index, (center - 1, center + 1))
            np.testing.assert_array_equal(changed.pixels, oracle)
            alternate = display_samples(changed.preview.image)
            # If the first window produces exactly the same display, choose a displaced window.
            if np.array_equal(original_display, alternate):
                changed = stack.frame(index, (center + 1, center + 2))
                alternate = display_samples(changed.preview.image)
            contrast_changed = not np.array_equal(original_display, alternate)
            if not contrast_changed:
                raise ValueError("Contrast change did not affect display samples")
            if stack.cache_bytes > stack.max_cache_bytes or len(stack.cache) > stack.max_cache_pages:
                raise ValueError("Cache exceeded its configured limit")
            records.append({"page": index + 1, "raw_equal": True, "dtype": str(frame.pixels.dtype),
                            "center_pixel": center, "contrast_changed": contrast_changed,
                            "display_range": [frame.low, frame.high],
                            "seconds": round(perf_counter() - start, 4)})
            del oracle, original_display, alternate, frame, changed
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source file changed during validation")
        return {"file": path.name, "status": "PASS", "width": m.width, "height": m.height,
                "pages": m.page_count, "dtype": m.dtype, "file_bytes": stat.st_size,
                "imagej_frames": stack.imagej_frames, "imagej_slices": stack.imagej_slices,
                "range_origin": stack.range_origin, "source_stat_unchanged": True,
                "cache_bytes": stack.cache_bytes, "cache_limit_bytes": stack.max_cache_bytes,
                "checks": records, "spatial_z": "unconfirmed"}
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "status": "FAIL", "reason": str(exc)}
    finally:
        if stack:
            stack.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=Path("/run/media/didgmltmd/6E25-3446/3D XRT"))
    parser.add_argument("--files", nargs="+", default=list(EXPECTED))
    args = parser.parse_args()
    records = [validate(args.folder / name, EXPECTED.get(name)) for name in args.files]
    status = "PASS" if all(r["status"] == "PASS" for r in records) else "FAIL" if any(r["status"] == "FAIL" for r in records) else "PARTIAL"
    print(json.dumps({"status": status, "files": records}, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
