"""Global LAP linking: frame-to-frame, then gap closing, then split/merge candidates.

Costs are in source pixels. A link is accepted only when it is cheaper than the
combined death + birth alternative (2 * no_link_cost). Confidence comes from
the assignment margin; low-margin links are flagged for review.
"""

import itertools
import math

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .model import Link, Track

BIG = 1e9


class _Geometry:
    def __init__(self, detections):
        self.dets = detections
        self.trees = {}
        self.by_page = {}
        for i, d in enumerate(detections):
            self.by_page.setdefault(d.page, []).append(i)
        self.centres = {}
        for k, idx in self.by_page.items():
            c = np.array([detections[i].centroid for i in idx])
            half = max(detections[i].length for i in idx) / 2
            self.centres[k] = (cKDTree(c), half)

    def around(self, page, det, shift, reach):
        """Column indices on page whose centroid may lie within reach of det+shift."""
        entry = self.centres.get(page)
        if entry is None:
            return []
        tree, half = entry
        centre = np.asarray(det.centroid) + shift
        return sorted(tree.query_ball_point(centre, reach + det.length / 2 + half))

    def tree(self, i):
        t = self.trees.get(i)
        if t is None:
            t = self.trees[i] = cKDTree(self.dets[i].points.astype(float))
        return t

    def distance(self, i, j, shift):
        a, b = self.dets[i], self.dets[j]
        if a.polarity != b.polarity:
            return math.inf
        if a.kind == b.kind == "BLOB" and len(a.points) <= 30 and len(b.points) <= 30:
            return float(np.hypot(*(np.asarray(b.centroid) - a.centroid - shift)))
        # Min of directed means: a growing/shrinking line still matches itself.
        da = self.tree(j).query(a.points + shift)[0].mean()
        db = self.tree(i).query(b.points - shift)[0].mean()
        return float(min(da, db))

    def cost(self, i, j, dist, s):
        a, b = self.dets[i], self.dets[j]
        c = dist + (s.kind_penalty if a.kind != b.kind else 0.0)
        if a.kind == b.kind == "SEGMENT" and min(a.length, b.length) > 5:
            c += s.orientation_weight * abs(math.sin(a.orientation - b.orientation))
        ca, cb = max(a.contrast_z, 0.5), max(b.contrast_z, 0.5)
        return c + s.contrast_weight * abs(math.log(ca / cb))

    def displacement(self, i, j):
        a, b = self.dets[i], self.dets[j]
        if "BLOB" in (a.kind, b.kind):
            return np.asarray(b.centroid) - a.centroid
        _, idx = self.tree(j).query(a.points)
        return np.median(b.points[idx] - a.points, axis=0)



def _solve(cost, no_link):
    """Augmented LAP; returns [(row, col)] with finite chosen cost."""
    n, m = cost.shape
    if not n or not m:
        return []
    full = np.full((n + m, n + m), BIG)
    full[:n, :m] = np.where(np.isfinite(cost), cost, BIG)
    full[:n, m:][np.diag_indices(n)] = no_link
    full[n:, :m][np.diag_indices(m)] = no_link
    full[n:, m:] = 0
    rows, cols = linear_sum_assignment(full)
    return [(r, c) for r, c in zip(rows, cols) if r < n and c < m and full[r, c] < BIG]


def _confidence(cost, r, c, no_link, scale):
    row = np.delete(cost[r], c)
    col = np.delete(cost[:, c], r)
    competitor = min(2 * no_link, row.min() if len(row) else math.inf,
                     col.min() if len(col) else math.inf)
    margin = max(0.0, competitor - cost[r, c])
    return 1.0 - math.exp(-margin / scale)


