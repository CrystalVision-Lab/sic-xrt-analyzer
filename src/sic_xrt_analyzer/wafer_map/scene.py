"""Derived, run-specific map layers. No candidate merging or physical density inference."""

import time
from collections import Counter, OrderedDict, defaultdict

import numpy as np
from PySide6.QtGui import QImage

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.results.sources import inspect_source, verify_content_hash

from .mapping import points, view


def check(cancelled):
    if cancelled():
        raise InterruptedError("지도 작업 취소")


def paths(geometry):
    if geometry.nodes:
        nodes = {n.node_id: [n.x, n.y] for n in geometry.nodes}
        return [
            list(e.points) or [nodes[e.start_node], nodes[e.end_node]]
            for e in geometry.edges
        ]
    if geometry.points:
        p = list(geometry.points)
        if geometry.kind.value == "POLYGON":
            p.append(p[0])
        return [p]
    if geometry.bbox:
        x, y, w, h = geometry.bbox
        return [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]
    return []


class Scene:
    def __init__(self):
        self.previews = OrderedDict()
        self.decode_count = 0
        self.preview_ms = []
        self.index_key = None
        self.index = []
        self.summary = {}
        self.index_ms = 0
        self.counts_by_source = {}

    def clear(self):
        self.previews.clear()
        self.index = []
        self.index_key = None

    def prepare_preview(self, source, cancelled):
        status = inspect_source(source)
        if not status.pixels_available:
            self.previews.pop(source.source_id, None)
            return None, status.status
        key = (
            source.source_id,
            source.file_identity,
            source.content_hash.value if source.content_hash else None,
        )
        if (
            source.source_id in self.previews
            and self.previews[source.source_id][0][:2] == key[:2]
            and (key[2] is None or self.previews[source.source_id][0][2] == key[2])
        ):
            value = self.previews.pop(source.source_id)
            self.previews[source.source_id] = value
            return value[1], "READY"
        verified = verify_content_hash(source, cancelled=cancelled)
        ts = time.perf_counter()
        reader = JpegImageSource(source.source_reference)
        data = reader.read_sampled(384)
        check(cancelled)
        reader.validate_identity()
        h, w, _ = data.shape
        image = QImage(data.data, w, h, data.strides[0], QImage.Format_RGB888).copy()
        self.decode_count += 1
        self.preview_ms.append((time.perf_counter() - ts) * 1000)
        key = (source.source_id, source.file_identity, verified.content_hash.value)
        self.previews[source.source_id] = (key, image, verified)
        while (
            len(self.previews) > 20
            or sum(v[1].sizeInBytes() for v in self.previews.values()) > 12 * 1024**2
        ):
            self.previews.popitem(last=False)
        return image, "READY"

    def rebuild(self, project, asset, cancelled):
        key = (id(project), tuple(sorted(asset["runs"].items())))
        if self.index_key == key:
            return
        ts = time.perf_counter()
        rows = []
        counts = Counter()
        by_source = defaultdict(Counter)
        runs = {r.run_id: r for r in project.analysis_runs}
        geoms = {g.geometry_id: g for g in project.geometries}
        selected = {rid for rid in asset["runs"].values() if rid}
        selected_observations = {
            o.observation_id: o for o in project.observations if o.run_id in selected
        }
        events = {}
        for e in project.review_events:
            events.setdefault((e.target_type.value, e.target_id), []).append(e)

        def review(kind, ident):
            es = events.get((kind, ident), [])
            superseded = {x for e in es for x in e.parent_review_ids}
            tips = [e for e in es if e.review_id not in superseded]
            meanings = {
                (
                    e.review_status,
                    e.existence,
                    e.class_decision,
                    e.geometry_decision,
                    e.corrected_geometry_reference,
                )
                for e in tips
            }
            conflict = len(meanings) > 1 or len({e.reviewer_id for e in tips}) < len(
                tips
            )
            return tips, conflict

        def add(source, run, kind, ident, geometry, layer, label, point=None):
            ps = [[point]] if point is not None else paths(geometry)
            if not ps:
                return
            if sum(len(p) for p in ps) > 4096:
                counts["omitted_large_shapes"] += 1
                by_source[source]["omitted_large_shapes"] += 1
                return
            rows.append(
                {
                    "source_id": source,
                    "run_id": run,
                    "target_type": kind,
                    "target_id": ident,
                    "geometry_id": geometry.geometry_id,
                    "layer": layer,
                    "label": label,
                    "paths": ps,
                    "mask_bounds": geometry.kind.value == "MASK_REFERENCE",
                }
            )

        for o in selected_observations.values():
            check(cancelled)
            r = runs[o.run_id]
            g = geoms[o.geometry_id]
            label = o.assigned_class or "UNKNOWN"
            add(
                r.source_id,
                o.run_id,
                "OBSERVATION",
                o.observation_id,
                g,
                label,
                label,
                [o.x, o.y] if o.x is not None else None,
            )
            counts[label] += 1
            by_source[r.source_id][label] += 1
            if g.kind.value != "POINT":
                add(
                    r.source_id,
                    o.run_id,
                    "OBSERVATION",
                    o.observation_id,
                    g,
                    "model_geometry",
                    label,
                )
            tips, conflict = review("OBSERVATION", o.observation_id)
            if conflict:
                counts["conflicts"] += 1
                by_source[r.source_id]["conflicts"] += 1
            if tips:
                counts["reviewed_observations"] += 1
                by_source[r.source_id]["reviewed_observations"] += 1
                for e in tips:
                    rg = geoms.get(e.corrected_geometry_reference, g)
                    add(
                        r.source_id,
                        o.run_id,
                        "OBSERVATION",
                        o.observation_id,
                        rg,
                        "reviews",
                        "CONFLICT" if conflict else e.existence.value,
                    )
        for i in project.defect_instances:
            check(cancelled)
            g = geoms[i.geometry_id]
            linked = {l.observation_id for l in i.linked_observations}
            if i.instance_status == "HUMAN":
                layer = "human"
                counts["human"] += 1
                by_source[i.source_id]["human"] += 1
            elif linked & selected_observations.keys() or not linked:
                layer = "experimental"
                counts["experimental"] += 1
                by_source[i.source_id]["experimental"] += 1
            else:
                continue
            rid = next(
                (
                    selected_observations[x].run_id
                    for x in linked
                    if x in selected_observations
                ),
                "",
            )
            add(
                i.source_id,
                rid,
                "DEFECT_INSTANCE",
                i.instance_id,
                g,
                layer,
                i.class_label or "UNKNOWN",
            )
            tips, conflict = review("DEFECT_INSTANCE", i.instance_id)
            if conflict:
                counts["conflicts"] += 1
                by_source[i.source_id]["conflicts"] += 1
            for e in tips:
                add(
                    i.source_id,
                    rid,
                    "DEFECT_INSTANCE",
                    i.instance_id,
                    geoms.get(e.corrected_geometry_reference, g),
                    "reviews",
                    "CONFLICT" if conflict else e.existence.value,
                )
        self.index = rows
        self.summary = dict(counts)
        self.counts_by_source = dict(by_source)
        self.index_key = key
        self.index_ms = (time.perf_counter() - ts) * 1000

    def render(
        self, project, asset, centre, zoom, width, height, cancelled=lambda: False
    ):
        ts = time.perf_counter()
        self.rebuild(project, asset, cancelled)
        group = next(g for g in asset["groups"] if g["id"] == asset["selected_group"])
        placements = {
            p["source_id"]: p
            for p in asset["placements"]
            if p["group_id"] == group["id"]
        }
        source_map = {s.source_id: s for s in project.image_sources}
        run_labels = {
            r.run_id: r.scope.value + " · " + r.run_id[:8]
            for r in project.analysis_runs
        }
        screen = view(centre, zoom, width, height, group["axes"])
        tiles = []
        images = {}
        shown = {}
        errors = []

        def visible(p):
            a = np.asarray(p)
            return not (
                a[:, 0].max() < 0
                or a[:, 1].max() < 0
                or a[:, 0].min() > width
                or a[:, 1].min() > height
            )

        for sid, p in placements.items():
            check(cancelled)
            s = source_map[sid]
            transform = screen @ np.asarray(p["matrix"])
            border = points(
                transform,
                [
                    [-0.5, -0.5],
                    [s.width - 0.5, -0.5],
                    [s.width - 0.5, s.height - 0.5],
                    [-0.5, s.height - 0.5],
                ],
            )
            if not visible(border):
                continue
            try:
                image, status = (
                    self.prepare_preview(s, cancelled)
                    if len(images) < 20
                    else (None, "PREVIEW_BUDGET")
                )
            except (OSError, ValueError) as exc:
                self.previews.pop(sid, None)
                image, status = None, "원본 연결/SHA 확인 필요: " + str(exc)
            if image is not None:
                images[sid] = image
            elif status not in ("PREVIEW_BUDGET",):
                errors.append(s.display_name + ": " + status)
            tiles.append(
                {
                    "source_id": sid,
                    "name": s.display_name,
                    "run_label": run_labels.get(
                        asset["runs"].get(sid, ""), "표시 결과 없음"
                    ),
                    "matrix": transform.tolist(),
                    "width": s.width,
                    "height": s.height,
                    "border": border,
                    "status": p["status"],
                    "availability": status,
                    "preview": image is not None,
                    "preview_key": str(image.cacheKey()) if image is not None else "",
                }
            )
            shown[sid] = transform
        paths_out = []
        summaries = Counter()
        counts_by_source = {
            sid: self.counts_by_source.get(sid, Counter()) for sid in placements
        }
        displayed_points = 0
        omitted = 0
        for row in self.index:
            check(cancelled)
            sid = row["source_id"]
            if sid not in placements:
                continue
            if sid not in shown or not asset["layers"].get(row["layer"], False):
                continue
            transformed = [points(shown[sid], p) for p in row["paths"]]
            if not any(visible(p) for p in transformed):
                continue
            # Small zoom draws one point per 3px cell/class/source; totals use every observation.
            if (
                row["layer"] in ("BPD", "TED", "TSD")
                and len(transformed) == 1
                and len(transformed[0]) == 1
            ):
                x, y = transformed[0][0]
                cell = (sid, row["layer"], int(x / 3), int(y / 3))
                if cell in summaries or displayed_points >= 10000:
                    omitted += 1
                    continue
                summaries[cell] += 1
                displayed_points += 1
            paths_out.append(
                {**{k: v for k, v in row.items() if k != "paths"}, "paths": transformed}
            )
        geo = group["geometry"]
        outline = None
        if geo:
            outline = {
                "centre": points(screen, [geo["centre"]])[0],
                "radius": float(geo["radius"] * zoom),
            }
        totals = Counter()
        for c in counts_by_source.values():
            totals.update(c)
        check(cancelled)
        return {
            "tiles": tiles,
            "paths": paths_out,
            "images": images,
            "summary": dict(totals),
            "counts_by_source": {sid: dict(c) for sid, c in counts_by_source.items()},
            "review_summary": dict(totals),
            "omitted_display_points": omitted,
            "unplaced": sum(
                s.acquisition_metadata.get("format") == "JPEG"
                and s.source_id not in {p["source_id"] for p in asset["placements"]}
                for s in project.image_sources
            ),
            "outline": outline,
            "errors": errors,
            "metrics": {
                "scene_ms": (time.perf_counter() - ts) * 1000,
                "index_ms": self.index_ms,
                "decoded": self.decode_count,
                "cache_items": len(self.previews),
                "cache_bytes": sum(v[1].sizeInBytes() for v in self.previews.values()),
                "visible_tiles": len(tiles),
                "display_paths": len(paths_out),
            },
        }


def hit_path(path, xy, tolerance=7):
    """Hit actual segment interiors as well as point/edge vertices, in screen pixels."""
    vertices = np.asarray(path, float)
    if len(vertices) == 1:
        return np.linalg.norm(vertices[0] - xy) <= tolerance
    start = vertices[:-1]
    edge = vertices[1:] - start
    lengths = (edge * edge).sum(axis=1)
    t = np.divide(
        ((np.asarray(xy) - start) * edge).sum(axis=1),
        lengths,
        out=np.zeros_like(lengths),
        where=lengths > 0,
    )
    closest = start + np.clip(t, 0, 1)[:, None] * edge
    return np.min(np.linalg.norm(closest - xy, axis=1)) <= tolerance
