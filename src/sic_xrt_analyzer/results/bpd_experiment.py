"""Additive experimental proposals, separate provenance and atomic new bundles.

Project schema 1.0.0 and all legacy runs/predictions/reviews remain unchanged.
"""

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .contracts import (
    DefectInstance,
    FileIdentity,
    ImageSourceRecord,
    LinkStatus,
    ObservationLink,
)
from .geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
    GraphEdge,
    GraphNode,
)
from .persistence import ProjectStore
from .serialization import plain
from .validation import stable_id

EXPERIMENT_FORMAT = "sic_xrt_bpd_structure_experiment"
EXPERIMENT_SCHEMA = "1.0.0"


@dataclass(frozen=True)
class AttachedExperiment:
    project: object
    manifest: dict
    masks: tuple  # safe relative path / ROI-derived bool mask


def attach_experiment(project, experiment, *, source_id=None, run_id=None):
    from sic_xrt_analyzer.analysis.bpd_structure import ALGORITHM_VERSION

    identity, meta = experiment.source_identity, experiment.source_metadata
    sources = (
        [s for s in project.image_sources if s.source_id == source_id]
        if source_id
        else [
            s
            for s in project.image_sources
            if s.file_identity
            == FileIdentity(
                identity["canonical_path"], identity["file_size"], identity["mtime_ns"]
            )
        ]
    )
    if len(sources) > 1:
        raise ValueError(
            "Explicit source_id required for duplicated original snapshots"
        )
    if source_id and not sources:
        raise ValueError("Unknown source_id")
    if sources:
        source = sources[0]
        if (
            source.file_identity,
            source.width,
            source.height,
            source.dtype,
            source.bit_depth,
            source.channels,
            source.page_count,
        ) != (
            FileIdentity(
                identity["canonical_path"], identity["file_size"], identity["mtime_ns"]
            ),
            meta["width"],
            meta["height"],
            meta["dtype"],
            meta["bit_depth"],
            meta["channels"],
            meta["page_count"],
        ):
            raise ValueError("Experiment does not match the saved original identity")
    else:
        source = ImageSourceRecord(
            stable_id(
                project.project_id,
                "structure-source:" + json.dumps(identity, sort_keys=True),
            ),
            Path(identity["canonical_path"]).name,
            identity["canonical_path"],
            meta["width"],
            meta["height"],
            meta["dtype"],
            meta["bit_depth"],
            meta["channels"],
            meta["page_count"],
            FileIdentity(
                identity["canonical_path"], identity["file_size"], identity["mtime_ns"]
            ),
            acquisition_metadata={"format": meta["format"]},
        )
    candidates = ()
    if run_id is not None:
        run = next((r for r in project.analysis_runs if r.run_id == run_id), None)
        if run is None or (run.source_id, run.page_index) != (
            source.source_id,
            identity["page_index"],
        ):
            raise ValueError("Grouping run belongs to another source/page")
        candidates = tuple(
            o
            for o in project.observations
            if o.run_id == run_id and o.assigned_class == "BPD" and o.x is not None
        )
    geometries, instances, rows, masks = [], [], [], []
    link_time = 0.0
    adapter_start = perf_counter()
    x0, y0 = experiment.roi.x, experiment.roi.y

    def original(point):
        return (point[0] + x0, point[1] + y0)

    for proposal in experiment.proposals:
        instance_id = stable_id(
            experiment.experiment_id, "instance:" + proposal.component_id
        )
        geometry_id = stable_id(instance_id, "centerline")
        t = proposal.topology
        is_line = len(t.paths) == 1 and len(t.nodes) == 2 and not t.cycle
        if is_line:
            geometry = DefectGeometry(
                geometry_id,
                source.source_id,
                identity["page_index"],
                DefectGeometryKind.POLYLINE,
                GeometrySource.RULE_BASED,
                points=tuple(original(p) for p in t.paths[0][2]),
            )
        else:
            geometry = DefectGeometry(
                geometry_id,
                source.source_id,
                identity["page_index"],
                DefectGeometryKind.BRANCHED_GRAPH,
                GeometrySource.RULE_BASED,
                nodes=tuple(
                    GraphNode(stable_id(geometry_id, "node:" + str(i)), *original(p))
                    for i, p in enumerate(t.nodes)
                ),
                edges=tuple(
                    GraphEdge(
                        stable_id(geometry_id, "edge:" + str(i)),
                        stable_id(geometry_id, "node:" + str(a)),
                        stable_id(geometry_id, "node:" + str(b)),
                        tuple(original(p) for p in path),
                    )
                    for i, (a, b, path) in enumerate(t.paths)
                ),
            )
        x, y, w, h = proposal.bbox
        region = experiment.regions[y : y + h, x : x + w] == int(proposal.component_id)
        skeleton = experiment.skeleton[y : y + h, x : x + w] & region
        link_tick = perf_counter()
        distance = ndi.distance_transform_edt(~skeleton)
        ambiguous = any(
            "AMBIGUOUS" in flag
            or "SHORT_BRANCH" in flag
            or "PRUNED" in flag
            or "INSUFFICIENT" in flag
            for flag in proposal.flags
        )
        links, evidence = [], []
        for o in candidates:
            px = int(np.floor(o.x - x0 + 0.5)) - x
            py = int(np.floor(o.y - y0 + 0.5)) - y
            if (
                0 <= px < w
                and 0 <= py < h
                and region[py, px]
                and distance[py, px] <= experiment.settings.link_distance_px
            ):
                status = LinkStatus.AMBIGUOUS if ambiguous else LinkStatus.PROPOSED
                links.append(ObservationLink(o.observation_id, status))
                evidence.append(
                    {
                        "observation_id": o.observation_id,
                        "source_candidate_id": o.source_candidate_id,
                        "same_image_supported_component": True,
                        "centerline_distance_px": float(distance[py, px]),
                        "link_status": status.value,
                    }
                )
        link_time += perf_counter() - link_tick
        instance = DefectInstance(
            instance_id,
            source.source_id,
            geometry_id,
            tuple(links),
            class_label=None,
            instance_status="AMBIGUOUS" if ambiguous else "PROPOSED",
        )
        reference = "geometry/references/" + instance_id + ".png"
        mask_id = stable_id(instance_id, "region-mask")
        mask_geometry = DefectGeometry(
            mask_id,
            source.source_id,
            identity["page_index"],
            DefectGeometryKind.MASK_REFERENCE,
            GeometrySource.RULE_BASED,
            bbox=(x + x0, y + y0, w, h),
            mask_reference=reference,
            mask_encoding="PNG_UINT8_BINARY",
        )
        geometries.extend((geometry, mask_geometry))
        instances.append(instance)
        region.setflags(write=False)
        masks.append((reference, region))
        rows.append(
            {
                "instance_id": instance_id,
                "geometry_id": geometry_id,
                "mask_geometry_id": mask_id,
                "interpretation": "UNVERIFIED_LINEAR_STRUCTURE_PROPOSAL",
                "classification": None,
                "review_required": True,
                "polarity": proposal.polarity,
                "flags": proposal.flags,
                "area_pixels": proposal.area,
                "length_px": t.length,
                "mean_width_px": proposal.mean_width_px,
                "ridge_support_fraction": proposal.ridge_support_fraction,
                "junction_cluster_count": len(t.junction_clusters),
                "node_degrees": t.degrees,
                "links": evidence,
                "before_pruning": {
                    "coordinate_space": "ORIGINAL",
                    "nodes": [original(p) for p in proposal.before_pruning.nodes],
                    "paths": [
                        [a, b, [original(p) for p in path]]
                        for a, b, path in proposal.before_pruning.paths
                    ],
                },
                "removed_paths": [
                    [original(p) for p in path] for path in proposal.removed_paths
                ],
            }
        )
    old_geoms = {g.geometry_id: g for g in project.geometries}
    old_instances = {i.instance_id: i for i in project.defect_instances}
    if any(
        g.geometry_id in old_geoms and old_geoms[g.geometry_id] != g for g in geometries
    ) or any(
        i.instance_id in old_instances and old_instances[i.instance_id] != i
        for i in instances
    ):
        raise ValueError("Experiment ID would rewrite existing geometry/instances")
    new_geoms = tuple(g for g in geometries if g.geometry_id not in old_geoms)
    new_instances = tuple(i for i in instances if i.instance_id not in old_instances)
    added_source = () if source in project.image_sources else (source,)
    updated = (
        project.evolve(
            image_sources=project.image_sources + added_source,
            geometries=project.geometries + new_geoms,
            defect_instances=project.defect_instances + new_instances,
        )
        if new_geoms or new_instances or added_source
        else project
    )
    import scipy
    import skimage

    manifest = {
        "format": EXPERIMENT_FORMAT,
        "schema_version": EXPERIMENT_SCHEMA,
        "experiment_id": experiment.experiment_id,
        "created_at": experiment.created_at.isoformat(),
        "project_id": updated.project_id,
        "source_id": source.source_id,
        "source_identity": identity,
        "source_metadata": meta,
        "roi": asdict(experiment.roi),
        "algorithm": "bpd_structure_" + experiment.settings.method,
        "algorithm_version": ALGORITHM_VERSION,
        "settings": asdict(experiment.settings),
        "preprocessing": experiment.preprocessing,
        "roi_sha256": experiment.roi_sha256,
        "grouping_run_id": run_id,
        "proposals": rows,
        "metrics": {
            **experiment.metrics,
            "candidate_link_s": link_time,
            "domain_adapter_s": perf_counter() - adapter_start,
        },
        "libraries": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "skimage": skimage.__version__,
        },
        "validation_status": "PRELIMINARY_NO_GROUND_TRUTH",
        "assets": {},
    }
    return AttachedExperiment(updated, plain(manifest), tuple(masks))


