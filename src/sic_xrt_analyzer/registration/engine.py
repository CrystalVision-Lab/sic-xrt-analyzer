"""Bounded CPU registration. Matrices map encoded Before pixel centres to After."""

import time

import cv2
import numpy as np

VERSION = "xrt-registration-cpu/1.0"
MODELS = ("translation", "rigid", "similarity", "affine")
PREVIEW_EDGE = 1600
FEATURE_LIMIT = 4000


def check(cancelled):
    if cancelled():
        raise InterruptedError("정합 취소됨")


def validate_transform(matrix, model=None, *, physical=True):
    m = np.asarray(matrix, dtype=float)
    if (
        m.shape != (3, 3)
        or not np.isfinite(m).all()
        or not np.allclose(m[2], [0, 0, 1], atol=1e-10)
    ):
        raise ValueError("유한한 affine 3×3 행렬이 필요합니다")
    a = m[:2, :2]
    singular = np.linalg.svd(a, compute_uv=False)
    if (
        np.linalg.det(a) <= 1e-12
        or (physical and not 0.1 <= singular.min() <= singular.max() <= 10)
        or (physical and singular.max() / singular.min() > 4)
    ):
        raise ValueError("특이·반전·과도한 변형 행렬은 지원하지 않습니다")
    if model not in (*MODELS, None):
        raise ValueError("지원하지 않는 변환 유형")
    if model == "translation" and not np.allclose(a, np.eye(2), atol=1e-6):
        raise ValueError("Translation은 이동만 허용합니다")
    if model in ("rigid", "similarity") and not np.allclose(
        a.T @ a, np.eye(2) * singular[0] ** 2, atol=1e-5
    ):
        raise ValueError("균일 회전/배율이 아닙니다")
    if model == "rigid" and not np.allclose(a.T @ a, np.eye(2), atol=1e-5):
        raise ValueError("Rigid는 배율을 변경할 수 없습니다")
    return m


def transform_points(matrix, points):
    m = validate_transform(matrix, physical=False)
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
        raise ValueError("유한한 N×2 좌표가 필요합니다")
    return p @ m[:2, :2].T + m[:2, 2]


def inverse_transform(matrix):
    return validate_transform(
        np.linalg.inv(validate_transform(matrix, physical=False)), physical=False
    )


def transform_bounds(matrix, bounds):
    x, y, w, h = bounds
    p = transform_points(matrix, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    lo, hi = p.min(0), p.max(0)
    return (*lo, *(hi - lo))


def pixel_mapping(width, height, original_width, original_height):
    # OpenCV resize: dst centre u maps to (u+.5)*original/preview-.5.
    sx, sy = original_width / width, original_height / height
    return np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1.0]], float)


def _fit(a, b, model):
    if model == "affine":
        if np.linalg.matrix_rank(np.column_stack((a, np.ones(len(a))))) < 3:
            raise ValueError("Affine 대응점이 공선입니다")
        m = np.eye(3)
        m[:2] = np.linalg.lstsq(np.column_stack((a, np.ones(len(a)))), b, rcond=None)[
            0
        ].T
    elif model == "translation":
        m = np.eye(3)
        m[:2, 2] = np.mean(b - a, axis=0)
    else:
        aa, bb = a - a.mean(0), b - b.mean(0)
        if np.sum(aa**2) < 1e-8 or np.sum(bb**2) < 1e-8:
            raise ValueError("대응점 위치가 중복되거나 퇴화했습니다")
        u, s, vt = np.linalg.svd(aa.T @ bb)
        fix = np.diag([1.0, np.linalg.det(vt.T @ u.T)])
        rotation = vt.T @ fix @ u.T
        scale = np.sum(s * np.diag(fix)) / np.sum(aa**2) if model == "similarity" else 1
        m = np.eye(3)
        m[:2, :2] = scale * rotation
        m[:2, 2] = b.mean(0) - m[:2, :2] @ a.mean(0)
    return validate_transform(m, model)


