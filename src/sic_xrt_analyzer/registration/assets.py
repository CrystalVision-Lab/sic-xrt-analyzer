"""Strict, content-addressed local registration assets; never mutate a prior attempt."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.results.contracts import (
    ImageRelationship,
    ImageRole,
    VerificationStatus,
)

SCHEMA = "xrt_registration/v1"
MAX_BYTES = 4 * 1024**2
PREFIX = "assets/registrations/"
FIELDS = {
    "schema",
    "registration_id",
    "project_id",
    "source_id",
    "target_id",
    "source_sha256",
    "target_sha256",
    "source_size",
    "target_size",
    "direction",
    "algorithm",
    "algorithm_version",
    "model",
    "matrix",
    "landmarks",
    "quality",
    "timings",
    "refinement",
    "status",
    "created_at",
    "reviewer_id",
    "parent_registration_id",
}


def validate(asset, project=None):
    from .engine import MODELS, validate_transform

    if (
        not isinstance(asset, dict)
        or set(asset) != FIELDS
        or asset["schema"] != SCHEMA
        or asset["direction"] != "before_to_after"
    ):
        raise ValueError("알 수 없는 정합 자산 계약")
    for k in (
        "registration_id",
        "project_id",
        "source_id",
        "target_id",
        "algorithm",
        "algorithm_version",
    ):
        if not isinstance(asset[k], str) or not 1 <= len(asset[k]) <= 256:
            raise ValueError("정합 식별값 오류")
    for k in ("source_sha256", "target_sha256"):
        if not isinstance(asset[k], str) or not re.fullmatch("[0-9a-f]{64}", asset[k]):
            raise ValueError("원본 SHA 오류")
    if (
        asset["source_id"] == asset["target_id"]
        or asset["source_sha256"] == asset["target_sha256"]
    ):
        raise ValueError("동일한 원본은 비교할 수 없습니다")
    for k in ("source_size", "target_size"):
        if (
            not isinstance(asset[k], list)
            or len(asset[k]) != 2
            or any(type(n) != int or n <= 0 for n in asset[k])
        ):
            raise ValueError("원본 크기 오류")
    if asset["model"] not in MODELS:
        raise ValueError("변환 유형 오류")
    if asset["matrix"] is not None:
        validate_transform(asset["matrix"], asset["model"])
    elif asset["status"] != "REJECTED":
        raise ValueError("실패 외에는 행렬이 필요합니다")
    if asset["status"] not in ("NEEDS_REVIEW", "REJECTED", "ACCEPTED"):
        raise ValueError("정합 상태 오류")
    created = datetime.fromisoformat(asset["created_at"])
    if created.tzinfo is None:
        raise ValueError("정합 시각의 시간대가 필요합니다")
    if asset["status"] == "ACCEPTED" and (
        not isinstance(asset["reviewer_id"], str)
        or not asset["reviewer_id"].strip()
        or not asset["parent_registration_id"]
    ):
        raise ValueError("승인은 로컬 검수자와 추정 이력을 요구합니다")
    if asset["status"] != "ACCEPTED" and asset["reviewer_id"] is not None:
        raise ValueError("미승인 자산에 검수자 지정 불가")
    if (
        not isinstance(asset["quality"], dict)
        or not isinstance(asset["quality"].get("reasons"), list)
        or not isinstance(asset["timings"], dict)
    ):
        raise TypeError("정합 근거 오류")
    if asset["status"] == "ACCEPTED" and asset["quality"]["reasons"]:
        raise ValueError("실패 정합 승인 불가")
    if not isinstance(asset["landmarks"], list) or len(asset["landmarks"]) > 4000:
        raise ValueError("대응점 예산 초과")
    for row in asset["landmarks"]:
        if set(row) != {"before", "after", "inlier"} or type(row["inlier"]) != bool:
            raise ValueError("대응점 형식 오류")
        for side, size in (
            ("before", asset["source_size"]),
            ("after", asset["target_size"]),
        ):
            xy = row[side]
            if (
                not isinstance(xy, list)
                or len(xy) != 2
                or any(
                    type(v) not in (int, float) or not 0 <= v < size[i]
                    for i, v in enumerate(xy)
                )
            ):
                raise ValueError("대응점 좌표 오류")
    if project:
        if asset["project_id"] != project.project_id:
            raise ValueError("다른 프로젝트의 정합")
        sources = {s.source_id: s for s in project.image_sources}
        for side in ("source", "target"):
            s = sources.get(asset[side + "_id"])
            if (
                not s
                or s.acquisition_metadata.get("format") != "JPEG"
                or not s.content_hash
                or s.content_hash.value != asset[side + "_sha256"]
                or [s.width, s.height] != asset[side + "_size"]
            ):
                raise ValueError("정합 원본 identity 불일치")
    # Reject non-finite values anywhere in nested evidence, not only the matrix.
    json.dumps(asset, allow_nan=False)
    return asset


def make_asset(project, source, target, result):
    asset = {
        "schema": SCHEMA,
        "registration_id": str(uuid4()),
        "project_id": project.project_id,
        "source_id": source.source_id,
        "target_id": target.source_id,
        "source_sha256": source.content_hash.value,
        "target_sha256": target.content_hash.value,
        "source_size": [source.width, source.height],
        "target_size": [target.width, target.height],
        "direction": "before_to_after",
        "created_at": utc_now().isoformat(),
        "reviewer_id": None,
        "parent_registration_id": None,
        **{
            k: result[k]
            for k in (
                "algorithm",
                "algorithm_version",
                "model",
                "matrix",
                "landmarks",
                "quality",
                "timings",
                "status",
            )
        },
        "refinement": result.get("refinement", {}),
    }
    return validate(asset, project)


def approve(asset, reviewer):
    validate(asset)
    if asset["status"] != "NEEDS_REVIEW" or not reviewer.strip() or len(reviewer) > 200:
        raise ValueError("검토 가능한 정합과 검수자 ID가 필요합니다")
    return validate(
        {
            **asset,
            "registration_id": str(uuid4()),
            "status": "ACCEPTED",
            "reviewer_id": reviewer.strip(),
            "parent_registration_id": asset["registration_id"],
            "created_at": utc_now().isoformat(),
        }
    )


def encoded(asset):
    validate(asset)
    data = (
        json.dumps(
            asset, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    if len(data) > MAX_BYTES:
        raise ValueError("정합 자산 예산 초과")
    return data


def reference(asset):
    return PREFIX + hashlib.sha256(encoded(asset)).hexdigest() + ".json"


def relationship(asset):
    return ImageRelationship(
        str(uuid4()),
        asset["source_id"],
        asset["target_id"],
        ImageRole.BEFORE_ANNEALING,
        ImageRole.AFTER_ANNEALING,
        asset["registration_id"],
        reference(asset),
        None,
        VerificationStatus.VERIFIED
        if asset["status"] == "ACCEPTED"
        else VerificationStatus.UNVERIFIED,
    )


def _pairs(rows):
    out = {}
    for k, v in rows:
        if k in out:
            raise ValueError("정합 JSON 중복 key")
        out[k] = v
    return out


def read(path, ref, project=None):
    from sic_xrt_analyzer.results.persistence import ProjectStore

    if not re.fullmatch(r"assets/registrations/[0-9a-f]{64}\.json", ref):
        raise ValueError("잘못된 정합 참조")
    asset_path = ProjectStore().resolve_asset(path, ref)
    with asset_path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != Path(ref).stem:
        raise ValueError("정합 자산 크기/해시 오류")
    asset = json.loads(
        data,
        object_pairs_hook=_pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("비유한 JSON")),
    )
    return validate(asset, project)


def publish(path, asset):
    root = Path(path).resolve().parent
    ref = reference(asset)
    target = root / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError("정합 자산 경로 이탈")
    data = encoded(asset)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("기존 자산 덮어쓰기 거부")
        return ref
    fd, name = tempfile.mkstemp(prefix=".registration-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Content addressing makes a concurrent publication of the same bytes harmless.
        try:
            os.link(name, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError("기존 자산 덮어쓰기 거부")
    finally:
        Path(name).unlink(missing_ok=True)
    read(path, ref)
    return ref


def validate_project_assets(path, project):
    for relation in project.image_relationships:
        if relation.transform_reference and relation.transform_reference.startswith(
            PREFIX
        ):
            a = read(path, relation.transform_reference, project)
            if (a["registration_id"], a["source_id"], a["target_id"]) != (
                relation.registration_id,
                relation.source_image_id,
                relation.target_image_id,
            ):
                raise ValueError("관계/자산 identity 불일치")
            if (
                (relation.source_role, relation.target_role)
                != (ImageRole.BEFORE_ANNEALING, ImageRole.AFTER_ANNEALING)
                or relation.match_quality is not None
                or (relation.verification_status == VerificationStatus.VERIFIED)
                != (a["status"] == "ACCEPTED")
            ):
                raise ValueError("관계/승인 상태 불일치")
            if a["parent_registration_id"] and not any(
                r.registration_id == a["parent_registration_id"]
                and r.source_image_id == a["source_id"]
                and r.target_image_id == a["target_id"]
                for r in project.image_relationships
            ):
                raise ValueError("정합 승인 근거 누락")
            if a["status"] == "ACCEPTED":
                parent_relation = next(
                    r
                    for r in project.image_relationships
                    if r.registration_id == a["parent_registration_id"]
                )
                parent = read(path, parent_relation.transform_reference, project)
                ignored = {
                    "registration_id",
                    "status",
                    "created_at",
                    "reviewer_id",
                    "parent_registration_id",
                }
                if (
                    parent["status"] != "NEEDS_REVIEW"
                    or any(a[k] != parent[k] for k in FIELDS - ignored)
                    or datetime.fromisoformat(a["created_at"])
                    < datetime.fromisoformat(parent["created_at"])
                ):
                    raise ValueError(
                        "승인은 추정 자산의 과학적 근거를 변경할 수 없습니다"
                    )


def copy_assets(old_path, new_path, project):
    for r in project.image_relationships:
        if r.transform_reference and r.transform_reference.startswith(PREFIX):
            publish(new_path, read(old_path, r.transform_reference, project))


def append(project, asset):
    validate(asset, project)
    return project.evolve(
        image_relationships=(*project.image_relationships, relationship(asset))
    )


def assign_roles(project, before_id, after_id):
    if before_id == after_id:
        raise ValueError("서로 다른 JPG를 선택하세요")
    return project.evolve(
        image_sources=tuple(
            replace(
                s,
                role=ImageRole.BEFORE_ANNEALING
                if s.source_id == before_id
                else ImageRole.AFTER_ANNEALING,
            )
            if s.source_id in (before_id, after_id)
            else s
            for s in project.image_sources
        )
    )
