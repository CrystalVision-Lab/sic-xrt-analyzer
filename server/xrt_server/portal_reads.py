"""ADMIN-only bounded read feeds; no auth fallback, research schema or writes."""

import hashlib
import re
from pathlib import Path

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from .model_registry import head, scientific_gate
from .models import (
    ENTITIES,
    Asset,
    Audit,
    Batch,
    Credential,
    Device,
    ModelCandidate,
    ModelEvent,
    Project,
    User,
)


def register_portal_reads(app, sessions, admin):
    auth = Depends(admin)
    prefix = "/api/v1/admin/portal"

    def page(s, cls, statement, offset, limit, mapper):
        total = s.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = s.scalars(statement.offset(offset).limit(limit)).all()
        return {
            "items": [mapper(r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @app.get(prefix + "/projects")
    def projects(
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(25, ge=1, le=100),
        pair=auth,
    ):
        with sessions() as s:
            return page(
                s,
                Project,
                select(Project).order_by(Project.received_at.desc(), Project.id),
                offset,
                limit,
                lambda p: {
                    "id": p.id,
                    "name": (p.payload or {}).get("project_name", "이름 없는 프로젝트"),
                    "schema_version": (p.payload or {}).get("schema_version"),
                    "received_at": p.received_at,
                },
            )

    @app.get(prefix + "/projects/{project_id}/entities/{kind}")
    def entities(
        project_id: str,
        kind: str,
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(50, ge=1, le=100),
        pair=auth,
    ):
        if kind not in ENTITIES:
            raise HTTPException(404, "ENTITY_KIND")
        with sessions() as s:
            if not s.get(Project, project_id):
                raise HTTPException(404, "PROJECT_NOT_FOUND")
            cls = ENTITIES[kind]
            return page(
                s,
                cls,
                select(cls).where(cls.project_id == project_id).order_by(cls.id),
                offset,
                limit,
                lambda r: {
                    "id": r.id,
                    "payload": r.payload,
                    "actor_id": r.actor_id,
                    "client_id": r.device_id,
                    "received_at": r.received_at,
                },
            )

    @app.get(prefix + "/batches")
    def batches(
        project_id: str | None = None,
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(25, ge=1, le=100),
        pair=auth,
    ):
        with sessions() as s:
            stmt = select(Batch).order_by(Batch.received_at.desc(), Batch.id)
            if project_id:
                stmt = stmt.where(Batch.project_id == project_id)
            return page(
                s,
                Batch,
                stmt,
                offset,
                limit,
                lambda b: {
                    "id": b.id,
                    "project_id": b.project_id,
                    "client_id": b.client_id,
                    "actor_id": b.actor_id,
                    "received_at": b.received_at,
                    "receipt": {
                        key: b.receipt.get(key)
                        for key in (
                            "status",
                            "accepted",
                            "batch_id",
                            "client_id",
                            "project_id",
                            "received_at",
                            "payload_hash",
                            "snapshot_hash",
                            "project_revision",
                        )
                    },
                },
            )

    @app.get(prefix + "/audit")
    def audit_feed(
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(25, ge=1, le=100),
        pair=auth,
    ):
        with sessions() as s:
            return page(
                s,
                Audit,
                select(Audit).order_by(Audit.id.desc()),
                offset,
                limit,
                lambda a: {
                    "id": a.id,
                    "action": a.action,
                    "actor_id": a.actor_id,
                    "project_id": a.project_id,
                    "detail": a.detail,
                    "created_at": a.created_at,
                },
            )

    @app.get(prefix + "/users")
    def users(pair=auth):
        with sessions() as s:
            return [
                {
                    "id": u.id,
                    "name": u.name,
                    "role": u.role,
                    "active": u.active,
                    "devices": [
                        {
                            "client_id": d.id,
                            "credentials": [
                                {
                                    "id": c.id,
                                    "revoked": c.revoked,
                                    "created_at": c.created_at,
                                }
                                for c in s.scalars(
                                    select(Credential)
                                    .where(Credential.device_id == d.id)
                                    .limit(30)
                                )
                            ],
                        }
                        for d in s.scalars(
                            select(Device).where(Device.user_id == u.id).limit(30)
                        )
                    ],
                }
                for u in s.scalars(select(User).order_by(User.id).limit(100))
            ]

    @app.get(prefix + "/models/{candidate_id}/evaluation")
    def evaluation(candidate_id: str, pair=auth):
        with sessions() as s:
            c = s.get(ModelCandidate, candidate_id)
            if not c or c.realm != app.state.model_config["realm"]:
                raise HTTPException(404, "CANDIDATE_NOT_FOUND")
            return {
                "candidate_id": c.id,
                "model_id": c.model_id,
                "version": c.version,
                "dataset_id": c.dataset_id,
                "model_sha256": c.payload["manifest"]["model_sha256"],
                "evaluation": c.payload["registry"]["evaluation"],
                "evaluation_sha256": c.payload["manifest"].get("evaluation_hash"),
                "deployment_gate": scientific_gate(s, c, app.state.asset_dir, "STABLE"),
                "current_event_id": head(s, c.id).id,
                "cpu_comparisons": [
                    {"id": e.id, "revision": e.revision, "payload": e.payload}
                    for e in s.scalars(
                        select(ModelEvent)
                        .where(
                            ModelEvent.subject_id == c.id,
                            ModelEvent.payload["action"].astext == "CPU_COMPARISON",
                        )
                        .order_by(ModelEvent.revision.desc())
                        .limit(10)
                    )
                ],
            }

    @app.get(prefix + "/projects/{project_id}/crops")
    def crops(project_id: str, pair=auth):
        with sessions() as s:
            return [
                {
                    "id": a.id,
                    "digest": a.digest,
                    "metadata": a.payload,
                    "received_at": a.received_at,
                }
                for a in s.scalars(
                    select(Asset).where(Asset.project_id == project_id).limit(100)
                )
            ]

    @app.get(prefix + "/projects/{project_id}/crops/{asset_id}")
    def crop_image(project_id: str, asset_id: str, pair=auth):
        with sessions() as s:
            a = s.get(Asset, (project_id, asset_id))
            if not a or not re.fullmatch(r"[0-9a-f]{64}\.png", a.storage_key):
                raise HTTPException(404, "CROP_NOT_FOUND")
            root = Path(app.state.asset_dir).resolve()
            path = root / a.storage_key
            if (
                path.is_symlink()
                or path.resolve().parent != root
                or not path.is_file()
                or path.stat().st_size > 4 * 1024**2
            ):
                raise HTTPException(409, "CROP_UNAVAILABLE")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != a.digest:
                raise HTTPException(409, "CROP_INTEGRITY")
            return Response(
                raw,
                media_type="image/png",
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
