"""Serialized client for the app-owned ImageJ worker, isolated from Qt rendering."""
import json
import os
import subprocess
import sys
from dataclasses import asdict
from tempfile import TemporaryDirectory
from threading import RLock

from .imagej_service import PREFIX


class ImageJClient:
    def __init__(self):
        self.process = None
        self.lock = RLock()
        self.session = 0
        self.directory = TemporaryDirectory(prefix='sic-xrt-engine-')

    def call(self, method, frame=None, **args):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                if self.process is not None:
                    self.process.stdin.close()
                    self.process.stdout.close()
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                self.process = subprocess.Popen([sys.executable, '-u', '-m', 'sic_xrt_analyzer.imaging.imagej_service'],
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                text=True, encoding='utf-8', creationflags=flags,
                                                env={**os.environ, 'SIC_XRT_IMAGEJ_TMP': self.directory.name})
            request = {'method': method, 'args': args, 'session': self.session}
            if method == 'classpath':
                request['path'] = args['path']
            if frame:
                source = frame.source
                request['source'] = {'path': source.path, 'page': source.page_index, 'format': source.metadata.format,
                                     'low': frame.low, 'high': frame.high,
                                     'file_size': source.identity.file_size, 'mtime_ns': source.identity.mtime_ns}
                cache = getattr(source, 'prepared', None)
                if cache and cache.pixels is not None:
                    pixels = cache.pixels
                    request['source']['prepared'] = {'path': str(pixels.filename), 'dtype': pixels.dtype.name, 'shape': list(pixels.shape)}
            if args.get('record'):
                args['record'] = asdict(args['record'])
            self.process.stdin.write(json.dumps(request, ensure_ascii=True) + '\n')
            self.process.stdin.flush()
            for line in self.process.stdout:
                if line.startswith(PREFIX):
                    response = json.loads(line[len(PREFIX):])
                    if not response['ok']:
                        raise RuntimeError(response['error'])
                    return response.get('value')
            raise RuntimeError('ImageJ 엔진이 종료되었습니다. 다음 실행에서 다시 시작합니다')

    def run(self, frame, **args):
        return self.call('run', frame, **args)

    def commands(self):
        return self.call('commands')

    def statistics(self, frame, record, kind):
        return self.call('statistics', frame, record=record, kind=kind)

    def wand(self, frame, x, y, tolerance):
        return self.call('wand', frame, x=x, y=y, tolerance=tolerance)

    def add_classpath(self, path):
        return self.call('classpath', path=path)

    def close(self):
        with self.lock:
            if self.process is not None:
                if self.process.poll() is None:
                    try:
                        self.call('close')
                        self.process.wait(timeout=5)
                    except (OSError, RuntimeError, subprocess.TimeoutExpired):
                        self.process.kill()
                        self.process.wait(timeout=5)
                for stream in (self.process.stdin, self.process.stdout):
                    stream.close()
                self.process = None
            self.directory.cleanup()

    def abort(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
