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

from .devices import install_access
from .guides import Guides
from .passwords import username
from .store import Store

COOKIE = "xrt_portal_session"


class Limit:
    def __init__(self, attempts=8):
        self.lock = threading.Lock()
        self.rows = OrderedDict()
        self.attempts = attempts

    def check(self, key):
        with self.lock:
            now = time.monotonic()
            values = [t for t in self.rows.get(key, []) if now - t < 600]
            if len(values) >= self.attempts:
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


def create_app(
    state=None, downloads=None, key=None, upstream=None, transport=None, guides=None
):
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
    library = Guides(guides or os.getenv("XRT_GUIDE_DIR", "/data/guides"))
    limiter = Limit()
    password_limit = Limit(60)
    password_capacity = threading.BoundedSemaphore(2)
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
        # The same upstream ADMIN guard, without aggregating every project.
        response = fetch(row["credential"], "admin/openapi")
        if response.status_code in (401, 403):
            raise HTTPException(401, "ADMIN_SESSION_UNAVAILABLE")
        response.raise_for_status()
        return row["user"]

    @app.get("/portal-api/status")
    def status():
        return {
            "status": "ONLINE",
            "application_release_contract": "xrt_app_release/v1",
            "site_access_contract": "xrt_site_access/v1",
        }

    @app.post("/portal-api/login")
    async def login(request: Request):
        secure = origin(request)
        b = await body(request, 8192)
        account = None
        if any(not isinstance(value, str) for value in b.values()):
            raise HTTPException(422, "LOGIN_FIELDS")
        if set(b) == {"username", "password"}:
            try:
                name = username(b["username"])
            except ValueError:
                raise HTTPException(422, "LOGIN_FIELDS") from None
            if not 1 <= len(b["password"]) <= 256:
                raise HTTPException(422, "LOGIN_FIELDS")
            # Bound both per-account guessing and cycling through arbitrary names.
            password_limit.check("password")
            limiter.check("password:" + name)
            if not password_capacity.acquire(blocking=False):
                raise HTTPException(429, "LOGIN_RATE_LIMITED")
            try:
                account = await run_in_threadpool(store.password_login, name, b["password"])
            finally:
                password_capacity.release()
            if account is None:
                store.audit(None, "LOGIN_REJECTED")
                raise HTTPException(401, "INVALID_ADMIN_LOGIN")
            credential, client_id = account["credential"], account["user"]["client_id"]
        elif (set(b) == {"client_id", "credential"}
              and 1 <= len(b["client_id"]) <= 128 and 1 <= len(b["credential"]) <= 200):
            # Keep existing local operator tooling compatible with API credentials.
            credential, client_id = b["credential"], b["client_id"]
            limiter.check(client_id)
        else:
            raise HTTPException(422, "LOGIN_FIELDS")
        h = await run_in_threadpool(fetch, credential, "health")
        a = await run_in_threadpool(fetch, credential, "admin/openapi")
        if (
            h.status_code != 200
            or a.status_code != 200
            or h.json().get("client_id") != client_id
            or (account is not None and h.json().get("user_id") != account["user"]["id"])
        ):
            store.audit(None, "LOGIN_REJECTED")
            raise HTTPException(401, "INVALID_ADMIN_LOGIN")
        user = {
            "id": h.json()["user_id"],
            "client_id": client_id,
            "name": account["account"]["username"] if account else client_id,
            "role": "ADMIN",
        }
        token, payload = await run_in_threadpool(
            store.session, credential, user, account["account"] if account else None
        )
        response = JSONResponse(payload)
        response.delete_cookie(COOKIE, path="/portal-api")
        response.set_cookie(
            COOKIE,
            token,
            max_age=7200,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
        return response

    def researcher(row):
        h = fetch(row["credential"], "health")
        if (
            h.status_code != 200
            or h.json().get("client_id") != row["user"]["client_id"]
            or h.json().get("user_id") != row["user"]["id"]
        ):
            raise HTTPException(401, "RESEARCHER_SESSION_UNAVAILABLE")
        return row["user"]

    def guide_access(row, project_id):
        researcher(row)
        response = fetch(row["credential"], "projects/" + project_id + "/summary")
        if response.status_code in (401, 403, 404):
            return False
        response.raise_for_status()
        return True

    @app.post("/portal-api/guide/login")
    async def guide_login(request: Request):
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
        if h.status_code != 200 or h.json().get("client_id") != b["client_id"]:
            raise HTTPException(401, "INVALID_RESEARCHER_LOGIN")
        user = {
            "id": h.json()["user_id"],
            "client_id": b["client_id"],
            "name": b["client_id"],
            "role": "RESEARCHER",
        }
        token, payload = await run_in_threadpool(store.session, b["credential"], user)
        response = JSONResponse(payload)
        response.delete_cookie(COOKIE, path="/portal-api")
        response.set_cookie(
            COOKIE,
            token,
            max_age=7200,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/portal-api/guide")
    def guide(request: Request):
        row = session(request)
        researcher(row)
        data = library.manifest()
        authorized = {
            pid
            for pid in {g["project_id"] for g in data["groups"]}
            if guide_access(row, pid)
        }
        groups = [
            {k: v for k, v in g.items() if k != "project_id"}
            for g in data["groups"]
            if g["project_id"] in authorized
        ]
        if not groups:
            raise HTTPException(403, "GUIDE_PROJECT_ACCESS_REQUIRED")
        return {"schema": data["schema"], "groups": groups}

    @app.get("/portal-api/guide/images/{ident}")
    def guide_image(ident: str, request: Request):
        row = session(request)
        data = library.manifest()
        groups = [
            g
            for g in data["groups"]
            if any(t.get("image_id") == ident for t in g["tabs"])
        ]
        if not groups or not any(guide_access(row, g["project_id"]) for g in groups):
            raise HTTPException(403, "GUIDE_IMAGE_ACCESS_REQUIRED")
        try:
            raw = library.image(ident, data)
        except (KeyError, ValueError, OSError):
            raise HTTPException(404, "GUIDE_IMAGE_UNAVAILABLE") from None
        return Response(raw, media_type="image/png")

    @app.get("/portal-api/guide/public")
    def public_guide():
        data = library.manifest()
        return {"schema": data["schema"], "groups": library.published_groups(data)}

    @app.get("/portal-api/guide/public/images/{ident}")
    def public_guide_image(ident: str):
        data = library.manifest()
        if not any(
            tab.get("image_id") == ident
            for group in library.published_groups(data)
            for tab in group["tabs"]
        ):
            raise HTTPException(404, "GUIDE_IMAGE_UNAVAILABLE")
        try:
            raw = library.image(ident, data)
        except (KeyError, ValueError, OSError):
            raise HTTPException(404, "GUIDE_IMAGE_UNAVAILABLE") from None
        return Response(raw, media_type="image/png")

    @app.get("/portal-api/session")
    def me(request: Request):
        row = session(request)
        (administrator if row["user"]["role"] == "ADMIN" else researcher)(row)
        return {k: row[k] for k in ("user", "csrf", "expires_at")}

    @app.post("/portal-api/logout")
    async def logout(request: Request):
        row = session(request)
        store.logout(request.cookies.get(COOKIE, ""))
        store.audit(row["user"]["id"], "LOGOUT")
        r = JSONResponse({"status": "SIGNED_OUT"})
        r.delete_cookie(COOKIE, path="/portal-api")
        r.delete_cookie(COOKIE, path="/")
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

    def release_file(ident: str, source=False):
        r = next((r for r in store.listing(True) if r["id"] == ident), None)
        if not r:
            raise HTTPException(404, "RELEASE_UNAVAILABLE")
        m = r["manifest"]["source_archive"] if source else r["manifest"]
        p = store.downloads / (m["sha256"] + (".zip" if source else ".exe"))
        if p.is_symlink() or not p.is_file() or p.stat().st_size != m["size"]:
            raise HTTPException(409, "FILE_UNAVAILABLE")
        if not capacity.acquire(False):
            raise HTTPException(429, "DOWNLOAD_CAPACITY")
        try:
            with store.connect() as db:
                if not source:
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

    @app.get("/portal-api/releases/{ident}/download")
    def download(ident: str):
        return release_file(ident)

    @app.get("/portal-api/releases/{ident}/source")
    def source_download(ident: str):
        return release_file(ident, source=True)

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
                "admin/labels/summary",
                "admin/models/candidates",
                "admin/models/statistics",
                "admin/models/audit",
                "admin/datasets",
                "admin/label-datasets",
            )
            or re.fullmatch(
                r"admin/portal/(projects|batches|audit|users)(/[^?]*)?", path
            )
            or re.fullmatch(r"admin/portal/models/[a-zA-Z0-9-]+/evaluation", path)
            or re.fullmatch(r"projects/[a-zA-Z0-9-]+/summary", path)
            or re.fullmatch(r"admin/datasets/(eligibility|events|[a-zA-Z0-9-]+)", path)
            or re.fullmatch(r"admin/label-datasets/(preview|[a-zA-Z0-9-]+(/samples)?)", path)
        )
        if ".." in path or "\\" in path or not read:
            raise HTTPException(404, "ROUTE_UNAVAILABLE")
        with client.stream(
            "GET",
            "/api/v1/" + path,
            headers={"Authorization": "Bearer " + row["credential"]},
            params=list(request.query_params.multi_items()),
        ) as upstream_response:
            parts = []
            received = 0
            for part in upstream_response.iter_bytes(65536):
                received += len(part)
                if received > 32 * 1024**2:
                    raise HTTPException(413, "UPSTREAM_TOO_LARGE")
                parts.append(part)
            result = httpx.Response(
                upstream_response.status_code,
                headers=upstream_response.headers,
                content=b"".join(parts),
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

    install_access(app, store, session, administrator, body, origin)
    return app
