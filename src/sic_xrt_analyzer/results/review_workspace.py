"""Individual, append-only review commands and isolated original-pixel drafts."""

import math
from copy import deepcopy
from dataclasses import replace

from sic_xrt_analyzer.analysis.contracts import utc_now

from .contracts import (
    ClassDecision,
    DefectInstance,
    ExistenceDecision,
    GeometryDecision,
    ReviewEvent,
    ReviewStatus,
    ReviewTarget,
)
from .geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
    GraphEdge,
    GraphNode,
)
from .reviews import ReviewRepository, prediction_snapshot
from .serialization import plain
from .validation import new_id


def upgrade(project):
    return replace(project, schema_version="1.1.0")


def target_source(project, target_type, target_id):
    rows = (
        project.observations
        if target_type == ReviewTarget.OBSERVATION
        else project.defect_instances
    )
    key = "observation_id" if target_type == ReviewTarget.OBSERVATION else "instance_id"
    target = next((r for r in rows if getattr(r, key) == target_id), None)
    if target is None:
        raise ValueError("Review target absent")
    run = next(
        (
            r
            for r in project.analysis_runs
            if target_type == ReviewTarget.OBSERVATION and r.run_id == target.run_id
        ),
        None,
    )
    return target, run.source_id if run else target.source_id


def append_review(
    project,
    target_type,
    target_id,
    reviewer,
    existence,
    classification,
    geometry_decision,
    comment="",
    geometry=None,
    source_id=None,
    run_id=None,
):
    reviewer = reviewer.strip()
    if not reviewer or len(reviewer) > 120 or any(ord(c) < 32 for c in reviewer):
        raise ValueError("연구원 ID는 제어문자 없는 1–120자입니다.")
    target, actual_source = target_source(project, target_type, target_id)
    if source_id != actual_source:
        raise ValueError("검수 Source가 대상과 다릅니다.")
    source = next(s for s in project.image_sources if s.source_id == actual_source)
    if source.acquisition_metadata.get("format") != "JPEG":
        raise ValueError("프로젝트 결함 검수는 JPG에만 지원합니다.")
    if run_id:
        run = next((r for r in project.analysis_runs if r.run_id == run_id), None)
        if (
            run is None
            or run.source_id != source_id
            or (target_type == ReviewTarget.OBSERVATION and run.run_id != target.run_id)
        ):
            raise ValueError("검수 Run이 대상과 다릅니다.")
    elif target_type == ReviewTarget.OBSERVATION:
        raise ValueError("후보 검수에는 정확한 Run이 필요합니다.")
    existence, classification, geometry_decision = (
        ExistenceDecision(existence),
        ClassDecision(classification),
        GeometryDecision(geometry_decision),
    )
    if (
        existence == ExistenceDecision.NOT_REVIEWED
        and classification == ClassDecision.NOT_REVIEWED
        and geometry_decision == GeometryDecision.NOT_REVIEWED
    ):
        raise ValueError("적어도 한 판정을 선택하세요.")
    if existence == ExistenceDecision.ABSENT and classification not in (
        ClassDecision.UNKNOWN,
        ClassDecision.NOT_REVIEWED,
    ):
        raise ValueError("결함 없음 판정에는 종류를 미확정으로 두세요.")
    snapshot, original_run = prediction_snapshot(project, target_type, target_id)
    history = ReviewRepository().history(project, target_type, target_id)
    parents = tuple(
        e
        for e in history
        if e.reviewer_id == reviewer
        and not any(e.review_id in child.parent_review_ids for child in history)
    )
    original_class = snapshot.get("assigned_class", snapshot.get("class_label"))
    corrected_class = (
        classification.value
        if classification != ClassDecision.NOT_REVIEWED
        and classification.value != original_class
        else None
    )
    if geometry is not None:
        original = next(
            g for g in project.geometries if g.geometry_id == target.geometry_id
        )
        if (
            geometry.geometry_source != GeometrySource.HUMAN
            or geometry.geometry_id in {g.geometry_id for g in project.geometries}
            or (geometry.source_id, geometry.page_index)
            != (original.source_id, original.page_index)
        ):
            raise ValueError("보정은 동일 원본의 새 HUMAN Geometry여야 합니다.")
        validate_edit_geometry(geometry, source)
        geometry_decision = GeometryDecision.CORRECTED
    elif geometry_decision == GeometryDecision.CORRECTED:
        raise ValueError("수정된 도형이 없습니다.")
    status = (
        ReviewStatus.CORRECTED
        if corrected_class is not None or geometry is not None
        else ReviewStatus.REJECTED
        if existence == ExistenceDecision.ABSENT
        else ReviewStatus.UNCERTAIN
        if existence == ExistenceDecision.UNCERTAIN
        or classification == ClassDecision.UNKNOWN
        or geometry_decision == GeometryDecision.UNCERTAIN
        else ReviewStatus.CONFIRMED
        if existence == ExistenceDecision.PRESENT
        else ReviewStatus.NEEDS_REVIEW
    )
    # Geometry/class corrections and an independent uncertain/absent decision coexist losslessly.
    event = ReviewEvent(
        new_id(),
        target_type,
        target_id,
        reviewer,
        status,
        snapshot,
        utc_now(),
        max((e.revision for e in parents), default=0) + 1,
        source_run_id=original_run or run_id,
        corrected_class=corrected_class,
        corrected_geometry_reference=geometry.geometry_id if geometry else None,
        comment=comment,
        parent_review_ids=tuple(e.review_id for e in parents),
        existence=existence,
        class_decision=classification,
        geometry_decision=geometry_decision,
    )
    p = upgrade(project)
    if geometry is not None:
        p = p.evolve(geometries=p.geometries + (geometry,))
    return ReviewRepository().append(p, event), event


