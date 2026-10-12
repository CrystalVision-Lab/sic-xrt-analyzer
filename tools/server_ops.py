"""Operate only the named XRT Compose stack; never publish or delete its volumes."""

import argparse
import contextlib
import hashlib
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose.yml"
PRIVATE = ROOT / "artifacts/sync106-private"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def compose(project, args, **kwargs):
    return run(
        ["docker", "compose", "-p", project, "-f", str(COMPOSE), *args], **kwargs
    )


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def initialize():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        account = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
        run(
            [
                "icacls",
                str(PRIVATE),
                "/inheritance:r",
                "/grant:r",
                account + ":(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
                "*S-1-5-32-544:(OI)(CI)F",
            ],
            stdout=subprocess.DEVNULL,
        )
        for child in PRIVATE.rglob("*"):
            if child.is_file():
                run(
                    [
                        "icacls",
                        str(child),
                        "/inheritance:r",
                        "/grant:r",
                        account + ":F",
                        "*S-1-5-18:F",
                        "*S-1-5-32-544:F",
                    ],
                    stdout=subprocess.DEVNULL,
                )
    else:
        PRIVATE.chmod(0o700)
    password = PRIVATE / "db-password.txt"
    if not password.exists():
        with password.open("x") as out:
            out.write(secrets.token_urlsafe(48))
        if sys.platform != "win32":
            password.chmod(0o600)
    print("Private password file ready; credential values are not printed")


@contextlib.contextmanager
def model_snapshot_lock(project):
    """Hold the same PostgreSQL session lock used by every registry mutator."""
    api = compose(
        project, ["ps", "-aq", "api"], capture_output=True, text=True
    ).stdout.strip()
    image = (
        compose(project, ["images", "-q", "api"], capture_output=True, text=True)
        .stdout.strip()
        .splitlines()[0]
    )
    script = "from xrt_server.db import connect; import sys; e,_=connect(); c=e.connect(); c.exec_driver_sql('SELECT pg_advisory_lock(11008)'); print('LOCKED',flush=True); sys.stdin.read(); c.close(); e.dispose()"
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        project + "_default",
        "--volumes-from",
        api + ":ro",
        "-e",
        "XRT_DB_PASSWORD_FILE=/run/secrets/db_password",
        image,
        "python",
        "-c",
        script,
    ]
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    ready = queue.Queue()
    threading.Thread(
        target=lambda: ready.put(child.stdout.readline()), daemon=True
    ).start()
    try:
        try:
            if ready.get(timeout=15).strip() != "LOCKED":
                raise ValueError("Model snapshot lock failed")
        except queue.Empty as exc:
            raise TimeoutError(
                "Model snapshot lock busy; retry after registration completes"
            ) from exc
        yield
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
        child.stdout.close()


def backup(project, output):
    with model_snapshot_lock(project):
        _backup(project, output)


