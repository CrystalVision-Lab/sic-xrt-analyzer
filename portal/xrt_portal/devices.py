"""Browser grants: random bearer cookies, hashed at rest, checked on every request."""

import json
import secrets
import time
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .store import token_hash

DEVICE_COOKIE = "xrt_site_device"
LIFETIME = 180 * 86400
# A rejected or revoked browser may ask again; pending/approved ones keep their record.
FINAL_STATES = ("REJECTED", "REVOKED")


class Devices:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS site_devices (
              id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              affiliation TEXT NOT NULL, device_name TEXT NOT NULL,
              user_agent TEXT NOT NULL, platform TEXT NOT NULL,
              status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
              revision INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
              decided_by TEXT, decided_at REAL
            );
            CREATE TABLE IF NOT EXISTS site_request_limits (
              peer TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS site_request_time ON site_request_limits(created);
            """)

    def get(self, token):
        if not token or len(token) > 128:
            return None
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM site_devices WHERE digest=? AND expires>?",
                             (token_hash(token), time.time())).fetchone()
        return dict(row) if row else None

    @staticmethod
    def public(row):
        return {k: row[k] for k in ("id", "status", "created", "expires", "reason")}

    def request(self, fields, agent, peer):
        now = time.time()
        token = secrets.token_urlsafe(48)
        ident = str(uuid4())
        with self.store.connect() as db:
            # Persist limits across restarts, serialize concurrent first-time requests.
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM site_request_limits WHERE created<?", (now - 3600,))
            total, matching = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(peer=?),0) FROM site_request_limits",
                (token_hash(peer),),
            ).fetchone()
            if total >= 200 or matching >= 30:
                raise HTTPException(429, "DEVICE_REQUEST_RATE_LIMITED")
            db.execute("INSERT INTO site_request_limits VALUES(?,?)", (token_hash(peer), now))
            db.execute(
                "INSERT INTO site_devices(id,digest,name,affiliation,device_name,user_agent,"
                "platform,status,created,expires) VALUES(?,?,?,?,?,?,?,'PENDING',?,?)",
                (ident, token_hash(token), fields["name"], fields["affiliation"],
                 fields["device_name"], agent[:512], fields["platform"], now, now + LIFETIME),
            )
            db.execute("INSERT INTO portal_audit(actor,action,detail,created) VALUES(NULL,?,?,?)",
                       ("SITE_DEVICE_REQUESTED", json.dumps({"device_id": ident}), now))
        return token, self.public(self.get(token))

    def listing(self):
        with self.store.connect() as db:
            return [{k: v for k, v in dict(r).items() if k != "digest"} for r in db.execute(
                "SELECT * FROM site_devices ORDER BY (status='PENDING') DESC,created DESC LIMIT 1000"
            )]

    def decide(self, ident, status, revision, reason, actor):
        if status not in ("APPROVED", "REJECTED", "REVOKED"):
            raise HTTPException(422, "DEVICE_STATE")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM site_devices WHERE id=?", (ident,)).fetchone()
            if not row:
                raise HTTPException(404, "DEVICE_NOT_FOUND")
            if row["revision"] != revision or row["expires"] <= time.time():
                raise HTTPException(409, "DEVICE_CHANGED_OR_EXPIRED")
            if (status == "REVOKED" and row["status"] != "APPROVED") or (
                status == "REJECTED" and row["status"] != "PENDING"
            ) or status == row["status"]:
                raise HTTPException(409, "DEVICE_STATE_CONFLICT")
            now = time.time()
            # Approval starts the full lifetime; waiting for a decision must not shorten it.
            expires = now + LIFETIME if status == "APPROVED" else row["expires"]
            db.execute("UPDATE site_devices SET status=?,revision=revision+1,reason=?,"
                       "decided_by=?,decided_at=?,expires=? WHERE id=?",
                       (status, reason, actor, now, expires, ident))
            db.execute("INSERT INTO portal_audit(actor,action,detail,created) VALUES(?,?,?,?)",
                       (actor, "SITE_DEVICE_" + status,
                        json.dumps({"device_id": ident, "reason": reason}), time.time()))


def install_access(app, store, session, administrator, body, origin):
    devices = Devices(store)
    app.state.devices = devices

    def allowed(request):
        row = devices.get(request.cookies.get(DEVICE_COOKIE, ""))
        if row and row["status"] == "APPROVED":
            return True
        admin = store.get_session(request.cookies.get("xrt_portal_session", ""))
        if admin and admin["user"]["role"] == "ADMIN":
            administrator(admin)
            return True
        return False

    def keep_cookie(response, request, row):
        # Align the browser cookie with the server-side lifetime (approval extends it).
        remaining = int(row["expires"] - time.time())
        # Same-origin GETs carry no Origin header; only loopback hosts are plain HTTP.
        host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
        if remaining > 0:
            response.set_cookie(DEVICE_COOKIE, request.cookies[DEVICE_COOKIE], max_age=remaining,
                                httponly=True, samesite="strict", path="/",
                                secure=host not in ("localhost", "127.0.0.1", "::1"))

    @app.middleware("http")
    async def site_gate(request, call_next):
        path = request.url.path
        exempt = path in ("/portal-api/status", "/portal-api/login", "/portal-api/session",
                          "/portal-api/logout", "/portal-api/access", "/portal-api/access/request")
        # Admin/research routes retain their stronger, live upstream ADMIN guard.
        if path.startswith("/portal-api/") and not exempt and not path.startswith(
            ("/portal-api/admin/", "/portal-api/research/")
        ):
            try:
                if not await run_in_threadpool(allowed, request):
                    raise HTTPException(403, "DEVICE_APPROVAL_REQUIRED")
            except (HTTPException, httpx.HTTPError) as exc:
                response = JSONResponse(
                    {"detail": exc.detail if isinstance(exc, HTTPException) else "AUTHORITY_UNAVAILABLE"},
                    status_code=exc.status_code if isinstance(exc, HTTPException) else 503,
                )
                response.headers["Cache-Control"] = "no-store"
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response
        return await call_next(request)

    @app.get("/portal-api/access/check")
    def check():
        return Response(status_code=204)

    @app.get("/portal-api/access")
    def access(request: Request):
        row = devices.get(request.cookies.get(DEVICE_COOKIE, ""))
        response = JSONResponse({"allowed": allowed(request),
                                 "device": devices.public(row) if row else None})
        if row and row["status"] == "APPROVED":
            keep_cookie(response, request, row)
        return response

    @app.post("/portal-api/access/request")
    async def request_access(request: Request):
        secure = origin(request)
        fields = await body(request, 4096)
        if set(fields) != {"name", "affiliation", "device_name", "platform"} or any(
            not isinstance(v, str) or not 1 <= len(v.strip()) <= 120 for v in fields.values()
        ):
            raise HTTPException(422, "DEVICE_REQUEST_FIELDS")
        old = devices.get(request.cookies.get(DEVICE_COOKIE, ""))
        if old and old["status"] not in FINAL_STATES:
            return devices.public(old)
        token, data = await run_in_threadpool(
            devices.request, {k: v.strip() for k, v in fields.items()},
            request.headers.get("user-agent", ""), request.client.host if request.client else "unknown",
        )
        response = JSONResponse(data, status_code=201)
        response.set_cookie(DEVICE_COOKIE, token, max_age=LIFETIME, httponly=True,
                            secure=secure, samesite="strict", path="/")
        return response

    @app.get("/portal-api/admin/site-devices")
    def device_list(request: Request):
        administrator(session(request))
        return devices.listing()

    @app.post("/portal-api/admin/site-devices/{ident}/state")
    async def device_state(ident: str, request: Request):
        user = await run_in_threadpool(administrator, session(request))
        fields = await body(request, 4096)
        if set(fields) != {"status", "revision", "reason"} or (
            not isinstance(fields["status"], str)
            or type(fields["revision"]) is not int
            or not isinstance(fields["reason"], str)
            or not 1 <= len(fields["reason"].strip()) <= 500
        ):
            raise HTTPException(422, "DEVICE_DECISION_FIELDS")
        await run_in_threadpool(devices.decide, ident, fields["status"], fields["revision"],
                               fields["reason"].strip(), user["id"])
        return {"status": "UPDATED"}
