"""Admin-only verified_xrt_dataset/v2 metadata routes. Crops leave only via the local export."""

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select

from .label_datasets import create_version, preview, usage
from .models import LabelDatasetVersion


def register_label_dataset_routes(app, sessions, admin):
    admin_dep = Depends(admin)
    prefix = "/api/v1/admin/label-datasets"

    @app.get(prefix + "/preview")
    def preview_route(
        seed: int = Query(0, ge=0, lt=2**32),
        min_reviewers: int = Query(1, ge=1, le=20),
        consensus: str = Query("majority", max_length=16),
        implicit_weight: float = Query(1.0, ge=0, le=1),
        received_before: str | None = Query(None, max_length=64),
        pair=admin_dep,
    ):
        body = {"seed": seed, "min_reviewers": min_reviewers, "consensus": consensus,
                "implicit_weight": implicit_weight}
        if received_before is not None:
            body["received_before"] = received_before
        with sessions() as s:
            return preview(s, pair[0], body)

    @app.post(prefix)
    def create(request: Request, pair=admin_dep):
        with sessions.begin() as s:
            return create_version(s, pair[0], request.scope["xrt_body"])

    @app.get(prefix)
    def listing(pair=admin_dep):
        with sessions() as s:
            records = s.scalars(
                select(LabelDatasetVersion).order_by(LabelDatasetVersion.created_at)
            ).all()
            status = usage(s, records)
            return [
                {
                    "dataset_id": d.id,
                    "version": d.version,
                    "dataset_hash": d.digest,
                    "content_hash": d.content_digest,
                    "created_at": d.created_at.isoformat(),
                    "samples": len(d.payload["rows"]),
                    "split_class_counts": d.payload["split_class_counts"],
                    "conflict_counts": d.payload["conflict_counts"],
                    "readiness": d.payload["readiness"],
                    **status[d.id],
                }
                for d in records
            ]

    def record(s, dataset_id):
        found = s.get(LabelDatasetVersion, dataset_id)
        if not found:
            raise HTTPException(404, "DATASET_NOT_FOUND")
        return found

    @app.get(prefix + "/{dataset_id}")
    def detail(dataset_id: str, pair=admin_dep):
        with sessions() as s:
            found = record(s, dataset_id)
            return {"manifest": found.payload, **usage(s, [found])[found.id]}

    @app.get(prefix + "/{dataset_id}/samples")
    def samples(
        dataset_id: str,
        split: str | None = Query(None, pattern="^(train|validation|test)$"),
        label: str | None = Query(None, pattern="^(BPD|TED|TSD|NOT_DEFECT)$"),
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(100, ge=1, le=500),
        pair=admin_dep,
    ):
        with sessions() as s:
            rows = [
                r for r in record(s, dataset_id).payload["rows"]
                if (split is None or r["split"] == split) and (label is None or r["label"] == label)
            ]
            return {"items": rows[offset:offset + limit], "total": len(rows),
                    "offset": offset, "limit": limit}
