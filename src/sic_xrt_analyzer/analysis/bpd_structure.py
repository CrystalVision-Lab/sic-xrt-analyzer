"""Experimental, explicit ROI-only structure proposals; no ONNX or GT claims."""

import math
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import pairwise
from time import perf_counter, process_time

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import apply_hysteresis_threshold, frangi, sato
from skimage.morphology import skeletonize

from sic_xrt_analyzer.analysis.contracts import Region, utc_now
from sic_xrt_analyzer.results.validation import integer, new_id, number

from .skeleton_graph import path_length, prune_spurs, trace_skeleton

ALGORITHM_VERSION = "0.1.0"


@dataclass(frozen=True)
class StructureSettings:
    method: str
    polarity: str
    scales: tuple[float, ...]
    low_threshold: float
    high_threshold: float
    contrast_floor: float
    background_sigma: float
    min_area: int
    min_length_px: float
    max_width_px: float
    min_aspect: float
    link_distance_px: float
    prune_length_px: float = 0
    min_ridge_support_fraction: float = 0.5
    max_roi_pixels: int = 4_194_304
    max_skeleton_pixels: int = 100_000
    max_regions: int = 2_000

    def __post_init__(self):
        if self.method not in ("local_contrast", "sato", "frangi"):
            raise ValueError("Unknown research method")
        if self.polarity not in ("bright", "dark", "both"):
            raise ValueError("Explicit bright/dark/both polarity required")
        object.__setattr__(self, "scales", tuple(self.scales))
        if not self.scales or len(self.scales) > 8:
            raise ValueError("One to eight explicit ridge scales required")
        for scale in self.scales:
            number(scale, "scale", 0)
            if not 0.5 <= scale <= 32:
                raise ValueError("Research scale outside supported ROI budget")
        for name in (
            "low_threshold",
            "high_threshold",
            "contrast_floor",
            "background_sigma",
            "min_length_px",
            "max_width_px",
            "min_aspect",
            "link_distance_px",
            "prune_length_px",
        ):
            number(getattr(self, name), name, 0)
        if not 0 < self.low_threshold <= self.high_threshold <= 1:
            raise ValueError("Thresholds use normalized response in (0,1]")
        if not 0 < self.contrast_floor <= 1 or not 0 < self.background_sigma <= 64:
            raise ValueError(
                "Explicit positive contrast floor/background sigma required"
            )
        number(self.min_ridge_support_fraction, "ridge support fraction", 0)
        if not 0 < self.min_ridge_support_fraction <= 1:
            raise ValueError("Explicit supported cross-section fraction required")
        if min(self.min_length_px, self.max_width_px, self.min_aspect) <= 0:
            raise ValueError("Explicit positive shape filters required")
        for name in (
            "min_area",
            "max_roi_pixels",
            "max_skeleton_pixels",
            "max_regions",
        ):
            integer(getattr(self, name), name, 1)
        if (
            self.max_roi_pixels > 4_194_304
            or self.max_skeleton_pixels > 100_000
            or self.max_regions > 2_000
        ):
            raise ValueError("ROI experiment cannot disable resource limits")


@dataclass(frozen=True)
class StructureProposal:
    component_id: str
    polarity: str
    topology: object
    bbox: tuple[int, int, int, int]
    area: int
    mean_width_px: float
    flags: tuple[str, ...]
    removed_paths: tuple
    before_pruning: object
    ridge_support_fraction: float | None


@dataclass(frozen=True)
class StructureExperiment:
    experiment_id: str
    created_at: object
    source_identity: dict
    source_metadata: dict
    roi: Region
    settings: StructureSettings
    preprocessing: dict
    roi_sha256: str
    proposals: tuple[StructureProposal, ...]
    response: np.ndarray
    regions: np.ndarray
    skeleton: np.ndarray
    original: np.ndarray
    metrics: dict


def _check_cancel(cancel):
    if cancel():
        raise InterruptedError("BPD experiment cancelled; no project has been changed")


