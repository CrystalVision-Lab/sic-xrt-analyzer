"""Install verified Fiji Java libraries for the embedded worker; never launch Fiji."""
import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

URL = 'https://downloads.imagej.net/fiji/latest/fiji-latest-portable-nojava.zip'
# Official portable no-Java checksum, reviewed 2026-10-06 (2026-10-04 build).
SHA256 = '4790b29860deafec11fa7921efa8ea0964b40852a6ab713cedc92f94733ce4c9'
# Keep previously verified installations; new downloads still require SHA256.
INSTALLED_SHA256 = {
    SHA256,
    '3ad5e202d6f1a5965265547e401c80e329f1af5529c4a69ec2096f8787877508',
}


def verify(path):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != SHA256:
        raise ValueError('Fiji SHA256 mismatch. The latest archive may have changed; update the pin only after review.')


def install(archive, destination):
    verify(archive)
    if destination.exists():
        marker = destination / '.sic-xrt-runtime-sha256'
        if marker.is_file() and marker.read_text() in INSTALLED_SHA256:
            return
        raise FileExistsError('Choose a new directory; existing files will not be overwritten: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fiji-install-', dir=destination.parent) as temporary:
        root = Path(temporary)
        total = 0
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                parts = PurePosixPath(entry.filename).parts
                if len(parts) < 3 or parts[:1] != ('Fiji',) or parts[1] not in ('jars', 'plugins'):
                    continue
                relative = PurePosixPath(*parts[1:])
                if '..' in parts or relative.is_absolute() or any(':' in part or '\\' in part for part in parts):
                    raise ValueError('Unsafe archive member: ' + entry.filename)
                if relative.suffix.lower() not in ('.jar', '.class', '.ijm', '.config'):
                    continue
                total += entry.file_size
                if total > 2 * 1024**3:
                    raise ValueError('Fiji libraries exceed the 2 GiB extraction limit')
                path = root.joinpath(*relative.parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, path.open('xb') as output:
                    shutil.copyfileobj(source, output, 1024**2)
        if not list((root / 'jars').glob('imagej-*.jar')):
            raise ValueError('Fiji ImageJ libraries are missing')
        (root / '.sic-xrt-runtime-sha256').write_text(SHA256)
        root.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('artifacts/fiji-runtime'))
    parser.add_argument('--archive', type=Path, help='Previously downloaded official portable no-Java ZIP')
    args = parser.parse_args()
    directory = args.directory.resolve()
    marker = directory / '.sic-xrt-runtime-sha256'
    if marker.is_file() and marker.read_text() in INSTALLED_SHA256:
        print('verified installation:', directory)
        return
    if args.archive:
        install(args.archive, directory)
    else:
        with tempfile.TemporaryDirectory(prefix='fiji-download-') as temporary:
            archive = Path(temporary) / 'fiji.zip'
            print('Downloading Fiji Java libraries (~907 MB); Java 21+ is required.', flush=True)
            with urllib.request.urlopen(URL, timeout=60) as response, archive.open('xb') as output:
                shutil.copyfileobj(response, output, 1024**2)
            install(archive, directory)
    print('Fiji libraries:', directory)


if __name__ == '__main__':
    main()
