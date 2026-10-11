"""Quality-gated 2D registration and tentative one-to-one point matching."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from sic_xrt_analyzer.analysis.research import (
    new_run,
    preview,
    read_rgb,
    write_csv,
    write_json,
)


def transform_points(points, matrix):
    array = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.column_stack((array, np.ones(len(array)))) @ np.asarray(matrix).T
    with np.errstate(divide="ignore", invalid="ignore"):
        return homogeneous[:, :2] / homogeneous[:, 2:3]


def _corners(shape):
    height, width = shape[:2]
    return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float64)


def fit_registration(before_xy, after_xy, before_shape, after_shape, *, method,
                     ransac_px=12.0, min_inliers=12, min_ratio=0.4):
    """Fit after -> before; all thresholds are in full-resolution before pixels."""
    before_xy, after_xy = np.asarray(before_xy, float), np.asarray(after_xy, float)
    result = {"status": "failed", "method": method, "direction": "after_to_before",
              "correspondence_count": len(before_xy), "ransac_threshold_before_px": ransac_px,
              "reasons": [], "human_verified": False, "registration_is_tentative": True}
    if (before_xy.shape != after_xy.shape or before_xy.ndim != 2 or before_xy.shape[1] != 2
            or len(before_xy) < min_inliers or not np.isfinite(before_xy).all()
            or not np.isfinite(after_xy).all()):
        result["reasons"] = ["insufficient_or_invalid_correspondences"]
        return result
    if not _inside(before_xy, before_shape).all() or not _inside(after_xy, after_shape).all():
        result["reasons"] = ["correspondences_outside_image"]
        return result
    # SIFT may emit several orientations at one location. They are one support point.
    seen_before, seen_after, keep = set(), set(), []
    for i, (a, b) in enumerate(zip(before_xy, after_xy, strict=True)):
        key_a, key_b = tuple(np.round(a, 1)), tuple(np.round(b, 1))
        if key_a not in seen_before and key_b not in seen_after:
            keep.append(i)
            seen_before.add(key_a)
            seen_after.add(key_b)
    before_xy, after_xy = before_xy[keep], after_xy[keep]
    result["unique_correspondence_count"] = len(keep)
    if len(keep) < min_inliers:
        result["reasons"] = ["insufficient_unique_correspondences"]
        return result
    cv2.setRNGSeed(42)
    matrix, mask = cv2.findHomography(after_xy, before_xy, cv2.RANSAC, ransac_px,
                                     maxIters=10000, confidence=0.999)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        result["reasons"] = ["homography_not_found"]
        return result
    inliers = mask.ravel().astype(bool)
    count = int(inliers.sum())
    result.update(inlier_count=count, inlier_ratio=float(inliers.mean()))
    if count < min_inliers or inliers.mean() < min_ratio:
        result["reasons"].append("insufficient_inliers")
    residual = np.linalg.norm(transform_points(after_xy[inliers], matrix) - before_xy[inliers], axis=1)
    result["median_inlier_error_before_px"] = float(np.median(residual)) if count else None
    result["p90_inlier_error_before_px"] = float(np.quantile(residual, .9)) if count else None
    if not count or np.quantile(residual, .9) > ransac_px:
        result["reasons"].append("excessive_reprojection_error")
    projected = transform_points(_corners(after_shape), matrix).astype(np.float32)
    homogeneous_corners = np.column_stack((_corners(after_shape), np.ones(4))) @ matrix.T
    if (not np.isfinite(projected).all() or abs(np.linalg.det(matrix)) < 1e-12
            or not cv2.isContourConvex(projected)
            or not (np.all(homogeneous_corners[:, 2] > 0) or np.all(homogeneous_corners[:, 2] < 0))):
        result["reasons"].append("invalid_or_folded_transform")
        return result
    before_area = float((before_shape[0] - 1) * (before_shape[1] - 1))
    after_area = abs(float(cv2.contourArea(projected)))
    original_after_area = (after_shape[0] - 1) * (after_shape[1] - 1)
    area_scale = after_area / max(1, original_after_area)
    # Magnification changes up to 5x in either direction; larger needs explicit study.
    if not .04 <= area_scale <= 25:
        result["reasons"].append("implausible_scale")
    overlap, polygon = cv2.intersectConvexConvex(_corners(before_shape).astype(np.float32), projected)
    result.update(overlap_before_fraction=float(overlap / max(1, before_area)),
                  overlap_after_fraction=float(overlap / max(1, after_area)),
                  linear_scale_after_to_before=float(np.sqrt(area_scale)))
    if overlap <= 0 or overlap / max(1, min(before_area, after_area)) < .15:
        result["reasons"].append("insufficient_overlap")
    if count >= 3 and overlap > 0:
        support_area = abs(cv2.contourArea(cv2.convexHull(before_xy[inliers].astype(np.float32))))
        result["inlier_support_over_overlap"] = float(support_area / overlap)
        if support_area / overlap < .05:
            result["reasons"].append("inliers_too_localized")
    if result["reasons"]:
        return result
    result.update(status="accepted_tentative", matrix_after_to_before=matrix.tolist(),
                  overlap_polygon_before=polygon.reshape(-1, 2).tolist(),
                  inlier_before_xy=before_xy[inliers].tolist(), inlier_after_xy=after_xy[inliers].tolist())
    return result


def register_images(before, after, landmarks_csv=None, max_side=3200):
    if landmarks_csv:
        with Path(landmarks_csv).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        before_xy = [[float(r["before_x"]), float(r["before_y"])] for r in rows]
        after_xy = [[float(r["after_x"]), float(r["after_y"])] for r in rows]
        result = fit_registration(before_xy, after_xy, before.shape, after.shape,
                                  method="supplied_landmarks", min_inliers=6, min_ratio=.7)
        result["landmarks_csv"] = str(landmarks_csv)
        return result
    a, sa = preview(before, max_side)
    b, sb = preview(after, max_side)
    sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=.02)
    ka, da = sift.detectAndCompute(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), None)
    kb, db = sift.detectAndCompute(cv2.cvtColor(b, cv2.COLOR_RGB2GRAY), None)
    if da is None or db is None or min(len(da), len(db)) < 12:
        return {"status": "failed", "method": "sift_ransac", "reasons": ["insufficient_features"]}
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(db, da, k=2)
    backward = matcher.knnMatch(da, db, k=2)
    reverse = {m.queryIdx: m.trainIdx for pair in backward if len(pair) == 2
               for m, n in [pair] if m.distance < .75 * n.distance}
    good = [m for pair in forward if len(pair) == 2 for m, n in [pair]
            if m.distance < .75 * n.distance and reverse.get(m.trainIdx) == m.queryIdx]
    before_xy = np.array([ka[m.trainIdx].pt for m in good]).reshape(-1, 2)
    after_xy = np.array([kb[m.queryIdx].pt for m in good]).reshape(-1, 2)
    before_xy = transform_points(before_xy, np.linalg.inv(sa))
    after_xy = transform_points(after_xy, np.linalg.inv(sb))
    return fit_registration(before_xy, after_xy, before.shape, after.shape, method="sift_ransac",
                            ransac_px=3 / min(sa[0, 0], sa[1, 1]))


def _inside(points, shape):
    points = np.asarray(points)
    return (np.isfinite(points).all(axis=1) & (points[:, 0] >= 0) & (points[:, 1] >= 0)
            & (points[:, 0] < shape[1]) & (points[:, 1] < shape[0]))


def match_points(before, after, matrix, before_shape, after_shape, radius=25.0):
    """Conservative graph: accept only when both points have exactly one neighbor.

    Type is not used for association, so a type change cannot force a match.
    Multiple possible partners remain ambiguous instead of being silently chosen.
    """
    if radius <= 0 or not np.isfinite(radius):
        raise ValueError("연결 반경은 유한한 양수여야 합니다.")
    aa = np.array([[p["x"], p["y"]] for p in before]).reshape(-1, 2)
    bb = np.array([[p["x"], p["y"]] for p in after]).reshape(-1, 2)
    mapped = transform_points(bb, matrix)
    valid_a = _inside(transform_points(aa, np.linalg.inv(matrix)), after_shape)
    valid_b = _inside(mapped, before_shape)
    ids_a, ids_b = np.flatnonzero(valid_a), np.flatnonzero(valid_b)
    neighbors_a, neighbors_b = {}, {}
    if len(ids_a) and len(ids_b):
        edges = cKDTree(aa[ids_a]).query_ball_tree(cKDTree(mapped[ids_b]), radius)
        for i, near in zip(ids_a, edges, strict=True):
            neighbors_a[int(i)] = [int(ids_b[j]) for j in near]
            for j in near:
                neighbors_b.setdefault(int(ids_b[j]), []).append(int(i))
    rows, used = [], set()
    for i, p in enumerate(before):
        near = neighbors_a.get(i, [])
        status = "outside_overlap" if not valid_a[i] else "unmatched"
        row = {"before_id": p["point_id"], "after_id": "", "before_x": p["x"], "before_y": p["y"],
               "before_type": p["predicted_type"], "status": status, "human_verified": False,
               "physical_conversion_confirmed": False, "type_change_candidate": False}
        if len(near) == 1 and len(neighbors_b[near[0]]) == 1:
            j = near[0]
            q = after[j]
            used.add(j)
            row.update(after_id=q["point_id"], after_x=q["x"], after_y=q["y"],
                       mapped_after_x=float(mapped[j, 0]), mapped_after_y=float(mapped[j, 1]),
                       residual_before_px=float(np.linalg.norm(aa[i] - mapped[j])),
                       after_type=q["predicted_type"], status="tentative_match",
                       type_change_candidate=p["predicted_type"] != q["predicted_type"],
                       either_low_score=bool(p.get("uncertain") or q.get("uncertain")))
        elif near:
            row["status"] = "ambiguous"
        rows.append(row)
    for j, q in enumerate(after):
        if j in used:
            continue
        status = "outside_overlap" if not valid_b[j] else "ambiguous" if neighbors_b.get(j) else "unmatched"
        rows.append({"before_id": "", "after_id": q["point_id"], "after_x": q["x"], "after_y": q["y"],
                     "after_type": q["predicted_type"], "status": status, "human_verified": False,
                     "physical_conversion_confirmed": False, "type_change_candidate": False})
    return rows


def track_analyses(before_result, after_result, output_root, *, radius=25.0, landmarks_csv=None):
    """Use completed analysis artifacts, recheck source hashes, then register/match."""
    if before_result["model_sha256"] != after_result["model_sha256"]:
        raise ValueError("전후 분석의 모델 버전이 다릅니다.")
    before, source_a = read_rgb(before_result["source"]["locator"])
    after, source_b = read_rgb(after_result["source"]["locator"])
    if (source_a["sha256"] != before_result["source"]["sha256"]
            or source_b["sha256"] != after_result["source"]["sha256"]):
        raise ValueError("분석 이후 원본 영상이 바뀌었습니다.")
    path = new_run(output_root, "tracking")
    registration = register_images(before, after, landmarks_csv)
    result = {"schema": "xrt_research_tracking", "schema_version": 1,
              "status": "registration_failed", "registration": registration,
              "before_analysis": before_result["output_dir"], "after_analysis": after_result["output_dir"],
              "before_source": source_a, "after_source": source_b,
              "radius_before_px": radius, "distance_unit": "before_image_pixel",
              "model_sha256": before_result["model_sha256"], "output_dir": str(path),
              "research_only": True, "human_verified": False, "physical_conversion_confirmed": False,
              "limitations": ["not_a_conversion_rate", "unmatched_does_not_mean_created_or_disappeared",
                              "no_verified_micrometre_scale", "no_direction_subtypes"], "matches": []}
    if registration["status"] == "accepted_tentative":
        matrix = np.asarray(registration["matrix_after_to_before"])
        rows = match_points(before_result["predictions"], after_result["predictions"], matrix,
                            before.shape, after.shape, radius)
        result.update(status="completed_tentative", matches=rows,
                      tentative_match_count=sum(r["status"] == "tentative_match" for r in rows),
                      type_change_candidate_count=sum(r["type_change_candidate"] for r in rows),
                      ambiguous_point_count=sum(r["status"] == "ambiguous" for r in rows),
                      unmatched_point_count=sum(r["status"] == "unmatched" for r in rows))
        a, sa = preview(before)
        b, sb = preview(after)
        small_matrix = sa @ matrix @ np.linalg.inv(sb)
        aligned = cv2.warpPerspective(b, small_matrix, (a.shape[1], a.shape[0]))
        mask = cv2.warpPerspective(np.ones(b.shape[:2], np.uint8), small_matrix, (a.shape[1], a.shape[0]))
        blend = a.copy()
        blend[mask > 0] = cv2.addWeighted(a, .5, aligned, .5, 0)[mask > 0]
        Image.fromarray(blend).save(path / "aligned_overlay.png")
        canvas = Image.fromarray(blend)
        draw = ImageDraw.Draw(canvas)
        for row in rows:
            if row["status"] != "tentative_match":
                continue
            x, y = row["before_x"] * sa[0, 0], row["before_y"] * sa[1, 1]
            u, v = row["mapped_after_x"] * sa[0, 0], row["mapped_after_y"] * sa[1, 1]
            color = "#ff6262" if row["type_change_candidate"] else "#00ffee"
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline=color, width=2)
            draw.line((x, y, u, v), fill=color, width=2)
        canvas.save(path / "tracking_overlay.png")
        paired = [r for r in rows if r["status"] == "tentative_match"]
        if paired:
            chosen = [paired[i] for i in np.linspace(0, len(paired) - 1, min(12, len(paired)), dtype=int)]
            gallery = Image.new("RGB", (3 * 280, ((len(chosen) + 2) // 3) * 175), "#111827")
            pen = ImageDraw.Draw(gallery)
            for i, row in enumerate(chosen):
                left, top = (i % 3) * 280, (i // 3) * 175
                for offset, image, phase in [(0, before, "before"), (138, after, "after")]:
                    x, y = round(row[f"{phase}_x"]), round(row[f"{phase}_y"])
                    tile = Image.fromarray(image[y - 64:y + 64, x - 64:x + 64]).copy()
                    tile_pen = ImageDraw.Draw(tile)
                    tile_pen.line((56, 64, 72, 64), fill="yellow", width=1)
                    tile_pen.line((64, 56, 64, 72), fill="yellow", width=1)
                    gallery.paste(tile, (left + offset, top + 23))
                    pen.text((left + offset, top + 4), f"{phase}: {row[f'{phase}_type']}", fill="white")
                pen.text((left, top + 153), f"Tentative; residual {row['residual_before_px']:.1f} px", fill="white")
            gallery.save(path / "matched_examples.png")
    fields = ["before_id", "after_id", "status", "before_x", "before_y", "after_x", "after_y",
              "mapped_after_x", "mapped_after_y", "residual_before_px", "before_type", "after_type",
              "type_change_candidate", "either_low_score", "human_verified", "physical_conversion_confirmed"]
    write_csv(path / "matches.csv", result["matches"], fields)
    write_json(path / "result.json", result)
    return result


def load_analysis(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
