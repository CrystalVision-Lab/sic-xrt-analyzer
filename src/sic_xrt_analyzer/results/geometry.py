"""Original-pixel shape extensions; the legacy model Geometry contract stays intact."""

from dataclasses import dataclass
from enum import Enum

from sic_xrt_analyzer.analysis.contracts import CoordinateSpace, Geometry, GeometryKind

from .validation import asset_reference, integer, number, text, unique


class DefectGeometryKind(str, Enum):
    POINT = "POINT"
    BOUNDING_BOX = "BOUNDING_BOX"
    POLYLINE = "POLYLINE"
    POLYGON = "POLYGON"
    MASK_REFERENCE = "MASK_REFERENCE"
    BRANCHED_GRAPH = "BRANCHED_GRAPH"


class GeometrySource(str, Enum):
    MODEL = "MODEL"
    RULE_BASED = "RULE_BASED"
    HUMAN = "HUMAN"
    IMPORTED = "IMPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    x: float
    y: float

    def __post_init__(self):
        text(self.node_id)
        number(self.x, "node x")
        number(self.y, "node y")


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    start_node: str
    end_node: str
    points: tuple[tuple[float, float], ...] = ()

    def __post_init__(self):
        for value in (self.edge_id, self.start_node, self.end_node):
            text(value)
        object.__setattr__(self, "points", tuple(tuple(p) for p in self.points))
        if self.start_node == self.end_node:
            raise ValueError("Graph self edges are not supported")


@dataclass(frozen=True)
class DefectGeometry:
    geometry_id: str
    source_id: str
    page_index: int
    kind: DefectGeometryKind
    geometry_source: GeometrySource = GeometrySource.UNKNOWN
    points: tuple[tuple[float, float], ...] = ()
    bbox: tuple[float, float, float, float] | None = None
    mask_reference: str | None = None
    mask_encoding: str | None = None
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    coordinate_space: CoordinateSpace = CoordinateSpace.ORIGINAL

    def __post_init__(self):
        text(self.geometry_id)
        text(self.source_id)
        integer(self.page_index, "page")
        if not isinstance(self.kind, DefectGeometryKind) or not isinstance(
            self.geometry_source, GeometrySource
        ):
            raise TypeError("Explicit geometry kind/source required")
        if self.coordinate_space != CoordinateSpace.ORIGINAL or not isinstance(
            self.coordinate_space, CoordinateSpace
        ):
            raise ValueError("Project geometry uses original pixel coordinates only")
        for name in ("points", "nodes", "edges"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "points", tuple(tuple(p) for p in self.points))
        if self.bbox is not None:
            object.__setattr__(self, "bbox", tuple(self.bbox))
        if self.kind not in (
            DefectGeometryKind.POLYLINE,
            DefectGeometryKind.BRANCHED_GRAPH,
        ):
            legacy_kind = (
                GeometryKind.MASK
                if self.kind == DefectGeometryKind.MASK_REFERENCE
                else GeometryKind(self.kind.value)
            )
            Geometry(
                legacy_kind,
                self.points,
                self.bbox,
                self.mask_reference,
                self.mask_encoding,
                self.coordinate_space,
            )
            if self.nodes or self.edges:
                raise ValueError("Only graphs can have nodes and edges")
            if self.kind == DefectGeometryKind.POLYGON:
                area = sum(
                    a[0] * b[1] - b[0] * a[1]
                    for a, b in zip(self.points, self.points[1:] + self.points[:1])
                )
                if area == 0 or len(set(self.points)) < 3:
                    raise ValueError(
                        "Polygon requires nonzero area and distinct vertices"
                    )
            if self.mask_reference is not None:
                asset_reference(self.mask_reference)
                text(self.mask_encoding, "mask encoding")
        else:
            if (
                self.bbox is not None
                or self.mask_reference is not None
                or self.mask_encoding is not None
            ):
                raise ValueError("Line/graph cannot include a box or mask")
            if self.kind == DefectGeometryKind.POLYLINE:
                if (
                    self.nodes
                    or self.edges
                    or len(self.points) < 2
                    or len(set(self.points)) < 2
                ):
                    raise ValueError(
                        "Polyline requires a path with distinct endpoints/vertices"
                    )
            else:
                if self.points or len(self.nodes) < 2 or not self.edges:
                    raise ValueError("Graph requires explicit nodes and edges")
                if any(not isinstance(n, GraphNode) for n in self.nodes) or any(
                    not isinstance(e, GraphEdge) for e in self.edges
                ):
                    raise ValueError("Typed graph records required")
                nodes = unique(self.nodes, "node_id")
                unique(self.edges, "edge_id")
                neighbors = {key: set() for key in nodes}
                pairs = set()
                for edge in self.edges:
                    if edge.start_node not in nodes or edge.end_node not in nodes:
                        raise ValueError("Graph edge references an absent node")
                    pair = frozenset((edge.start_node, edge.end_node))
                    if pair in pairs:
                        raise ValueError("Duplicate graph connection")
                    pairs.add(pair)
                    neighbors[edge.start_node].add(edge.end_node)
                    neighbors[edge.end_node].add(edge.start_node)
                    if edge.points:
                        a, b = nodes[edge.start_node], nodes[edge.end_node]
                        if (
                            len(edge.points) < 2
                            or edge.points[0] != (a.x, a.y)
                            or edge.points[-1] != (b.x, b.y)
                        ):
                            raise ValueError("Edge paths must meet their nodes")
                visited, pending = set(), [next(iter(nodes))]
                while pending:
                    key = pending.pop()
                    if key not in visited:
                        visited.add(key)
                        pending.extend(neighbors[key] - visited)
                if visited != set(nodes):
                    raise ValueError(
                        "Graph must be connected; separate defects use separate geometries"
                    )
        for point in self.all_points():
            if len(point) != 2:
                raise ValueError("Geometry points require x/y")
            for value in point:
                number(value, "geometry coordinate")

    def all_points(self):
        return (
            self.points
            + tuple((n.x, n.y) for n in self.nodes)
            + tuple(p for e in self.edges for p in e.points)
        )

    def validate_source(self, source):
        if self.page_index >= source.page_count:
            raise ValueError("Geometry page outside source")
        strict = self.kind == DefectGeometryKind.POINT
        for x, y in self.all_points():
            if (
                x < 0
                or y < 0
                or x > source.width
                or y > source.height
                or strict
                and (x == source.width or y == source.height)
            ):
                raise ValueError("Geometry outside original coordinates")
        if self.bbox:
            x, y, w, h = self.bbox
            if x < 0 or y < 0 or x + w > source.width or y + h > source.height:
                raise ValueError("Geometry extent outside source")
