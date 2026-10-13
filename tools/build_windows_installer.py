"""Build an explicit Windows bundle; private originals/models/secrets are never collected."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jdk", type=Path, required=True)
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--version", default="0.1.0")
    args = p.parse_args()
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
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--workpath",
            str(out / "work"),
            "--distpath",
            str(out / "dist"),
            str(ROOT / "installer/SiCXrtAnalyzer.spec"),
        ],
        cwd=ROOT,
        env=environment,
    )
    bundle = out / "dist/SiCXrtAnalyzer"
    forbidden = {".onnx", ".pt", ".pth", ".tif", ".tiff", ".env"}
    for file in bundle.rglob("*"):
        if file.is_file() and (
            file.suffix.lower() in forbidden
            or file.name.lower() in ("admin.json", "db-password.txt")
        ):
            raise RuntimeError("Private file in package")
    run(
        [
            str(args.compiler.resolve()),
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
        "distribution_clearance": {
            "status": "PENDING",
            "reference": "Publisher must select GPLv3 with corresponding source or licensed commercial Qt distribution before publication.",
        },
        "notes": "첫 Windows 연구용 설치 배포. TIFF/JPG·원본 ROI·페이지 기반 3D·검수 프로젝트·ImageJ/Fiji와 별도 모델 연결을 제공합니다. 실제 Z축·결함 연속성은 미검증이며 원본·모델·인증값은 포함하지 않습니다.",
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
