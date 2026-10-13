"""Versioned content addressed workspace revisions anchored in existing WaferPlacement references."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from uuid import uuid4

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.results.contracts import VerificationStatus, WaferPlacement
from sic_xrt_analyzer.results.serialization import plain

from .mapping import calibration, matrix

PREFIX = "assets/wafer-maps/"
SCHEMA = "xrt_wafer_placement/v1"
MAX_BYTES = 8 * 1024**2
LAYERS = ("BPD", "TED", "TSD", "reviews", "human", "experimental", "model_geometry")
FIELDS = {
    "schema",
    "project_id",
    "map_id",
    "revision_id",
    "revision",
    "parent_reference",
    "created_at",
    "editor",
    "groups",
    "placements",
    "selected_group",
    "runs",
    "layers",
    "prior_wafer_metadata",
}


def blank(project):
    return {
        "schema": SCHEMA,
        "project_id": project.project_id,
        "map_id": str(uuid4()),
        "revision_id": str(uuid4()),
        "revision": 0,
        "parent_reference": None,
        "created_at": utc_now().isoformat(),
        "editor": "",
        "groups": [
            {
                "id": "relative",
                "label": "임시 관측 그룹",
                "mode": "TEMPORARY",
                "wafer_id": None,
                "coordinate_system": "RELATIVE_LAYOUT",
                "unit": None,
                "origin": "사용자 상대 원점",
                "axes": "X_RIGHT_Y_DOWN",
                "evidence": "",
                "geometry": None,
            }
        ],
        "placements": [],
        "selected_group": "relative",
        "runs": {},
        "layers": {k: True for k in LAYERS},
        "prior_wafer_metadata": {
            s.source_id: plain(s.wafer_placement)
            for s in project.image_sources
            if s.acquisition_metadata.get("format") == "JPEG"
        },
    }


def _text(x, empty=False):
    if not isinstance(x, str) or len(x) > 2000 or (not empty and not x.strip()):
        raise ValueError("지도 텍스트 필드 오류")


def _validate(a, project=None):
    if not isinstance(a, dict) or set(a) != FIELDS or a["schema"] != SCHEMA:
        raise ValueError("지원하지 않는 지도 자산 계약")
    for k in ("project_id", "map_id", "revision_id", "editor"):
        _text(a[k], empty=k == "editor")
    dt = datetime.fromisoformat(a["created_at"])
    if dt.tzinfo is None:
        raise ValueError("지도 시각에 timezone 필요")
    if type(a["revision"]) is not int or a["revision"] < 1:
        raise ValueError("지도 revision 오류")
    if a["parent_reference"] is not None and not re.fullmatch(
        r"assets/wafer-maps/[0-9a-f]{64}\.json", a["parent_reference"]
    ):
        raise ValueError("지도 부모 경로 오류")
    if not isinstance(a["groups"], list) or not 1 <= len(a["groups"]) <= 100:
        raise ValueError("그룹 예산 오류")
    groups = {}
    for g in a["groups"]:
        if set(g) != {
            "id",
            "label",
            "mode",
            "wafer_id",
            "coordinate_system",
            "unit",
            "origin",
            "axes",
            "evidence",
            "geometry",
        }:
            raise ValueError("그룹 필드 오류")
        for k in ("id", "label", "coordinate_system", "origin", "axes"):
            _text(g[k])
        _text(g["evidence"], True)
        if g["id"] in groups:
            raise ValueError("중복 그룹")
        groups[g["id"]] = g
        if g["axes"] not in ("X_RIGHT_Y_DOWN", "X_RIGHT_Y_UP"):
            raise ValueError("알 수 없는 축")
        if g["mode"] == "TEMPORARY":
            if (
                g["unit"] is not None
                or g["wafer_id"] is not None
                or g["coordinate_system"] != "RELATIVE_LAYOUT"
                or g["axes"] != "X_RIGHT_Y_DOWN"
                or g["geometry"] is not None
            ):
                raise ValueError("임시 배치에 물리 단위/외곽 금지")
        elif g["mode"] == "PHYSICAL":
            _text(g["wafer_id"])
            if (
                g["unit"] not in ("mm", "um")
                or g["coordinate_system"] in ("UNKNOWN", "RELATIVE_LAYOUT")
                or not g["evidence"].strip()
            ):
                raise ValueError("물리 좌표계 근거 부족")
            geo = g["geometry"]
            if geo is not None:
                if set(geo) != {"centre", "radius", "evidence", "reviewer"}:
                    raise ValueError("웨이퍼 외곽 근거 오류")
                _text(geo["evidence"])
                _text(geo["reviewer"])
                import numpy as np

                if (
                    len(geo["centre"]) != 2
                    or not np.isfinite([*geo["centre"], geo["radius"]]).all()
                    or geo["radius"] <= 0
                ):
                    raise ValueError("웨이퍼 외곽 값 오류")
        else:
            raise ValueError("지도 모드 오류")
    if a["selected_group"] not in groups:
        raise ValueError("선택 그룹 누락")
    if (
        not isinstance(a["layers"], dict)
        or set(a["layers"]) != set(LAYERS)
        or any(type(v) is not bool for v in a["layers"].values())
    ):
        raise ValueError("레이어 계약 오류")
    if (
        not isinstance(a["runs"], dict)
        or not isinstance(a["prior_wafer_metadata"], dict)
        or not isinstance(a["placements"], list)
        or len(a["placements"]) > 500
    ):
        raise ValueError("지도 예산/필드 오류")
    source_ids = set()
    for p in a["placements"]:
        if set(p) != {
            "placement_id",
            "source_id",
            "source_sha256",
            "size",
            "group_id",
            "matrix",
            "status",
            "evidence",
            "created_at",
            "editor",
        }:
            raise ValueError("배치 필드 오류")
        for k in ("placement_id", "source_id", "editor"):
            _text(p[k], k == "editor")
        if p["source_id"] in source_ids:
            raise ValueError("Source 중복 활성 배치")
        source_ids.add(p["source_id"])
        if not re.fullmatch("[0-9a-f]{64}", p["source_sha256"]):
            raise ValueError("배치 SHA 오류")
        if len(p["size"]) != 2 or any(type(v) is not int or v < 1 for v in p["size"]):
            raise ValueError("배치 해상도 오류")
        datetime.fromisoformat(p["created_at"])
        g = groups[p["group_id"]]
        matrix(p["matrix"], g["axes"])
        if p["status"] not in ("UNVERIFIED", "VERIFIED"):
            raise ValueError("배치 상태 오류")
        if p["status"] == "VERIFIED":
            calibration(p["matrix"], p["size"], g, p["evidence"])
        elif not isinstance(p["evidence"], dict):
            raise ValueError("배치 근거 오류")
    if project:
        if a["project_id"] != project.project_id:
            raise ValueError("다른 프로젝트 지도")
        sources = {s.source_id: s for s in project.image_sources}
        for p in a["placements"]:
            s = sources.get(p["source_id"])
            if (
                not s
                or s.acquisition_metadata.get("format") != "JPEG"
                or not s.content_hash
                or s.content_hash.value != p["source_sha256"]
                or [s.width, s.height] != p["size"]
            ):
                raise ValueError("지도 Source/SHA/해상도 불일치")
        for sid, rid in a["runs"].items():
            if sid not in sources or (
                rid
                and not any(
                    r.run_id == rid and r.source_id == sid
                    for r in project.analysis_runs
                )
            ):
                raise ValueError("지도 Run/Source 불일치")
    return a


def validate(a, project=None):
    try:
        return _validate(a, project)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("지도 계약의 필드·값·참조가 올바르지 않습니다") from exc


def encoded(a):
    validate(a)
    data = (
        json.dumps(a, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode()
    if len(data) > MAX_BYTES:
        raise ValueError("지도 자산 예산 초과")
    return data


def reference(a):
    return PREFIX + hashlib.sha256(encoded(a)).hexdigest() + ".json"


def publish(path, a):
    root = Path(path).resolve().parent
    ref = reference(a)
    target = root / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError("지도 경로 이탈")
    data = encoded(a)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("지도 자산 덮어쓰기 금지")
        return ref
    fd, name = tempfile.mkstemp(prefix=".wafer-map-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(name, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError("동시 지도 게시 불일치")
    finally:
        Path(name).unlink(missing_ok=True)
    return ref


def read(path, ref, project=None):
    from sic_xrt_analyzer.results.persistence import ProjectStore

    if not re.fullmatch(r"assets/wafer-maps/[0-9a-f]{64}\.json", ref):
        raise ValueError("지도 경로 오류")
    with ProjectStore().resolve_asset(path, ref).open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != Path(ref).stem:
        raise ValueError("지도 자산 크기/SHA 오류")

    def pairs(rows):
        out = {}
        for k, v in rows:
            if k in out:
                raise ValueError("지도 JSON 중복 key")
            out[k] = v
        return out

    a = json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("비유한 지도 값")),
    )
    return validate(a, project)


def active_reference(project):
    refs = {
        s.wafer_placement.alignment_reference
        for s in project.image_sources
        if s.wafer_placement.alignment_reference
        and s.wafer_placement.alignment_reference.startswith(PREFIX)
    }
    if len(refs) > 1:
        raise ValueError("서로 다른 활성 지도 revision")
    return next(iter(refs), None)


def chain(path, ref, project):
    result = []
    seen = set()
    total_bytes = 0
    while ref:
        if ref in seen or len(seen) >= 128:
            raise ValueError("지도 부모 순환/이력 예산")
        seen.add(ref)
        a = read(path, ref, project)
        total_bytes += len(encoded(a))
        if total_bytes > 32 * 1024**2:
            raise ValueError("지도 이력 32MiB 예산 초과")
        result.append((ref, a))
        ref = a["parent_reference"]
    for (_, a), (_, b) in pairwise(result):
        if (
            a["map_id"] != b["map_id"]
            or a["revision"] != b["revision"] + 1
            or datetime.fromisoformat(a["created_at"])
            < datetime.fromisoformat(b["created_at"])
        ):
            raise ValueError("지도 revision 이력 오류")
    if result and result[-1][1]["revision"] != 1:
        raise ValueError("지도 최초 이력 누락")
    return result


def validate_project_assets(path, project):
    ref = active_reference(project)
    if not ref:
        return
    rows = chain(path, ref, project)
    a = rows[0][1]
    placements = {p["source_id"]: p for p in a["placements"]}
    groups = {g["id"]: g for g in a["groups"]}
    for s in project.image_sources:
        if s.source_id in placements and s.wafer_placement.alignment_reference != ref:
            raise ValueError("배치 Source의 활성 자산 참조 누락")
        if s.wafer_placement.alignment_reference != ref:
            continue
        p = placements.get(s.source_id)
        expected = placement_metadata(ref, p, groups)
        if s.wafer_placement != expected:
            raise ValueError("지도/Source 배치 상태 불일치")


def placement_metadata(ref, p, groups):
    if not p:
        return WaferPlacement(
            alignment_reference=ref, calibration_status=VerificationStatus.UNVERIFIED
        )
    g = groups[p["group_id"]]
    return WaferPlacement(
        g["wafer_id"] if g["mode"] == "PHYSICAL" else g["id"],
        tuple(float(row[2]) for row in p["matrix"][:2]),
        ref,
        g["coordinate_system"],
        VerificationStatus(p["status"]),
    )


def append(project, a, path):
    validate(a, project)
    ref = publish(path, a)
    groups = {g["id"]: g for g in a["groups"]}
    placements = {p["source_id"]: p for p in a["placements"]}
    return project.evolve(
        image_sources=tuple(
            replace(
                s,
                wafer_placement=placement_metadata(
                    ref, placements.get(s.source_id), groups
                ),
            )
            if s.acquisition_metadata.get("format") == "JPEG"
            else s
            for s in project.image_sources
        )
    )


def copy_assets(old_path, new_path, project):
    ref = active_reference(project)
    if ref:
        for _, a in reversed(chain(old_path, ref, project)):
            publish(new_path, a)


def check_history(old, new):
    oldref = active_reference(old)
    newref = active_reference(new)
    if oldref and not newref:
        raise ValueError("지도 이력 삭제 금지")
    return oldref, newref