def add_manual(
    project, source_id, geometry, reviewer, classification, comment="", run_id=None
):
    source = next(s for s in project.image_sources if s.source_id == source_id)
    if (
        geometry.source_id != source_id
        or geometry.geometry_source != GeometrySource.HUMAN
    ):
        raise ValueError("수동 결함은 동일 원본의 HUMAN 도형을 요구합니다.")
    validate_edit_geometry(geometry, source)
    instance = DefectInstance(
        new_id(),
        source_id,
        geometry.geometry_id,
        class_label=classification if classification != "NOT_REVIEWED" else "UNKNOWN",
        instance_status="HUMAN",
    )
    p = upgrade(project).evolve(
        geometries=project.geometries + (geometry,),
        defect_instances=project.defect_instances + (instance,),
    )
    p, event = append_review(
        p,
        ReviewTarget.DEFECT_INSTANCE,
        instance.instance_id,
        reviewer,
        "PRESENT",
        classification,
        "ACCEPTED",
        comment,
        source_id=source_id,
        run_id=run_id,
    )
    return p, event, instance


def validate_edit_geometry(geometry, source):
    geometry.validate_source(source)
    if geometry.kind == DefectGeometryKind.POLYGON:
        points = geometry.points
        if len(set(points)) != len(points):
            raise ValueError("중복 Polygon 꼭짓점은 지원하지 않습니다.")

        def cross(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        def intersects(a, b, c, d):
            ab1, ab2, cd1, cd2 = (
                cross(a, b, c),
                cross(a, b, d),
                cross(c, d, a),
                cross(c, d, b),
            )

            def on(a, b, p):
                return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(
                    a[1], b[1]
                ) <= p[1] <= max(a[1], b[1])

            return (
                (ab1 * ab2 < 0 and cd1 * cd2 < 0)
                or (ab1 == 0 and on(a, b, c))
                or (ab2 == 0 and on(a, b, d))
                or (cd1 == 0 and on(c, d, a))
                or (cd2 == 0 and on(c, d, b))
            )

        segments = list(zip(points, points[1:] + points[:1]))
        for i, (a, b) in enumerate(segments):
            for j, (c, d) in enumerate(segments):
                if (
                    j > i + 1
                    and not (i == 0 and j == len(points) - 1)
                    and intersects(a, b, c, d)
                ):
                    raise ValueError("자기 교차 Polygon은 저장할 수 없습니다.")


class GeometryDraft:
    """Undo acts only on this copy, never on an existing geometry or review."""

    def __init__(self, source, page=0, geometry=None, kind="POLYLINE"):
        self.source, self.page = source, page
        self.original = (
            plain(geometry)
            if geometry
            else {"kind": kind, "points": [], "nodes": [], "edges": []}
        )
        if self.original["kind"] in ("MASK_REFERENCE", "BOUNDING_BOX"):
            self.original = {"kind": "POLYGON", "points": [], "nodes": [], "edges": []}
        self.data = deepcopy(self.original)
        self.history = []
        self.selected = None
        self.gesture = None

    def checkpoint(self):
        self.history.append(deepcopy(self.data))
        self.history = self.history[-100:]

    def undo(self):
        if self.history:
            self.data = self.history.pop()
            self.selected = None

    def restore(self):
        self.checkpoint()
        self.data = deepcopy(self.original)
        self.selected = None

    def coordinate(self, x, y):
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or not 0 <= x < self.source.width
            or not 0 <= y < self.source.height
        ):
            raise ValueError("원본 이미지 경계 안의 좌표를 선택하세요.")
        return [x, y]

    def handles(self):
        if self.data["kind"] != "BRANCHED_GRAPH":
            return [
                {"key": f"p:{i}", "x": p[0], "y": p[1]}
                for i, p in enumerate(self.data["points"])
            ]
        rows = [
            {"key": "n:" + n["node_id"], "x": n["x"], "y": n["y"]}
            for n in self.data["nodes"]
        ]
        for edge in self.data["edges"]:
            rows.extend(
                {"key": f"e:{edge['edge_id']}:{i}", "x": p[0], "y": p[1]}
                for i, p in enumerate(edge["points"] or [])
                if 0 < i < len(edge["points"]) - 1
            )
        return rows

    def select(self, x, y, radius):
        hits = [(math.hypot(h["x"] - x, h["y"] - y), h["key"]) for h in self.handles()]
        self.selected = min(hits)[1] if hits and min(hits)[0] <= radius else None
        return bool(self.selected)

    def move(self, x, y, checkpoint=True):
        p = self.coordinate(x, y)
        if not self.selected:
            return
        if checkpoint:
            self.checkpoint()
        parts = self.selected.split(":")
        if parts[0] == "p":
            self.data["points"][int(parts[1])] = p
        elif parts[0] == "n":
            n = next(n for n in self.data["nodes"] if n["node_id"] == parts[1])
            n["x"], n["y"] = p
            for e in self.data["edges"]:
                if e["points"]:
                    if e["start_node"] == n["node_id"]:
                        e["points"][0] = p[:]
                    if e["end_node"] == n["node_id"]:
                        e["points"][-1] = p[:]
        else:
            next(e for e in self.data["edges"] if e["edge_id"] == parts[1])["points"][
                int(parts[2])
            ] = p

    def add(self, x, y):
        p = self.coordinate(x, y)
        self.checkpoint()
        if self.data["kind"] == "POINT":
            self.data["points"] = [p]
            self.selected = "p:0"
        elif self.data["kind"] == "BRANCHED_GRAPH":
            node = {"node_id": new_id(), "x": x, "y": y}
            old = next(
                (n for n in self.data["nodes"] if self.selected == "n:" + n["node_id"]),
                None,
            )
            if old is None and self.data["nodes"]:
                old = self.data["nodes"][-1]
            self.data["nodes"].append(node)
            if old:
                self.data["edges"].append(
                    {
                        "edge_id": new_id(),
                        "start_node": old["node_id"],
                        "end_node": node["node_id"],
                        "points": [[old["x"], old["y"]], p],
                    }
                )
            self.selected = "n:" + node["node_id"]
        else:
            index = (
                int(self.selected.split(":")[1]) + 1
                if self.selected and self.selected.startswith("p:")
                else len(self.data["points"])
            )
            self.data["points"].insert(index, p)
            self.selected = f"p:{index}"

    def delete(self):
        if not self.selected:
            return
        self.checkpoint()
        parts = self.selected.split(":")
        if parts[0] == "p":
            del self.data["points"][int(parts[1])]
        elif parts[0] == "e":
            del next(e for e in self.data["edges"] if e["edge_id"] == parts[1])[
                "points"
            ][int(parts[2])]
        else:
            self.data["nodes"] = [
                n for n in self.data["nodes"] if n["node_id"] != parts[1]
            ]
            self.data["edges"] = [
                e
                for e in self.data["edges"]
                if parts[1] not in (e["start_node"], e["end_node"])
            ]
        self.selected = None

    def edge(self, start, end, delete=False):
        self.checkpoint()
        if delete:
            self.data["edges"] = [
                e for e in self.data["edges"] if e["edge_id"] != start
            ]
            return
        a = next(n for n in self.data["nodes"] if n["node_id"] == start)
        b = next(n for n in self.data["nodes"] if n["node_id"] == end)
        self.data["edges"].append(
            {
                "edge_id": new_id(),
                "start_node": start,
                "end_node": end,
                "points": [[a["x"], a["y"]], [b["x"], b["y"]]],
            }
        )

    def add_edge_vertex(self, edge_id, x, y):
        p = self.coordinate(x, y)
        e = next(e for e in self.data["edges"] if e["edge_id"] == edge_id)
        self.checkpoint()
        if not e["points"]:
            nodes = {n["node_id"]: n for n in self.data["nodes"]}
            e["points"] = [
                [nodes[k]["x"], nodes[k]["y"]] for k in (e["start_node"], e["end_node"])
            ]
        index = len(e["points"]) - 1
        e["points"].insert(index, p)
        self.selected = f"e:{edge_id}:{index}"

    def finish(self):
        data = self.data
        g = DefectGeometry(
            new_id(),
            self.source.source_id,
            self.page,
            DefectGeometryKind(data["kind"]),
            GeometrySource.HUMAN,
            points=tuple(tuple(p) for p in data["points"]),
            nodes=tuple(GraphNode(**n) for n in data["nodes"]),
            edges=tuple(GraphEdge(**e) for e in data["edges"]),
        )
        validate_edit_geometry(g, self.source)
        return g
