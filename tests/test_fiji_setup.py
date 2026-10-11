"""Installer checksum failure and preservation of an existing verified runtime."""
import importlib.util
import sys
from pathlib import Path

import pytest


def installer():
    spec = importlib.util.spec_from_file_location(
        'setup_fiji', Path(__file__).parents[1] / 'tools' / 'setup_fiji.py',
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_previous_runtime_is_preserved_without_download(tmp_path, monkeypatch):
    module = installer()
    previous = '3ad5e202d6f1a5965265547e401c80e329f1af5529c4a69ec2096f8787877508'
    marker = tmp_path / '.sic-xrt-runtime-sha256'
    marker.write_text(previous)
    sentinel = tmp_path / 'existing.jar'
    sentinel.write_bytes(b'existing runtime')
    monkeypatch.setattr(sys, 'argv', ['setup_fiji.py', '--directory', str(tmp_path)])

    def unexpected_download(*args, **kwargs):
        pytest.fail('An existing verified runtime must not trigger a download')

    monkeypatch.setattr(module.urllib.request, 'urlopen', unexpected_download)
    module.main()
    assert marker.read_text() == previous
    assert sentinel.read_bytes() == b'existing runtime'


def test_invalid_archive_is_rejected_before_destination_changes(tmp_path):
    module = installer()
    archive = tmp_path / 'invalid.zip'
    archive.write_bytes(b'not the pinned archive')
    destination = tmp_path / 'runtime'
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        module.install(archive, destination)
    assert not destination.exists()
