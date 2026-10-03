"""Serialized client for the app-owned ImageJ worker, isolated from Qt rendering."""
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from threading import RLock, Thread

from .imagej_service import PREFIX, WINDOW_PREFIX


class ImageJClient:
    def __init__(self):
        self.process = None
        self.lock = RLock()
        self.session = 0
        self.gui = False
        self.fiji_home = ''
        self.classpaths = []
        self.calibration = {'pixelWidth':1.,'pixelHeight':1.,'unit':'pixel'}
        self.window_event = None
        self.responses = Queue()
        self.listener = None
        self.directory = TemporaryDirectory(prefix='sic-xrt-engine-')

    def call(self, method, frame=None, **args):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                if self.process is not None:
                    self.process.stdin.close()
                    self.process.stdout.close()
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                extra = list(self.classpaths)
                if self.fiji_home:
                    home = Path(self.fiji_home)
                    excluded = ('ij-', 'ij1-patcher-', 'javassist-', 'classgraph-', 'jna-', 'jna-platform-')
                    extra += [str(p.resolve()) for folder in ('jars','plugins') for p in (home/folder).rglob('*.jar')
                              if not p.name.startswith(excluded)]
                    extra += [str(home/'plugins')]
                self.process = subprocess.Popen([sys.executable, '-u', '-m', 'sic_xrt_analyzer.imaging.imagej_service'],
                                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                text=True, encoding='utf-8', errors='replace', creationflags=flags,
                                                env={**os.environ, 'SIC_XRT_IMAGEJ_TMP': self.directory.name,
                                                     'SIC_XRT_IMAGEJ_GUI': '1' if self.gui else '0',
                                                     'SIC_XRT_FIJI_HOME': self.fiji_home,
                                                     'SIC_XRT_IMAGEJ_EXTRA_PATHS': json.dumps(extra),
                                                     'PYTHONIOENCODING': 'utf-8'})
                self.responses = Queue()
                self.listener = Thread(target=self.consume, args=(self.process, self.responses), daemon=True)
                self.listener.start()
            request = {'method': method, 'args': args, 'session': self.session}
            if method == 'classpath':
                request['path'] = args['path']
            if frame:
                source = frame.source
                request['source'] = {'path': source.path, 'page': source.page_index, 'format': source.metadata.format,
                                     'low': frame.low, 'high': frame.high,
                                     'calibration': self.calibration,
                                     'file_size': source.identity.file_size, 'mtime_ns': source.identity.mtime_ns}
                cache = getattr(source, 'prepared', None)
                if cache and cache.pixels is not None:
                    pixels = cache.pixels
                    request['source']['prepared'] = {'path': str(pixels.filename), 'dtype': pixels.dtype.name, 'shape': list(pixels.shape)}
            if args.get('record'):
                args['record'] = asdict(args['record'])
            self.process.stdin.write(json.dumps(request, ensure_ascii=True) + '\n')
            self.process.stdin.flush()
            while True:
                try:
                    response = self.responses.get(timeout=.25)
                    break
                except Empty:
                    if self.process.poll() is not None or not self.listener.is_alive():
                        raise RuntimeError('ImageJ 엔진 연결이 종료되었습니다')
            if not response['ok']:
                raise RuntimeError(response['error'])
            return response.get('value')

    def consume(self, process, responses):
        try:
            for line in process.stdout:
                if line.startswith(WINDOW_PREFIX):
                    if self.window_event:
                        event = json.loads(line[len(WINDOW_PREFIX):])
                        event['enginePid'] = process.pid
                        self.window_event(event)
                elif line.startswith(PREFIX):
                    responses.put(json.loads(line[len(PREFIX):]))
        except (OSError, ValueError) as exc:
            responses.put({'ok': False, 'error': 'ImageJ 응답 읽기 실패: ' + str(exc)})
        finally:
            responses.put({'ok': False, 'error': 'ImageJ 엔진이 종료되었습니다. 다음 실행에서 다시 시작합니다'})

    def configure(self, gui, fiji_home=''):
        if bool(gui) != self.gui or fiji_home != self.fiji_home:
            self.abort()
            self.gui, self.fiji_home = bool(gui), fiji_home

    def run(self, frame, **args):
        return self.call('run', frame, **args)

    def commands(self):
        return self.call('commands')

    def modern_commands(self):
        return self.call('modern_commands')

    def statistics(self, frame, record, kind):
        return self.call('statistics', frame, record=record, kind=kind)

    def wand(self, frame, x, y, tolerance):
        return self.call('wand', frame, x=x, y=y, tolerance=tolerance)

    def add_classpath(self, path):
        if self.fiji_home:
            # SciJava indexes plugins at Context creation. Recreate the context on
            # the next request, with the plugin present in the initial classpath.
            if path not in self.classpaths:
                self.classpaths.append(path)
            self.abort()
            return path
        result = self.call('classpath', path=path)
        if path not in self.classpaths:
            self.classpaths.append(path)
        return result

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
                if self.listener:
                    self.listener.join(timeout=2)
                self.process = None
            self.directory.cleanup()

    def abort(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if self.window_event:
            self.window_event({'windows': []})
