"""Authenticated metadata/streaming only; binaries are registered by the private local CLI."""

import threading
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select

from .auth import audit
from .model_registry import (
    approve_model,
    channel_allowed,
    check_files,
    config,
    event,
    head,
    lookup,
    release_status,
    scientific_gate,
)
from .models import Audit, ModelCandidate, ModelEvent, ModelRelease


def register_model_routes(app, sessions, identity, admin):
    app.state.model_config = getattr(app.state, "model_config", None) or config()
    cfg = app.state.model_config
    capacity = threading.BoundedSemaphore(4)
    user_dep = Depends(identity)
    admin_dep = Depends(admin)
    prefix = "/api/v1/models/releases"
    manage = "/api/v1/admin/models"

    def release(s, release_id, user):
        r = s.get(ModelRelease, release_id)
        if not r or not channel_allowed(s, user, r.channel, cfg):
            raise HTTPException(404, "RELEASE_NOT_FOUND")
        c = lookup(s, r.candidate_id, cfg)
        return r, c

    @app.get(prefix)
    def listing(channel: str = "STABLE", pair=user_dep):
        with sessions() as s:
            if not channel_allowed(s, pair[0], channel, cfg):
                raise HTTPException(403, "CHANNEL_NOT_AUTHORIZED")
            return [
                {
                    "release": r.payload,
                    "status": release_status(s, r, cfg, app.state.asset_dir),
                }
                for r in s.scalars(
                    select(ModelRelease)
                    .where(ModelRelease.channel == channel)
                    .order_by(ModelRelease.sequence.desc())
                    .limit(100)
                )
            ]

    @app.get(prefix + "/{release_id}")
    def detail(release_id: str, pair=user_dep):
        with sessions() as s:
            r, _c = release(s, release_id, pair[0])
            return {
                "release": r.payload,
                "status": release_status(s, r, cfg, app.state.asset_dir),
            }

    @app.get(prefix + "/{release_id}/manifest")
    def manifest(release_id: str, pair=user_dep):
        with sessions() as s:
            r, c = release(s, release_id, pair[0])
            if release_status(s, r, cfg, app.state.asset_dir) != "AVAILABLE":
                raise HTTPException(409, "RELEASE_UNAVAILABLE")
            root = check_files(c, cfg)
            return FileResponse(root / "manifest.json", media_type="application/json")

    @app.get(prefix + "/{release_id}/download")
    def download(release_id: str, request: Request, pair=user_dep):
        with sessions() as s:
            r, c = release(s, release_id, pair[0])
            if release_status(s, r, cfg, app.state.asset_dir) != "AVAILABLE":
                raise HTTPException(409, "RELEASE_UNAVAILABLE")
            root = check_files(c, cfg)
            path = Path(root) / "model.onnx"
            size = path.stat().st_size
        if not capacity.acquire(False):
            raise HTTPException(429, "DOWNLOAD_CAPACITY")

        def chunks():
            completed = False
            try:
                with path.open("rb") as f:
                    yield from iter(lambda: f.read(1024**2), b"")
                completed = True
            finally:
                capacity.release()
                with sessions.begin() as s:
                    audit(
                        s,
                        "MODEL_DOWNLOAD_COMPLETE"
                        if completed
                        else "MODEL_DOWNLOAD_INTERRUPTED",
                        pair[0].id,
                        release_id=release_id,
                    )

        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={"Content-Length": str(size), "Cache-Control": "no-store"},
        )

    @app.get(manage + "/candidates")
    def candidates(pair=admin_dep):
        with sessions() as s:
            return [
                {
                    "candidate_id": c.id,
                    "model_id": c.model_id,
                    "version": c.version,
                    "dataset_id": c.dataset_id,
                    "manifest": c.payload["manifest"],
                    "event_id": head(s, c.id).id,
                    "state": head(s, c.id).payload,
                }
                for c in s.scalars(
                    select(ModelCandidate)
                    .where(ModelCandidate.realm == cfg["realm"])
                    .limit(1000)
                )
            ]

    @app.post(manage + "/validate")
    def validate(request: Request, pair=admin_dep):
        b = request.scope["xrt_body"]
        with sessions() as s:
            c = lookup(s, b["candidate_id"], cfg)
            check_files(c, cfg)
            return scientific_gate(
                s, c, app.state.asset_dir, b.get("channel", "STABLE")
            )

    @app.post(manage + "/approvals")
    def approval(request: Request, pair=admin_dep):
        b = request.scope["xrt_body"]
        with sessions.begin() as s:
            c = lookup(s, b["candidate_id"], cfg)
            row = approve_model(
                s,
                pair[0],
                c,
                cfg,
                app.state.asset_dir,
                b["channel"],
                b["reason"],
                b["previous_event_id"],
            )
            return {"event_id": row.id, "revision": row.revision, "state": row.payload}

    @app.post(manage + "/revocations")
    def revoke(request: Request, pair=admin_dep):
        b = request.scope["xrt_body"]
        with sessions.begin() as s:
            r, _c = release(s, b["release_id"], pair[0])
            if (
                not isinstance(b["reason"], str)
                or len(b["reason"]) < 10
                or not b["previous_event_id"]
            ):
                raise ValueError("REVOCATION_REASON")
            e = event(
                s,
                pair[0],
                "release." + r.id,
                "REVOKED",
                {"reason": b["reason"]},
                b["previous_event_id"],
            )
            return {"event_id": e.id, "status": "REVOKED"}

    @app.get(manage + "/audit")
    def events(pair=admin_dep):
        with sessions() as s:
            return [
                {
                    "id": e.id,
                    "subject": e.subject_id,
                    "revision": e.revision,
                    "actor": e.actor_id,
                    "payload": e.payload,
                }
                for e in s.scalars(
                    select(ModelEvent)
                    .order_by(ModelEvent.created_at.desc())
                    .limit(1000)
                )
            ]

    @app.get(manage + "/statistics")
    def statistics(pair=admin_dep):
        with sessions() as s:
            candidates = s.scalars(
                select(ModelCandidate).where(ModelCandidate.realm == cfg["realm"])
            ).all()
            releases = s.scalars(select(ModelRelease)).all()
            return {
                "candidates": len(candidates),
                "approved": sum(
                    head(s, c.id).payload["action"] == "APPROVED" for c in candidates
                ),
                "releases": [
                    {
                        "release_id": r.id,
                        "channel": r.channel,
                        "status": release_status(s, r, cfg, app.state.asset_dir),
                        "downloads": len(
                            s.scalars(
                                select(Audit).where(
                                    Audit.action == "MODEL_DOWNLOAD_COMPLETE",
                                    Audit.detail["release_id"].astext == r.id,
                                )
                            ).all()
                        ),
                    }
                    for r in releases
                    if s.get(ModelCandidate, r.candidate_id).realm == cfg["realm"]
                ],
            }