def quality(matrix, a, b, source_size, target_size, threshold=8.0, automatic=False):
    m = validate_transform(matrix)
    error = np.linalg.norm(transform_points(m, a) - b, axis=1)
    mask = error <= threshold
    support = []
    for points, size in ((a[mask], source_size), (b[mask], target_size)):
        area = (
            abs(cv2.contourArea(cv2.convexHull(points.astype(np.float32))))
            if len(points) >= 3
            else 0
        )
        support.append(area / (size[0] * size[1]))
    sw, sh = source_size
    tw, th = target_size
    projected = transform_points(
        m, [[-0.5, -0.5], [sw - 0.5, -0.5], [sw - 0.5, sh - 0.5], [-0.5, sh - 0.5]]
    ).astype(np.float32)
    target = np.array(
        [[-0.5, -0.5], [tw - 0.5, -0.5], [tw - 0.5, th - 0.5], [-0.5, th - 0.5]],
        np.float32,
    )
    overlap, _ = cv2.intersectConvexConvex(projected, target)
    coverage = float(overlap / (tw * th))
    reasons = []
    if not mask.any() or coverage < 0.05:
        reasons.append("공통 유효 영역 또는 대응점 부족")
    if automatic and (mask.sum() < 12 or mask.mean() < 0.4 or min(support) < 0.02):
        reasons.append("자동 대응점 수·비율·공간 분포 부족")
    return {
        "candidate_count": len(a),
        "inlier_count": int(mask.sum()),
        "inlier_ratio": float(mask.mean()),
        "median_error_after_px": float(np.median(error)),
        "p90_error_after_px": float(np.quantile(error, 0.9)),
        "source_support_fraction": support[0],
        "target_support_fraction": support[1],
        "overlap_target_fraction": coverage,
        "linear_condition": float(np.linalg.cond(m[:2, :2])),
        "error_unit": "after_original_pixel",
        "reasons": reasons,
    }, mask


def fit_landmarks(
    before,
    after,
    source_size,
    target_size,
    model="similarity",
    *,
    robust=False,
    threshold=8.0,
):
    if model not in MODELS:
        raise ValueError("지원하지 않는 변환")
    a, b = (
        np.asarray(before, float).reshape(-1, 2),
        np.asarray(after, float).reshape(-1, 2),
    )
    minimum = {"translation": 1, "rigid": 2, "similarity": 2, "affine": 3}[model]
    if (
        a.shape != b.shape
        or len(a) < minimum
        or len(a) > FEATURE_LIMIT
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
    ):
        raise ValueError("대응점 수 또는 값이 유효하지 않습니다")
    for points, (w, h) in ((a, source_size), (b, target_size)):
        if np.any(points < 0) or np.any(points[:, 0] >= w) or np.any(points[:, 1] >= h):
            raise ValueError("원본 밖의 대응점")
        if len(np.unique(points, axis=0)) != len(points):
            raise ValueError("중복 대응점")
        if (
            len(points) >= 3
            and np.linalg.svd(points - points.mean(0), compute_uv=False)[-1]
            < np.linalg.svd(points - points.mean(0), compute_uv=False)[0] * 0.01
        ):
            raise ValueError("대응점이 거의 일직선에 있습니다")
    if robust:
        if model == "translation":
            offset = np.median(b - a, axis=0)
            mask = np.linalg.norm(b - a - offset, axis=1) <= threshold
        else:
            fn = (
                cv2.estimateAffine2D
                if model == "affine"
                else cv2.estimateAffinePartial2D
            )
            cv2.setRNGSeed(114)
            _, mask = fn(
                a,
                b,
                method=cv2.RANSAC,
                ransacReprojThreshold=threshold,
                maxIters=3000,
                confidence=0.995,
            )
            if mask is None:
                raise ValueError("RANSAC 대응점 추정 실패")
            mask = mask.ravel().astype(bool)
        if mask.sum() < minimum:
            raise ValueError("유효 대응점 부족")
        matrix = _fit(a[mask], b[mask], model)
    else:
        matrix = _fit(a, b, model)
    metrics, mask = quality(matrix, a, b, source_size, target_size, threshold, robust)
    return {
        "matrix": matrix.tolist(),
        "model": model,
        "quality": metrics,
        "landmarks": [
            {"before": x.tolist(), "after": y.tolist(), "inlier": bool(k)}
            for x, y, k in zip(a, b, mask, strict=True)
        ],
        "status": "REJECTED" if metrics["reasons"] else "NEEDS_REVIEW",
    }


def grey(image):
    g = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)


