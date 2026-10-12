"""Real PostgreSQL approval, append-only version and safe export tests; synthetic ONLY."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_collection import headers, upload
from xrt_server.api import create_app
from xrt_server.datasets import export_version, split_rows
from xrt_server.models import Asset, DatasetEvent, DatasetVersion, User

from sic_xrt_analyzer.results.contracts import (
    FileIdentity,
    ReviewTarget,
    VerifiedContentHash,
)
from sic_xrt_analyzer.results.review_workspace import append_review
from sic_xrt_analyzer.results.reviews import ReviewRepository
from sic_xrt_analyzer.sync.client import make_crop
from sic_xrt_analyzer.sync.protocol import digest

PREFIX = "/api/v1/admin/datasets"


def large(project, tmp_path, seed=1):
    source = project.image_sources[0]
    path = tmp_path / f"synthetic-{seed}.jpg"
    Image.fromarray(
        np.random.default_rng(seed).integers(0, 256, (256, 256, 3), dtype=np.uint8)
    ).save(path)
    stat = path.stat()
    identity = FileIdentity(str(path), stat.st_size, stat.st_mtime_ns)
    source = replace(
        source,
        display_name=path.name,
        source_reference=str(path),
        width=256,
        height=256,
        file_identity=identity,
        content_hash=VerifiedContentHash(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            source.content_hash.verified_at,
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
        ),
    )
    run = project.analysis_runs[0]
    run = replace(
        run,
        source_identity={
            **run.source_identity,
            "canonical_path": str(path),
            "file_size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "width": 256,
            "height": 256,
        },
    )
    return project.evolve(image_sources=(source,), analysis_runs=(run,))


def register(api, p, size=128):
    upload(api, p)
    http = api[0]
    body = make_crop(
        p,
        p.image_sources[0].source_id,
        p.analysis_runs[0].run_id,
        "OBSERVATION",
        p.observations[0].observation_id,
        (20, 20, size, size),
        consent=True,
    )
    response = http.post(
        f"/api/v1/projects/{p.project_id}/crops", json=body, headers=headers(api[5])
    )
    assert response.status_code == 200, response.text
    return response.json()["asset_id"]


def mapping(
    p, group="synthetic-group", wafer=None, evaluation=False, previous=None, rights=True
):
    return {
        "project_id": p.project_id,
        "source_id": p.image_sources[0].source_id,
        "source_hash": p.image_sources[0].content_hash.value,
        "group_id": group,
        "wafer_id": wafer,
        "provider_group": group,
        "before_after_group": None,
        "duplicate_group": None,
        "evaluation_only": evaluation,
        "data_origin": "synthetic_fixture",
        "training_use_authorized": rights,
        "evidence": "Synthetic fixture ONLY, not expert ground truth",
        "previous_event_id": previous,
    }


def approval(p, asset, status="APPROVED", previous=None):
    return {
        "project_id": p.project_id,
        "asset_id": asset,
        "status": status,
        "approved_class": "TED",
        "review_ids": sorted(
            i
            for ids in ReviewRepository()
            .current(p, ReviewTarget.OBSERVATION, p.observations[0].observation_id)
            .tips_by_reviewer.values()
            for i in ids
        ),
        "reason": "Synthetic functional test only",
        "resolve_conflict": False,
        "previous_event_id": previous,
    }


def post(api, path, body):
    r = api[0].post(PREFIX + path, json=body, headers=headers(api[6]))
    assert r.status_code == 200, r.text
    return r.json()


def report(api, p):
    r = api[0].get(
        PREFIX + "/eligibility",
        params={"project_id": p.project_id},
        headers=headers(api[6]),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_missing_unapproved_group_and_role(api, project, tmp_path):
    p = large(project, tmp_path)
    upload(api, p)
    assert report(api, p)["exclusion_counts"] == {"IMAGE_ASSET_MISSING": 1}
    asset = register(api, p)
    assert report(api, p)["exclusion_counts"] == {"GROUP_NOT_READY": 1}
    assert (
        api[0]
        .post(PREFIX + "/groups", json=mapping(p), headers=headers(api[5]))
        .status_code
        == 403
    )
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=approval(p, asset), headers=headers(api[5]))
        .status_code
        == 403
    )
    post(api, "/groups", mapping(p))
    assert report(api, p)["exclusion_counts"] == {"APPROVAL_MISSING": 1}
    assert (
        api[0]
        .post(
            PREFIX,
            json={"version": "empty", "project_ids": [p.project_id], "seed": 3},
            headers=headers(api[6]),
        )
        .status_code
        == 409
    )


def test_approve_export_restart_revoke_immutable(api, project, tmp_path):
    p = large(project, tmp_path)
    asset = register(api, p)
    post(api, "/groups", mapping(p))
    event = post(api, "/approvals", approval(p, asset))
    assert report(api, p)["approved_usable_crops"] == 1
    manifest = post(
        api,
        "",
        {
            "version": "synthetic-" + str(uuid4()),
            "project_ids": [p.project_id],
            "seed": 42,
        },
    )
    assert manifest["readiness"] == "DATA_NOT_READY"
    assert manifest["dataset_hash"] == digest(
        {k: v for k, v in manifest.items() if k != "dataset_hash"}
    )
    with api[2].begin() as s:
        record = s.get(DatasetVersion, manifest["dataset_id"])
        admin = s.get(User, event["payload"]["adjudicator_id"])
        result = export_version(
            s, admin, record, api[1].state.asset_dir, tmp_path / "export"
        )
        assert result["images"] == 1
        with pytest.raises(HTTPException):
            export_version(
                s,
                s.get(User, api[3].id),
                record,
                api[1].state.asset_dir,
                tmp_path / "unauthorized",
            )
    exported = json.loads((tmp_path / "export/manifest.json").read_text())
    assert exported == manifest
    png = tmp_path / "export" / next(iter(manifest["files"]))
    assert hashlib.sha256(png.read_bytes()).hexdigest() == next(
        iter(manifest["files"].values())
    )
    # A fresh app/session sees the persisted version; no process-local registry.
    new_app = create_app(api[1].state.engine.url, api[1].state.asset_dir)
    with new_app.state.sessions() as s:
        assert s.get(DatasetVersion, manifest["dataset_id"]).payload == manifest
    new_app.state.engine.dispose()
    for table in ("dataset_events", "dataset_versions"):
        with api[2]() as s, pytest.raises(DBAPIError):
            s.execute(text(f"UPDATE {table} SET actor_id=actor_id"))
            s.commit()
    post(api, "/approvals", approval(p, asset, "REVOKED", event["event_id"]))
    detail = (
        api[0]
        .get(PREFIX + "/" + manifest["dataset_id"], headers=headers(api[6]))
        .json()
    )
    assert detail["usage_status"] == "RESTRICTED" and detail["manifest"] == manifest
    with api[2].begin() as s, pytest.raises(HTTPException):
        export_version(
            s,
            s.get(User, event["payload"]["adjudicator_id"]),
            s.get(DatasetVersion, manifest["dataset_id"]),
            api[1].state.asset_dir,
            tmp_path / "revoked",
        )
    assert json.loads((tmp_path / "export/manifest.json").read_text()) == manifest


@pytest.mark.parametrize("bad", ["sha", "pixels", "source", "target", "size"])
def test_bad_crop_not_approved(api, project, tmp_path, bad):
    p = large(project, tmp_path)
    asset = register(api, p, 64 if bad == "size" else 128)
    post(api, "/groups", mapping(p))
    if bad != "size":
        with api[2].begin() as s:
            a = s.get(Asset, (p.project_id, asset))
            m = deepcopy(a.payload)
            if bad == "sha":
                (api[1].state.asset_dir / a.storage_key).write_bytes(b"damaged")
            else:
                m[
                    {
                        "pixels": "pixel_hash",
                        "source": "source_hash",
                        "target": "target_id",
                    }[bad]
                ] = "0" * 64
                a.payload = m
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=approval(p, asset), headers=headers(api[6]))
        .status_code
        == 422
    )
    assert report(api, p)["approved_usable_crops"] == 0


def test_conflict_adjudication_and_new_review_stales_version(api, project, tmp_path):
    p = large(project, tmp_path)
    p, _ = append_review(
        p,
        ReviewTarget.OBSERVATION,
        p.observations[0].observation_id,
        "second-reviewer",
        "PRESENT",
        "BPD",
        "ACCEPTED",
        "synthetic conflict",
        source_id=p.image_sources[0].source_id,
        run_id=p.analysis_runs[0].run_id,
    )
    asset = register(api, p)
    post(api, "/groups", mapping(p))
    assert report(api, p)["exclusion_counts"] == {"REVIEW_CONFLICT": 1}
    body = approval(p, asset)
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=body, headers=headers(api[6]))
        .status_code
        == 422
    )
    body["resolve_conflict"] = True
    post(api, "/approvals", body)
    manifest = post(
        api,
        "",
        {
            "version": "conflict-" + str(uuid4()),
            "project_ids": [p.project_id],
            "seed": 1,
        },
    )
    p, _ = append_review(
        p,
        ReviewTarget.OBSERVATION,
        p.observations[0].observation_id,
        "second-reviewer",
        "PRESENT",
        "TED",
        "ACCEPTED",
        "new synthetic opinion",
        source_id=p.image_sources[0].source_id,
        run_id=p.analysis_runs[0].run_id,
    )
    upload(api, p)
    assert report(api, p)["exclusion_counts"] == {"APPROVAL_STALE": 1}
    detail = (
        api[0]
        .get(PREFIX + "/" + manifest["dataset_id"], headers=headers(api[6]))
        .json()
    )
    assert detail["usage_status"] == "RESTRICTED" and detail["manifest"] == manifest


def test_waf8_rights_and_stale_mapping(api, project, tmp_path):
    p = large(project, tmp_path)
    asset = register(api, p)
    body = mapping(p, wafer="8")
    assert (
        api[0].post(PREFIX + "/groups", json=body, headers=headers(api[6])).status_code
        == 422
    )
    body["evaluation_only"] = True
    group = post(api, "/groups", body)
    event = post(api, "/approvals", approval(p, asset))
    manifest = post(
        api,
        "",
        {"version": "wafer8-" + str(uuid4()), "project_ids": [p.project_id], "seed": 0},
    )
    assert all(r["split"] == "test" for r in manifest["rows"])
    body["previous_event_id"] = group["event_id"]
    body["training_use_authorized"] = False
    post(api, "/groups", body)
    assert report(api, p)["exclusion_counts"] == {"USE_RIGHTS_MISSING": 1}
    assert (
        api[0]
        .get(PREFIX + "/" + manifest["dataset_id"], headers=headers(api[6]))
        .json()["usage_status"]
        == "RESTRICTED"
    )
    assert (
        api[0]
        .post(
            PREFIX + "/approvals",
            json=approval(p, asset, previous=event["event_id"]),
            headers=headers(api[6]),
        )
        .status_code
        == 422
    )


def row(i):
    return {
        "sample_id": str(i),
        "source_hash": str(i),
        "run_id": str(i),
        "target_id": str(i),
        "group_id": str(i),
        "wafer_id": None,
        "provider_group": str(i),
        "before_after_group": None,
        "duplicate_group": None,
        "pixel_hash": str(i),
        "dhash": hashlib.sha256(str(i).encode()).hexdigest()[:16],
        "evaluation_only": False,
    }


@pytest.mark.parametrize(
    "key",
    [
        "source_hash",
        "wafer_id",
        "run_id",
        "target_id",
        "group_id",
        "provider_group",
        "before_after_group",
        "duplicate_group",
        "pixel_hash",
    ],
)
def test_leakage_union_determinism_and_seed(key):
    rows = [row(i) for i in range(12)]
    rows[1][key] = rows[0][key] = "same-verified-group"
    result = split_rows(rows, 2026)
    byid = {r["sample_id"]: r for r in result}
    assert byid["0"]["split"] == byid["1"]["split"]
    assert result == split_rows(rows[::-1], 2026)
    assert digest(result) == digest(split_rows(rows, 2026))
    assert result != split_rows(rows, 2027)
    rows[0]["evaluation_only"] = True
    assert all(
        r["split"] == "test"
        for r in split_rows(rows, 2026)
        if r["sample_id"] in {"0", "1"}
    )


def test_unsafe_export_and_event_revision(api, project, tmp_path):
    p = large(project, tmp_path)
    asset = register(api, p)
    post(api, "/groups", mapping(p))
    e = post(api, "/approvals", approval(p, asset))
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=approval(p, asset), headers=headers(api[6]))
        .status_code
        == 409
    )
    m = post(
        api,
        "",
        {"version": "safe-" + str(uuid4()), "project_ids": [p.project_id], "seed": 7},
    )
    assert (
        api[0]
        .post(
            PREFIX,
            json={
                "version": m["dataset_version"],
                "project_ids": [p.project_id],
                "seed": 7,
            },
            headers=headers(api[6]),
        )
        .status_code
        == 409
    )
    with api[2].begin() as s:
        admin = s.get(User, e["payload"]["adjudicator_id"])
        record = s.get(DatasetVersion, m["dataset_id"])
        with pytest.raises(ValueError):
            export_version(s, admin, record, api[1].state.asset_dir, tmp_path)
        assert (
            len(
                s.scalars(
                    select(DatasetEvent).where(DatasetEvent.project_id == p.project_id)
                ).all()
            )
            == 2
        )


def clone_fixture(p, tmp_path, seed):
    p = large(p, tmp_path, seed)
    pid, sid, rid, oid, gid = (str(uuid4()) for _ in range(5))
    source = replace(p.image_sources[0], source_id=sid)
    run = replace(p.analysis_runs[0], project_id=pid, source_id=sid, run_id=rid)
    geometry = replace(p.geometries[0], source_id=sid, geometry_id=gid)
    observation = replace(
        p.observations[0], observation_id=oid, run_id=rid, geometry_id=gid
    )
    prediction = replace(
        p.predictions[0], observation_id=oid, prediction_id=str(uuid4())
    )
    p = replace(
        p,
        project_id=pid,
        image_sources=(source,),
        analysis_runs=(run,),
        geometries=(geometry,),
        observations=(observation,),
        predictions=(prediction,),
        review_events=(),
    )
    return append_review(
        p,
        ReviewTarget.OBSERVATION,
        oid,
        "synthetic-reviewer",
        "PRESENT",
        "TED",
        "ACCEPTED",
        "Generated functional fixture ONLY",
        source_id=sid,
        run_id=rid,
    )[0]


def test_producer_export_three_class_grouped_fixture(api, project, tmp_path):
    import os
    import shutil

    from xrt_server.auth import grant

    projects = []
    for group in range(3):
        for label, name in enumerate(("BPD", "TED", "TSD")):
            p = clone_fixture(project, tmp_path, 10000 + group * 3 + label)
            with api[2].begin() as s:
                grant(s, api[3].id, p.project_id, True)
            asset = register(api, p)
            body = mapping(
                p,
                group="synthetic-independent-" + str(group),
                wafer="8" if group == 2 else str(group),
                evaluation=group == 2,
            )
            post(api, "/groups", body)
            body = approval(p, asset)
            body["approved_class"] = name
            post(api, "/approvals", body)
            projects.append(p.project_id)
    manifest = post(
        api,
        "",
        {
            "version": "contract-smoke-" + str(uuid4()),
            "project_ids": projects,
            "seed": 2026,
        },
    )
    assert len(manifest["rows"]) == 9
    assert all(
        manifest["split_class_counts"][s] == {"BPD": 1, "TED": 1, "TSD": 1}
        for s in ("train", "validation", "test")
    )
    assert all(r["split"] == "test" for r in manifest["rows"] if r["wafer_id"] == "8")
    output = tmp_path / "producer-export"
    with api[2].begin() as s:
        record = s.get(DatasetVersion, manifest["dataset_id"])
        export_version(
            s,
            s.get(User, manifest["created_by"]),
            record,
            api[1].state.asset_dir,
            output,
        )
    # Optional explicit private artifact destination for cross-repository acceptance.
    if os.getenv("XRT_CONTRACT_SMOKE_EXPORT"):
        destination = Path(os.environ["XRT_CONTRACT_SMOKE_EXPORT"])
        assert not destination.exists()
        shutil.copytree(output, destination)


def test_uncertain_label_origin_and_crop_duplicates(api, project, tmp_path):
    p = large(project, tmp_path)
    p, _ = append_review(
        p,
        ReviewTarget.OBSERVATION,
        p.observations[0].observation_id,
        "local-reviewer",
        "UNCERTAIN",
        "UNKNOWN",
        "UNCERTAIN",
        "synthetic uncertain",
        source_id=p.image_sources[0].source_id,
        run_id=p.analysis_runs[0].run_id,
    )
    asset = register(api, p)
    g = post(api, "/groups", mapping(p))
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=approval(p, asset), headers=headers(api[6]))
        .status_code
        == 422
    )
    bad = mapping(p, previous=g["event_id"])
    bad["data_origin"] = "real_research"
    assert (
        api[0].post(PREFIX + "/groups", json=bad, headers=headers(api[6])).status_code
        == 422
    )
    bad = mapping(p, wafer="Wafer 8", previous=g["event_id"])
    assert (
        api[0].post(PREFIX + "/groups", json=bad, headers=headers(api[6])).status_code
        == 422
    )


def test_authenticated_local_export_cli(api, project, tmp_path, monkeypatch, capsys):
    import sys

    from xrt_server import dataset_admin
    from xrt_server.db import connect

    p = large(project, tmp_path)
    asset = register(api, p)
    post(api, "/groups", mapping(p))
    post(api, "/approvals", approval(p, asset))
    manifest = post(
        api,
        "",
        {"version": "cli-" + str(uuid4()), "project_ids": [p.project_id], "seed": 9},
    )
    monkeypatch.setattr(
        dataset_admin, "connect", lambda: connect(api[1].state.engine.url)
    )
    monkeypatch.setenv("XRT_ASSET_DIR", str(api[1].state.asset_dir))
    credential = tmp_path / "synthetic-private-admin.json"
    credential.write_text(json.dumps({"credential": api[6]}))

    def invoke(output):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dataset_admin",
                "--credential-file",
                str(credential),
                "--dataset-id",
                manifest["dataset_id"],
                "--output",
                str(output),
            ],
        )
        dataset_admin.main()

    invoke(tmp_path / "cli-export")
    assert api[6] not in capsys.readouterr().out
    assert json.loads((tmp_path / "cli-export/manifest.json").read_text()) == manifest
    credential.write_text(json.dumps({"credential": api[5]}))
    with pytest.raises(HTTPException) as error:
        invoke(tmp_path / "denied-cli")
    assert error.value.status_code == 403 and not (tmp_path / "denied-cli").exists()


def test_duplicate_before_exclusion_preserves_source_links_and_holdout():
    from xrt_server.datasets import deduplicate

    rows = [
        {**row(i), "project_id": "synthetic", "asset_id": str(i), "class_label": "TED"}
        for i in range(6)
    ]
    rows[1]["pixel_hash"] = rows[0]["pixel_hash"]
    rows[1]["source_hash"] = rows[2]["source_hash"]
    rows[1]["evaluation_only"] = True
    rows[0]["source_hash"] = rows[3]["source_hash"]
    kept, excluded = deduplicate(rows)
    assert len(kept) == 5 and len(excluded) == 1
    assert all(r["evaluation_only"] for r in kept if r["sample_id"] in {"0", "2", "3"})
    result = split_rows(kept, 2026)
    assert all(
        r["split"] == "test" for r in result if r["sample_id"] in {"0", "2", "3"}
    )
    rows[1]["class_label"] = "BPD"
    kept, excluded = deduplicate(rows)
    assert all(r["sample_id"] not in {"0", "1"} for r in kept)
    assert sum(r["reason"] == "DUPLICATE_LABEL_CONFLICT" for r in excluded) == 2


def test_rgb16_png_cannot_silently_become_rgb8_training_data(api, project, tmp_path):
    import io
    import struct
    import zlib

    p = large(project, tmp_path)
    asset = register(api, p)
    post(api, "/groups", mapping(p))

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    payload = b"".join(b"\0" + b"\x80\x00" * (128 * 3) for _ in range(128))
    raw = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 128, 16, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(payload))
        + chunk(b"IEND", b"")
    )
    with Image.open(io.BytesIO(raw)) as image:
        assert image.mode == "RGB"  # mode alone does not prove encoded 8-bit RGB
        pixel_hash = hashlib.sha256(image.tobytes()).hexdigest()
    with api[2].begin() as s:
        a = s.get(Asset, (p.project_id, asset))
        m = deepcopy(a.payload)
        m["crop_hash"] = hashlib.sha256(raw).hexdigest()
        m["pixel_hash"] = pixel_hash
        a.payload = m
        a.digest = m["crop_hash"]
        a.storage_key = m["crop_hash"] + ".png"
        (api[1].state.asset_dir / a.storage_key).write_bytes(raw)
    assert report(api, p)["exclusion_counts"] == {"PNG_RGB8_ENCODING_REQUIRED": 1}
    assert (
        api[0]
        .post(PREFIX + "/approvals", json=approval(p, asset), headers=headers(api[6]))
        .status_code
        == 422
    )
