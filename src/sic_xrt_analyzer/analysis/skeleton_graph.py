"""Condense image-supported 2D skeletons, suppress redundant corner diagonals.

This module describes pixel topology, never physical defect identity.
"""

import math
from collections import deque
from dataclasses import dataclass
from itertools import pairwise

import numpy as np


@dataclass(frozen=True)
class SkeletonTopology:
    nodes: tuple[tuple[int, int], ...]  # local x/y, actual skeleton pixels
    paths: tuple[tuple[int, int, tuple[tuple[int, int], ...]], ...]
    junction_clusters: tuple[tuple[tuple[int, int], ...], ...]
    cycle: bool = False

    @property
    def degrees(self):
        degrees = [0] * len(self.nodes)
        for a, b, _ in self.paths:
            degrees[a] += 1
            degrees[b] += 1
        return tuple(degrees)

    @property
    def length(self):
        return sum(path_length(path) for _, _, path in self.paths)


def path_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(points))


def pixel_neighbors(skeleton):
    pixels = {(int(x), int(y)) for y, x in np.argwhere(skeleton)}
    neighbors = {}
    for x, y in sorted(pixels, key=lambda p: (p[1], p[0])):
        near = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                q = (x + dx, y + dy)
                if not (dx or dy) or q not in pixels:
                    continue
                # Keep true diagonals, remove corner triangle shortcuts only.
                if dx and dy and ((x + dx, y) in pixels or (x, y + dy) in pixels):
                    continue
                near.append(q)
        neighbors[(x, y)] = tuple(near)
    return neighbors


def trace_skeleton(skeleton):
    graph = pixel_neighbors(skeleton)
    if len(graph) < 2:
        return SkeletonTopology((), (), ())
    junctions = {p for p, near in graph.items() if len(near) >= 3}
    clusters = []
    remaining = set(junctions)
    while remaining:
        seed = min(remaining, key=lambda p: (p[1], p[0]))
        cluster, pending = set(), [seed]
        while pending:
            p = pending.pop()
            if p in cluster:
                continue
            cluster.add(p)
            pending.extend(q for q in graph[p] if q in junctions and q not in cluster)
        remaining -= cluster
        clusters.append(tuple(sorted(cluster, key=lambda p: (p[1], p[0]))))
    groups = [(p,) for p, near in graph.items() if len(near) <= 1] + clusters
    groups.sort(key=lambda c: (min(p[1] for p in c), min(p[0] for p in c)))
    if not groups:
        # A closed ring has no critical pixels. Anchor three real points so
        # the domain can store a cycle without forbidden self/parallel edges.
        first = min(graph, key=lambda p: (p[1], p[0]))
        ring, previous, current = [first], first, graph[first][0]
        while current != first:
            ring.append(current)
            choices = [p for p in graph[current] if p != previous]
            if not choices or len(ring) > len(graph):
                raise ValueError("Untraceable skeleton cycle")
            previous, current = current, choices[0]
        if len(ring) < 3:
            return SkeletonTopology((), (), ())
        indices = (0, len(ring) // 3, 2 * len(ring) // 3)
        nodes = tuple(ring[i] for i in indices)
        paths = (
            (0, 1, tuple(ring[: indices[1] + 1])),
            (1, 2, tuple(ring[indices[1] : indices[2] + 1])),
            (2, 0, tuple(ring[indices[2] :] + [first])),
        )
        return SkeletonTopology(nodes, paths, (), True)
    nodes = []
    owner = {}
    for index, group in enumerate(groups):
        cx = sum(p[0] for p in group) / len(group)
        cy = sum(p[1] for p in group) / len(group)
        nodes.append(
            min(group, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
        )
        owner.update((p, index) for p in group)
    visited, paths, pairs = set(), [], set()
    cycle = False

    def cluster_path(owner_id, destination):
        # Traverse the actual junction pixels. A representative-to-exit chord
        # can otherwise cross unsupported pixels inside a large cluster.
        start = nodes[owner_id]
        parents, pending = {start: None}, deque([start])
        while pending and destination not in parents:
            current = pending.popleft()
            for neighbor in graph[current]:
                if owner.get(neighbor) == owner_id and neighbor not in parents:
                    parents[neighbor] = current
                    pending.append(neighbor)
        if destination not in parents:
            raise ValueError("Disconnected junction cluster")
        result, current = [], destination
        while current is not None:
            result.append(current)
            current = parents[current]
        return result[::-1]

    def add_path(a, b, raw):
        nonlocal cycle
        points = cluster_path(a, raw[0]) + raw[1:]
        points += cluster_path(b, raw[-1])[::-1][1:]
        points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
        key = frozenset((a, b))
        if a == b:
            cycle = True
            distinct = [p for p in points[1:-1] if p != nodes[a]]
            if len(distinct) < 2:
                raise ValueError("Unrepresentable junction loop")
            i1, i2 = len(points) // 3, 2 * len(points) // 3
            if points[i1] == points[i2]:
                raise ValueError("Degenerate junction loop")
            n1, n2 = len(nodes), len(nodes) + 1
            nodes.extend((points[i1], points[i2]))
            paths.extend(
                (
                    (a, n1, tuple(points[: i1 + 1])),
                    (n1, n2, tuple(points[i1 : i2 + 1])),
                    (n2, b, tuple(points[i2:])),
                )
            )
        elif key in pairs:
            cycle = True
            mid = len(points) // 2
            if points[mid] in (nodes[a], nodes[b]):
                raise ValueError("Degenerate parallel skeleton paths")
            n = len(nodes)
            nodes.append(points[mid])
            paths.extend(
                ((a, n, tuple(points[: mid + 1])), (n, b, tuple(points[mid:])))
            )
        else:
            pairs.add(key)
            paths.append((a, b, tuple(points)))

    for a, group in enumerate(groups):
        for start in group:
            for neighbor in graph[start]:
                edge = frozenset((start, neighbor))
                if owner.get(neighbor) == a or edge in visited:
                    continue
                visited.add(edge)
                raw, previous, current = [start, neighbor], start, neighbor
                while current not in owner:
                    choices = [q for q in graph[current] if q != previous]
                    if len(choices) != 1:
                        raise ValueError("Uncondensed critical skeleton pixel")
                    following = choices[0]
                    visited.add(frozenset((current, following)))
                    raw.append(following)
                    previous, current = current, following
                    if len(raw) > len(graph) + 1:
                        raise ValueError("Unterminated skeleton path")
                add_path(a, owner[current], raw)
    return SkeletonTopology(tuple(nodes), tuple(paths), tuple(clusters), cycle)


def prune_spurs(
    skeleton, topology, minimum_length, *, boundary_edges=(True, True, True, True)
):
    result = skeleton.copy()
    removed = []
    degrees = topology.degrees
    h, w = skeleton.shape
    protected = {p for c in topology.junction_clusters for p in c}
    for a, b, path in topology.paths:
        leaf = (
            a
            if degrees[a] == 1 and degrees[b] >= 3
            else b
            if degrees[b] == 1 and degrees[a] >= 3
            else None
        )
        if leaf is None or path_length(path) >= minimum_length:
            continue
        x, y = topology.nodes[leaf]
        if (
            boundary_edges[0]
            and x == 0
            or boundary_edges[1]
            and x == w - 1
            or boundary_edges[2]
            and y == 0
            or boundary_edges[3]
            and y == h - 1
        ):
            continue  # Truncated endpoints cannot be judged short by this crop.
        for x, y in path:
            if (x, y) not in protected and (x, y) != topology.nodes[
                b if leaf == a else a
            ]:
                result[y, x] = False
        removed.append(path)
    return result, tuple(removed)
