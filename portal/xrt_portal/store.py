"""Portal-only SQLite ledger and encrypted sessions; independent from research PostgreSQL."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from packaging.version import Version

MAX_FILE = 3 * 1024**3


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def token_hash(s):
    return hashlib.sha256(s.encode()).hexdigest()


class Store:
    def __init__(self, state, downloads, key):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        self.downloads = Path(downloads)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.key = Fernet(key)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, cipher BLOB NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS releases (id TEXT PRIMARY KEY, version TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, release_id TEXT NOT NULL REFERENCES releases(id), revision INTEGER NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created REAL NOT NULL, UNIQUE(release_id,revision));
            CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY, release_id TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS portal_audit (id INTEGER PRIMARY KEY, actor TEXT, action TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
            CREATE TRIGGER IF NOT EXISTS releases_no_update BEFORE UPDATE ON releases BEGIN SELECT RAISE(ABORT,'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS releases_no_delete BEFORE DELETE ON releases BEGIN SELECT RAISE(ABORT,'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.state / "portal.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def audit(self, actor, action, detail=None):
        with self.connect() as db:
            db.execute(
                "INSERT INTO portal_audit(actor,action,detail,created) VALUES(?,?,?,?)",
                (actor, action, json.dumps(detail or {}), time.time()),
            )

    def session(self, credential, user):
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expires = time.time() + 7200
        cipher = self.key.encrypt(
            json.dumps({"credential": credential, "user": user}).encode()
        )
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (token_hash(token), cipher, csrf, expires),
            )
        self.audit(user["id"], "LOGIN")
        return token, {"user": user, "csrf": csrf, "expires_at": expires}

    def get_session(self, token):
        if not token or len(token) > 160:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE digest=? AND expires>?",
                (token_hash(token), time.time()),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(self.key.decrypt(row["cipher"]))
        return {**payload, "csrf": row["csrf"], "expires_at": row["expires"]}

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (token_hash(token),))

    def register(self, payload, file, actor):
        p = dict(payload)
        required = {
            "schema",
            "version",
            "platform",
            "source_revision",
            "filename",
            "size",
            "sha256",
            "components",
            "model_included",
            "signature",
            "notes",
            "minimum_os",
        }
        if (
            set(p) != required
            or p["schema"] != "xrt_app_release/v1"
            or p["platform"] != "windows-x64"
            or p["model_included"] is not False
            or p["signature"] not in ("UNSIGNED", "AUTHENTICODE_VALID")
        ):
            raise ValueError("APP_MANIFEST_FIELDS")
        import re

        Version(p["version"])
        if (
            not re.fullmatch(r"[0-9a-f]{40}", p["source_revision"])
            or not re.fullmatch(r"[0-9a-f]{64}", p["sha256"])
            or not re.fullmatch(
                r"SiCXrtAnalyzer-[A-Za-z0-9._-]+-windows-x64-setup\.exe", p["filename"]
            )
        ):
            raise ValueError("APP_IDENTITY")
        if (
            type(p["size"]) is not int
            or not 0 < p["size"] <= MAX_FILE
            or file.is_symlink()
            or file.stat().st_size != p["size"]
            or sha(file) != p["sha256"]
        ):
            raise ValueError("APP_FILE_INTEGRITY")
        if (
            not isinstance(p["notes"], str)
            or not 10 <= len(p["notes"]) <= 10000
            or not isinstance(p["components"], list)
            or any(
                c
                not in (
                    "VIEWER",
                    "ROI",
                    "STACK_3D",
                    "PROJECTS",
                    "MODEL_CLIENT",
                    "IMAGEJ",
                    "FIJI",
                    "OPENJDK",
                )
                for c in p["components"]
            )
        ):
            raise ValueError("APP_NOTES_COMPONENTS")
        with self.connect() as db:
            old = db.execute(
                "SELECT * FROM releases WHERE version=?", (p["version"],)
            ).fetchone()
            if old:
                if json.loads(old["payload"]) != p:
                    raise ValueError("IMMUTABLE_VERSION_CONFLICT")
                return old["id"]
        dest = self.downloads / (p["sha256"] + ".exe")
        if dest.exists():
            if dest.is_symlink() or sha(dest) != p["sha256"]:
                raise ValueError("APP_CAS_CONFLICT")
        else:
            import shutil

            staging = self.downloads / (".stage-" + str(uuid4()))
            try:
                shutil.copyfile(file, staging)
                if sha(staging) != p["sha256"]:
                    raise ValueError("APP_COPY_INTEGRITY")
                os.rename(staging, dest)
            finally:
                if staging.exists():
                    staging.unlink()
        ident = str(uuid4())
        created = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO releases VALUES(?,?,?,?,?)",
                (
                    ident,
                    p["version"],
                    json.dumps(p, ensure_ascii=False),
                    actor,
                    created,
                ),
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    ident,
                    1,
                    json.dumps(
                        {
                            "status": "DRAFT",
                            "channel": "BETA",
                            "reason": "Locally registered and SHA verified",
                        }
                    ),
                    actor,
                    created,
                ),
            )
        self.audit(actor, "RELEASE_REGISTERED", {"release_id": ident})
        return ident

    def listing(self, public=False):
        with self.connect() as db:
            result = []
            for r in db.execute(
                "SELECT * FROM releases ORDER BY created DESC LIMIT 100"
            ):
                e = db.execute(
                    "SELECT * FROM events WHERE release_id=? ORDER BY revision DESC LIMIT 1",
                    (r["id"],),
                ).fetchone()
                state = json.loads(e["payload"])
                if public and state["status"] != "PUBLISHED":
                    continue
                requests = db.execute(
                    "SELECT COUNT(*) FROM downloads WHERE release_id=?", (r["id"],)
                ).fetchone()[0]
                result.append(
                    {
                        "id": r["id"],
                        "manifest": json.loads(r["payload"]),
                        "created_at": r["created"],
                        "state": state,
                        "event_id": e["id"],
                        "revision": e["revision"],
                        "download_requests": requests,
                    }
                )
            return result

    def transition(self, ident, status, channel, reason, previous, actor):
        if (
            status not in ("PUBLISHED", "WITHDRAWN")
            or channel not in ("BETA", "STABLE")
            or not isinstance(reason, str)
            or not 10 <= len(reason) <= 2000
        ):
            raise ValueError("APP_TRANSITION")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT * FROM releases WHERE id=?", (ident,)).fetchone()
            e = db.execute(
                "SELECT * FROM events WHERE release_id=? ORDER BY revision DESC LIMIT 1",
                (ident,),
            ).fetchone()
            if not r or not e or e["id"] != previous:
                raise ValueError("STALE_RELEASE_EVENT")
            if channel == "STABLE" and Version(r["version"]).is_prerelease:
                raise ValueError("PRERELEASE_NOT_STABLE")
            if status == "PUBLISHED":
                m = json.loads(r["payload"])
                file = self.downloads / (m["sha256"] + ".exe")
                if not file.is_file() or file.is_symlink() or sha(file) != m["sha256"]:
                    raise ValueError("APP_FILE_INTEGRITY")
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    ident,
                    e["revision"] + 1,
                    json.dumps(
                        {"status": status, "channel": channel, "reason": reason},
                        ensure_ascii=False,
                    ),
                    actor,
                    time.time(),
                ),
            )
        self.audit(actor, "RELEASE_" + status, {"release_id": ident})

    def history(self, ident):
        with self.connect() as db:
            return [
                {
                    "id": r["id"],
                    "revision": r["revision"],
                    "state": json.loads(r["payload"]),
                    "actor": r["actor"],
                    "created_at": r["created"],
                }
                for r in db.execute(
                    "SELECT * FROM events WHERE release_id=? ORDER BY revision",
                    (ident,),
                )
            ]

    def backup(self, destination):
        """Call with the portal stopped; create an independent ledger without browser sessions."""
        import shutil

        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        inventory = {}
        snapshot = destination / "portal.sqlite3"
        with self.connect() as db, sqlite3.connect(snapshot) as target:
            db.backup(target)
            target.execute("DELETE FROM sessions")
            target.commit()
            assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            payloads = [
                json.loads(r[0]) for r in target.execute("SELECT payload FROM releases")
            ]
        (destination / "releases").mkdir()
        for manifest in payloads:
            name = manifest["sha256"] + ".exe"
            source = self.downloads / name
            if (
                source.is_symlink()
                or not source.is_file()
                or sha(source) != manifest["sha256"]
            ):
                raise ValueError("BACKUP_RELEASE_INTEGRITY")
            output = destination / "releases" / name
            shutil.copyfile(source, output)
            if sha(output) != manifest["sha256"]:
                raise ValueError("BACKUP_COPY_INTEGRITY")
            inventory["releases/" + name] = {
                "sha256": manifest["sha256"],
                "size": output.stat().st_size,
            }
        inventory["portal.sqlite3"] = {
            "sha256": sha(snapshot),
            "size": snapshot.stat().st_size,
        }
        (destination / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": "xrt_portal_backup/v1",
                    "sessions_included": False,
                    "files": inventory,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "status": "BACKUP_COMPLETE",
            "release_files": len(payloads),
            "sessions_included": False,
        }
