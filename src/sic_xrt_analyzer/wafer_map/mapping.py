"""Original integer pixel centres -> explicit relative/physical affine coordinates."""

import math

import numpy as np


def matrix(value, axes="X_RIGHT_Y_DOWN"):
    m = np.asarray(value, dtype=float)
    if (
        m.shape != (3, 3)
        or not np.isfinite(m).all()
        or not np.allclose(m[2], [0, 0, 1], atol=1e-12)
    ):
        raise ValueError("유한한 3×3 affine 행렬이 필요합니다")
    s = np.linalg.svd(m[:2, :2], compute_uv=False)
    if (
        s.min() < 1e-9
        or s.max() > 1e9
        or s.max() / s.min() > 1e4
        or np.max(np.abs(m)) > 1e12
    ):
        raise ValueError("특이·과도한 배율/좌표 변환")
    expected = -1 if axes == "X_RIGHT_Y_UP" else 1
    if (
        axes not in ("X_RIGHT_Y_DOWN", "X_RIGHT_Y_UP")
        or np.linalg.det(m[:2, :2]) * expected <= 0
    ):
        raise ValueError("명시한 축 방향과 행렬 반전이 다릅니다")
    return m


def points(transform, xy):
    p = np.asarray(xy, float)
    if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
        raise ValueError("유한한 XY 좌표가 필요합니다")
    m = np.asarray(transform, float)
    return (p @ m[:2, :2].T + m[:2, 2]).tolist()


def inverse(transform):
    return np.linalg.inv(np.asarray(transform, float)).tolist()


def footprint(transform, width, height):
    return points(
        transform,
        [
            [-0.5, -0.5],
            [width - 0.5, -0.5],
            [width - 0.5, height - 0.5],
            [-0.5, height - 0.5],
        ],
    )


def layout(x, y, rotation, sx, sy, axes="X_RIGHT_Y_DOWN"):
    values = np.array([x, y, rotation, sx, sy], float)
    if not np.isfinite(values).all() or min(sx, sy) <= 0:
        raise ValueError("위치·회전·양수 크기를 입력하세요")
    r = math.radians(rotation)
    c, s = math.cos(r), math.sin(r)
    sign = -1 if axes == "X_RIGHT_Y_UP" else 1
    return matrix(
        [[c * sx, -s * sy * sign, x], [s * sx, c * sy * sign, y], [0, 0, 1]], axes
    ).tolist()


def calibration(transform, source_size, group, evidence):
    """Independent control points plus explicit scale and provenance; local attestation only."""
    m = matrix(transform, group["axes"])
    if (
        group["mode"] != "PHYSICAL"
        or not group["wafer_id"]
        or group["unit"] not in ("mm", "um")
        or not group["origin"].strip()
        or not group["evidence"].strip()
    ):
        raise ValueError("물리 Wafer ID·단위·원점·좌표계 근거가 필요합니다")
    if set(evidence) != {
        "source",
        "reviewer",
        "pixel_spacing",
        "landmarks",
        "tolerance",
        "registration_reference",
        "same_target_evidence",
    }:
        raise ValueError("캘리브레이션 근거 필드가 다릅니다")
    if not evidence["source"].strip() or not evidence["reviewer"].strip():
        raise ValueError("측정 출처·검수자 ID가 필요합니다")
    scales = np.asarray(evidence["pixel_spacing"], float)
    if (
        scales.shape != (2,)
        or not np.isfinite(scales).all()
        or min(scales) <= 0
        or not np.allclose(
            np.linalg.norm(m[:2, :2], axis=0), scales, rtol=0.01, atol=1e-12
        )
    ):
        raise ValueError("두 축 픽셀 크기와 변환이 일치하지 않습니다")
    pairs = evidence["landmarks"]
    if not isinstance(pairs, list) or not 3 <= len(pairs) <= 64:
        raise ValueError("독립적인 비공선 기준점 3쌍 이상이 필요합니다")
    a = np.asarray([p["image"] for p in pairs], float)
    b = np.asarray([p["map"] for p in pairs], float)
    if (
        a.shape != b.shape
        or a.shape[1:] != (2,)
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
    ):
        raise ValueError("기준점 좌표 오류")
    if (
        (a < 0).any()
        or (a >= np.asarray(source_size)).any()
        or len(np.unique(a, axis=0)) != len(a)
        or len(np.unique(b, axis=0)) != len(b)
    ):
        raise ValueError("원본 밖/중복 기준점")
    centred = (a - a.mean(0)) / np.asarray(source_size)
    singular = np.linalg.svd(centred, compute_uv=False)
    if singular.min() < 1e-4 or singular.max() / singular.min() > 100:
        raise ValueError("기준점이 거의 일직선이거나 근거가 좁습니다")
    tol = evidence["tolerance"]
    if (
        type(tol) not in (int, float)
        or not math.isfinite(tol)
        or tol <= 0
        or tol > max(scales) * 10
    ):
        raise ValueError("측정 허용 오차는 양수·최대 10 원본 픽셀 범위입니다")
    errors = np.linalg.norm(np.asarray(points(m, a)) - b, axis=1)
    if errors.max() > tol:
        raise ValueError("독립 기준점 오차가 허용 범위를 초과합니다")
    return {
        "max_error": float(errors.max()),
        "median_error": float(np.median(errors)),
        "unit": group["unit"],
        "local_attestation_not_independent_science": True,
    }


def compose(registration, target, group, source, target_source, same_target_evidence):
    from sic_xrt_analyzer.registration.engine import validate_transform

    if (
        registration["status"] != "ACCEPTED"
        or not registration["matrix"]
        or target["status"] != "VERIFIED"
        or target["group_id"] != group["id"]
        or group["mode"] != "PHYSICAL"
        or not same_target_evidence.strip()
    ):
        raise ValueError("승인 정합·검증 배치·동일 실험 대상 근거가 필요합니다")
    if (registration["source_id"], registration["target_id"]) != (
        source.source_id,
        target_source.source_id,
    ) or target["source_id"] != target_source.source_id:
        raise ValueError("Source/Target 방향 불일치")
    for r, sha in (
        (source, registration["source_sha256"]),
        (target_source, registration["target_sha256"]),
    ):
        if not r.content_hash or r.content_hash.value != sha:
            raise ValueError("정합 원본 SHA 불일치")
    result = matrix(
        matrix(target["matrix"], group["axes"])
        @ validate_transform(registration["matrix"]),
        group["axes"],
    )
    # Composition is a proposal: independent source control points are still required to verify it.
    return result.tolist()


def view(centre, zoom, width, height, axes="X_RIGHT_Y_DOWN"):
    """Physical +Y up maps toward screen -Y; relative/image +Y maps down."""
    sign = -1 if axes == "X_RIGHT_Y_UP" else 1
    values = np.asarray([*centre, zoom, width, height], float)
    if (
        values.shape != (5,)
        or not np.isfinite(values).all()
        or min(zoom, width, height) <= 0
    ):
        raise ValueError("유한한 지도 화면 크기·양수 배율이 필요합니다")
    return matrix(
        [
            [zoom, 0, width / 2 - zoom * centre[0]],
            [0, sign * zoom, height / 2 - sign * zoom * centre[1]],
            [0, 0, 1],
        ],
        axes,
    )
