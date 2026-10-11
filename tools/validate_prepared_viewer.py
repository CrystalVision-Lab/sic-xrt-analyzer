"""Read-only native preparation checks; exports edited ROI to temporary copies only."""
import argparse
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from sic_xrt_analyzer.imaging.image_stack import SampledImageStack, open_stack
from sic_xrt_analyzer.imaging.imagej_roi import load_rois
from sic_xrt_analyzer.imaging.roi_edit import export_copy, geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = sorted(p for p in args.directory.rglob('*') if p.is_file())
    jpgs = [p for p in files if p.suffix.lower() in ('.jpg', '.jpeg')]
    # Largest JPEG and two others exercise real compressed inputs without
    # rebuilding every temporary cache in the entire dataset.
    jpgs = sorted(jpgs, key=lambda p: p.stat().st_size, reverse=True)[:3]
    jpgs = list(dict.fromkeys(jpgs + [p for p in files if p.parent == args.directory and p.suffix.lower() in ('.jpg', '.jpeg')]))
    tiffs = [p for p in files if p.suffix.lower() in ('.tif', '.tiff')]
    result = {'images': [], 'roi_copies': []}
    metadata = None
    for path in jpgs + tiffs:
        stat = path.stat()
        stack = open_stack(path)
        try:
            started = time.monotonic()
            assert isinstance(stack, SampledImageStack)
            assert stack.prepare_native()
            frame = stack.frame(0)
            prepare_seconds = time.monotonic() - started
            meta = frame.source.metadata
            if path.suffix.lower() in ('.tif', '.tiff') and (metadata is None or meta.width * meta.height > metadata.width * metadata.height):
                metadata = meta
            started = time.monotonic()
            for i in range(20):
                x = i * (meta.width - 512) // 19
                y = i * (meta.height - 512) // 19
                pixels = frame.source.read_region(x, y, 512, 512)
                assert pixels.shape == (512, 512, 3)
                if meta.format == 'JPEG':
                    assert not pixels.flags.writeable
            region_seconds = time.monotonic() - started
            stack.frame(0, (0, 128))
            after = path.stat()
            assert (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            cache = getattr(frame.source, 'prepared', None)
            cache_directory = Path(cache.directory.name) if cache else None
            row = {'format': meta.format, 'size': [meta.width, meta.height],
                   'prepare_seconds': round(prepare_seconds, 4), 'region_20_seconds': round(region_seconds, 4),
                   'source_unchanged': True}
            result['images'].append(row)
            print(json.dumps(row), flush=True)
        finally:
            stack.close()
        if cache_directory is not None:
            assert not cache_directory.exists()
    if metadata is not None:
        with TemporaryDirectory(prefix='sic-xrt-roi-test-') as directory:
            for path in [p for p in files if p.suffix.lower() == '.roi']:
                before = path.read_bytes()
                records, errors = load_rois([path], metadata)
                if not records:
                    result['roi_copies'].append({'ok': False, 'errors': len(errors)})
                    continue
                record = records[0]
                shifted = geometry(record, [[(x + 0.25, y + 0.25) for x, y in record.paths[0]]], metadata)
                target = Path(directory) / 'edited.zip'
                export_copy(target, [shifted])
                loaded, errors = load_rois([target], metadata)
                assert not errors and loaded[0].kind == shifted.kind
                np.testing.assert_allclose(loaded[0].paths, shifted.paths, atol=0.001)
                assert path.read_bytes() == before
                target.unlink()  # Only the test-created copy in its owned temp directory.
                result['roi_copies'].append({'ok': True})
    result['summary'] = {'images': len(result['images']), 'roi_copy_roundtrip': sum(r['ok'] for r in result['roi_copies']),
                         'invalid_roi': sum(not r['ok'] for r in result['roi_copies'])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    main()