def link(detections, settings, cancelled=lambda: False, progress=lambda *a: None):
    """Return (tracks, links) for detections (any order)."""
    s = settings
    dets = sorted(detections, key=lambda d: (d.page, d.id))
    geo = _Geometry(dets)
    by_page = geo.by_page
    pages = sorted(by_page)
    tracklets = []  # [members, velocity, observations]
    owner = {}
    links = {}  # (i, j) -> (kind, cost, confidence)
    active = []
    for step, k in enumerate(pages):
        if cancelled():
            raise InterruptedError("결함 추적 취소")
        progress(step + 1, len(pages), "페이지 간 결함 연결")
        cols = by_page[k]
        rows = [t for t in active if dets[tracklets[t][0][-1]].page == k - 1]
        cost = np.full((len(rows), len(cols)), math.inf)
        for r, t in enumerate(rows):
            i = tracklets[t][0][-1]
            v = tracklets[t][1]
            for c in geo.around(k, dets[i], v, s.gate_px):
                j = cols[c]
                dist = geo.distance(i, j, v)
                if dist <= s.gate_px:
                    cost[r, c] = geo.cost(i, j, dist, s)
        used = set()
        for r, c in _solve(cost, s.no_link_cost):
            t, j = rows[r], cols[c]
            i = tracklets[t][0][-1]
            conf = _confidence(cost, r, c, s.no_link_cost, s.confidence_scale)
            links[(i, j)] = ("CONTINUE", float(cost[r, c]), conf)
            _advance(tracklets[t], geo, i, j, 1, s)
            owner[j] = t
            used.add(j)
        for j in cols:
            if j not in used:
                owner[j] = len(tracklets)
                tracklets.append([[j], np.zeros(2), 1])
        active = [owner[j] for j in cols]

    # Gap closing over tracklet ends/starts (missing 1..max_gap pages).
    first_at = {tracklets[t][0][0]: t for t in range(len(tracklets))}
    pairs = {}
    for e in range(len(tracklets)):
        i = tracklets[e][0][-1]
        ke = dets[i].page
        for gap in range(2, s.max_gap + 2):
            shift = tracklets[e][1] * gap
            gate = s.gate_px * (1 + 0.25 * (gap - 1))
            for c in geo.around(ke + gap, dets[i], shift, gate):
                j = by_page[ke + gap][c]
                st = first_at.get(j)
                if st is None:
                    continue
                dist = geo.distance(i, j, shift)
                if dist <= gate:
                    pairs[(e, st)] = geo.cost(i, j, dist, s) + s.gap_penalty * (gap - 1)
    keep_r = sorted({e for e, _ in pairs})
    keep_c = sorted({st for _, st in pairs})
    rpos = {e: n for n, e in enumerate(keep_r)}
    cpos = {st: n for n, st in enumerate(keep_c)}
    sub = np.full((len(keep_r), len(keep_c)), math.inf)
    for (e, st), c in pairs.items():
        sub[rpos[e], cpos[st]] = c
    successor, has_predecessor = {}, set()
    for r, c in _solve(sub, s.no_link_cost):
        e, st = keep_r[r], keep_c[c]
        i, j = tracklets[e][0][-1], tracklets[st][0][0]
        gap = dets[j].page - dets[i].page
        conf = _confidence(sub, r, c, s.no_link_cost, s.confidence_scale)
        conf *= 0.85 ** (gap - 1)
        links[(i, j)] = ("GAP", float(sub[r, c]), conf)
        successor[e] = st
        has_predecessor.add(st)

    chains = []
    for t in range(len(tracklets)):
        if t in has_predecessor:
            continue
        members, cur = [], t
        while cur is not None:
            members += tracklets[cur][0]
            cur = successor.get(cur)
        chains.append(members)
    chains.sort(key=lambda m: (dets[m[0]].page, dets[m[0]].id))

    out_links = []
    tracks = []
    track_of = {}
    for n, members in enumerate(chains):
        confs = []
        for a, b in itertools.pairwise(members):
            kind, c, conf = links[(a, b)]
            confs.append(conf)
            out_links.append(Link(dets[a].id, dets[b].id, kind, c, conf,
                                  conf < s.review_below))
        for m in members:
            track_of[m] = n
        low = min(confs, default=1.0)
        tracks.append(Track(
            f"t{n}", tuple(dets[m].id for m in members), tuple(dets[m].page for m in members),
            low, low < s.review_below,
        ))
    out_links += _split_merge(dets, geo, chains, track_of, s)
    return tracks, out_links


def _advance(tracklet, geo, i, j, gap, s):
    observed = geo.displacement(i, j) / gap
    a = s.velocity_smoothing
    tracklet[1] = observed if tracklet[2] < 2 else (1 - a) * tracklet[1] + a * observed
    tracklet[0].append(j)
    tracklet[2] += 1


def _split_merge(dets, geo, chains, track_of, s):
    """Candidate SPLIT/MERGE links between tracks; always flagged for review."""
    by_page = geo.by_page
    out = []
    zero = np.zeros(2)
    for n, members in enumerate(chains):
        if len(members) < 2:
            continue
        for kind, anchor, page in (("SPLIT", members[0], dets[members[0]].page - 1),
                                   ("MERGE", members[-1], dets[members[-1]].page + 1)):
            best = None
            for j in by_page.get(page, ()):
                other = chains[track_of[j]]
                if track_of[j] == n or len(other) < 2:
                    continue
                # The partner must continue across the event page.
                pos = other.index(j)
                if (kind == "SPLIT" and pos + 1 >= len(other)) or (kind == "MERGE" and pos == 0):
                    continue
                dist = geo.distance(anchor, j, zero)
                if dist <= s.split_merge_px and (best is None or dist < best[0]):
                    best = (dist, j)
            if best:
                dist, j = best
                conf = 1.0 - math.exp(-(s.split_merge_px - dist) / s.confidence_scale)
                src, dst = (j, anchor) if kind == "SPLIT" else (anchor, j)
                out.append(Link(dets[src].id, dets[dst].id, kind, dist, conf, True))
    return out