def _cross_section_support(gray, topology, ox, oy, polarity, radius, settings):
    supported = 0
    evaluated = 0
    height, width = gray.shape
    for _, _, path in topology.paths:
        if path_length(path) < settings.min_length_px:
            continue
        points = np.asarray(path, dtype=np.float32) + np.array([ox, oy], np.float32)
        indices = np.arange(len(points))
        direction = (
            points[np.minimum(indices + 2, len(points) - 1)]
            - points[np.maximum(indices - 2, 0)]
        )
        norms = np.linalg.norm(direction, axis=1)
        valid_direction = norms > 0
        normal = np.column_stack((-direction[:, 1], direction[:, 0])) / np.maximum(
            norms[:, None], 1
        )
        center = np.rint(points).astype(int)
        left = np.rint(points + radius * normal).astype(int)
        right = np.rint(points - radius * normal).astype(int)
        valid = (
            valid_direction
            & (left[:, 0] >= 0)
            & (left[:, 0] < width)
            & (left[:, 1] >= 0)
            & (left[:, 1] < height)
            & (right[:, 0] >= 0)
            & (right[:, 0] < width)
            & (right[:, 1] >= 0)
            & (right[:, 1] < height)
        )
        if not valid.any():
            continue
        c, l, r = center[valid], left[valid], right[valid]
        value = gray[c[:, 1], c[:, 0]]
        a = gray[l[:, 1], l[:, 0]]
        b = gray[r[:, 1], r[:, 0]]
        contrasts = (
            np.minimum(value - a, value - b)
            if polarity == "bright"
            else np.minimum(a - value, b - value)
        )
        supported += int(np.count_nonzero(contrasts >= settings.contrast_floor / 2))
        evaluated += len(contrasts)
    return supported / evaluated if evaluated else None


