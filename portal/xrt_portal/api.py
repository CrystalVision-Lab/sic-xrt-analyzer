"""Read-only research BFF; only its independent program-release ledger is editable."""

import json
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .store import Store

COOKIE = "xrt_portal_session"


class Limit:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = OrderedDict()

    def check(self, key):
        with self.lock:
            now = time.monotonic()
            values = [t for t in self.rows.get(key, []) if now - t < 600]
            if len(values) >= 8:
                raise HTTPException(429, "LOGIN_RATE_LIMITED")
            self.rows[key] = values + [now]
            self.rows.move_to_end(key)
            while len(self.rows) > 2048:
                self.rows.popitem(last=False)


def origin(request):
    o = urlsplit(request.headers.get("origin", ""))
    if o.netloc != request.headers.get("host") or o.path or o.query or o.fragment:
        raise HTTPException(403, "SAME_ORIGIN_REQUIRED")
    local = o.hostname in ("localhost", "127.0.0.1", "::1")
    if o.scheme != "https" and not (local and o.scheme == "http"):
        raise HTTPException(403, "HTTPS_REQUIRED")
    return not local


def create_app(state=None, downloads=None, key=None, upstream=None, transport=None):
    @asynccontextmanager
    async def lifespan(_app):
        yield
        client.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    key = (
        key
        or Path(os.getenv("XRT_PORTAL_KEY_FILE", "/run/secrets/portal_key"))
        .read_bytes()
        .strip()
    )
    store = Store(
        state or os.getenv("XRT_PORTAL_STATE", "/data/state"),
        downloads or os.getenv("XRT_DOWNLOAD_DIR", "/data/releases"),
        key,
    )
    app.state.store = store
    client = httpx.Client(
        base_url=upstream or os.getenv("XRT_RESEARCH_API", "http://api:8000"),
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        transport=transport,
    )
    app.state.client = client
    limiter = Limit()
    capacity = threading.BoundedSemaphore(4)

    @app.middleware("http")
    async def security(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    def invalid(request, exc):
        return JSONResponse({"detail": "INVALID_PORTAL_OPERATION"}, status_code=409)

    @app.exception_handler(httpx.HTTPError)
    def unavailable(request, exc):
        return JSONResponse({"detail": "RESEARCH_API_UNAVAILABLE"}, status_code=503)

    async def body(request, limit=65536):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "JSON_REQUIRED")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > limit:
                raise HTTPException(413, "BODY_TOO_LARGE")
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError()
        except (ValueError, TypeError):
            raise HTTPException(422, "INVALID_JSON") from None
        return data

    def session(request):
        row = store.get_session(request.cookies.get(COOKIE, ""))
        if not row:
            raise HTTPException(401, "SESSION_REQUIRED")
        if request.method not in ("GET", "HEAD"):
            origin(request)
            if not secrets.compare_digest(
                row["csrf"], request.headers.get("x-xrt-csrf", "")
            ):
                raise HTTPException(403, "CSRF_REQUIRED")
        return row

    def fetch(credential, path, params=None):
        # Research requests are strictly GET. No model/user/credential mutation is proxied.
        return client.get(
            "/api/v1/" + path,
            headers={"Authorization": "Bearer " + credential},
            params=params,
        )

    def administrator(row):
        response = fetch(row["credential"], "admin/statistics")
        if response.status_code in (401, 403):
            raise HTTPException(401, "ADMIN_SESSION_UNAVAILABLE")
        response.raise_for_status()
        return row["user"]

    @app.get("/portal-api/status")
    def status():
        return {
            "status": "ONLINE",
            "application_release_contract": "xrt_app_release/v1",
        }

    @app.post("/portal-api/login")
    async def login(request: Request):
        secure = origin(request)
        b = await body(request, 8192)
        if (
            set(b) != {"client_id", "credential"}
            or any(not isinstance(b[k], str) for k in b)
            or not 1 <= len(b["client_id"]) <= 128
            or not 1 <= len(b["credential"]) <= 200
        ):
            raise HTTPException(422, "LOGIN_FIELDS")
        limiter.check(b["client_id"])
        h = await run_in_threadpool(fetch, b["credential"], "health")
        a = await run_in_threadpool(fetch, b["credential"], "admin/statistics")
        if (
            h.status_code != 200
            or a.status_code != 200
            or h.json().get("client_id") != b["client_id"]
        ):
            store.audit(None, "LOGIN_REJECTED")
            raise HTTPException(401, "INVALID_ADMIN_LOGIN")
        user = {
            "id": h.json()["user_id"],
            "client_id": b["client_id"],
            "name": b["client_id"],
            "role": "ADMIN",
        }
        token, payload = await run_in_threadpool(store.session, b["credential"], user)
        response = JSONResponse(payload)
        response.set_cookie(
            COOKIE,
            token,
            max_age=7200,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/portal-api",
        )
        return response

    @app.get("/portal-api/session")
    def me(request: Request):
        row = session(request)
        administrator(row)
        return {k: row[k] for k in ("user", "csrf", "expires_at")}

    @app.post("/portal-api/logout")
    async def logout(request: Request):
        row = session(request)
        store.logout(request.cookies.get(COOKIE, ""))
        store.audit(row["user"]["id"], "LOGOUT")
        r = JSONResponse({"status": "SIGNED_OUT"})
        r.delete_cookie(COOKIE, path="/portal-api")
        return r

    @app.get("/portal-api/releases")
    def releases():
        return store.listing(public=True)

    class Download(FileResponse):
        async def __call__(self, scope, receive, send):
            try:
                return await super().__call__(scope, receive, send)
            finally:
                capacity.release()

    @app.get("/portal-api/releases/{ident}/download")
    def download(ident: str):
        r = next((r for r in store.listing(True) if r["id"] == ident), None)
        if not r:
            raise HTTPException(404, "RELEASE_UNAVAILABLE")
        m = r["manifest"]
        p = store.downloads / (m["sha256"] + ".exe")
        if p.is_symlink() or not p.is_file() or p.stat().st_size != m["size"]:
            raise HTTPException(409, "FILE_UNAVAILABLE")
        if not capacity.acquire(False):
            raise HTTPException(429, "DOWNLOAD_CAPACITY")
        try:
            with store.connect() as db:
                db.execute(
                    "INSERT INTO downloads(release_id,created) VALUES(?,?)",
                    (ident, time.time()),
                )
            return Download(
                p,
                filename=m["filename"],
                media_type="application/octet-stream",
                headers={"ETag": '"' + m["sha256"] + '"'},
            )
        except Exception:
            capacity.release()
            raise

    @app.get("/portal-api/admin/releases")
    def managed(request: Request):
        row = session(request)
        administrator(row)
        return store.listing()

    @app.get("/portal-api/admin/releases/{ident}/history")
    def history(ident: str, request: Request):
        row = session(request)
        administrator(row)
        return store.history(ident)

    @app.post("/portal-api/admin/releases/{ident}/state")
    async def change(ident: str, request: Request):
        row = session(request)
        user = await run_in_threadpool(administrator, row)
        b = await body(request)
        if set(b) != {"status", "channel", "reason", "previous_event_id"}:
            raise HTTPException(422, "RELEASE_FIELDS")
        await run_in_threadpool(
            store.transition,
            ident,
            b["status"],
            b["channel"],
            b["reason"],
            b["previous_event_id"],
            user["id"],
        )
        return {"status": "UPDATED"}

    @app.get("/portal-api/admin/audit")
    def portal_audit(request: Request):
        row = session(request)
        administrator(row)
        with store.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM portal_audit ORDER BY id DESC LIMIT 100"
                )
            ]

    @app.get("/portal-api/research/{path:path}")
    def proxy(path: str, request: Request):
        row = session(request)
        administrator(row)
        read = (
            path
            in (
                "admin/statistics",
                "admin/models/candidates",
                "admin/models/statistics",
                "admin/models/audit",
                "admin/datasets",
            )
            or re.fullmatch(
                r"admin/portal/(projects|batches|audit|users)(/[^?]*)?", path
            )
            or re.fullmatch(r"admin/portal/models/[a-zA-Z0-9-]+/evaluation", path)
            or re.fullmatch(r"projects/[a-zA-Z0-9-]+/summary", path)
            or re.fullmatch(r"admin/datasets/(eligibility|events|[a-zA-Z0-9-]+)", path)
        )
        if ".." in path or "\\" in path or not read:
            raise HTTPException(404, "ROUTE_UNAVAILABLE")
        result = fetch(
            row["credential"], path, params=list(request.query_params.multi_items())
        )
        if result.status_code in (401, 403):
            raise HTTPException(401, "ADMIN_SESSION_UNAVAILABLE")
        if len(result.content) > 32 * 1024**2:
            raise HTTPException(413, "UPSTREAM_TOO_LARGE")
        media = result.headers.get("content-type", "application/json").split(";")[0]
        if media not in ("application/json", "image/png"):
            raise HTTPException(502, "UPSTREAM_FORMAT")
        return Response(
            result.content, status_code=result.status_code, media_type=media
        )

    return app
