"""Read-only app releases; executable bytes stay separate from models and source images."""

import hashlib
import json
import re
import shutil
import threading
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from packaging.version import Version

DEFAULT_ORIGIN = "https://gba-math-charlotte-lightweight.trycloudflare.com"
MAX_INSTALLER = 3 * 1024**3
MAX_METADATA = 1024**2


def normalize_origin(value):
    p = urlsplit(value.strip())
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.path not in ("", "/")
        or p.query
        or p.fragment
        or not re.fullmatch(r"[a-zA-Z0-9.-]+", p.hostname)
        or p.port not in (None, 443)
    ):
        raise ValueError("INVALID_ORIGIN")
    return "https://" + p.hostname.lower()


def cancelled(cancel):
    if cancel.is_set():
        raise ValueError("CANCELLED")


def digest_file(path, cancel):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024**2):
            cancelled(cancel)
            h.update(block)
    return h.hexdigest()


def valid_release(row):
    try:
        UUID(row["id"])
        m = row["manifest"]
        v = m["version"]
        if (
            not re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+)?", v)
            or m["schema"] != "xrt_app_release/v1"
            or m["platform"] != "windows-x64"
            or m["model_included"] is not False
            or m["license"] != "GPL-3.0-only"
            or m["signature"] not in ("UNSIGNED", "AUTHENTICODE_VALID")
            or m["distribution_clearance"]["status"] != "APPROVED"
            or not re.fullmatch(r"[0-9a-f]{64}", m["sha256"])
            or type(m["size"]) is not int
            or not 0 < m["size"] <= MAX_INSTALLER
            or m["filename"] != f"SiCXrtAnalyzer-{v}-windows-x64-setup.exe"
            or not re.fullmatch(r"[0-9a-f]{40}", m["source_revision"])
            or m["source_archive"]["source_revision"] != m["source_revision"]
            or not re.fullmatch(r"[0-9a-f]{64}", m["source_archive"]["sha256"])
            or not isinstance(m.get("notes"), str)
            or len(m["notes"]) > 20000
            or row["state"]["status"] != "PUBLISHED"
            or row["state"]["channel"] not in ("BETA", "STABLE")
        ):
            raise ValueError("INVALID_RELEASE")
        Version(v)
        return row
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("INVALID_RELEASE") from exc


class AppUpdateClient:
    def __init__(self, origin, cancel=None, transport=None):
        self.origin = normalize_origin(origin)
        self.cancel = cancel or threading.Event()
        self.transport = transport

    def client(self):
        # No credentials or redirect URLs from the release payload are ever used.
        return httpx.Client(
            timeout=httpx.Timeout(15, connect=8),
            follow_redirects=False,
            transport=self.transport,
            trust_env=False,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "SiC-XRT-App-Updater",
            },
        )

    def listing(self):
        with (
            self.client() as client,
            client.stream("GET", self.origin + "/portal-api/releases") as response,
        ):
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("REDIRECT_REJECTED")
            data = bytearray()
            for block in response.iter_bytes(64 * 1024):
                cancelled(self.cancel)
                data.extend(block)
                if len(data) > MAX_METADATA:
                    raise ValueError("INVALID_RELEASE")
        rows = json.loads(data)
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("INVALID_RELEASE")
        return [valid_release(row) for row in rows]

    def latest(self, current, beta=True):
        rows = [
            r
            for r in self.listing()
            if Version(r["manifest"]["version"]) > Version(current)
            and (beta or r["state"]["channel"] == "STABLE")
        ]
        return max(rows, key=lambda r: Version(r["manifest"]["version"]), default=None)

    def ensure_published(self, release):
        valid_release(release)
        if not any(
            r["id"] == release["id"] and r["manifest"] == release["manifest"]
            for r in self.listing()
        ):
            raise ValueError("RELEASE_UNAVAILABLE")

    def verify(self, path, release):
        m = release["manifest"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != m["size"]:
            raise ValueError("INTEGRITY_FAILED")
        with path.open("rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("INTEGRITY_FAILED")
        if digest_file(path, self.cancel) != m["sha256"]:
            raise ValueError("INTEGRITY_FAILED")
        cancelled(self.cancel)

    def download(self, release, directory, progress=lambda done, total: None):
        self.ensure_published(release)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            raise ValueError("CACHE_UNAVAILABLE")
        m = release["manifest"]
        target = directory / (m["sha256"] + ".exe")
        if target.exists():
            try:
                self.verify(target, release)
                return target
            except ValueError as exc:
                if str(exc) != "INTEGRITY_FAILED":
                    raise
                target.unlink()
        if shutil.disk_usage(directory).free < m["size"] + 64 * 1024**2:
            raise ValueError("NO_DISK_SPACE")
        partial = directory / (uuid4().hex + ".part")
        try:
            count = 0
            with (
                self.client() as client,
                client.stream(
                    "GET",
                    self.origin + "/portal-api/releases/" + release["id"] + "/download",
                ) as response,
            ):
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError("REDIRECT_REJECTED")
                with partial.open("xb") as output:
                    for block in response.iter_bytes(1024**2):
                        cancelled(self.cancel)
                        count += len(block)
                        if count > m["size"]:
                            raise ValueError("INTEGRITY_FAILED")
                        output.write(block)
                        progress(count, m["size"])
            self.verify(partial, release)
            self.ensure_published(release)
            cancelled(self.cancel)
            partial.replace(target)
            return target
        finally:
            partial.unlink(missing_ok=True)
