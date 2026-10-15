"""Exercise real Inno upgrade/relaunch using a unique test AppId and tiny local app.

Never run the production app installer or alter its uninstall record/shortcuts.
"""

import argparse
import hashlib
import json
import subprocess
import time
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUID = "47130000-0000-4000-8000-000000000131"
KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{" + GUID + "}_is1"


def registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return winreg.QueryValueEx(key, "InstallLocation")[0]
    except FileNotFoundError:
        return None


def run(args, **kwargs):
    return subprocess.run(
        [str(a) for a in args],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        **kwargs,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "artifacts") or out.exists() or registered():
        raise ValueError("New task artifacts directory and unused test AppId required")
    out.mkdir(parents=True)
    installed = out / "installed"
    compiler = ROOT / "artifacts/distribution120/inno/ISCC.exe"
    csc = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    assert csc.is_file()
    helper = out / "XrtUpdateHandoff.exe"
    run(
        [
            csc,
            "/nologo",
            "/target:winexe",
            "/out:" + str(helper),
            ROOT / "installer/UpdateHandoff.cs",
        ]
    )
    bundles = {}
    for version in ["0.2.0", "0.3.0", "0.3.1"]:
        folder = out / version
        bundle = folder / "bundle"
        bundle.mkdir(parents=True)
        output = folder / "output"
        output.mkdir()
        code = (
            'using System;using System.IO;class App{static void Main(){File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"launch-'
            + version
            + '.txt"),"'
            + version
            + '");}}'
        )
        source = folder / "App.cs"
        source.write_text(code, encoding="utf-8")
        with (folder / "build.log").open("wb") as log:
            run(
                [
                    csc,
                    "/nologo",
                    "/target:winexe",
                    "/out:" + str(bundle / "SiCXrtAnalyzer.exe"),
                    source,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            run(
                [
                    compiler,
                    "/DUpdateHelper=" + str(helper),
                    "/DAppVersion=" + version,
                    "/DAppGuid=" + GUID,
                    "/DAppDisplayName=XRT Workflow131 Acceptance",
                    "/DBundleDir=" + str(bundle),
                    "/DOutputPath=" + str(output),
                    ROOT / "installer/setup.iss",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        bundles[version] = output / (
            "SiCXrtAnalyzer-" + version + "-windows-x64-setup.exe"
        )
    receipt = {
        "status": "FAIL",
        "test_app_id": GUID,
        "production_install_touched": False,
        "paths": {},
    }
    try:
        run(
            [
                bundles["0.2.0"],
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/NOICONS",
                "/DIR=" + str(installed),
                "/LOG=" + str(out / "first.log"),
            ]
        )
        assert Path(registered()).resolve() == installed
        run([installed / "SiCXrtAnalyzer.exe"])
        assert (installed / "launch-0.2.0.txt").read_text() == "0.2.0"
        cache = out / "app-updates"
        cache.mkdir()

        def cache_file(version):
            original = bundles[version]
            target = cache / (
                hashlib.sha256(original.read_bytes()).hexdigest() + ".exe"
            )
            target.write_bytes(original.read_bytes())
            return target

        def wait_version(version):
            until = time.monotonic() + 90
            while not (installed / ("launch-" + version + ".txt")).exists():
                if time.monotonic() > until:
                    raise TimeoutError("silent update or relaunch failed: " + version)
                time.sleep(0.2)
            assert (installed / ("launch-" + version + ".txt")).read_text() == version
            assert Path(registered()).resolve() == installed

        # Exact 0.2.0 updater invocation, with no silent or target-directory flags.
        legacy = subprocess.Popen(
            [
                str(cache_file("0.3.0")),
                "/NORESTART",
                "/LOG=" + str(out / "legacy-bootstrap.log"),
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            code = legacy.wait(timeout=30)
        except subprocess.TimeoutExpired:
            import psutil

            for child in psutil.Process(legacy.pid).children(recursive=True):
                child.kill()
            legacy.kill()
            legacy.wait()
            raise
        assert code in (0, 1, 2), code
        wait_version("0.3.0")
        receipt["paths"]["old_client_bootstrap"] = "PASS"
        from sic_xrt_analyzer.application_updates import update_command

        run(update_command(cache_file("0.3.1"), installed / "SiCXrtAnalyzer.exe"))
        wait_version("0.3.1")
        receipt["paths"]["new_client_inplace_relaunch"] = "PASS"
        receipt["status"] = "PASS"
    finally:
        # The uninstall target must be our unique registration and bounded sandbox.
        location = registered()
        if location:
            target = Path(location).resolve()
            assert target == installed and target.is_relative_to(out)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
                uninstall = Path(
                    winreg.QueryValueEx(key, "UninstallString")[0].strip(chr(34))
                ).resolve()
            assert (
                uninstall.parent == target
                and uninstall.name.startswith("unins")
                and uninstall.suffix == ".exe"
            )
            run([uninstall, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
        receipt["test_registration_removed"] = registered() is None
        (out / "report.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
