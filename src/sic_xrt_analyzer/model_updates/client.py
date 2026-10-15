"""Same-origin authenticated requests and bounded streaming; no URL supplied by registry is followed."""

import hashlib
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from sic_xrt_analyzer.sync.client import endpoint_url

from .contracts import MAX_METADATA, read_json


class UpdateClient:
    def __init__(self, origin, credential, cancel=None, transport=None):
        self.origin = endpoint_url(origin)
        self.cancel = cancel or threading.Event()
        self.http = httpx.Client(
            base_url=self.origin,
            headers={
                "Authorization": "Bearer " + credential,
                "Accept-Encoding": "identity",
            },
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self.deadline = time.monotonic() + 120

    def check(self):
        if self.cancel.is_set():
            raise ValueError("UPDATE_CANCELED")
        if time.monotonic() > self.deadline:
            raise ValueError("UPDATE_TIMEOUT")

    def close(self):
        self.http.close()

    def _bytes(self, path, maximum, progress=None):
        self.check()
        with self.http.stream("GET", path) as r:
            if r.status_code != 200:
                raise ValueError("UPDATE_SERVER_UNAVAILABLE")
            if r.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("ENCODED_ARTIFACT")
            if (
                "Content-Length" in r.headers
                and int(r.headers["Content-Length"]) > maximum
            ):
                raise ValueError("DOWNLOAD_SIZE")
            total = 0
            for block in r.iter_bytes(64 * 1024):
                self.check()
                total += len(block)
                if total > maximum:
                    raise ValueError("DOWNLOAD_SIZE")
                if progress:
                    progress(total, maximum)
                yield block
        self.check()

    def json(self, path):
        return read_json(b"".join(self._bytes(path, MAX_METADATA)))

    def listing(self, channel):
        return self.json("/api/v1/models/releases?channel=" + quote(channel, safe=""))

    def status(self, release_id):
        return self.json("/api/v1/models/releases/" + quote(release_id, safe=""))

    def download(self, release_id, part, path, size, sha, progress=None):
        route = (
            "/api/v1/models/releases/"
            + quote(release_id, safe="")
            + ("/manifest" if part == "manifest" else "/download")
        )
        total = 0
        h = hashlib.sha256()
        with Path(path).open("xb") as f:
            for block in self._bytes(route, size, progress):
                f.write(block)
                h.update(block)
                total += len(block)
            f.flush()
            __import__("os").fsync(f.fileno())
        if total != size or h.hexdigest() != sha:
            raise ValueError("DOWNLOADED_HASH_OR_SIZE")
