"""Bounded original-pixel inference for the desktop's existing worker pipeline."""
from collections import Counter

import numpy as np

from .contracts import (
    AdapterOutput,
    AnalysisScope,
    CoordinateSpace,
    Detection,
    Geometry,
    GeometryKind,
)
from .model_adapter import ModelInputContract, ModelOutputContract
from .research import CLASSES, FrozenClassifier, propose_points


class DesktopResearchAdapter:
    research_only = True
    available = True
    device = "CPU"
    model_name = "BPD · TED · TSD 연구 모델"
    input_contract = ModelInputContract(
        (AnalysisScope.FULL_IMAGE, AnalysisScope.ROI), (3,), ("uint8",),
        "128px original RGB patches; bounded source reads", "uint8 / 255; contrast inside model",
        "RGB", "uint8 only; no implicit conversion")
    output_contract = ModelOutputContract((GeometryKind.POINT,), CoordinateSpace.ORIGINAL)

    def __init__(self, bundle, classifier=None):
        self.classifier = classifier if classifier is not None else FrozenClassifier(bundle)
        self.model_id = self.classifier.manifest["bundle_id"]
        self.model_version = self.classifier.manifest["model_sha256"]

    def analyze_source(self, request, token):
        source, meta = request.source, request.source.metadata
        r = request.roi
        x0, y0, width, height = (r.x, r.y, r.width, r.height) if r else (0, 0, meta.width, meta.height)
        params = request.parameters
        mode = params.get("point_mode", "contrast_proposals")
        threshold = float(params.get("proposal_threshold", 12))
        score_threshold = float(params.get("score_threshold", .6))
        limit = int(params.get("max_candidates", 3000))
        if not 0 <= score_threshold <= 1 or not 1 <= limit <= 10000 or not 0 < threshold <= 255:
            raise ValueError("분석 설정 범위를 확인하세요.")
        limited = False
        if mode == "provided_coordinates":
            points = [dict(p) for p in params.get("points", ())]
            if not points or len(points) > 50000:
                raise ValueError("제공 좌표는 1~50,000개여야 합니다.")
        elif mode == "contrast_proposals":
            points = []
            for top in range(y0, y0 + height, 1024):
                for left in range(x0, x0 + width, 1024):
                    token.check()
                    # Halo supplies the same local context at tile edges.
                    sx, sy = max(x0, left - 64), max(y0, top - 64)
                    right, bottom = min(x0 + width, left + 1088), min(y0 + height, top + 1088)
                    image = source.read_region(sx, sy, right - sx, bottom - sy)
                    local, capped = propose_points(image, threshold=threshold, max_candidates=limit + 1)
                    limited |= capped
                    for p in local:
                        x, y = p["x"] + sx, p["y"] + sy
                        if left <= x < min(x0 + width, left + 1024) and top <= y < min(y0 + height, top + 1024):
                            points.append({"x": x, "y": y, "response": p["proposal_response"]})
                    points.sort(key=lambda p: (-p["response"], p["y"], p["x"]))
                    if len(points) > limit:
                        limited = True
                        points = points[:limit]
            for i, p in enumerate(points):
                p["point_id"] = f"auto_{i:06d}"
        else:
            raise ValueError("알 수 없는 좌표 모드입니다.")
        token.check()
        accepted, excluded, seen = [], Counter(), set()
        for p in points:
            x, y = float(p["x"]), float(p["y"])
            if not np.isfinite([x, y]).all():
                excluded["invalid_coordinate"] += 1
                continue
            if not x0 <= x < x0 + width or not y0 <= y < y0 + height:
                excluded["outside_scope"] += 1
                continue
            cx, cy = round(x), round(y)
            if (cx, cy) in seen:
                excluded["duplicate_center"] += 1
                continue
            if cx < x0 + 64 or cy < y0 + 64 or cx + 64 > x0 + width or cy + 64 > y0 + height:
                excluded["incomplete_patch"] += 1
                continue
            seen.add((cx, cy))
            accepted.append({"x": x, "y": y, "cx": cx, "cy": cy,
                             "point_id": str(p.get("point_id", len(accepted)))})
        detections = []
        for start in range(0, len(accepted), 32):
            token.check()
            batch = accepted[start:start + 32]
            patches = [source.read_region(p["cx"] - 64, p["cy"] - 64, 128, 128) for p in batch]
            scores = self.classifier.predict(patches)
            token.check()
            for p, score in zip(batch, scores, strict=True):
                index = int(np.argmax(score))
                detections.append(Detection(
                    f"candidate_{len(detections):06d}", index, CLASSES[index], float(score[index]),
                    Geometry(GeometryKind.POINT, ((p["x"], p["y"]),), coordinate_space=CoordinateSpace.ORIGINAL),
                    {"point_id": p["point_id"], "scores": [float(v) for v in score],
                     "low_score": bool(score[index] < score_threshold), "human_verified": False}))
        summary = {"counts": dict(Counter(d.class_name for d in detections)), "candidate_count": len(points),
                   "classified_count": len(detections), "excluded": dict(excluded),
                   "low_score_count": sum(d.metadata["low_score"] for d in detections),
                   "candidate_limit_reached": limited, "point_mode": mode, "research_only": True,
                   "human_verified": False, "counts_are": "candidate_points_not_verified_defect_totals",
                   "model_sha256": self.model_version}
        return AdapterOutput(tuple(detections), summary,
                             {"input": "original_uint8_RGB", "patch_size": 128, "batch_size": 32,
                              "coordinates": "original_pixels", "no_subtype_or_conversion_claim": True})
