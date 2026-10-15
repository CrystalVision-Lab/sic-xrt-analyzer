"""Exercise native bootstrap, update exit wait and actual Inno extraction on Windows."""

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSC = (
    Path(os.environ.get("WINDIR", "C:/Windows"))
    / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
)
ISCC = ROOT / "artifacts/distribution120/inno/ISCC.exe"
pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not CSC.is_file() or not ISCC.is_file(),
    reason="Windows .NET/Inno installation gate",
)


def compile_cs(source, target):
    subprocess.run(
        [
            str(CSC),
            "/nologo",
            "/target:winexe",
            "/reference:System.Windows.Forms.dll",
            "/reference:System.Drawing.dll",
            "/out:" + str(target),
            str(source),
        ],
        check=True,
        capture_output=True,
    )


def wait_file(path, timeout=20):
    until = time.monotonic() + timeout
    while not path.is_file():
        assert time.monotonic() < until, str(path)
        time.sleep(0.02)


@pytest.fixture
def native(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    compile_cs(ROOT / "installer/NativeLauncher.cs", root / "SiCXrtAnalyzer.exe")
    fake = tmp_path / "fake.cs"
    fake.write_text(
        'using System;using System.IO;using System.Threading;class Fake{static int Main(string[] a){string r=AppDomain.CurrentDomain.BaseDirectory;if(a.Length>0&&a[0]=="wait"){Thread.Sleep(2000);File.WriteAllText(Path.Combine(r,"worker.done"),"done");}else File.WriteAllText(Path.Combine(r,"backend.ran"),"ran");return 0;}}'
    )
    compile_cs(fake, root / "SiCXrtApp.exe")
    shutil.copyfile(root / "SiCXrtApp.exe", root / "SiCXrtWorker.exe")
    (root / "segmentation.pyi").write_text("from ._watershed import watershed")
    (root / "ui.qml").write_text("Item {}")
    rows = [
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name
        for p in root.iterdir()
    ]
    (root / "runtime-files.sha256").write_text("\n".join(rows) + "\n")
    return root


def test_native_start_waits_for_setup_and_rejects_bad_runtime(native):
    exe = native / "SiCXrtAnalyzer.exe"
    assert (
        subprocess.run(
            [str(exe), "--verify-runtime"], timeout=10, check=False
        ).returncode
        == 0
    )
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    api.CreateMutexW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.CreateMutexW(
        None, False, "CrystalVisionLab_SicXrt_81CAB3F6-F3BE-4B05-ACB8-E9F47113CC32"
    )
    assert handle
    try:
        assert subprocess.run([str(exe)], timeout=10, check=False).returncode == 0
        time.sleep(0.25)
        assert not (native / "backend.ran").exists()
    finally:
        api.CloseHandle(handle)
    wait_file(native / "backend.ran")
    (native / "segmentation.pyi").write_text("corrupted")
    assert (
        subprocess.run(
            [str(exe), "--verify-runtime"], timeout=10, check=False
        ).returncode
        == 65
    )


def test_update_helper_waits_for_same_install_worker(native, tmp_path):
    helper = tmp_path / "helper.exe"
    compile_cs(ROOT / "installer/UpdateHandoff.cs", helper)
    setup_source = tmp_path / "setup.cs"
    setup_source.write_text(
        'using System;using System.IO;class Fake{static int Main(){File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"setup.ran"),"ran");return 0;}}'
    )
    binary = tmp_path / "setup.exe"
    compile_cs(setup_source, binary)
    cache = tmp_path / "app-updates"
    cache.mkdir()
    setup = cache / (hashlib.sha256(binary.read_bytes()).hexdigest() + ".exe")
    shutil.copyfile(binary, setup)
    # A separate path is deliberately not part of this installation scope.
    worker = subprocess.Popen([str(native / "SiCXrtWorker.exe"), "wait"])
    parent = subprocess.Popen([str(binary)])
    run = subprocess.Popen([str(helper), str(parent.pid), str(setup), str(native)])
    try:
        token = hashlib.sha256(str(native).lower().encode("utf-8")).hexdigest().upper()
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenMutexW.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_wchar_p]
        api.OpenMutexW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        until = time.monotonic() + 10
        while True:
            handle = api.OpenMutexW(
                0x100000, False, "CrystalVisionLab_XrtUpdating_" + token
            )
            if handle:
                api.CloseHandle(handle)
                break
            assert time.monotonic() < until
            time.sleep(0.01)
        assert (
            subprocess.run(
                [str(native / "SiCXrtAnalyzer.exe")], timeout=10, check=False
            ).returncode
            == 0
        )
        assert not (native / "backend.ran").exists()
        assert not (cache / "setup.ran").exists()
        assert worker.wait(timeout=10) == 0
        assert run.wait(timeout=20) == 0
        assert (cache / "setup.ran").exists()
        assert "VERIFIED_AND_APP_EXITED" in (cache / "handoff.log").read_text()
        wait_file(native / "backend.ran")
    finally:
        for p in (worker, parent, run):
            if p.poll() is None:
                p.kill()
                p.wait()


def test_real_inno_install_validates_runtime_and_keeps_failure_marker(native, tmp_path):
    helper = tmp_path / "helper.exe"
    compile_cs(ROOT / "installer/UpdateHandoff.cs", helper)
    for bad in (False, True):
        output = tmp_path / ("bad-output" if bad else "good-output")
        output.mkdir()
        target = tmp_path / ("bad-install" if bad else "good-install")
        if bad:
            (native / "segmentation.pyi").write_text("corrupted")
        cmd = [
            str(ISCC),
            "/DAppVersion=0.4.1",
            "/DAppGuid=" + str(uuid4()),
            "/DAppDisplayName=XRT isolated installation QA",
            "/DBundleDir=" + str(native),
            "/DUpdateHelper=" + str(helper),
            "/DOutputPath=" + str(output),
            str(ROOT / "installer/setup.iss"),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        setup = output / "SiCXrtAnalyzer-0.4.1-windows-x64-setup.exe"
        r = subprocess.run(
            [
                str(setup),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/DIR=" + str(target),
                "/LOG=" + str(output / "install.log"),
            ],
            timeout=45,
            check=False,
        )
        if bad:
            assert r.returncode != 0
            assert (target / ".xrt-install-incomplete").exists()
        else:
            assert r.returncode == 0, (output / "install.log").read_text(
                errors="replace"
            )[-3000:]
            assert not (target / ".xrt-install-incomplete").exists()
            assert (
                subprocess.run(
                    [str(target / "SiCXrtAnalyzer.exe"), "--verify-runtime"],
                    timeout=10,
                    check=False,
                ).returncode
                == 0
            )
        # Only the test AppGuid is unregistered; this does not target the real app.
        uninstaller = target / "unins000.exe"
        if uninstaller.is_file():
            subprocess.run(
                [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                timeout=30,
                check=False,
            )
