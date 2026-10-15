"""Display-only planar mosaics, with observed alignment evidence and bounded canvases."""

import math
import re

import cv2
import numpy as np

MAX_CANVAS = 3072


def _check(cancelled):
    if cancelled():
        raise InterruptedError("사진 맞춤 취소")


def reference_layout(images, metadata):
    """Locate tiles in a supplied larger composite; do not count it twice."""
    areas = np.array([m["width"] * m["height"] for m in metadata])
    base = int(np.argmax(areas))
    if len(areas) < 3 or areas[base] < 4 * np.median(np.delete(areas, base)):
        return None
    background = cv2.cvtColor(images[base], cv2.COLOR_RGB2GRAY)
    scale = images[base].shape[1] / metadata[base]["width"]
    matrices = {base: np.eye(3)}
    scores = []
    for i, (image, m) in enumerate(zip(images, metadata)):
        if i == base:
            continue
        w = round(m["width"] * scale)
        h = round(m["height"] * scale)
        if min(w, h) < 16 or w > background.shape[1] or h > background.shape[0]:
            continue
        template = cv2.cvtColor(
            cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY
        )
        if float(template.std()) < 0.5:
            continue
        match = cv2.matchTemplate(background, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, position = cv2.minMaxLoc(match)
        if score >= 0.72:
            matrices[i] = np.array(
                [
                    [w / image.shape[1], 0, position[0]],
                    [0, h / image.shape[0], position[1]],
                    [0, 0, 1.0],
                ]
            )
            scores.append(float(score))
    if len(matrices) < max(3, math.ceil(len(images) * 0.45)):
        return None
    return matrices, {
        "method": "PROVIDED_COMPOSITE",
        "reference": base,
        "matched": len(matrices) - 1,
        "minimum_correlation": min(scores),
    }


def edge_order(images, metadata):
    """Infer numbered non-overlap scan order only with boundary continuity evidence."""
    n = len(images)
    side = math.isqrt(n)
    ranked = [
        re.fullmatch(r"(.*?)(\d+)", m["name"].rsplit(".", 1)[0]) for m in metadata
    ]
    if n < 4 or side * side != n or not all(ranked):
        return None
    if len({m[1].strip().lower() for m in ranked}) != 1:
        return None
    if (
        max(im.shape[0] / im.shape[1] for im in images)
        / min(im.shape[0] / im.shape[1] for im in images)
        > 1.05
    ):
        return None
    ids = sorted(range(n), key=lambda i: int(ranked[i][2]))
    if [int(ranked[i][2]) for i in ids] != list(range(1, n + 1)):
        return None
    tiles = [
        cv2.resize(im, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32)
        for im in images
    ]

    def cost(order):
        costs = []
        for r in range(side):
            for c in range(side):
                a = tiles[order[r * side + c]]
                if c + 1 < side:
                    costs.append(
                        float(
                            np.mean(
                                np.abs(
                                    a[:, -2:].mean(1)
                                    - tiles[order[r * side + c + 1]][:, :2].mean(1)
                                )
                            )
                        )
                    )
                if r + 1 < side:
                    costs.append(
                        float(
                            np.mean(
                                np.abs(
                                    a[-2:].mean(0)
                                    - tiles[order[(r + 1) * side + c]][:2].mean(0)
                                )
                            )
                        )
                    )
        return np.mean(costs)

    grid = np.array(ids).reshape(side, side)
    snake = grid.copy()
    snake[1::2] = snake[1::2, ::-1]
    candidates = [grid.ravel(), snake.ravel(), grid.T.ravel(), snake.T.ravel()]
    best = min(candidates, key=cost)
    score = cost(best)
    rng = np.random.default_rng(131)
    random_costs = np.array([cost(rng.permutation(ids)) for _ in range(64)])
    if (
        score >= np.median(random_costs) * 0.65
        or np.count_nonzero(random_costs <= score) > 1
    ):
        return None
    w = int(np.median([im.shape[1] for im in images]))
    h = int(np.median([im.shape[0] for im in images]))
    matrices = {
        int(i): np.array(
            [
                [w / images[i].shape[1], 0, (k % side) * w],
                [0, h / images[i].shape[0], (k // side) * h],
                [0, 0, 1.0],
            ]
        )
        for k, i in enumerate(best)
    }
    return matrices, {
        "method": "ACQUISITION_EDGE_ORDER",
        "edge_error": float(score),
        "random_edge_error": float(np.median(random_costs)),
        "matched": n,
    }


def feature_layout(images, cancelled, progress):
    cv2.setRNGSeed(131)
    sift = cv2.SIFT_create(nfeatures=1800, contrastThreshold=0.015)
    features = []
    for i, im in enumerate(images):
        _check(cancelled)
        features.append(
            sift.detectAndCompute(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), None)
        )
        progress(i + 1, len(images), "겹침 특징 확인")
    pairs = [
        (i, j)
        for i in range(len(images))
        for j in range(i + 1, len(images))
        if len(images) <= 40 or j - i <= 6
    ]
    edges = []
    matcher = cv2.BFMatcher()
    for k, (i, j) in enumerate(pairs):
        _check(cancelled)
        ka, da = features[i]
        kb, db = features[j]
        if da is None or db is None:
            continue
        matches = matcher.knnMatch(da, db, k=2)
        good = [
            m
            for pair in matches
            if len(pair) == 2
            for m, n in [pair]
            if m.distance < 0.7 * n.distance
        ]
        if len(good) < 12:
            continue
        a = np.float32([ka[m.queryIdx].pt for m in good])
        b = np.float32([kb[m.trainIdx].pt for m in good])
        affine, inliers = cv2.estimateAffinePartial2D(
            b,
            a,
            method=cv2.RANSAC,
            ransacReprojThreshold=2.0,
            maxIters=2000,
            confidence=0.995,
        )
        if affine is None:
            continue
        keep = inliers.ravel().astype(bool)
        count = int(keep.sum())
        if count < 12 or count / len(good) < 0.35:
            continue
        scale = float(np.linalg.norm(affine[0, :2]))
        if not 0.45 <= scale <= 2.2:
            continue
        if min(np.ptp(a[keep], axis=0)) < min(images[i].shape[:2]) * 0.05:
            continue
        pred = b[keep] @ affine[:, :2].T + affine[:, 2]
        error = float(np.sqrt(np.mean(np.sum((pred - a[keep]) ** 2, axis=1))))
        if error > 1.8:
            continue
        matrix = np.vstack([affine, [0, 0, 1.0]])
        corners = np.float32(
            [
                [0, 0],
                [images[j].shape[1], 0],
                [images[j].shape[1], images[j].shape[0]],
                [0, images[j].shape[0]],
            ]
        )
        mapped = cv2.transform(corners[None], affine)[0]
        overlap, _ = cv2.intersectConvexConvex(
            np.float32(
                [
                    [0, 0],
                    [images[i].shape[1], 0],
                    [images[i].shape[1], images[i].shape[0]],
                    [0, images[i].shape[0]],
                ]
            ),
            mapped,
        )
        if (
            overlap
            < min(
                images[i].shape[0] * images[i].shape[1],
                images[j].shape[0] * images[j].shape[1],
            )
            * 0.025
        ):
            continue
        edges.append((count / (1 + error), i, j, matrix, error))
        if k % 10 == 0:
            progress(k + 1, len(pairs), "사진 위치 맞춤")
    if not edges:
        raise ValueError(
            "겹치는 부분이나 촬영 순서의 근거를 찾지 못했습니다. 같은 촬영 묶음의 사진을 선택하세요."
        )
    # Maximum-confidence forest. Disconnected images are never forced into a circle.
    components = [{i} for i in range(len(images))]
    for _, i, j, _, _ in edges:
        a = next(g for g in components if i in g)
        b = next(g for g in components if j in g)
        if a is not b:
            a.update(b)
            components.remove(b)
    chosen = max(components, key=len)
    root = min(chosen)
    matrices = {root: np.eye(3)}
    used = []
    while len(matrices) < len(chosen):
        available = [
            e
            for e in edges
            if (e[1] in matrices) != (e[2] in matrices)
            and e[1] in chosen
            and e[2] in chosen
        ]
        if not available:
            break
        _, i, j, h, err = max(available, key=lambda e: e[0])
        if i in matrices:
            matrices[j] = matrices[i] @ h
        else:
            matrices[i] = matrices[j] @ np.linalg.inv(h)
        used.append(err)
    # Reject cycles contradicting accumulated positions instead of mixing captures.
    inconsistent = 0
    for _, i, j, h, _ in edges:
        if i in matrices and j in matrices:
            center = np.array([images[j].shape[1] / 2, images[j].shape[0] / 2, 1.0])
            if (
                np.linalg.norm((matrices[i] @ h @ center - matrices[j] @ center)[:2])
                > 12
            ):
                inconsistent += 1
    if inconsistent > max(1, len(edges) * 0.15):
        raise ValueError(
            "사진 위치가 서로 모순됩니다. 전/후 또는 다른 촬영 묶음을 분리하세요."
        )
    return matrices, {
        "method": "SIFT_SIMILARITY_RANSAC",
        "matched": len(matrices),
        "maximum_edge_rmse": max(used, default=0.0),
        "disconnected": len(images) - len(matrices),
    }


def compose(images, metadata, *, cancelled=lambda: False, progress=lambda *a: None):
    if not images:
        raise ValueError("사진이 없습니다")
    if len(images) == 1:
        matrices = {0: np.eye(3)}
        evidence = {"method": "SINGLE_SOURCE", "matched": 1}
    else:
        found = reference_layout(images, metadata)
        if found is None:
            found = edge_order(images, metadata)
        matrices, evidence = (
            found if found is not None else feature_layout(images, cancelled, progress)
        )
    _check(cancelled)
    if evidence["method"] == "PROVIDED_COMPOSITE":
        base = evidence["reference"]
        rgb = images[base]
        rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
        return {
            "rgba": rgba,
            "transforms": matrices,
            "evidence": evidence,
            "size": [rgb.shape[1], rgb.shape[0]],
        }
    corners = []
    for i, h in matrices.items():
        height, width = images[i].shape[:2]
        c = (
            np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1.0]])
            @ h.T
        )
        corners.extend(c[:, :2])
    corners = np.array(corners)
    lo = np.floor(corners.min(0))
    hi = np.ceil(corners.max(0))
    extent = hi - lo
    if min(extent) <= 0 or max(extent) > 100_000:
        raise ValueError("사진 배치 범위 오류")
    scale = min(1.0, MAX_CANVAS / max(extent))
    w, h = np.maximum(1, np.ceil(extent * scale).astype(int))
    offset = np.array(
        [[scale, 0, -lo[0] * scale], [0, scale, -lo[1] * scale], [0, 0, 1.0]]
    )
    colors = np.zeros((h, w, 3), np.float32)
    weights = np.zeros((h, w), np.float32)
    output = {}
    for n, (i, transform) in enumerate(matrices.items()):
        _check(cancelled)
        matrix = offset @ transform
        im = images[i]
        yy, xx = np.indices(im.shape[:2])
        weight = np.minimum.reduce(
            [xx + 1, yy + 1, im.shape[1] - xx, im.shape[0] - yy]
        ).astype(np.float32)
        weight = np.minimum(weight, 32.0) / 32
        warped = cv2.warpAffine(
            im.astype(np.float32) * weight[:, :, None],
            matrix[:2],
            (int(w), int(h)),
            flags=cv2.INTER_LINEAR,
        )
        blend = cv2.warpAffine(
            weight, matrix[:2], (int(w), int(h)), flags=cv2.INTER_LINEAR
        )
        colors += warped
        weights += blend
        output[i] = matrix
        progress(n + 1, len(matrices), "연속 이미지 생성")
    rgb = np.clip(colors / np.maximum(weights[:, :, None], 1e-6), 0, 255).astype(
        np.uint8
    )
    rgba = np.dstack([rgb, np.where(weights > 0, 255, 0).astype(np.uint8)])
    return {
        "rgba": rgba,
        "transforms": output,
        "evidence": evidence,
        "size": [int(w), int(h)],
    }
