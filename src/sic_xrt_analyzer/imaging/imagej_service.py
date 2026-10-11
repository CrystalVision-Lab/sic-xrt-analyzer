"""Private embedded ImageJ engine; optional plugin windows, no external executable."""
import json
import sys
from threading import Lock
from types import SimpleNamespace

import numpy as np

from .image_stack import JpegImageSource
from .imagej_roi import ImportedRoi
from .imagej_runtime import ImageJRuntime
from .original_source import OriginalImageSource

PREFIX = 'SIC_XRT_RESULT:'
WINDOW_PREFIX = 'SIC_XRT_WINDOW:'
OUTPUT_LOCK = Lock()


def reply(prefix, value):
    with OUTPUT_LOCK:
        sys.stdout.write(prefix + json.dumps(value, ensure_ascii=True) + '\n')
        sys.stdout.flush()


class SharedPreparedPixels:
    def __init__(self, spec):
        self.pixels = np.memmap(spec['path'], mode='r', dtype=spec['dtype'], shape=tuple(spec['shape']))

    def region(self, source, x, y, width, height):
        source.validate_identity()
        return self.pixels[y:y + height, x:x + width].copy()

    def close(self):
        self.pixels._mmap.close()


def serve():
    runtime = ImageJRuntime(lambda value: reply(WINDOW_PREFIX, value))
    session = None
    try:
        for line in sys.stdin:
            cache = None
            try:
                request = json.loads(line)
                method = request['method']
                if method == 'close':
                    reply(PREFIX, {'ok': True, 'value': None})
                    break
                if method == 'commands':
                    value = runtime.commands()
                elif method == 'modern_commands':
                    value = runtime.modern_commands()
                elif method == 'classpath':
                    runtime.start().addClassPath(request['path'])
                    value = None
                else:
                    if request['session'] != session:
                        runtime.invalidate()
                        session = request['session']
                    spec = request['source']
                    source = JpegImageSource(spec['path']) if spec['format'] == 'JPEG' else OriginalImageSource(spec['path'], spec['page'])
                    if (source.identity.file_size, source.identity.mtime_ns) != (spec['file_size'], spec['mtime_ns']):
                        raise ValueError('원본 파일이 변경되었습니다. 파일을 다시 여세요')
                    if spec.get('prepared') and isinstance(source, JpegImageSource):
                        cache = SharedPreparedPixels(spec['prepared'])
                        object.__setattr__(source, 'prepared', cache)
                    frame = SimpleNamespace(source=source, low=spec['low'], high=spec['high'], calibration=spec.get('calibration',{}))
                    args = request.get('args', {})
                    if args.get('record'):
                        record = args['record']
                        record['paths'] = tuple(tuple(tuple(p) for p in path) for path in record['paths'])
                        record['bbox'] = tuple(record['bbox'])
                        args['record'] = ImportedRoi(**record)
                    if method == 'run':
                        value = runtime.run(frame, **args)
                    elif method == 'statistics':
                        value = runtime.statistics(frame, args.get('record'), args['kind'])
                    elif method == 'wand':
                        value = runtime.wand(frame, args['x'], args['y'], args['tolerance'])
                    else:
                        raise ValueError('Unknown engine method')
                reply(PREFIX, {'ok': True, 'value': value})
            except Exception as exc:  # noqa: BLE001 (private process protocol boundary)
                runtime.invalidate()
                reply(PREFIX, {'ok': False, 'error': str(exc)})
            finally:
                if cache:
                    cache.close()
    finally:
        runtime.close()


if __name__ == '__main__':
    serve()