def estimate(
    before,
    after,
    source_size,
    target_size,
    *,
    method="sift",
    model="auto",
    cancelled=lambda: False,
):
    timings = {}
    started = time.perf_counter()
    check(cancelled)
    a, b = grey(before), grey(after)
    ma = pixel_mapping(a.shape[1], a.shape[0], *source_size)
    mb = pixel_mapping(b.shape[1], b.shape[0], *target_size)
    if method in ("phase", "ecc"):
        w, h = min(1024, a.shape[1]), min(1024, a.shape[0])
        aa = cv2.resize(a, (w, h)).astype(np.float32) / 255
        bb = cv2.resize(b, (w, h)).astype(np.float32) / 255
        if min(aa.std(), bb.std()) < 0.005:
            raise ValueError("명암 구조가 부족합니다")
        shift, response = cv2.phaseCorrelate(aa, bb)
        m = np.eye(3)
        m[:2, 2] = shift
        if method == "ecc":
            # template=Before,input=After: ECC returns Before -> After, never invert it here.
            score, warp = cv2.findTransformECC(
                aa,
                bb,
                m[:2].astype(np.float32),
                cv2.MOTION_AFFINE
                if model == "affine"
                else cv2.MOTION_EUCLIDEAN
                if model == "rigid"
                else cv2.MOTION_TRANSLATION,
                (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 80, 1e-5),
                None,
                5,
            )
            m[:2] = warp
            response = score
        check(cancelled)
        matrix = (
            pixel_mapping(w, h, *target_size)
            @ m
            @ np.linalg.inv(pixel_mapping(w, h, *source_size))
        )
        chosen = (
            "affine"
            if method == "ecc" and model == "affine"
            else "similarity"
            if source_size != target_size
            else "rigid"
            if model == "rigid" and method == "ecc"
            else "translation"
        )
        validate_transform(matrix, chosen)
        sample = np.array(
            [
                [source_size[0] * x, source_size[1] * y]
                for x in (0.2, 0.5, 0.8)
                for y in (0.2, 0.5, 0.8)
            ]
        )
        mapped = transform_points(matrix, sample)
        metrics, _ = quality(matrix, sample, mapped, source_size, target_size)
        metrics.update(
            candidate_count=0,
            inlier_count=0,
            inlier_ratio=0.0,
            median_error_after_px=None,
            p90_error_after_px=None,
            source_support_fraction=None,
            target_support_fraction=None,
            intensity_response=float(response),
            evidence="intensity_only_no_independent_reprojection",
        )
        if response < 0.2:
            metrics["reasons"].append("명암 상관 부족")
        result = {
            "matrix": matrix.tolist(),
            "model": chosen,
            "quality": metrics,
            "landmarks": [],
            "status": "REJECTED" if metrics["reasons"] else "NEEDS_REVIEW",
        }
        timings["intensity_ms"] = (time.perf_counter() - started) * 1000
    else:
        if method not in ("sift", "orb"):
            raise ValueError("지원하지 않는 정합 방식")
        detector = (
            cv2.SIFT_create(nfeatures=FEATURE_LIMIT)
            if method == "sift"
            else cv2.ORB_create(nfeatures=FEATURE_LIMIT)
        )
        ka, da = detector.detectAndCompute(a, None)
        check(cancelled)
        kb, db = detector.detectAndCompute(b, None)
        check(cancelled)
        timings["features_ms"] = (time.perf_counter() - started) * 1000
        if da is None or db is None or min(len(da), len(db)) < 12:
            raise ValueError("특징점 부족: 수동 대응점을 지정하세요")
        ts = time.perf_counter()
        matcher = cv2.BFMatcher(cv2.NORM_L2 if method == "sift" else cv2.NORM_HAMMING)
        reverse = {
            x.queryIdx: x.trainIdx
            for pair in matcher.knnMatch(db, da, k=2)
            if len(pair) == 2
            for x, y in [pair]
            if x.distance < 0.75 * y.distance
        }
        good = [
            x
            for pair in matcher.knnMatch(da, db, k=2)
            if len(pair) == 2
            for x, y in [pair]
            if x.distance < 0.75 * y.distance and reverse.get(x.trainIdx) == x.queryIdx
        ]
        seen_a, seen_b = set(), set()
        pairs = []
        for match in good:
            x, y = ka[match.queryIdx].pt, kb[match.trainIdx].pt
            sx, sy = tuple(np.round(x, 1)), tuple(np.round(y, 1))
            if sx not in seen_a and sy not in seen_b:
                pairs.append((x, y))
                seen_a.add(sx)
                seen_b.add(sy)
        if len(pairs) < 12:
            raise ValueError("서로 일치하는 독립 특징점 부족")
        aa = transform_points(ma, [p[0] for p in pairs])
        bb = transform_points(mb, [p[1] for p in pairs])
        check(cancelled)
        timings["matching_ms"] = (time.perf_counter() - ts) * 1000
        ts = time.perf_counter()
        candidates = []
        for kind in MODELS if model == "auto" else (model,):
            try:
                candidate = fit_landmarks(
                    aa,
                    bb,
                    source_size,
                    target_size,
                    kind,
                    robust=True,
                    threshold=3 * max(mb[0, 0], mb[1, 1]),
                )
                if candidate["status"] != "REJECTED":
                    candidates.append(candidate)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("대응점·분포·변환 품질 검사 실패")
        best = min(candidates, key=lambda r: r["quality"]["median_error_after_px"])
        # Prefer simpler transform if its error is within half a preview pixel and support comparable.
        result = next(
            (
                r
                for r in candidates
                if r["quality"]["median_error_after_px"]
                <= best["quality"]["median_error_after_px"]
                + 0.5 * max(mb[0, 0], mb[1, 1])
                and r["quality"]["inlier_count"]
                >= best["quality"]["inlier_count"] * 0.9
            ),
            best,
        )
        timings["transform_ms"] = (time.perf_counter() - ts) * 1000
    result.update(algorithm=method, algorithm_version=VERSION, timings=timings)
    result["timings"]["total_ms"] = (time.perf_counter() - started) * 1000
    return result


