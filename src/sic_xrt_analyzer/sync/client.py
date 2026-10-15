"""Persistent transmission ledger and bounded, explicit HTTP actions."""

import base64
import hashlib
import io
import json
import sqlite3
import threading
import warnings
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .protocol import digest, encode, make_batch, safe_id


class SyncError(ValueError):
    pass


def endpoint_url(value):
    value = value.strip().rstrip("/")
    u = urlsplit(value)
    if (
        u.username
        or u.password
        or u.query
        or u.fragment
        or u.path not in ("", "/")
        or not u.hostname
    ):
        raise SyncError("SERVER_ORIGIN_REQUIRED")
    if u.scheme != "https" and not (
        u.scheme == "http" and u.hostname in ("127.0.0.1", "::1")
    ):
        raise SyncError("HTTPS_REQUIRED_OUTSIDE_LOOPBACK")
    return value


class Outbox:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as s:
            s.executescript("""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,endpoint TEXT NOT NULL,project TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',receipt TEXT);
            CREATE TABLE IF NOT EXISTS receipts(endpoint TEXT NOT NULL,project TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(endpoint,project));""")
            row = s.execute(
                "SELECT value FROM settings WHERE key='client_id'"
            ).fetchone()
            if not row:
                s.execute("INSERT INTO settings VALUES('client_id',?)", (str(uuid4()),))

    def db(self):
        return sqlite3.connect(self.path, timeout=5)

    @property
    def client_id(self):
        with self.db() as s:
            return s.execute(
                "SELECT value FROM settings WHERE key='client_id'"
            ).fetchone()[0]

    def set_client_id(self, value):
        safe_id(value)
        with self.db() as s:
            if s.execute("SELECT COUNT(*) FROM batches").fetchone()[0]:
                raise SyncError("DEVICE_ID_LOCKED_AFTER_QUEUE")
            s.execute("UPDATE settings SET value=? WHERE key='client_id'", (value,))

    def receipt(self, endpoint, project_id):
        with self.db() as s:
            row = s.execute(
                "SELECT payload FROM receipts WHERE endpoint=? AND project=?",
                (endpoint, project_id),
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def stage(self, endpoint, project):
        ack = self.receipt(endpoint, project.project_id)
        value = make_batch(project, self.client_id, known=ack.get("inventory"))
        with self.db() as s:
            existing = s.execute(
                "SELECT payload FROM batches WHERE endpoint=? AND project=? AND kind='metadata' AND state!='ACKNOWLEDGED' ORDER BY rowid",
                (endpoint, project.project_id),
            ).fetchall()
            for (payload,) in existing:
                old = json.loads(payload)
                if old["snapshot_hash"] == value["snapshot_hash"]:
                    return old
            s.execute(
                "INSERT INTO batches(id,endpoint,project,kind,payload,digest,state) VALUES(?,?,?,?,?,?,?)",
                (
                    value["batch_id"],
                    endpoint,
                    project.project_id,
                    "metadata",
                    encode(value).decode(),
                    value["payload_hash"],
                    "PENDING",
                ),
            )
        return value

    def pending(self, endpoint, project_id, kind="metadata"):
        with self.db() as s:
            return [
                (r[0], json.loads(r[1]))
                for r in s.execute(
                    "SELECT id,payload FROM batches WHERE endpoint=? AND project=? AND kind=? AND state!='ACKNOWLEDGED' ORDER BY rowid LIMIT 20",
                    (endpoint, project_id, kind),
                )
            ]

    def pending_count(self, endpoint, project_id, kind="metadata"):
        with self.db() as s:
            return s.execute(
                "SELECT COUNT(*) FROM batches WHERE endpoint=? AND project=? AND kind=? AND state!='ACKNOWLEDGED'",
                (endpoint, project_id, kind),
            ).fetchone()[0]

    def attempt(self, ident, error=""):
        with self.db() as s:
            s.execute(
                "UPDATE batches SET attempts=attempts+1,state='SENT',error=? WHERE id=? AND state!='ACKNOWLEDGED'",
                (error, ident),
            )

    def failed(self, ident, code):
        with self.db() as s:
            s.execute(
                "UPDATE batches SET state='RETRY',error=? WHERE id=? AND state!='ACKNOWLEDGED'",
                (code, ident),
            )

    def acknowledge(self, ident, ack):
        with self.db() as s:
            row = s.execute(
                "SELECT endpoint,project,payload,kind FROM batches WHERE id=?", (ident,)
            ).fetchone()
            if not row:
                raise SyncError("UNKNOWN_OUTBOX_BATCH")
            endpoint, project, payload, kind = row
            value = json.loads(payload)
            if kind == "metadata":
                for k in (
                    "batch_id",
                    "project_id",
                    "client_id",
                    "payload_hash",
                    "snapshot_hash",
                    "project_revision",
                    "inventory",
                ):
                    if ack.get(k) != value[k]:
                        raise SyncError("ACK_MISMATCH")
                if ack.get("status") != "ACKNOWLEDGED":
                    raise SyncError("ACK_NOT_COMPLETE")
                s.execute(
                    "INSERT INTO receipts VALUES(?,?,?) ON CONFLICT(endpoint,project) DO UPDATE SET payload=excluded.payload",
                    (endpoint, project, encode(ack).decode()),
                )
            elif (ack.get("status"), ack.get("asset_id"), ack.get("crop_hash")) != (
                "ACKNOWLEDGED",
                digest(value["metadata"]),
                value["metadata"]["crop_hash"],
            ):
                raise SyncError("CROP_ACK_MISMATCH")
            s.execute(
                "UPDATE batches SET state='ACKNOWLEDGED',receipt=?,error='' WHERE id=?",
                (encode(ack).decode(), ident),
            )

    def stage_crop(self, endpoint, project_id, body):
        ident = str(uuid4())
        with self.db() as s:
            found = s.execute(
                "SELECT id FROM batches WHERE endpoint=? AND project=? AND kind='crop' AND digest=? AND state!='ACKNOWLEDGED' ORDER BY rowid LIMIT 1",
                (endpoint, project_id, digest(body)),
            ).fetchone()
            if found:
                return found[0]
            s.execute(
                "INSERT INTO batches(id,endpoint,project,kind,payload,digest,state) VALUES(?,?,?,?,?,?,?)",
                (
                    ident,
                    endpoint,
                    project_id,
                    "crop",
                    encode(body).decode(),
                    digest(body),
                    "PENDING",
                ),
            )
        return ident


class Transport:
    def __init__(self, endpoint, token, cancel=None):
        self.endpoint = endpoint_url(endpoint)
        if not token or not token.startswith("xrt_") or len(token) > 200:
            raise SyncError("CREDENTIAL_REQUIRED")
        self.token = token
        self.cancel = cancel or threading.Event()

    def request(self, method, path, body=None):
        import httpx

        for attempt in range(3):
            if self.cancel.is_set():
                raise SyncError("CANCELED")
            try:
                with (
                    httpx.Client(
                        timeout=httpx.Timeout(10, connect=3),
                        follow_redirects=False,
                        trust_env=False,
                    ) as client,
                    client.stream(
                        method,
                        self.endpoint + path,
                        headers={
                            "Authorization": "Bearer " + self.token,
                            "Content-Type": "application/json",
                        },
                        content=encode(body) if body is not None else None,
                    ) as response,
                ):
                    chunks = []
                    size = 0
                    for part in response.iter_bytes():
                        if self.cancel.is_set():
                            raise SyncError("CANCELED")
                        size += len(part)
                        if size > 64 * 1024**2:
                            raise SyncError("RESPONSE_TOO_LARGE")
                        chunks.append(part)
                    status = response.status_code
                    if status == 401:
                        raise SyncError("AUTHENTICATION_FAILED")
                    if status == 403:
                        raise SyncError("PROJECT_ACCESS_DENIED")
                    if status == 409:
                        raise SyncError("SYNC_CONFLICT")
                    if status in (502, 503, 504):
                        raise httpx.ConnectError("SERVER_UNAVAILABLE")
                    if not 200 <= status < 300:
                        raise SyncError("SERVER_REJECTED_" + str(status))
                    from .protocol import read_json

                    try:
                        value = read_json(b"".join(chunks))
                    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                        raise SyncError("INVALID_SERVER_RESPONSE") from exc
                    if self.cancel.is_set():
                        raise SyncError("CANCELED")
                    return value
            except httpx.TimeoutException:
                code = "TIMEOUT"
            except httpx.TransportError:
                code = "OFFLINE"
            if attempt == 2:
                raise SyncError(code)
            if self.cancel.wait(0.25 * 2**attempt):
                raise SyncError("CANCELED")


def synchronize(outbox, project, transport):
    outbox.stage(transport.endpoint, project)
    result = None
    for ident, value in outbox.pending(transport.endpoint, project.project_id):
        outbox.attempt(ident)
        try:
            result = transport.request("POST", "/api/v1/sync/batches", value)
            outbox.acknowledge(ident, result)
        except (ValueError, OSError) as exc:
            code = str(exc) if isinstance(exc, SyncError) else "OUTBOX_UNAVAILABLE"
            outbox.failed(ident, code)
            raise SyncError(code) from None
    if outbox.pending(transport.endpoint, project.project_id):
        raise SyncError("MORE_PENDING_BATCHES_RETRY")
    return result


def make_crop(
    project,
    source_id,
    run_id,
    target_type,
    target_id,
    rectangle,
    *,
    consent=False,
    cancel=None,
):
    from PIL import Image

    if consent is not True:
        raise SyncError("EXPLICIT_CROP_CONSENT_REQUIRED")
    source = next(s for s in project.image_sources if s.source_id == source_id)
    run = next(r for r in project.analysis_runs if r.run_id == run_id)
    if (
        run.source_id != source_id
        or not source.display_name.lower().endswith((".jpg", ".jpeg"))
        or (source.dtype, source.channels, source.page_count) != ("uint8", 3, 1)
    ):
        raise SyncError("JPEG_CROP_ONLY")
    targets = (
        project.observations
        if target_type == "OBSERVATION"
        else project.defect_instances
        if target_type == "DEFECT_INSTANCE"
        else ()
    )
    target = next(
        (
            o
            for o in targets
            if getattr(o, "observation_id", getattr(o, "instance_id", None))
            == target_id
        ),
        None,
    )
    if (
        not target
        or (target_type == "OBSERVATION" and target.run_id != run_id)
        or (target_type == "DEFECT_INSTANCE" and target.source_id != source_id)
    ):
        raise SyncError("CROP_TARGET_MISMATCH")
    reviews = [
        e.review_id
        for e in project.review_events
        if e.target_id == target_id and e.target_type.value == target_type
    ]
    if not reviews or len(reviews) > 100 or not source.content_hash:
        raise SyncError("VERIFIED_REVIEWED_SOURCE_REQUIRED")
    x, y, w, h = rectangle
    if (
        any(type(v) is not int for v in rectangle)
        or min(x, y) < 0
        or min(w, h) < 1
        or max(w, h) > 1024
        or x + w > source.width
        or y + h > source.height
        or w * h >= source.width * source.height
    ):
        raise SyncError("CROP_BOUNDS_OR_WHOLE_SOURCE")
    path = Path(source.source_reference)
    before = path.stat()
    if (before.st_size, before.st_mtime_ns) != (
        source.file_identity.file_size,
        source.file_identity.mtime_ns,
    ):
        raise SyncError("SOURCE_CHANGED")
    with path.open("rb") as file:
        sha = hashlib.sha256()
        for part in iter(lambda: file.read(1024 * 1024), b""):
            if cancel and cancel.is_set():
                raise SyncError("CANCELED")
            sha.update(part)
        if sha.hexdigest() != source.content_hash.value:
            raise SyncError("SOURCE_HASH_MISMATCH")
        file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(file) as image:
                if (
                    image.format != "JPEG"
                    or image.mode != "RGB"
                    or image.size != (source.width, source.height)
                ):
                    raise SyncError("SOURCE_FORMAT_CHANGED")
                crop = image.crop((x, y, x + w, y + h))
                pixels = crop.tobytes()
                data = io.BytesIO()
                crop.save(data, format="PNG")
                raw = data.getvalue()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SyncError("SOURCE_CHANGED")
    if len(raw) > 4 * 1024**2:
        raise SyncError("CROP_TOO_LARGE")
    meta = {
        "source_id": source_id,
        "run_id": run_id,
        "target_type": target_type,
        "target_id": target_id,
        "crop_x": x,
        "crop_y": y,
        "crop_width": w,
        "crop_height": h,
        "source_dtype": source.dtype,
        "source_channels": source.channels,
        "source_hash": source.content_hash.value,
        "crop_hash": hashlib.sha256(raw).hexdigest(),
        "pixel_hash": hashlib.sha256(pixels).hexdigest(),
        "linked_review_ids": reviews,
        "geometry_coordinate_space": "ORIGINAL",
        "mime_type": "image/png",
    }
    return {
        "metadata": meta,
        "image_base64": base64.b64encode(raw).decode(),
        "consent": True,
    }
