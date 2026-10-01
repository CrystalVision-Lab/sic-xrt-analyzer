"""Download pinned ImageJ runtime dependencies from Maven Central; verify SHA256."""
import argparse
import hashlib
import urllib.request
from pathlib import Path

from sic_xrt_analyzer.imaging.imagej_runtime import JARS, runtime_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=runtime_directory())
    directory = parser.parse_args().directory
    directory.mkdir(parents=True, exist_ok=True)
    for name, (artifact, digest) in JARS.items():
        path = directory / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            print('verified', name)
            continue
        with urllib.request.urlopen(f'https://repo.maven.apache.org/maven2/{artifact}/{name}', timeout=60) as response:
            data = response.read(16 * 1024**2)
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('SHA256 mismatch: ' + name)
        path.write_bytes(data)
        print('installed', name)
    print('ImageJ runtime:', directory.resolve())


if __name__ == '__main__':
    main()