def refine(result, before_source, after_source, cancelled=lambda: False):
    """Bounded original crops: local phase shifts adjust translation only when consistent."""
    ts = time.perf_counter()
    matrix = validate_transform(result["matrix"])
    offsets = []
    evidence = []
    for row in result["landmarks"][:: max(1, len(result["landmarks"]) // 8)][:8]:
        check(cancelled)
        if not row["inlier"]:
            continue
        x, y = np.round(row["before"]).astype(int)
        u, v = np.round(transform_points(matrix, [[x, y]])[0]).astype(int)
        radius = 64
        if (
            min(x, y, u, v) < radius
            or x + radius >= before_source.metadata.width
            or y + radius >= before_source.metadata.height
            or u + radius >= after_source.metadata.width
            or v + radius >= after_source.metadata.height
        ):
            continue
        # Rotation/scale needs a resampled crop. Keep this conservative path near translation.
        if not np.allclose(matrix[:2, :2], np.eye(2), atol=0.03):
            break
        a = grey(
            before_source.read_region(int(x - radius), int(y - radius), 128, 128)
        ).astype(np.float32)
        b = grey(
            after_source.read_region(int(u - radius), int(v - radius), 128, 128)
        ).astype(np.float32)
        shift, response = cv2.phaseCorrelate(a, b)
        if response > 0.3 and np.linalg.norm(shift) < 8:
            offset = np.array([u, v]) + shift - transform_points(matrix, [[x, y]])[0]
            offsets.append(offset)
            evidence.append(
                {
                    "before": [int(x), int(y)],
                    "shift_after_px": offset.tolist(),
                    "response": float(response),
                }
            )
    if (
        len(offsets) >= 3
        and np.max(np.linalg.norm(offsets - np.median(offsets, axis=0), axis=1)) < 2
    ):
        adjusted = matrix.copy()
        adjusted[:2, 2] += np.median(offsets, axis=0)
        a = [r["before"] for r in result["landmarks"]]
        b = [r["after"] for r in result["landmarks"]]
        q, _ = quality(
            adjusted,
            np.array(a),
            np.array(b),
            (before_source.metadata.width, before_source.metadata.height),
            (after_source.metadata.width, after_source.metadata.height),
            threshold=max(8, result["quality"]["p90_error_after_px"] * 2),
            automatic=True,
        )
        if (
            not q["reasons"]
            and q["median_error_after_px"] <= result["quality"]["median_error_after_px"]
        ):
            result = {**result, "matrix": adjusted.tolist(), "quality": q}
    result["refinement"] = {
        "method": "original_crop_phase_translation",
        "crop_limit": 8,
        "crop_edge": 128,
        "evidence": evidence,
        "accepted_count": len(offsets),
    }
    result["timings"]["refinement_ms"] = (time.perf_counter() - ts) * 1000
    check(cancelled)
    return result
