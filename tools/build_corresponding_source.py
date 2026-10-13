"""Archive committed application/build source and verified public third-party source mirrors."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(destination, version, revision, upstream):
    upstream = Path(upstream).resolve()
    if not upstream.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Source mirrors must be under artifacts")
    entries = json.loads((upstream / "upstream.json").read_text(encoding="utf-8"))
    entries.append(
        json.loads((upstream / "openjdk-source.json").read_text(encoding="utf-8"))
    )
    catalog = json.loads((upstream / "fiji-catalog.json").read_text(encoding="utf-8"))
    entries.extend(r for r in catalog["source_inventory"] if r["status"] == "MIRRORED")
    for row in entries:
        p = upstream / row["filename"]
        if (
            not p.resolve().is_relative_to(upstream)
            or p.is_symlink()
            or not p.is_file()
            or sha(p) != row["sha256"]
        ):
            raise ValueError("Source mirror integrity mismatch")
    destination = Path(destination).resolve()
    if (
        not destination.is_relative_to(ROOT / "artifacts")
        or destination.suffix != ".zip"
        or destination.exists()
    ):
        raise ValueError("Choose a new artifacts source ZIP path")
    with tempfile.TemporaryDirectory(
        dir=destination.parent, prefix="source-archive-"
    ) as tmp:
        app = Path(tmp) / "application.zip"
        paths = [
            "src",
            "installer",
            "tools",
            "tests",
            "server",
            "portal",
            "web",
            "deploy",
            ".github",
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "NOTICE",
            ".gitignore",
            ".dockerignore",
        ]
        subprocess.run(
            [
                "git",
                "archive",
                "--format=zip",
                "--output=" + str(app),
                revision,
                *paths,
            ],
            cwd=ROOT,
            check=True,
        )
        with (
            zipfile.ZipFile(
                destination, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as out,
            zipfile.ZipFile(app) as git,
        ):
            for info in git.infolist():
                path = Path(info.filename)
                if info.is_dir():
                    continue
                if path.suffix.lower() in {
                    ".onnx",
                    ".pt",
                    ".pth",
                    ".tif",
                    ".tiff",
                    ".npy",
                    ".npz",
                    ".pyc",
                    ".tsbuildinfo",
                } or path.name in {"admin.json", "db-password.txt", ".env"}:
                    raise ValueError("Forbidden artifact in committed source")
                out.writestr("application/" + info.filename, git.read(info))
            for row in entries:
                out.write(
                    upstream / row["filename"],
                    "third-party/" + row["filename"],
                    compress_type=zipfile.ZIP_STORED,
                )
            for name in ("upstream.json", "openjdk-source.json", "fiji-catalog.json"):
                out.write(upstream / name, "third-party/" + name)
            out.writestr(
                "SOURCE-IDENTITY.json",
                json.dumps(
                    {
                        "version": version,
                        "source_revision": revision,
                        "license": "GPL-3.0-only",
                        "application_prefix": "application/",
                        "mirrored_third_party_sources": len(entries),
                    },
                    indent=2,
                ),
            )
    return {
        "filename": destination.name,
        "sha256": sha(destination),
        "size": destination.stat().st_size,
        "source_revision": revision,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--version", default="0.1.0")
    a = p.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    print(json.dumps(build(a.output, a.version, revision, a.upstream)))


if __name__ == "__main__":
    main()
