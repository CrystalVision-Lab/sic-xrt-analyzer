"""Read-only local 2D image and ROI validation. Never export image pixels."""
import argparse
import json
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from sic_xrt_analyzer.imaging.image_stack import open_stack
from sic_xrt_analyzer.imaging.imagej_roi import load_rois


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve(strict=True)
    paths = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.tif', '.tiff'))
    result = {'images': [], 'roi_files': [], 'roi_zips': []}
    maximum_width = maximum_height = 0
    reference_metadata = None
    started = time.monotonic()
    for i, path in enumerate(paths):
        before = path.stat()
        stack = None
        row = {'path': str(path), 'ok': False}
        try:
            stack = open_stack(path)
            frame = stack.frame(0)
            row.update(ok=True, format=frame.source.metadata.format,
                       width=frame.source.metadata.width, height=frame.source.metadata.height,
                       preview=[frame.preview.image.width(), frame.preview.image.height()],
                       sampled=frame.preview.sampled)
            reference_metadata = frame.source.metadata
            maximum_width = max(maximum_width, row['width'])
            maximum_height = max(maximum_height, row['height'])
            low, high = frame.low, frame.high
            adjusted = stack.frame(0, (low, (low + high) / 2))
            assert adjusted.high != high
            # Exact region read stays bounded even for 12k RGB images.
            x, y = row['width'] // 2, row['height'] // 2
            crop = frame.source.read_region(x, y, 1, 1)
            assert crop.shape[:2] == (1, 1)
            row['contrast_and_exact_region_ok'] = True
        except Exception as exc:  # noqa: BLE001
            row['ok'] = False
            row['error'] = str(exc)
        finally:
            if stack:
                stack.close()
        after = path.stat()
        row['source_unchanged'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        assert row['source_unchanged']
        result['images'].append(row)
        if (i + 1) % 20 == 0 or i + 1 == len(paths):
            print(json.dumps({'images_checked':i + 1, 'total':len(paths), 'seconds':round(time.monotonic() - started, 1)}), flush=True)
    if reference_metadata is not None:
        # This checks file geometry, not automatic association with a particular exposure.
        bounds = replace(reference_metadata, width=maximum_width, height=maximum_height, page_count=1)
        for path in sorted(root.rglob('*.roi')):
            records, errors = load_rois([path], bounds)
            result['roi_files'].append({'path':str(path), 'valid':len(records), 'errors':errors})
        for path in sorted(root.rglob('*.zip')):
            if path.name.lower() == 'roiset.zip':
                records, errors = load_rois([path], bounds)
                result['roi_zips'].append({'path':str(path), 'valid':len(records), 'errors':errors})
    counts = Counter((row.get('format', 'invalid'), row['ok']) for row in result['images'])
    result['summary'] = {f'{fmt}_{"ok" if ok else "failed"}':count for (fmt, ok), count in counts.items()}
    result['summary'].update(roi_valid=sum(r['valid'] for r in result['roi_files']),
                             roi_failed=sum(bool(r['errors']) for r in result['roi_files']),
                             roi_zip_valid=sum(r['valid'] for r in result['roi_zips']),
                             seconds=round(time.monotonic() - started, 2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    main()