def _backup(project, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Backup destination must be new")
    output.mkdir(parents=True)
    identifier = str(uuid4())
    remote = "/tmp/xrt-" + identifier + ".dump"
    compose(project, ["stop", "api"])
    try:
        compose(
            project,
            [
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "xrt",
                "-d",
                "xrt",
                "-Fc",
                "-f",
                remote,
            ],
        )
        container = compose(
            project, ["ps", "-q", "postgres"], capture_output=True, text=True
        ).stdout.strip()
        run(["docker", "cp", container + ":" + remote, str(output / "postgres.dump")])
        refs = compose(
            project,
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "xrt",
                "-d",
                "xrt",
                "-tAc",
                "SELECT coalesce(jsonb_object_agg(storage_key,digest),'{}'::jsonb) FROM crop_assets",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        (output / "asset_refs.json").write_text(
            json.dumps(json.loads(refs), sort_keys=True), encoding="utf-8"
        )
        image = (
            compose(project, ["images", "-q", "api"], capture_output=True, text=True)
            .stdout.strip()
            .splitlines()[0]
        )
        api = compose(
            project, ["ps", "-aq", "api"], capture_output=True, text=True
        ).stdout.strip()
        script = """import hashlib,json,pathlib,tarfile
root=pathlib.Path('/data/assets');files={}
with tarfile.open('/backup/assets.tar','w') as archive:
 for file in sorted(root.iterdir()):
  if file.is_symlink():raise ValueError('Asset symlink')
  if file.name.endswith('.png'):
   value=hashlib.sha256(file.read_bytes()).hexdigest()
   if file.name!=value+'.png':raise ValueError('Asset digest')
   files[file.name]=value;archive.add(file,arcname=file.name)
required=json.loads(pathlib.Path('/backup/asset_refs.json').read_text())
if any(files.get(key)!=value for key,value in required.items()):raise ValueError('DB referenced asset missing or corrupted')
pathlib.Path('/backup/assets.json').write_text(json.dumps(files,sort_keys=True))
"""
        run(
            [
                "docker",
                "run",
                "--rm",
                "--volumes-from",
                api + ":ro",
                "--mount",
                "type=bind,source=" + str(output) + ",target=/backup",
                image,
                "python",
                "-c",
                script,
            ]
        )
        # API remains stopped while collecting DB/Crop/model references and volumes.
        exists = compose(
            project,
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "xrt",
                "-d",
                "xrt",
                "-tAc",
                "SELECT to_regclass('public.model_candidates') is not null",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        refs = {}
        if exists == "t":
            records = compose(
                project,
                [
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "xrt",
                    "-d",
                    "xrt",
                    "-tAc",
                    "SELECT coalesce(jsonb_agg(payload),'[]'::jsonb) FROM model_candidates",
                ],
                capture_output=True,
                text=True,
            ).stdout.strip()
            for record in json.loads(records):
                key = record["artifact_key"] + "/"
                refs[key + "model.onnx"] = record["manifest"]["model_sha256"]
                refs[key + "manifest.json"] = record["manifest_sha256"]
                refs[key + "candidate-registry.json"] = record["registry_sha256"]
        (output / "model_refs.json").write_text(
            json.dumps(refs, sort_keys=True), encoding="utf-8"
        )
        from model_blob_backup import BACKUP

        run(
            [
                "docker",
                "run",
                "--rm",
                "--volumes-from",
                api + ":ro",
                "--mount",
                "type=bind,source=" + str(output) + ",target=/backup",
                image,
                "python",
                "-c",
                BACKUP,
            ]
        )
        manifest = {
            "format": "xrt-server-backup-2",
            "project": project,
            "files": {
                name: hash_file(output / name)
                for name in (
                    "postgres.dump",
                    "assets.tar",
                    "assets.json",
                    "asset_refs.json",
                    "models.tar",
                    "models.json",
                    "model_refs.json",
                )
            },
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        print("Backup complete: database and assets with SHA-256 manifest")
    finally:
        compose(project, ["start", "api"])


def restore(project, backup_dir, port):
    if not project.startswith("xrt-restore-"):
        raise ValueError("Restore requires a separate xrt-restore-* Compose project")
    source = Path(backup_dir).resolve()
    manifest = json.loads((source / "manifest.json").read_text())
    allowed = {"postgres.dump", "assets.tar", "assets.json", "asset_refs.json"}
    if manifest["format"] == "xrt-server-backup-2":
        allowed |= {"models.tar", "models.json", "model_refs.json"}
    if (
        manifest["format"] not in ("xrt-server-backup-1", "xrt-server-backup-2")
        or set(manifest["files"]) != allowed
    ):
        raise ValueError("Backup manifest invalid")
    if any(hash_file(source / name) != sha for name, sha in manifest["files"].items()):
        raise ValueError("Backup hash mismatch")
    os.environ["XRT_API_PORT"] = str(port)
    compose(project, ["up", "-d", "postgres", "--wait"])
    tables = compose(
        project,
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "xrt",
            "-d",
            "xrt",
            "-tAc",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tables != "0":
        raise ValueError("Restore destination DB is not empty; preserved")
    remote = "/tmp/restore-" + str(uuid4()) + ".dump"
    container = compose(
        project, ["ps", "-q", "postgres"], capture_output=True, text=True
    ).stdout.strip()
    run(["docker", "cp", str(source / "postgres.dump"), container + ":" + remote])
    compose(
        project,
        [
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "-U",
            "xrt",
            "-d",
            "xrt",
            remote,
        ],
    )
    script = """import hashlib,json,pathlib,re,tarfile
root=pathlib.Path('/data/assets');root.mkdir(exist_ok=True)
expected=json.loads(pathlib.Path('/backup/assets.json').read_text());found=set()
required=json.loads(pathlib.Path('/backup/asset_refs.json').read_text())
if any(expected.get(key)!=value for key,value in required.items()):raise ValueError('DB asset reference mismatch')
with tarfile.open('/backup/assets.tar') as archive:
 for entry in archive:
  if not entry.isfile() or entry.size>4*1024**2 or not re.fullmatch(r'[0-9a-f]{64}\\.png',entry.name):raise ValueError('Unsafe archive entry')
  content=archive.extractfile(entry).read()
  sha=hashlib.sha256(content).hexdigest()
  if expected.get(entry.name)!=sha or entry.name!=sha+'.png':raise ValueError('Asset hash mismatch')
  target=root/entry.name
  if target.exists():raise ValueError('Asset destination exists')
  target.write_bytes(content);found.add(entry.name)
if found!=set(expected):raise ValueError('Asset inventory mismatch')
"""
    compose(
        project,
        [
            "run",
            "--rm",
            "--no-deps",
            "-v",
            str(source) + ":/backup:ro",
            "api",
            "python",
            "-c",
            script,
        ],
    )
    if manifest["format"] == "xrt-server-backup-2":
        from model_blob_backup import RESTORE

        compose(
            project,
            [
                "run",
                "--rm",
                "--no-deps",
                "-v",
                str(source) + ":/backup:ro",
                "-v",
                project + "_models:/data/models",
                "api",
                "python",
                "-c",
                RESTORE,
            ],
        )
    compose(project, ["up", "-d", "api"])
    print("Restored to isolated Compose stack; original stack and volumes preserved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "init",
            "start",
            "stop",
            "status",
            "logs",
            "migrate",
            "bootstrap",
            "backup",
            "restore",
            "test",
            "dataset-export",
            "model-admin",
        ],
    )
    parser.add_argument("--project", default="xrt-research")
    parser.add_argument("--output")
    parser.add_argument("--backup")
    parser.add_argument("--dataset-id")
    parser.add_argument("--input")
    parser.add_argument("--signing-key")
    parser.add_argument("--admin-credential")
    parser.add_argument("--model-command", nargs=argparse.REMAINDER)
    parser.add_argument("--port", type=int, default=18767)
    args = parser.parse_args()
    if args.action == "init":
        initialize()
    elif args.action == "start":
        compose(args.project, ["up", "-d", "--build"])
    elif args.action == "stop":
        compose(args.project, ["stop"])
    elif args.action == "status":
        compose(args.project, ["ps"])
    elif args.action == "logs":
        compose(args.project, ["logs", "--tail", "100", "api"])
    elif args.action == "migrate":
        compose(
            args.project,
            [
                "exec",
                "-T",
                "api",
                "alembic",
                "-c",
                "server/alembic.ini",
                "upgrade",
                "head",
            ],
        )
    elif args.action == "bootstrap":
        compose(
            args.project,
            [
                "run",
                "--rm",
                "--no-deps",
                "-v",
                str(PRIVATE) + ":/private",
                "api",
                "python",
                "-m",
                "xrt_server.cli",
                "bootstrap",
                "--output",
                "/private/admin.json",
            ],
        )
    elif args.action == "model-admin":
        if not args.model_command:
            parser.error("--model-command required")
        run(
            [
                "docker",
                "build",
                "--target",
                "model-admin",
                "-t",
                "xrt-research-model-admin",
                "-f",
                str(ROOT / "server/Dockerfile"),
                str(ROOT),
            ]
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            args.project + "_default",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--security-opt",
            "no-new-privileges",
            "--cap-drop",
            "ALL",
            "-e",
            "XRT_DB_PASSWORD_FILE=/run/secrets/db_password",
            "-e",
            "XRT_MODEL_REALM=" + os.getenv("XRT_MODEL_REALM", "PRODUCTION"),
            "-e",
            "XRT_MODEL_REGISTRY_ID="
            + os.getenv("XRT_MODEL_REGISTRY_ID", "xrt-local-production"),
            "--mount",
            "type=bind,source="
            + str(PRIVATE / "db-password.txt")
            + ",target=/run/secrets/db_password,readonly",
            "--mount",
            "type=bind,source="
            + str(
                Path(args.admin_credential).resolve()
                if args.admin_credential
                else PRIVATE / "admin.json"
            )
            + ",target=/private/admin.json,readonly",
            "-v",
            args.project + "_assets:/data/assets:ro",
            "-v",
            args.project + "_models:/data/models",
        ]
        if args.input:
            from sic_xrt_analyzer.model_updates.contracts import safe_path

            source = safe_path(args.input)
            if not source.is_dir():
                raise ValueError("Input directory required")
            command += [
                "--mount",
                "type=bind,source=" + str(source) + ",target=/input,readonly",
            ]
        if args.output:
            output = Path(args.output).absolute()
            if output.exists() or not output.resolve().is_relative_to(
                PRIVATE.resolve()
            ):
                raise ValueError("New private operation directory required")
            from sic_xrt_analyzer.model_updates.contracts import safe_path

            safe_path(output).mkdir(parents=True)
            command += [
                "--mount",
                "type=bind,source=" + str(output) + ",target=/operation",
            ]
        if args.signing_key:
            from sic_xrt_analyzer.model_updates.contracts import safe_path

            key = safe_path(args.signing_key)
            if key.stat().st_size != 32:
                raise ValueError("Private key format")
            command += [
                "--mount",
                "type=bind,source="
                + str(key)
                + ",target=/signing/private.key,readonly",
            ]
        command += [
            "xrt-research-model-admin",
            "python",
            "-m",
            "xrt_server.model_admin",
            *args.model_command,
        ]
        if args.model_command[0] not in ("sign", "key-create"):
            command += ["--credential-file", "/private/admin.json"]
        run(command)
    elif args.action == "dataset-export":
        if not args.output or not args.dataset_id:
            parser.error("--output and --dataset-id required")
        output = Path(args.output).absolute()
        private_root = PRIVATE.resolve()
        if (
            output.exists()
            or not output.resolve().is_relative_to(private_root)
            or output == private_root
            or any(
                p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                for p in (output, *output.parents)
            )
        ):
            raise ValueError(
                "New destination under the ACL-protected private folder required"
            )
        output.mkdir(parents=True)
        compose(
            args.project,
            [
                "run",
                "--rm",
                "--no-deps",
                "-v",
                str(output) + ":/export",
                "-v",
                str(PRIVATE / "admin.json") + ":/private/admin.json:ro",
                "api",
                "python",
                "-m",
                "xrt_server.dataset_admin",
                "--credential-file",
                "/private/admin.json",
                "--dataset-id",
                args.dataset_id,
                "--output",
                "/export/dataset",
            ],
        )
        print("Explicit private export complete; no network publication")
    elif args.action == "backup":
        backup(args.project, args.output or str(PRIVATE / "backups" / str(uuid4())))
    elif args.action == "restore":
        if not args.backup:
            parser.error("--backup required")
        restore(args.project, args.backup, args.port)
    else:
        # Create only the dedicated test DB if absent; never initialize the main DB.
        exists = compose(
            args.project,
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "xrt",
                "-d",
                "postgres",
                "-tAc",
                "SELECT count(*) FROM pg_database WHERE datname='xrt_td106_test'",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if exists == "0":
            compose(
                args.project,
                ["exec", "-T", "postgres", "createdb", "-U", "xrt", "xrt_td106_test"],
            )
        run(
            [
                "docker",
                "build",
                "--target",
                "testing",
                "-t",
                "xrt-research-testing",
                "-f",
                str(ROOT / "server/Dockerfile"),
                str(ROOT),
            ]
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                args.project + "_default",
                "--mount",
                "type=bind,source="
                + str(PRIVATE / "db-password.txt")
                + ",target=/run/secrets/db_password,readonly",
                "-e",
                "XRT_DB_PASSWORD_FILE=/run/secrets/db_password",
                "-e",
                "XRT_TEST_DATABASE_NAME=xrt_td106_test",
                "xrt-research-testing",
                "python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "server/tests",
            ]
        )


if __name__ == "__main__":
    main()
