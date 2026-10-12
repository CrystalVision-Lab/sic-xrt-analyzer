"""User model store: immutable directories, durable pointer, no inference/result writes."""

import contextlib
import os
import shutil
import sys
from uuid import uuid4

from .contracts import (
    MAX_METADATA,
    MODEL_QUOTA,
    canonical,
    file_sha,
    read_json,
    safe_name,
    safe_path,
    verify_release,
)
from .validation import validate_bundle


def atomic_json(path, value):
    path = safe_path(path)
    temporary = path.with_name("." + path.name + "-" + uuid4().hex)
    try:
        with temporary.open("xb") as f:
            f.write(canonical(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ModelStore:
    def __init__(self, root):
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def exclusive(self):
        path = safe_path(self.root / ".transaction.lock")
        with path.open("a+b") as f:
            if path.stat().st_size == 0:
                f.write(b"0")
                f.flush()
            f.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                f.seek(0)
                if sys.platform == "win32":
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def state(self):
        path = self.root / "state.json"
        return (
            read_json(safe_path(path).read_bytes())
            if path.exists()
            else {"current": None, "previous": None, "sequences": {}, "revoked": []}
        )

    def remember(self, origin, channel, envelope, revoked=False):
        with self.exclusive():
            state = self.state()
            m = envelope["metadata"]
            key = origin + "|" + channel
            state["sequences"][key] = max(
                state["sequences"].get(key, 0), m["release_sequence"]
            )
            if revoked and m["release_id"] not in state["revoked"]:
                state["revoked"].append(m["release_id"])
            atomic_json(self.root / "state.json", state)

    def installed(self):
        rows = []
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                try:
                    e = read_json(safe_path(p / "release.json").read_bytes())
                    m = e["metadata"]
                    rows.append(
                        {
                            "release_id": m["release_id"],
                            "model_id": m["model_id"],
                            "version": m["model_version"],
                            "channel": m["channel"],
                        }
                    )
                except (OSError, ValueError, KeyError):
                    continue
        return rows

    def verify_installed(self, record, trust):
        if "legacy_bundle" in record:
            root = safe_path(record["legacy_bundle"])
            if file_sha(root / "model.onnx") != record["model_hash"]:
                raise ValueError("PREVIOUS_MODEL_CORRUPTED")
            return root
        root = safe_path(self.root / safe_name(record["release_id"]))
        envelope = read_json((root / "release.json").read_bytes())
        m = verify_release(
            envelope,
            trust,
            record["origin"],
            channel=record["channel"],
            allow_expired=True,
        )
        if (
            m["release_id"] != record["release_id"]
            or m["release_id"] in self.state()["revoked"]
        ):
            raise ValueError("INSTALLED_MODEL_REVOKED")
        for name, k, limit in (
            ("model.onnx", "model_sha256", 64 * 1024**2),
            ("manifest.json", "manifest_sha256", MAX_METADATA),
        ):
            if file_sha(root / name, limit) != m[k]:
                raise ValueError("INSTALLED_MODEL_CORRUPTED")
        return root

    def install(
        self,
        client,
        envelope,
        trust,
        channel="STABLE",
        progress=None,
        validator=validate_bundle,
    ):
        origin = client.origin
        minimum = self.state()["sequences"].get(origin + "|" + channel, 0)
        m = verify_release(
            envelope, trust, origin, channel=channel, minimum_sequence=minimum
        )
        if m["release_id"] in self.state()["revoked"]:
            raise ValueError("RELEASE_REVOKED")
        final = self.root / safe_name(m["release_id"])
        record = {"release_id": m["release_id"], "origin": origin, "channel": channel}
        with self.exclusive():
            if final.exists():
                self.verify_installed(record, trust)
                return record
            if shutil.disk_usage(self.root).free < m["model_bytes"] * 2 + 16 * 1024**2:
                raise ValueError("INSUFFICIENT_MODEL_DISK")
            if (
                sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
                + m["model_bytes"]
                + m["manifest_bytes"]
                > MODEL_QUOTA
            ):
                raise ValueError("LOCAL_MODEL_QUOTA")
            stage = self.root / (".staging-" + uuid4().hex)
            stage.mkdir(mode=0o700)
            try:
                client.download(
                    m["release_id"],
                    "manifest",
                    stage / "manifest.json",
                    m["manifest_bytes"],
                    m["manifest_sha256"],
                )
                client.download(
                    m["release_id"],
                    "model",
                    stage / "model.onnx",
                    m["model_bytes"],
                    m["model_sha256"],
                    progress,
                )
                if validator is validate_bundle:
                    validator(stage, cancel=client.cancel)
                else:
                    validator(stage)
                client.check()
                live = client.status(m["release_id"])
                if live["status"] != "AVAILABLE" or live["release"] != envelope:
                    raise ValueError("RELEASE_STATUS_CHANGED")
                (stage / "release.json").write_bytes(canonical(envelope))
                client.check()
                stage.rename(final)
            # Installation alone never changes current model or selected research bundle.
            finally:
                if stage.exists():
                    shutil.rmtree(safe_path(stage))
        return record

    def activate(self, record, previous_legacy=None):
        with self.exclusive():
            state = self.state()
            if state["current"] != record:
                state["previous"] = state["current"] or previous_legacy
                state["current"] = record
                atomic_json(self.root / "state.json", state)

    def rollback_record(self):
        return self.state()["previous"]

    def recover_record(self, trust):
        state = self.state()
        for record in (state["current"], state["previous"]):
            if record:
                try:
                    self.verify_installed(record, trust)
                    return record
                except (ValueError, OSError, KeyError):
                    continue
        return None
