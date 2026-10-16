"""Operate only the XRT portal overlay. Secrets stay private; research volumes are never removed."""

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "artifacts/sync106-private"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def compose(args, **kwargs):
    return run(
        [
            "docker",
            "compose",
            "-p",
            "xrt-research",
            "-f",
            str(ROOT / "deploy/docker-compose.yml"),
            "-f",
            str(ROOT / "deploy/portal.compose.yml"),
            *args,
        ],
        cwd=ROOT,
        **kwargs,
    )


def init():
    if not (PRIVATE / "admin.json").is_file():
        raise RuntimeError("Existing private server bootstrap credential required")
    key = PRIVATE / "portal-key.txt"
    if not key.exists():
        with key.open("xb") as f:
            f.write(Fernet.generate_key())
    Fernet(key.read_bytes().strip())
    if sys.platform == "win32":
        account = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
        run(
            [
                "icacls",
                str(key),
                "/inheritance:r",
                "/grant:r",
                account + ":F",
                "*S-1-5-18:F",
                "*S-1-5-32-544:F",
            ],
            stdout=subprocess.DEVNULL,
        )
    else:
        key.chmod(0o600)
    print("Portal key ready; plaintext secret not printed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action",
        choices=[
            "init",
            "start",
            "status",
            "logs",
            "stop",
            "register",
            "backup",
            "tunnel",
            "set-admin-login",
        ],
    )
    p.add_argument("--bundle", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--username")
    args = p.parse_args()
    if args.action == "init":
        init()
    elif args.action == "start":
        init()
        compose(["up", "-d", "--build", "api", "portal", "web"])
    elif args.action == "status":
        compose(["ps"])
    elif args.action == "logs":
        compose(["logs", "--tail", "50", "portal", "web"])
    elif args.action == "stop":
        compose(["stop", "portal", "web"])
    elif args.action == "register":
        if not args.bundle:
            raise ValueError("--bundle required")
        bundle = args.bundle.resolve()
        m = json.loads((bundle / "release.json").read_text(encoding="utf-8"))
        if not bundle.is_relative_to(ROOT / "artifacts"):
            raise ValueError("Local artifacts bundle required")
        # Credential is RO and present only in this temporary local registration process.
        compose(
            [
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-v",
                str(bundle) + ":/operation/input:ro",
                "-v",
                str(PRIVATE / "admin.json") + ":/operation/admin.json:ro",
                "release-admin",
                "python",
                "-m",
                "xrt_portal.cli",
                "--manifest",
                "/operation/input/release.json",
                "--file",
                "/operation/input/" + m["filename"],
                "--credential",
                "/operation/admin.json",
                "--source-file",
                "/operation/input/" + m["source_archive"]["filename"],
            ]
        )
    elif args.action == "set-admin-login":
        if not args.username:
            p.error("--username required")
        password = getpass.getpass("New administrator password: ")
        compose([
            "run", "--rm", "--no-deps", "-T",
            "-v", str(PRIVATE / "admin.json") + ":/operation/admin.json:ro",
            "release-admin", "python", "-m", "xrt_portal.admin_login",
            "--username", args.username, "--credential", "/operation/admin.json",
            "--password-stdin",
        ], input=password + "\n", text=True)
    elif args.action == "backup":
        if not args.output:
            raise ValueError("--output required")
        out = args.output.resolve()
        if not out.is_relative_to(PRIVATE.resolve()) or out.exists():
            raise ValueError("New private backup directory required")
        out.mkdir(parents=True)
        compose(["stop", "portal"])
        try:
            compose(
                [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-v",
                    str(out) + ":/operation/output:rw",
                    "portal",
                    "python",
                    "-m",
                    "xrt_portal.cli",
                    "--backup",
                    "/operation/output/snapshot",
                ]
            )
        finally:
            compose(["up", "-d", "portal"])
    else:
        out = (args.output or ROOT / "artifacts/distribution120/tunnel").resolve()
        if not out.is_relative_to(ROOT / "artifacts"):
            raise ValueError("Task artifacts directory required")
        out.mkdir(parents=True, exist_ok=True)
        executable = (
            Path("C:/Program Files (x86)/cloudflared/cloudflared.exe")
            if sys.platform == "win32"
            else Path("/usr/local/bin/cloudflared")
        )
        # Existing tunnels/configuration are not read, changed or stopped. Empty config prevents accidental reuse.
        config = out / "empty-config.yml"
        config.write_text("{}\n", encoding="utf-8")
        log = (out / "cloudflared.log").open("ab")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            [
                str(executable),
                "--config",
                str(config),
                "tunnel",
                "--url",
                "http://127.0.0.1:18770",
                "--no-autoupdate",
            ],
            stdout=log,
            stderr=log,
            creationflags=flags,
            start_new_session=sys.platform != "win32",
        )
        (out / "process.json").write_text(
            json.dumps({"pid": process.pid, "target": "http://127.0.0.1:18770"}),
            encoding="utf-8",
        )
        print(
            "Started dedicated temporary Cloudflare tunnel; see private task log for public URL"
        )


if __name__ == "__main__":
    main()
