"""Build an explicit Windows bundle; private originals/models/secrets are never collected."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path

from sic_xrt_analyzer import __version__

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jdk", type=Path, required=True)
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--version", default=__version__)
    p.add_argument(
        "--notes",
        default="선택한 검은 결함의 연결 3D 표면, 실제 촬영 구역의 웨이퍼 모자이크, 설치 화면 없는 업데이트와 자동 재실행을 제공합니다.",
    )
    p.add_argument("--source-directory", type=Path, required=True)
    p.add_argument("--work-cache", type=Path)
    p.add_argument("--reuse-bundle", type=Path)
    p.add_argument("--reuse-source-revision")
    args = p.parse_args()
    package_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    if args.version != __version__ or args.version != package_version:
        raise ValueError("Installer, application and package versions must agree")
    if sys.platform != "win32":
        raise RuntimeError("Build on Windows x64")
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "artifacts") or out.exists():
        raise ValueError("Choose a new artifacts directory")
    changed = subprocess.check_output(
        [
            "git",
            "diff",
            "HEAD",
            "--name-only",
            "--",
            "src",
            "installer",
            "pyproject.toml",
        ],
        cwd=ROOT,
        text=True,
    )
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "src", "installer"],
        cwd=ROOT,
        text=True,
    )
    if changed.strip() or untracked.strip():
        raise ValueError("Commit package inputs before building")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    out.mkdir(parents=True)
    environment = {**os.environ, "XRT_BUILD_JDK": str(args.jdk.resolve())}
    bundle = out / "dist/SiCXrtAnalyzer"
    if args.reuse_bundle:
        import shutil

        candidate = args.reuse_bundle.resolve()
        if (
            not candidate.is_relative_to(ROOT / "artifacts")
            or not args.reuse_source_revision
        ):
            raise ValueError("Verified task bundle and its source revision required")
        diff = subprocess.check_output(
            [
                "git",
                "diff",
                args.reuse_source_revision,
                revision,
                "--name-only",
                "--",
                "src",
                "installer/launcher.py",
            ],
            cwd=ROOT,
            text=True,
        )
        if diff.strip():
            raise ValueError(
                "Compiled application inputs changed; perform a full PyInstaller build"
            )
        shutil.copytree(candidate, bundle)
    else:
        cache = (args.work_cache or out / "work").resolve()
        if not cache.is_relative_to(ROOT / "artifacts"):
            raise ValueError("Task artifacts work-cache required")
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--workpath",
                str(cache),
                "--distpath",
                str(out / "dist"),
                str(ROOT / "installer/SiCXrtAnalyzer.spec"),
            ],
            cwd=ROOT,
            env=environment,
        )

    import shutil

    shutil.copyfile(
        ROOT / "installer/PYTHON-LICENSE.txt", bundle / "_internal/PYTHON-LICENSE.txt"
    )
    forbidden = {".onnx", ".pt", ".pth", ".tif", ".tiff", ".env"}
    for file in bundle.rglob("*"):
        if file.is_file() and (
            file.suffix.lower() in forbidden
            or file.name.lower() in ("admin.json", "db-password.txt")
        ):
            raise RuntimeError("Private file in package")
    helper = out / "XrtUpdateHandoff.exe"
    csc = (
        Path(os.environ.get("WINDIR", "C:/Windows"))
        / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    for source, target in [
        ("UpdateHandoff.cs", helper),
        ("NativeLauncher.cs", bundle / "SiCXrtAnalyzer.exe"),
    ]:
        run(
            [
                str(csc),
                "/nologo",
                "/target:winexe",
                "/reference:System.Windows.Forms.dll",
                "/reference:System.Drawing.dll",
                "/win32icon:"
                + str(ROOT / "src/sic_xrt_analyzer/ui/assets/app-icon.ico"),
                "/out:" + str(target),
                str(ROOT / "installer" / source),
            ],
            cwd=ROOT,
        )
    # Required lazy-loader stubs are runtime assets, not optional type hints.
    package = Path(sysconfig.get_paths()["purelib"]) / "skimage"
    for stub in package.rglob("*.pyi"):
        target = bundle / "_internal/skimage" / stub.relative_to(package)
        if not target.is_file():
            raise RuntimeError(
                "Missing runtime stub: " + str(stub.relative_to(package))
            )
    required = [
        bundle / "SiCXrtAnalyzer.exe",
        bundle / "SiCXrtApp.exe",
        bundle / "SiCXrtWorker.exe",
    ]
    required += list((bundle / "_internal/skimage").rglob("*.pyi"))
    required += list((bundle / "_internal/skimage/segmentation").glob("*.pyd"))
    required += list((bundle / "_internal/sic_xrt_analyzer/ui").glob("*.qml"))
    # Fluent is a startup dependency. Check every shipped style asset while building,
    # and keep a small critical set in the launcher's runtime integrity manifest.
    fluent_path = Path("PySide6/qml/QtQuick/Controls/FluentWinUI3")
    fluent_source = Path(sysconfig.get_paths()["purelib"]) / fluent_path
    fluent_bundle = bundle / "_internal" / fluent_path
    for asset in fluent_source.rglob("*"):
        if asset.is_file() and not (fluent_bundle / asset.relative_to(fluent_source)).is_file():
            raise RuntimeError("Missing Fluent runtime asset: " + str(asset.relative_to(fluent_source)))
    for name in ["qmldir", "Config.qml", "Button.qml", "Dialog.qml", "TextField.qml",
                 "ComboBox.qml", "FocusFrame.qml", "qtquickcontrols2fluentwinui3styleplugin.dll",
                 "impl/qmldir", "impl/ButtonBackground.qml", "impl/qtquickcontrols2fluentwinui3styleimplplugin.dll"]:
        asset = fluent_bundle / name
        if not asset.is_file():
            raise RuntimeError("Missing Fluent startup dependency: " + name)
        required.append(asset)
    lines = []
    for file in sorted(required):
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(digest + "  " + file.relative_to(bundle).as_posix())
    (bundle / "runtime-files.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    run(
        [
            str(args.compiler.resolve()),
            "/DUpdateHelper=" + str(helper),
            "/DAppVersion=" + args.version,
            "/DBundleDir=" + str(bundle),
            "/DOutputPath=" + str(out),
            str(ROOT / "installer/setup.iss"),
        ],
        cwd=ROOT,
    )
    setup = out / ("SiCXrtAnalyzer-" + args.version + "-windows-x64-setup.exe")
    with setup.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    from build_corresponding_source import build

    source = build(
        out / ("SiCXrtAnalyzer-" + args.version + "-source.zip"),
        args.version,
        revision,
        args.source_directory,
    )
    manifest = {
        "schema": "xrt_app_release/v1",
        "version": args.version,
        "platform": "windows-x64",
        "source_revision": revision,
        "filename": setup.name,
        "size": setup.stat().st_size,
        "sha256": digest,
        "components": [
            "VIEWER",
            "ROI",
            "STACK_3D",
            "PROJECTS",
            "MODEL_CLIENT",
            "IMAGEJ",
            "FIJI",
            "OPENJDK",
        ],
        "model_included": False,
        "signature": "UNSIGNED",
        "license": "GPL-3.0-only",
        "source_archive": source,
        "distribution_clearance": {
            "status": "APPROVED",
            "reference": "Publisher explicitly authorized GPLv3 with source delivery on 2026-10-13; exact revision application and Qt/PySide/OpenJDK sources and source catalogue included.",
        },
        "notes": args.notes,
        "minimum_os": "Windows 10 / 11 (64-bit)",
    }
    (out / "release.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "BUILT",
                "file": setup.name,
                "bytes": manifest["size"],
                "source_revision": revision,
                "sha256": digest,
            }
        )
    )


if __name__ == "__main__":
    main()
