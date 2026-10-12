import os
from collections import Counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from sic_xrt_analyzer.sync.protocol import MAX_BYTES, SPECS, read_json, safe_id

from .assets import store_crop
from .auth import audit, authenticate, authorize, grant, issue
from .db import connect
from .models import ENTITIES, Asset, Audit, Batch, Credential, Device, Snapshot, User
from .service import collect, review_summary, rows_for


class BodyGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] in ("POST", "PUT", "PATCH"):
            headers = dict(scope["headers"])
            if headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
                return await JSONResponse(
                    {"detail": "JSON_CONTENT_TYPE_REQUIRED"}, status_code=415
                )(scope, receive, send)
            chunks = []
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > MAX_BYTES:
                    return await JSONResponse(
                        {"detail": "PAYLOAD_TOO_LARGE"}, status_code=413
                    )(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body"):
                    break
            try:
                scope["xrt_body"] = read_json(b"".join(chunks))
            except (ValueError, TypeError, UnicodeError, RecursionError):
                return await JSONResponse({"detail": "INVALID_JSON"}, status_code=400)(
                    scope, receive, send
                )
        return await self.app(scope, receive, send)


def create_app(url=None, asset_dir=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    engine, sessions = connect(url)
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.asset_dir = asset_dir or os.getenv("XRT_ASSET_DIR", "/data/assets")
    app.add_middleware(BodyGuard)

    def record(action, actor=None, project=None):
        try:
            with sessions.begin() as s:
                audit(s, action, actor, project)
        except SQLAlchemyError:
            pass  # Never expose driver/credentials/path on audit failure.

    def identity(request: Request):
        with sessions() as s:
            try:
                user, device = authenticate(s, request.headers.get("Authorization"))
            except HTTPException:
                record("AUTH_FAILURE")
                raise
            request.state.actor = user.id
            return user, device

    def admin(pair: Annotated[tuple, Depends(identity)]):
        if pair[0].role != "ADMIN":
            raise HTTPException(403, "ADMIN_REQUIRED")
        return pair

    @app.exception_handler(ValueError)
    @app.exception_handler(TypeError)
    @app.exception_handler(KeyError)
    def invalid(request, exc):
        record("VALIDATION_REJECTED", getattr(request.state, "actor", None))
        return JSONResponse({"detail": "INVALID_SYNC_DATA"}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(OSError)
    def unavailable(request, exc):
        record("STORAGE_FAILURE", getattr(request.state, "actor", None))
        return JSONResponse({"detail": "STORAGE_UNAVAILABLE"}, status_code=503)

    @app.exception_handler(RequestValidationError)
    def request_invalid(request, exc):
        return JSONResponse({"detail": "INVALID_REQUEST"}, status_code=422)

    @app.exception_handler(HTTPException)
    def denied(request, exc):
        if exc.status_code in (403, 409):
            record(
                "SYNC_CONFLICT" if exc.status_code == 409 else "ACCESS_DENIED",
                getattr(request.state, "actor", None),
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/api/v1/health")
    def health(pair: Annotated[tuple, Depends(identity)]):
        return {
            "status": "OK",
            "database": "OK",
            "sync_protocol_version": 1,
            "user_id": pair[0].id,
            "client_id": pair[1].id,
        }

    @app.post("/api/v1/sync/batches")
    def upload(request: Request, pair: Annotated[tuple, Depends(identity)]):
        value = request.scope["xrt_body"]
        with sessions.begin() as s:
            p = authorize(s, pair[0], safe_id(value["project_id"]))
            audit(s, "SYNC_RECEIVED", pair[0].id, p.id, batch_id=value.get("batch_id"))
            return collect(s, *pair, p, value)

    @app.get("/api/v1/sync/batches/{batch_id}")
    def batch(batch_id: str, pair: Annotated[tuple, Depends(identity)]):
        with sessions() as s:
            b = s.get(Batch, safe_id(batch_id))
            if not b or b.actor_id != pair[0].id or b.client_id != pair[1].id:
                raise HTTPException(404, "BATCH_NOT_FOUND")
            authorize(s, pair[0], b.project_id)
            return b.receipt

    @app.get("/api/v1/sync/status")
    def status(pair: Annotated[tuple, Depends(identity)]):
        with sessions() as s:
            batches = s.scalars(
                select(Batch)
                .where(Batch.actor_id == pair[0].id, Batch.client_id == pair[1].id)
                .order_by(Batch.received_at.desc())
                .limit(20)
            ).all()
            return {
                "client_id": pair[1].id,
                "recent_batches": [
                    {
                        "batch_id": b.id,
                        "project_id": b.project_id,
                        "received_at": b.received_at.isoformat(),
                    }
                    for b in batches
                ],
            }

    @app.get("/api/v1/projects/{project_id}/summary")
    def summary(project_id: str, pair: Annotated[tuple, Depends(identity)]):
        with sessions() as s:
            p = authorize(s, pair[0], safe_id(project_id))
            rows = rows_for(s, p.id)
            versions = []
            devices = set()
            for snapshot in s.scalars(
                select(Snapshot)
                .where(Snapshot.project_id == p.id)
                .order_by(Snapshot.revision.desc(), Snapshot.client_id)
            ):
                if snapshot.client_id in devices:
                    continue
                devices.add(snapshot.client_id)
                batch = s.get(Batch, snapshot.batch_id)
                versions.append(
                    {
                        "client_id": snapshot.client_id,
                        "project_revision": snapshot.revision,
                        "snapshot_hash": snapshot.snapshot_hash,
                        "project_snapshot": batch.receipt.get("project_snapshot"),
                        "server_received_at": batch.received_at.isoformat(),
                    }
                )
            return {
                "project_id": p.id,
                **{
                    key: (p.payload or {}).get(key)
                    for key in (
                        "project_name",
                        "schema_version",
                        "created_at",
                        "updated_at",
                    )
                },
                "source_version": versions,
                "server_received_at": s.scalar(
                    select(func.max(Batch.received_at)).where(Batch.project_id == p.id)
                ),
                "counts": {k: len(v) for k, v in rows.items()},
                "crops": s.scalar(
                    select(func.count())
                    .select_from(Asset)
                    .where(Asset.project_id == p.id)
                ),
                **review_summary(p, rows),
            }

    @app.get("/api/v1/projects/{project_id}/entities/{kind}")
    def entities(project_id: str, kind: str, pair: Annotated[tuple, Depends(identity)]):
        if kind not in SPECS:
            raise HTTPException(404, "ENTITY_KIND")
        with sessions() as s:
            authorize(s, pair[0], safe_id(project_id))
            return [
                {
                    "payload": r.payload,
                    "authenticated_actor_id": r.actor_id,
                    "client_id": r.device_id,
                    "received_at": r.received_at.isoformat(),
                }
                for r in s.scalars(
                    select(ENTITIES[kind]).where(
                        ENTITIES[kind].project_id == project_id
                    )
                )
            ]

    @app.post("/api/v1/projects/{project_id}/crops")
    def crop(
        project_id: str, request: Request, pair: Annotated[tuple, Depends(identity)]
    ):
        with sessions.begin() as s:
            p = authorize(s, pair[0], safe_id(project_id), crop=True)
            return store_crop(
                s, *pair, p, request.scope["xrt_body"], app.state.asset_dir
            )

    @app.get("/api/v1/admin/statistics")
    def statistics(pair: Annotated[tuple, Depends(admin)]):
        from .models import Project

        with sessions() as s:
            counts = {
                k: s.scalar(select(func.count()).select_from(cls))
                for k, cls in ENTITIES.items()
            }
            details = [
                review_summary(p, rows_for(s, p.id)) for p in s.scalars(select(Project))
            ]
            return {
                "projects": s.scalar(select(func.count()).select_from(Project)),
                "users": s.scalar(select(func.count()).select_from(User)),
                "crops": s.scalar(select(func.count()).select_from(Asset)),
                "counts": counts,
                "reviewed_targets": sum(d["reviewed_targets"] for d in details),
                "conflict_targets": sum(d["conflict_targets"] for d in details),
                "ground_truth_approved": sum(
                    d["ground_truth_approved"] for d in details
                ),
                "manual_instances": sum(d.get("manual_instances", 0) for d in details),
                "reviewer_events": dict(
                    sum(
                        (Counter(d.get("reviewer_events", {})) for d in details),
                        Counter(),
                    )
                ),
                "status_distribution": dict(
                    sum(
                        (Counter(d.get("status_distribution", {})) for d in details),
                        Counter(),
                    )
                ),
                "recent_received_at": s.scalar(select(func.max(Batch.received_at))),
                "audit_counts": dict(
                    s.execute(
                        select(Audit.action, func.count()).group_by(Audit.action)
                    ).all()
                ),
            }

    @app.post("/api/v1/admin/users")
    def users(request: Request, pair: Annotated[tuple, Depends(admin)]):
        data = request.scope["xrt_body"]
        if (
            set(data) != {"name", "role", "client_id"}
            or data["role"] not in ("ADMIN", "RESEARCHER")
            or not isinstance(data["name"], str)
            or not 1 <= len(data["name"]) <= 160
        ):
            raise ValueError("USER_FIELDS")
        with sessions.begin() as s:
            user = User(id=str(uuid4()), name=data["name"], role=data["role"])
            s.add(user)
            s.flush()
            cred, token = issue(s, user.id, safe_id(data["client_id"]))
            audit(s, "ADMIN_USER_CREATED", pair[0].id, user_id=user.id)
            return {
                "user_id": user.id,
                "client_id": data["client_id"],
                "credential_id": cred.id,
                "credential": token,
                "one_time": True,
            }

    @app.post("/api/v1/admin/grants")
    def grants(request: Request, pair: Annotated[tuple, Depends(admin)]):
        d = request.scope["xrt_body"]
        if set(d) != {"user_id", "project_id", "crops"} or type(d["crops"]) is not bool:
            raise ValueError("GRANT_FIELDS")
        with sessions.begin() as s:
            grant(s, safe_id(d["user_id"]), safe_id(d["project_id"]), d["crops"])
            audit(
                s,
                "ADMIN_PROJECT_GRANT",
                pair[0].id,
                d["project_id"],
                user_id=d["user_id"],
                crops=d["crops"],
            )
        return {"status": "GRANTED"}

    @app.post("/api/v1/admin/credentials/{credential_id}/revoke")
    def revoke(credential_id: str, pair: Annotated[tuple, Depends(admin)]):
        with sessions.begin() as s:
            cred = s.get(Credential, safe_id(credential_id))
            if not cred:
                raise HTTPException(404, "CREDENTIAL_NOT_FOUND")
            cred.revoked = True
            audit(s, "CREDENTIAL_REVOKED", pair[0].id, credential_id=cred.id)
        return {"status": "REVOKED"}

    @app.post("/api/v1/admin/devices/{client_id}/credentials")
    def reissue(client_id: str, pair: Annotated[tuple, Depends(admin)]):
        with sessions.begin() as s:
            device = s.get(Device, safe_id(client_id))
            if not device:
                raise HTTPException(404, "DEVICE_NOT_FOUND")
            cred, token = issue(s, device.user_id, device.id)
            audit(s, "ADMIN_CREDENTIAL_REISSUED", pair[0].id, credential_id=cred.id)
            return {
                "credential_id": cred.id,
                "client_id": device.id,
                "credential": token,
                "one_time": True,
            }

    @app.get("/api/v1/admin/openapi")
    def openapi(pair: Annotated[tuple, Depends(admin)]):
        return app.openapi()

    from .dataset_api import register_dataset_routes

    register_dataset_routes(app, sessions, admin)
    return app
