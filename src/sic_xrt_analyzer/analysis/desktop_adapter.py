"""Bounded original-pixel inference for the desktop's existing worker pipeline."""
from collections import Counter

import cv2
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


class RegionOutline(list):
    def __init__(self, points, context, clipped):
        super().__init__(points)
        self.context = context
        self.clipped = clipped


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
        self.model_id = self.classifier.manifest.get("bundle_id") or (
            self.classifier.manifest["architecture"] + "-" + self.classifier.manifest["model_sha256"][:12])
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
        scanned = 0
        tile_total = ((height + 1023) // 1024) * ((width + 1023) // 1024)
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
                    scanned += 1
                    token.report(stage="원본 탐색", completed=scanned, total=tile_total, region=[left, top, min(1024, x0+width-left), min(1024, y0+height-top)])
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
            first_detection = len(detections)
            for p, score in zip(batch, scores, strict=True):
                index = int(np.argmax(score))
                region, region_error = [], ""
                if CLASSES[index] == "BPD" and params.get("include_regions", True):
                    try:
                        region = self._region(source, {**p, "region_bounds": (x0, y0, width, height)}, token)
                    except (ValueError, cv2.error) as exc:
                        token.check()
                        region_error = type(exc).__name__
                detections.append(Detection(
                    f"candidate_{len(detections):06d}", index, CLASSES[index], float(score[index]),
                    Geometry(GeometryKind.POINT, ((p["x"], p["y"]),), coordinate_space=CoordinateSpace.ORIGINAL),
                    {"bpd_region": list(region), "region_error": region_error,
                     "region_context": getattr(region, "context", 0),
                     "region_clipped": getattr(region, "clipped", False),
                     "region_provenance": "EXPERIMENTAL_LOCAL_CONTRAST_REGION" if CLASSES[index] == "BPD" else "",
                     "point_id": p["point_id"], "scores": [float(v) for v in score],
                     "low_score": bool(score[index] < score_threshold), "human_verified": False}))
            token.report(stage="후보 분석", completed=len(detections), total=len(accepted), detections=detections[first_detection:])
        summary = {"counts": dict(Counter(d.class_name for d in detections)), "candidate_count": len(points),
                   "classified_count": len(detections), "excluded": dict(excluded),
                   "low_score_count": sum(d.metadata["low_score"] for d in detections),
                   "candidate_limit_reached": limited, "point_mode": mode, "research_only": True,
                   "human_verified": False, "counts_are": "candidate_points_not_verified_defect_totals",
                   "model_sha256": self.model_version}
        return AdapterOutput(tuple(detections), summary,
                             {"input": "original_uint8_RGB", "patch_size": 128, "batch_size": 32,
                              "coordinates": "original_pixels", "no_subtype_or_conversion_claim": True})

    @staticmethod
    def _region(source, point, token):
        """Adaptively read the connected contrast region, without clipping at 128px.

        This remains a structure proposal attached to the unchanged classifier
        point; it is not an ONNX segmentation or a verified physical boundary.
        """
        from scipy import ndimage as ndi
        from skimage.filters import apply_hysteresis_threshold

        bounds = point.get("region_bounds", (0, 0, source.metadata.width, source.metadata.height))
        left, top, full_width, full_height = bounds
        chosen_polarity = None
        for edge in (128, 256, 512, 1024):
            token.check()
            w, h = min(edge, full_width), min(edge, full_height)
            x = max(left, min(left + full_width - w, point["cx"] - w // 2))
            y = max(top, min(top + full_height - h, point["cy"] - h // 2))
            original = source.read_region(x, y, w, h)
            gray = np.sum(original.astype(np.float32) * np.array([.2126, .7152, .0722], np.float32), axis=2) / 255
            residual = gray - ndi.gaussian_filter(gray, 8., mode="reflect")
            cx, cy = point["cx"] - x, point["cy"] - y
            yy, xx = np.indices((h, w))
            distances = (xx-(point["x"]-x))**2 + (yy-(point["y"]-y))**2
            choices = []
            for sign in (1., -1.):
                if chosen_polarity is not None and sign != chosen_polarity:
                    continue
                response = np.maximum(sign * residual, 0)
                # A distant dark defect must not set the seed's threshold.
                peak = float(response[max(0, cy-8):cy+9, max(0, cx-8):cx+9].max())
                if peak < .015:
                    continue
                mask = apply_hysteresis_threshold(response, max(.008, peak*.12), max(.015, peak*.28))
                labels, _count = ndi.label(mask, structure=np.ones((3, 3), int))
                areas = np.bincount(labels.ravel())
                near_labels = np.unique(labels[distances <= 8**2])
                for label in near_labels[near_labels > 0]:
                    if not 8 <= areas[label] <= min(65536, w*h*.5):
                        continue
                    distance = float(distances[labels == label].min())
                    py, px = np.nonzero(labels == label)
                    coordinates = np.column_stack((px, py)).astype(float)
                    eigenvalues = np.linalg.eigvalsh(np.cov(coordinates.T))
                    aspect = float(np.sqrt(eigenvalues[-1] / max(eigenvalues[0], 1)))
                    extent = max(int(np.ptp(px)), int(np.ptp(py)))
                    # BPD classification commonly anchors on a bright spot on
                    # a long dark line. Prefer the supported elongated region
                    # within 8 source pixels, rather than that tiny bright spot.
                    # Weight contrast as well as length: the weak opposite-polarity
                    # halo beside a dark line is not the defect itself.
                    line_rank = extent * float(response[labels == label].mean()) if aspect >= 2.5 and extent >= 24 else 0
                    choices.append((-line_rank, distance, -int(areas[label]), labels, label, sign))
            token.check()
            if not choices:
                return []
            _, _, _, labels, label, chosen_polarity = min(choices, key=lambda r: (r[0], r[1], r[2]))
            mask = (labels == label).astype("uint8")
            touches = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
            if touches and edge < 1024 and (w < full_width or h < full_height):
                continue
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return []
            contour = max(contours, key=cv2.contourArea)
            contour = cv2.approxPolyDP(contour, .75, True).reshape(-1, 2)
            if len(contour) > 512:
                contour = contour[::(len(contour)+511)//512]
            if len(contour) < 3:
                return []
            return RegionOutline([[int(px)+x, int(py)+y] for px, py in contour], edge, touches)
        return []