def save_experiment_bundle(output, attached, comparison_png):
    """Publish one entirely new bundle; never replace a project/session/original.

    An incomplete sibling staging directory is cleaned on exceptions. A process
    crash may leave it, but the final target and the prior project remain intact.
    """
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError("Choose a new experiment output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + output.name + ".", dir=output.parent))
    try:
        ProjectStore().save(stage / "project.json", attached.project)
        manifest = dict(attached.manifest)
        assets = {}
        for reference, mask in attached.masks:
            path = stage / reference
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(mask.astype(np.uint8) * 255).save(path)
            assets[reference] = hashlib.sha256(path.read_bytes()).hexdigest()
        (stage / "comparison.png").write_bytes(comparison_png)
        assets["comparison.png"] = hashlib.sha256(comparison_png).hexdigest()
        manifest["assets"] = assets
        data = json.dumps(
            manifest, ensure_ascii=False, indent=2, allow_nan=False
        ).encode("utf-8")
        with (stage / "experiment.json").open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if ProjectStore().load(stage / "project.json") != attached.project:
            raise ValueError("Experiment project verification failed")
        load_experiment_bundle(stage)  # Verify refs/hash/PNG before publishing.
        os.rename(stage, output)
        return output
    finally:
        if stage.exists():
            resolved = stage.resolve()
            if not resolved.is_relative_to(
                output.parent.resolve()
            ) or not stage.name.startswith("." + output.name + "."):
                raise ValueError("Unsafe staging cleanup path")
            shutil.rmtree(resolved)


def load_experiment_bundle(output):
    try:
        return _load_experiment_bundle(output)
    except (
        KeyError,
        TypeError,
        AttributeError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Corrupt experiment metadata") from exc


def _load_experiment_bundle(output):
    output = Path(output)
    from .serialization import MAX_PROJECT_BYTES, _pairs

    with (output / "experiment.json").open("rb") as stream:
        data = stream.read(MAX_PROJECT_BYTES + 1)
    if len(data) > MAX_PROJECT_BYTES:
        raise ValueError("Experiment metadata too large")
    manifest = json.loads(
        data,
        object_pairs_hook=_pairs,
        parse_constant=lambda s: (_ for _ in ()).throw(
            ValueError("Nonfinite experiment data")
        ),
    )
    required = {
        "format",
        "schema_version",
        "experiment_id",
        "created_at",
        "project_id",
        "source_id",
        "source_identity",
        "source_metadata",
        "roi",
        "algorithm",
        "algorithm_version",
        "settings",
        "preprocessing",
        "roi_sha256",
        "grouping_run_id",
        "proposals",
        "metrics",
        "libraries",
        "validation_status",
        "assets",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != required
        or manifest["format"] != EXPERIMENT_FORMAT
        or manifest["schema_version"] != EXPERIMENT_SCHEMA
    ):
        raise ValueError("Unsupported/corrupt experiment manifest")
    from datetime import datetime

    from sic_xrt_analyzer.analysis.bpd_structure import (
        ALGORITHM_VERSION,
        StructureSettings,
    )
    from sic_xrt_analyzer.analysis.contracts import Region

    from .validation import digest, integer, text, timestamp

    text(manifest["experiment_id"])
    timestamp(datetime.fromisoformat(manifest["created_at"]))
    digest(manifest["roi_sha256"])
    settings = StructureSettings(**manifest["settings"])
    if (
        manifest["algorithm"] != "bpd_structure_" + settings.method
        or manifest["algorithm_version"] != ALGORITHM_VERSION
        or manifest["validation_status"] != "PRELIMINARY_NO_GROUND_TRUTH"
    ):
        raise ValueError("Unsupported experiment algorithm/validation")
    project = ProjectStore().load(output / "project.json")
    source = next(
        (s for s in project.image_sources if s.source_id == manifest["source_id"]), None
    )
    if project.project_id != manifest["project_id"] or source is None:
        raise ValueError("Experiment/project/source mismatch")
    identity = manifest["source_identity"]
    if (
        identity["canonical_path"],
        identity["file_size"],
        identity["mtime_ns"],
        identity["width"],
        identity["height"],
    ) != (
        source.file_identity.canonical_path,
        source.file_identity.file_size,
        source.file_identity.mtime_ns,
        source.width,
        source.height,
    ):
        raise ValueError("Experiment original identity mismatch")
    for key in ("width", "height", "dtype", "bit_depth", "channels", "page_count"):
        if manifest["source_metadata"][key] != getattr(source, key):
            raise ValueError("Experiment source header mismatch")
    integer(identity["page_index"], "experiment page")
    if identity["page_index"] >= source.page_count:
        raise ValueError("Experiment page outside source")
    if not isinstance(manifest["proposals"], list) or not isinstance(
        manifest["assets"], dict
    ):
        raise TypeError("Invalid experiment proposal/asset collections")
    roi = Region(**manifest["roi"])
    for key in ("x", "y", "width", "height"):
        integer(
            getattr(roi, key),
            "experiment ROI " + key,
            1 if key in ("width", "height") else 0,
        )
    if roi.x + roi.width > source.width or roi.y + roi.height > source.height:
        raise ValueError("Experiment ROI outside source")
    geometry = {g.geometry_id: g for g in project.geometries}
    instances = {i.instance_id: i for i in project.defect_instances}
    mask_extents = {}
    seen = set()
    for row in manifest["proposals"]:
        if (
            row["instance_id"] in seen
            or row["classification"] is not None
            or row["review_required"] is not True
            or row["interpretation"] != "UNVERIFIED_LINEAR_STRUCTURE_PROPOSAL"
        ):
            raise ValueError("Invalid/duplicate/unreviewed proposal metadata")
        seen.add(row["instance_id"])
        instance = instances.get(row["instance_id"])
        mask = geometry.get(row["mask_geometry_id"])
        if (
            instance is None
            or instance.geometry_id != row["geometry_id"]
            or instance.source_id != source.source_id
            or mask is None
            or mask.source_id != source.source_id
        ):
            raise ValueError("Experiment geometry/instance references invalid")
        if (
            mask.kind != DefectGeometryKind.MASK_REFERENCE
            or mask.mask_encoding != "PNG_UINT8_BINARY"
            or mask.page_index != identity["page_index"]
        ):
            raise ValueError("Invalid experiment mask contract")
        mask_extents[mask.mask_reference] = (int(mask.bbox[2]), int(mask.bbox[3]))
        if mask.mask_reference not in manifest["assets"]:
            raise ValueError("Untracked mask asset")
    for reference, expected in manifest["assets"].items():
        digest(expected)
        path = ProjectStore().resolve_asset(output / "project.json", reference)
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Experiment asset hash mismatch")
        if path.suffix.lower() != ".png":
            raise ValueError("Only explicit PNG experiment assets supported")
        with Image.open(path) as image:
            if image.width * image.height > 8_388_608:
                raise ValueError("Experiment PNG exceeds image budget")
            image.verify()
        if reference in mask_extents:
            with Image.open(path) as image:
                if image.size != mask_extents[reference] or image.mode != "L":
                    raise ValueError("Mask pixels do not match original bbox/encoding")
                values = np.asarray(image)
                if not np.all((values == 0) | (values == 255)):
                    raise ValueError("Mask must contain explicit binary samples")
    return project, manifest


def comparison_image(experiment, project, attached):
    import io

    from PIL import ImageFont

    # Explicit visualization conversion only; detection used dtype-range floats.
    pixels = experiment.original
    if pixels.dtype == np.uint16:
        lo, hi = np.percentile(pixels, (1, 99))
        pixels = (
            np.clip((pixels.astype(np.float32) - lo) / max(hi - lo, 1), 0, 1) * 255
        ).astype(np.uint8)
    source = Image.fromarray(pixels).convert("RGB")
    panels = [source.copy() for _ in range(6)]
    draw = [ImageDraw.Draw(p) for p in panels]
    w, h = source.size
    x0, y0 = experiment.roi.x, experiment.roi.y
    for o in project.observations:
        if o.x is None or o.page_index != experiment.source_identity["page_index"]:
            continue
        run = next(r for r in project.analysis_runs if r.run_id == o.run_id)
        if run.source_id != attached.manifest["source_id"] or (
            attached.manifest["grouping_run_id"]
            and run.run_id != attached.manifest["grouping_run_id"]
        ):
            continue
        x, y = o.x - x0, o.y - y0
        if not 0 <= x < w or not 0 <= y < h:
            continue
        for d in (draw[1], draw[3]):
            d.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(255, 200, 0), width=2)
            d.text((x + 5, y), o.assigned_class, fill="white")
    proposals = attached.manifest["proposals"]
    geometries = {g.geometry_id: g for g in attached.project.geometries}
    for index, row in enumerate(proposals):
        geometry = geometries[row["geometry_id"]]
        paths = (
            (geometry.points,)
            if geometry.kind == DefectGeometryKind.POLYLINE
            else tuple(e.points for e in geometry.edges)
        )
        for path in paths:
            local = [(x - x0, y - y0) for x, y in path]
            for d in (draw[2], draw[3], draw[4]):
                d.line(local, fill=(0, 255, 200), width=2)
        p = experiment.proposals[index]
        for node, degree in zip(p.topology.nodes, p.topology.degrees):
            x, y = node
            if degree >= 3:
                draw[4].rectangle(
                    (x - 5, y - 5, x + 5, y + 5), outline="white", width=2
                )
                draw[4].text((x + 6, y), str(degree), fill="white")
            elif degree == 1:
                draw[4].polygon(
                    ((x, y - 5), (x - 4, y + 4), (x + 4, y + 4)), outline="white"
                )
        x, y, bw, bh = p.bbox
        draw[3].text((x, y), "G" + str(index + 1), fill="white")
        draw[5].rectangle(
            (x, y, x + bw - 1, y + bh - 1), outline=(255, 120, 120), width=1
        )
        draw[5].text(
            (x, y),
            "G" + str(index + 1) + (" ?" if p.flags else " unreviewed"),
            fill="white",
        )
        # Actual mask boundaries are traced, not a bounding box substituted for them.
        import cv2

        region = (experiment.regions == int(p.component_id)).astype(np.uint8)
        contours, _ = cv2.findContours(
            region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            points = [tuple(p) for p in contour[:, 0, :].tolist()]
            if len(points) > 1:
                draw[5].line(points + [points[0]], fill=(255, 120, 120), width=1)
    edge = min(512, w)
    ratio = edge / w
    ph = max(1, int(h * ratio))
    titles = (
        "A Source",
        "B Existing points (class labels)",
        "C Image-supported centerlines",
        "D Proposed groups + points",
        "E Square=junction, triangle=end",
        "F Boundaries; ?=review flags",
    )
    sheet = Image.new("RGB", (edge * 3, (ph + 35) * 2 + 60), (24, 28, 32))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, panel in enumerate(panels):
        px = (i % 3) * edge
        py = (i // 3) * (ph + 35)
        d.text((px + 5, py + 6), titles[i], font=font, fill="white")
        sheet.paste(panel.resize((edge, ph)), (px, py + 30))
    d.text(
        (5, (ph + 35) * 2),
        "UNREVIEWED STRUCTURE PROPOSALS - no BPD ground truth / no calibrated confidence",
        fill="white",
    )
    d.text(
        (5, (ph + 35) * 2 + 20),
        f"{experiment.settings.method}/{experiment.settings.polarity}; ROI {x0},{y0},{w},{h}; original pixels unchanged",
        fill="white",
    )
    stream = io.BytesIO()
    sheet.save(stream, format="PNG")
    return stream.getvalue()
