"""Follow an image-supported centreline through contacts, never invent pixels.

Local tangents select a continuation, not a globally straight line. Competing
directions with similar support remain ambiguous. This is a display proposal.
"""
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

from sic_xrt_analyzer.analysis.skeleton_graph import path_length, trace_skeleton


def translated_reference(reference, labels, radius=6):
    """Recover a small inter-slice translation only with unambiguous shape support.

    Returns a shifted reference for matching, never foreground to add to a slice.
    Empty slices, low overlap and equally plausible neighbours remain unlinked.
    """
    yy, xx = np.nonzero(reference)
    if not len(xx):
        return None, "NO_CONTACT"
    sizes = np.bincount(labels.ravel())
    best = {}
    h, w = labels.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            y, x = yy + dy, xx + dx
            valid = (y >= 0) & (y < h) & (x >= 0) & (x < w)
            counts = np.bincount(labels[y[valid], x[valid]], minlength=len(sizes))
            for label in np.flatnonzero(counts[1:]) + 1:
                score = counts[label] / (len(xx) + sizes[label] - counts[label])
                key = (score, -(dx * dx + dy * dy))
                if label not in best or key > best[label][0]:
                    best[label] = (key, dx, dy)
    ranked = sorted(best.values(), reverse=True)
    if not ranked or ranked[0][0][0] < 0.6:
        return None, "NO_CONTACT"
    if len(ranked) > 1 and ranked[1][0][0] >= ranked[0][0][0] * 0.85:
        return None, "AMBIGUOUS_BRANCH"
    _, dx, dy = ranked[0]
    shifted = np.zeros_like(reference)
    y, x = yy + dy, xx + dx
    valid = (y >= 0) & (y < h) & (x >= 0) & (x < w)
    shifted[y[valid], x[valid]] = True
    return shifted, "ACCEPTED"


def line_shape(mask):
    """Length/width evidence, independent of the initial slice's total area."""
    sk = skeletonize(mask)
    length = int(sk.sum())
    if not length:
        return False, 0.0
    radii = ndi.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1][sk]
    width = float(np.percentile(radii, 85) * 2)
    return length >= max(12, width * 4), width


def continue_line(component, anchor, reference=None):
    """Return (supported mask, resolved). A reference is in crop coordinates."""
    linear, width = line_shape(reference if reference is not None else component)
    if not linear:
        return component, False
    skeleton = skeletonize(component)
    if skeleton.sum() > 50000:
        return component, False
    topology = trace_skeleton(skeleton)
    paths = topology.paths
    if not paths or len(paths) > 128 or topology.cycle:
        return component, False
    if max(topology.degrees, default=0) <= 2:
        current_linear, current_width = line_shape(component)
        return component, bool(current_linear and current_width <= max(2.5 * width, width + 4))
    # Score a seed arm using the preceding observation. A click directly at a
    # crossing without any directional history is not enough to choose an arm.
    distance = ndi.distance_transform_edt(~reference) if reference is not None else None
    ranked = []
    for i, (_, _, points) in enumerate(paths):
        p = np.asarray(points)
        if path_length(points) < max(6, width):
            continue
        if distance is not None:
            near = distance[p[:, 1], p[:, 0]] <= max(2, width / 2)
            score = float(near.sum())
        else:
            score = -float(np.min((p[:, 0] - anchor[1])**2 + (p[:, 1] - anchor[0])**2))
        ranked.append((score, i))
    ranked.sort(reverse=True)
    if not ranked or (distance is not None and ranked[0][0] < max(6, width)):
        return component, False
    if distance is None and len(ranked) > 1 and ranked[0][0] - ranked[1][0] < width**2:
        return component, False
    seed = ranked[0][1]
    chosen = {seed}

    def oriented(index, node):
        a, _b, points = paths[index]
        return np.asarray(points if a == node else points[::-1], dtype=float)

    def extend(index, node):
        for _ in range(len(paths)):
            incoming = oriented(index, node)
            reach = min(len(incoming)-1, max(4, int(width * 2)))
            heading = incoming[0] - incoming[reach]
            heading /= max(np.linalg.norm(heading), 1e-6)
            candidates = []
            for j, (a, b, points) in enumerate(paths):
                if j in chosen or node not in (a, b) or path_length(points) < max(6, width):
                    continue
                p = oriented(j, node)
                reach = min(len(p)-1, max(4, int(width * 2)))
                tangent = p[reach] - p[0]
                cosine = float(heading @ tangent / max(np.linalg.norm(tangent), 1e-6))
                candidates.append((cosine, j, b if a == node else a))
            candidates.sort(reverse=True)
            if not candidates:
                return True
            # A single arm may bend sharply and still be the same curve.
            # Direction disambiguates competing substantial arms, not bends.
            if len(candidates) > 1 and (candidates[0][0] < 0.65 or candidates[0][0]-candidates[1][0] < 0.18):
                # A small intensity notch can split one line into two nearly
                # parallel skeleton arms inside its measured width. Keep both
                # observed arms, without filling the notch between them.
                if len(candidates) != 2 or candidates[1][0] < 0.8:
                    return False
                left = oriented(candidates[0][1], node)
                right = oriented(candidates[1][1], node)
                from scipy.spatial import cKDTree
                separation = max(cKDTree(left).query(right)[0].max(), cKDTree(right).query(left)[0].max())
                if separation > max(4, width * 1.5):
                    return False
                _, alternate, destination = candidates[1]
                chosen.add(alternate)
                if not extend(alternate, destination):
                    return False
            _, index, node = candidates[0]
            chosen.add(index)
        return False

    a, b, _ = paths[seed]
    if not extend(seed, a) or not extend(seed, b):
        return None, False
    selected_skeleton = np.zeros_like(component)
    for i in chosen:
        p = np.asarray(paths[i][2])
        selected_skeleton[p[:, 1], p[:, 0]] = True
    other = skeleton & ~selected_skeleton
    if not other.any():
        return component, True
    # Partition only measured foreground between selected and rejected arms.
    # Shared junction pixels belong to the selected centreline; no gap filling.
    ds = ndi.distance_transform_edt(~selected_skeleton)
    do = ndi.distance_transform_edt(~other)
    selected = component & (ds <= do)
    return selected, True