def detect_structures(source, roi, settings, *, cancel=lambda: False):
    if not isinstance(roi, Region) or not isinstance(settings, StructureSettings):
        raise TypeError("Explicit Region and StructureSettings required")
    for name in ("x", "y", "width", "height"):
        integer(getattr(roi, name), name, 1 if name in ("width", "height") else 0)
    if roi.width * roi.height > settings.max_roi_pixels:
        raise ValueError("ROI exceeds research pixel budget; split the experiment")
    source.validate_region(roi.x, roi.y, roi.width, roi.height)
    source.validate_identity()
    _check_cancel(cancel)
    wall, cpu = perf_counter(), process_time()
    timings = {}
    tick = perf_counter()
    original = np.array(
        source.read_region(roi.x, roi.y, roi.width, roi.height), copy=True
    )
    if original.shape[:2] != (roi.height, roi.width):
        raise ValueError("Source returned a different ROI shape")
    if original.dtype.kind != "u" or original.dtype.itemsize not in (1, 2):
        raise ValueError("Research preprocessing supports explicitly uint8/uint16 only")
    if original.ndim == 3 and original.shape[2] != 3 or original.ndim not in (2, 3):
        raise ValueError("Research processing supports gray or interleaved RGB only")
    meta = source.metadata
    if (
        original.dtype.name != meta.dtype
        or (1 if original.ndim == 2 else 3) != meta.channels
    ):
        raise ValueError("ROI dtype/channel identity mismatch")
    digest = sha256(original.tobytes()).hexdigest()
    original.setflags(write=False)
    timings["original_read_s"] = perf_counter() - tick
    tick = perf_counter()
    maximum = float(np.iinfo(original.dtype).max)
    gray = original.astype(np.float32) / maximum
    if gray.ndim == 3:
        gray = np.sum(gray * np.array([0.2126, 0.7152, 0.0722], np.float32), axis=2)
    background = ndi.gaussian_filter(gray, settings.background_sigma, mode="reflect")
    residual = gray - background
    timings["preprocessing_s"] = perf_counter() - tick
    polarities = (
        ("bright", "dark") if settings.polarity == "both" else (settings.polarity,)
    )
    union_response = np.zeros(gray.shape, np.float32)
    all_regions = np.zeros(gray.shape, np.int32)
    all_skeleton = np.zeros(gray.shape, bool)
    proposals = []
    response_maxima = {}
    rejected = {"area": 0, "shape": 0, "degenerate": 0, "cross_section": 0}
    region_total = 0
    skeleton_total = 0
    for polarity in polarities:
        _check_cancel(cancel)
        tick = perf_counter()
        signed = residual if polarity == "bright" else -residual
        support = signed >= settings.contrast_floor
        if settings.method == "local_contrast":
            raw = np.maximum(signed, 0)
        else:
            func = sato if settings.method == "sato" else frangi
            raw = func(
                gray,
                sigmas=settings.scales,
                black_ridges=polarity == "dark",
                mode="reflect",
            )
        top = float(np.max(raw))
        response_maxima[polarity] = top
        response = (raw / top).astype(np.float32) if top > 0 else np.zeros_like(gray)
        response[~support] = 0  # No bridges through unsupported contrast pixels.
        union_response = np.maximum(union_response, response)
        timings["enhancement_s"] = (
            timings.get("enhancement_s", 0) + perf_counter() - tick
        )
        tick = perf_counter()
        mask = apply_hysteresis_threshold(
            response, settings.low_threshold, settings.high_threshold
        )
        labels, count = ndi.label(mask, structure=np.ones((3, 3), int))
        if count > 100_000:
            raise ValueError("Raw noise component count exceeds ROI processing budget")
        areas = np.bincount(labels.ravel())
        keep = areas >= settings.min_area
        keep[0] = False
        rejected["area"] += count - int(np.count_nonzero(keep))
        # Remove small regions without connecting any pixels or closing gaps.
        labels, count = ndi.label(keep[labels], structure=np.ones((3, 3), int))
        region_total += count
        if region_total > settings.max_regions:
            raise ValueError(
                "Too many supported regions; choose smaller ROI/noise settings"
            )
        slices = ndi.find_objects(labels)
        timings["threshold_components_s"] = (
            timings.get("threshold_components_s", 0) + perf_counter() - tick
        )
        for label, bounds in enumerate(slices, 1):
            _check_cancel(cancel)
            ys, xs = bounds
            piece = labels[bounds] == label
            area = int(piece.sum())
            if area < settings.min_area:
                rejected["area"] += 1
                continue
            tick = perf_counter()
            # Work with the actual component crop, not the entire original image.
            center = skeletonize(piece, method="zhang")
            skeleton_total += int(np.count_nonzero(center))
            if skeleton_total > settings.max_skeleton_pixels:
                raise ValueError("Skeleton exceeds research connectivity budget")
            timings["skeleton_s"] = timings.get("skeleton_s", 0) + perf_counter() - tick
            tick = perf_counter()
            topology = trace_skeleton(center)
            if not topology.paths:
                rejected["degenerate"] += 1
                timings["graph_s"] = timings.get("graph_s", 0) + perf_counter() - tick
                continue
            before = topology
            removed = ()
            if settings.prune_length_px:
                center, removed = prune_spurs(
                    center,
                    topology,
                    settings.prune_length_px,
                    boundary_edges=(
                        xs.start == 0,
                        xs.stop == roi.width,
                        ys.start == 0,
                        ys.stop == roi.height,
                    ),
                )
                topology = trace_skeleton(center)
            width = (
                float(
                    2
                    * ndi.distance_transform_edt(np.pad(piece, 1))[1:-1, 1:-1][
                        center
                    ].mean()
                )
                if center.any()
                else math.inf
            )
            if (
                not topology.paths
                or max((path_length(path) for _, _, path in topology.paths), default=0)
                < settings.min_length_px
                or width > settings.max_width_px
                or topology.length / width < settings.min_aspect
            ):
                rejected["shape"] += 1
                timings["graph_s"] = timings.get("graph_s", 0) + perf_counter() - tick
                continue
            timings["graph_s"] = timings.get("graph_s", 0) + perf_counter() - tick

            tick = perf_counter()
            support_fraction = _cross_section_support(
                gray,
                topology,
                xs.start,
                ys.start,
                polarity,
                max(3 * max(settings.scales), width + 1),
                settings,
            )
            timings["cross_section_s"] = (
                timings.get("cross_section_s", 0) + perf_counter() - tick
            )
            if (
                support_fraction is not None
                and support_fraction < settings.min_ridge_support_fraction
            ):
                rejected["cross_section"] += 1
                continue

            # Shift component-local topology to ROI-local pixels.
            def shift(t, x_shift=xs.start, y_shift=ys.start):
                from .skeleton_graph import SkeletonTopology

                def point(p):
                    return (p[0] + x_shift, p[1] + y_shift)

                return SkeletonTopology(
                    tuple(point(p) for p in t.nodes),
                    tuple(
                        (a, b, tuple(point(p) for p in path)) for a, b, path in t.paths
                    ),
                    tuple(tuple(point(p) for p in c) for c in t.junction_clusters),
                    t.cycle,
                )

            flags = []
            if support_fraction is None:
                flags.append("INSUFFICIENT_CROSS_SECTION_CONTEXT")
            edge_boundary = np.zeros_like(piece)
            if ys.start == 0:
                edge_boundary[0] = piece[0]
            if xs.start == 0:
                edge_boundary[:, 0] = piece[:, 0]
            if ys.stop == roi.height:
                edge_boundary[-1] = piece[-1]
            if xs.stop == roi.width:
                edge_boundary[:, -1] = piece[:, -1]
            if edge_boundary.any():
                flags.append("TRUNCATED_AT_ROI_BOUNDARY")
                if (
                    (roi.x == 0 and xs.start == 0 and piece[:, 0].any())
                    or (roi.y == 0 and ys.start == 0 and piece[0].any())
                    or (
                        roi.x + roi.width == meta.width
                        and xs.stop == roi.width
                        and piece[:, -1].any()
                    )
                    or (
                        roi.y + roi.height == meta.height
                        and ys.stop == roi.height
                        and piece[-1].any()
                    )
                ):
                    flags.append("TRUNCATED_AT_IMAGE_BOUNDARY")
            if max(topology.degrees, default=0) >= 3:
                flags.append("JUNCTION_REQUIRES_REVIEW")
            if max(topology.degrees, default=0) >= 4:
                flags.append("CROSSING_OR_CONTACT_AMBIGUOUS")
            if topology.cycle:
                flags.append("CYCLE_AMBIGUOUS")
            if any(
                min(topology.degrees[a], topology.degrees[b]) == 1
                and len(topology.nodes) > 2
                and sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in pairwise(path))
                < settings.min_length_px
                for a, b, path in topology.paths
            ):
                flags.append("SHORT_BRANCH_REQUIRES_REVIEW")
            if removed:
                flags.append("PRUNED_REVIEW_REQUIRED")
            component = len(proposals) + 1
            roi_piece = all_regions[bounds]
            # Opposite polarities can touch, but are never fused into one label.
            roi_piece[piece] = component
            all_skeleton[bounds] |= center
            proposals.append(
                StructureProposal(
                    str(component),
                    polarity,
                    shift(topology),
                    (xs.start, ys.start, xs.stop - xs.start, ys.stop - ys.start),
                    area,
                    width,
                    tuple(flags),
                    tuple(
                        tuple((x + xs.start, y + ys.start) for x, y in path)
                        for path in removed
                    ),
                    shift(before),
                    support_fraction,
                )
            )
    _check_cancel(cancel)
    source.validate_identity()
    if sha256(original.tobytes()).hexdigest() != digest:
        raise ValueError("Research processing modified original ROI samples")
    timings.update(
        total_s=perf_counter() - wall,
        cpu_s=process_time() - cpu,
        response_maxima=response_maxima,
        rejected=rejected,
    )
    timings["cpu_core_percent"] = 100 * timings["cpu_s"] / timings["total_s"]
    for array in (union_response, all_regions, all_skeleton):
        array.setflags(write=False)
    return StructureExperiment(
        new_id(),
        utc_now(),
        asdict(source.identity),
        asdict(meta),
        roi,
        settings,
        {
            "normalization": "dtype_full_range_float32",
            "divisor": maximum,
            "rgb_luminance_weights": [0.2126, 0.7152, 0.0722]
            if original.ndim == 3
            else None,
            "background": "gaussian_reflect",
            "contrast_units": "fraction_of_original_dtype_range",
            "gap_closing": False,
            "cross_section": "both_sides_original_luminance; radius=max(3*max_scale,mean_width+1)",
            "skeleton": "zhang",
            "pruning": "single_pass_explicit_length",
        },
        digest,
        tuple(proposals),
        union_response,
        all_regions,
        all_skeleton,
        original,
        timings,
    )
