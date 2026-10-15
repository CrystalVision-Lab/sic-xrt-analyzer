"""Admin-only metadata endpoints. Dataset images have no download route."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .datasets import approve, create_version, eligibility, map_group, version_status
from .models import DatasetEvent, DatasetVersion


def register_dataset_routes(app, sessions, admin):
    admin_dep = Depends(admin)
    prefix = "/api/v1/admin/datasets"

    @app.get(prefix + "/eligibility")
    def eligible(project_id: str, pair=admin_dep):
        with sessions() as s:
            return eligibility(s, [project_id], app.state.asset_dir)

    @app.post(prefix + "/groups")
    def groups(request: Request, pair=admin_dep):
        with sessions.begin() as s:
            return map_group(s, pair[0], request.scope["xrt_body"])

    @app.post(prefix + "/approvals")
    def approvals(request: Request, pair=admin_dep):
        with sessions.begin() as s:
            return approve(s, pair[0], request.scope["xrt_body"], app.state.asset_dir)

    @app.get(prefix + "/events")
    def events(project_id: str, pair=admin_dep):
        with sessions() as s:
            return [
                {
                    "event_id": e.id,
                    "kind": e.kind,
                    "subject_id": e.subject_id,
                    "revision": e.revision,
                    "payload": e.payload,
                }
                for e in s.scalars(
                    select(DatasetEvent)
                    .where(DatasetEvent.project_id == project_id)
                    .order_by(DatasetEvent.created_at, DatasetEvent.id)
                )
            ]

    @app.post(prefix)
    def create(request: Request, pair=admin_dep):
        with sessions.begin() as s:
            return create_version(
                s, pair[0], request.scope["xrt_body"], app.state.asset_dir
            )

    @app.get(prefix)
    def listing(pair=admin_dep):
        with sessions() as s:
            return [
                {
                    "dataset_id": d.id,
                    "version": d.version,
                    "dataset_hash": d.digest,
                    **version_status(s, d, app.state.asset_dir),
                }
                for d in s.scalars(
                    select(DatasetVersion).order_by(DatasetVersion.created_at)
                )
            ]

    @app.get(prefix + "/{dataset_id}")
    def detail(dataset_id: str, pair=admin_dep):
        with sessions() as s:
            record = s.get(DatasetVersion, dataset_id)
            if not record:
                raise HTTPException(404, "DATASET_NOT_FOUND")
            return {
                "manifest": record.payload,
                **version_status(s, record, app.state.asset_dir),
            }
