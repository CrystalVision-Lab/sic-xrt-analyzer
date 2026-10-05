"""Read-only image analysis using the frozen research classifier contract v1.

This module produces candidate classifications, never human-verified labels.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import tifffile
from PIL import Image, ImageDraw

CLASSES = ("BPD", "TED", "TSD")
COLORS = {"BPD": "#ffad42", "TED": "#50e0ee", "TSD": "#ff78c4"}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def new_run(root, prefix):
    path = Path(root) / f"{prefix}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def read_rgb(locator):
    """Read an explicit file or archive.zip::member; no extraction or conversion."""
    locator = str(locator)
    if "::" in locator:
        archive, member = locator.split("::", 1)
        with zipfile.ZipFile(archive) as zipped:
            info = zipped.getinfo(member)
            if info.file_size > 2_000_000_000:
                raise ValueError("압축 내부 영상이 2 GB 제한을 초과합니다.")
            raw = zipped.read(member)
        suffix = Path(member).suffix.lower()
    else:
        path = Path(locator)
        if path.stat().st_size > 2_000_000_000:
            raise ValueError("영상이 2 GB 제한을 초과합니다.")
        raw = path.read_bytes()
        suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        with tifffile.TiffFile(io.BytesIO(raw)) as tif:
            if len(tif.pages) != 1:
                raise ValueError("단일 RGB 영상만 지원합니다. 3D 스택은 별도 분석 대상입니다.")
            array = tif.asarray()
    elif suffix in {".png", ".jpg", ".jpeg"}:
        with Image.open(io.BytesIO(raw)) as image:
            array = np.asarray(image).copy()
    else:
        raise ValueError("TIFF, PNG, JPEG 영상만 지원합니다.")
    require_rgb(array)
    return array, {"locator": locator, "sha256": hashlib.sha256(raw).hexdigest(),
                   "shape": list(array.shape), "dtype": str(array.dtype)}


def require_rgb(array):
    if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("이 모델은 원본 uint8 RGB 영상 전용입니다. 16비트/흑백은 자동 변환하지 않습니다.")


class FrozenClassifier:
    def __init__(self, bundle):
        import onnxruntime as ort

        bundle = Path(bundle)
        m = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        expected_input = {"name": "images", "dtype": "float32", "shape": ["N", 3, 128, 128],
                          "conversion": "uint8_RGB_to_NCHW_div255", "local_contrast_inside_model": True}
        expected_output = {"name": "probabilities", "shape": ["N", 3],
                           "meaning": "uncalibrated_class_scores"}
        if (m.get("schema") != "frozen_xrt_patch_classifier" or m.get("schema_version") != 1
                or m.get("status") != "validated_export" or m.get("classes") != list(CLASSES)
                or m.get("input") != expected_input or m.get("output") != expected_output
                or m.get("model_file") != "model.onnx" or m.get("research_only") is not True
                or m.get("background_class") is not False or m.get("localizes_defects") is not False):
            raise ValueError("지원하지 않는 고정 모델 계약입니다.")
        model = bundle / "model.onnx"
        if hashlib.sha256(model.read_bytes()).hexdigest() != m.get("model_sha256"):
            raise ValueError("모델 해시가 일치하지 않습니다.")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self.session = ort.InferenceSession(str(model), sess_options=options,
                                           providers=["CPUExecutionProvider"])
        self.manifest = m

    def predict(self, patches):
        array = np.stack(patches)
        if array.shape[1:] != (128, 128, 3) or array.dtype != np.uint8:
            raise ValueError("128×128 uint8 RGB 패치가 필요합니다.")
        inputs = np.ascontiguousarray(array.transpose(0, 3, 1, 2), dtype=np.float32) / 255
        scores = self.session.run(["probabilities"], {"images": inputs})[0]
        if (scores.shape != (len(patches), 3) or not np.isfinite(scores).all()
                or (scores < 0).any() or not np.allclose(scores.sum(axis=1), 1, atol=1e-4)):
            raise ValueError("모델 출력 점수가 올바르지 않습니다.")
        return scores


def load_points(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"x", "y"}.issubset(rows[0]):
        raise ValueError("좌표 CSV에 x,y 열과 한 개 이상의 행이 필요합니다.")
    return rows


def propose_points(image, threshold=12.0, min_distance=20, max_candidates=3000):
    """Brightness-contrast proposals only; misses/false positives are expected.

    Tile with halos at original resolution; cap by response across the full image.
    """
    require_rgb(image)
    if threshold <= 0 or min_distance < 1 or max_candidates < 1:
        raise ValueError("후보 설정은 양수여야 합니다.")
    height, width = image.shape[:2]
    proposals = []
    halo = max(48, min_distance + 2)
    kernel = np.ones((2 * min_distance + 1, 2 * min_distance + 1), np.uint8)
    # Keep bounded candidates from each tile. Full-image selection follows below.
    for top in range(0, height, 1024):
        for left in range(0, width, 1024):
            y0, x0 = max(0, top - halo), max(0, left - halo)
            y1, x1 = min(height, top + 1024 + halo), min(width, left + 1024 + halo)
            gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32)
            smooth = cv2.GaussianBlur(gray, (0, 0), 1.2)
            response = np.abs(smooth - cv2.GaussianBlur(gray, (0, 0), 8.0))
            peaks = (response >= threshold) & (response == cv2.dilate(response, kernel))
            yy, xx = np.nonzero(peaks)
            keep = ((yy + y0 >= top) & (yy + y0 < min(height, top + 1024))
                    & (xx + x0 >= left) & (xx + x0 < min(width, left + 1024)))
            yy, xx = yy[keep], xx[keep]
            order = np.argsort(-response[yy, xx], kind="stable")[:max_candidates + 1]
            proposals.extend((float(response[yy[i], xx[i]]), int(xx[i] + x0), int(yy[i] + y0))
                             for i in order)
    proposals.sort(key=lambda item: (-item[0], item[2], item[1]))
    selected, grid = [], {}
    for response, x, y in proposals:
        gx, gy = x // min_distance, y // min_distance
        nearby = [p for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                  for p in grid.get((gx + dx, gy + dy), [])]
        if any((x - px) ** 2 + (y - py) ** 2 <= min_distance ** 2 for px, py in nearby):
            continue
        selected.append({"point_id": f"auto_{len(selected):06d}", "x": x, "y": y,
                         "proposal_response": response})
        grid.setdefault((gx, gy), []).append((x, y))
        if len(selected) > max_candidates:
            break
    return selected[:max_candidates], len(selected) > max_candidates


def classify_points(image, points, classifier, score_threshold=0.6, batch_size=32):
    require_rgb(image)
    if not 0 <= score_threshold <= 1 or batch_size < 1:
        raise ValueError("점수 기준/배치 크기가 올바르지 않습니다.")
    height, width = image.shape[:2]
    accepted, rejected, seen = [], [], set()
    for index, point in enumerate(points):
        p = {"point_id": str(point.get("point_id", index)), "x": point.get("x"), "y": point.get("y")}
        try:
            x, y = float(p["x"]), float(p["y"])
            if not np.isfinite([x, y]).all():
                raise ValueError()
            cx, cy = round(x), round(y)
        except (ValueError, TypeError, OverflowError):
            rejected.append({**p, "reason": "invalid_coordinate"})
            continue
        p.update(x=x, y=y, crop_x=cx, crop_y=cy)
        if (cx, cy) in seen:
            rejected.append({**p, "reason": "duplicate_crop_center"})
        elif cx < 64 or cy < 64 or cx + 64 > width or cy + 64 > height:
            rejected.append({**p, "reason": "incomplete_128px_patch"})
        else:
            seen.add((cx, cy))
            accepted.append(p)
    for start in range(0, len(accepted), batch_size):
        batch = accepted[start:start + batch_size]
        patches = [image[p["crop_y"] - 64:p["crop_y"] + 64,
                         p["crop_x"] - 64:p["crop_x"] + 64] for p in batch]
        scores = classifier.predict(patches)
        for p, probs in zip(batch, scores, strict=True):
            best = int(np.argmax(probs))
            p.update(predicted_type=CLASSES[best], score=float(probs[best]),
                     uncertain=bool(probs[best] < score_threshold), human_verified=False)
            p.update({f"score_{name}": float(value) for name, value in zip(CLASSES, probs, strict=True)})
    return accepted, rejected


def preview(image, max_side=1600):
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    # Actual per-axis scales avoid rounding drift in registration.
    shape = (max(1, round(width * scale)), max(1, round(height * scale)))
    small = cv2.resize(image, shape, interpolation=cv2.INTER_AREA)
    return small, np.diag([shape[0] / width, shape[1] / height, 1.0])


def save_overlay(image, predictions, path):
    small, scale = preview(image)
    canvas = Image.fromarray(small)
    draw = ImageDraw.Draw(canvas)
    for point in predictions:
        x, y = point["x"] * scale[0, 0], point["y"] * scale[1, 1]
        color = "#ffffff" if point["uncertain"] else COLORS[point["predicted_type"]]
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline=color, width=1)
    draw.rectangle((0, 0, min(canvas.width, 680), 23), fill="black")
    draw.text((5, 5), "Candidate classes: BPD orange / TED cyan / TSD pink / low-score white", fill="white")
    canvas.save(path)


def analyze_image(locator, classifier, output_root, *, points_csv=None, score_threshold=0.6,
                  proposal_threshold=12.0, min_distance=20, max_candidates=3000):
    image, source = read_rgb(locator)
    mode = "provided_coordinates" if points_csv else "contrast_proposals"
    truncated = False
    if points_csv:
        points = load_points(points_csv)
    else:
        points, truncated = propose_points(image, proposal_threshold, min_distance, max_candidates)
    predictions, rejected = classify_points(image, points, classifier, score_threshold)
    path = new_run(output_root, "analysis")
    fields = ["point_id", "x", "y", "crop_x", "crop_y", "predicted_type", "score", "uncertain",
              "score_BPD", "score_TED", "score_TSD", "human_verified"]
    write_csv(path / "predictions.csv", predictions, fields)
    write_csv(path / "excluded_points.csv", rejected, ["point_id", "x", "y", "reason"])
    save_overlay(image, predictions, path / "overlay.png")
    summary = {"schema": "xrt_research_analysis", "schema_version": 1, "status": "completed",
               "source": source, "bundle_id": classifier.manifest["bundle_id"],
               "model_sha256": classifier.manifest["model_sha256"],
               "mode": mode, "candidate_count": len(points), "classified_count": len(predictions),
               "excluded_count": len(rejected), "candidate_limit_reached": truncated,
               "counts_by_predicted_type": dict(Counter(p["predicted_type"] for p in predictions)),
               "low_score_count": sum(p["uncertain"] for p in predictions),
               "score_threshold": score_threshold, "scores_calibrated": False,
               "proposal_settings": {"threshold": proposal_threshold, "min_distance": min_distance,
                                     "max_candidates": max_candidates},
               "points_csv": str(points_csv) if points_csv else None,
               "points_sha256": hashlib.sha256(Path(points_csv).read_bytes()).hexdigest() if points_csv else None,
               "research_only": True, "human_verified": False,
               "counts_are": "classified_candidate_points_not_verified_defect_totals",
               "predictions": predictions, "output_dir": str(path)}
    write_json(path / "result.json", summary)
    return summary
