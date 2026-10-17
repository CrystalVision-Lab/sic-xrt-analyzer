"""Synthetic page-track benchmark with ground-truth ids (no real XRT data).

Run: python -m sic_xrt_analyzer.stack3d.tracking.benchmark
Synthetic scores are regression evidence, not real-data accuracy claims.
"""


import itertools
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment

from .engine import nearest_detection, track_stack
from .model import TrackSettings

K, H, W, BG = 24, 128, 128, 60000.0


@dataclass(frozen=True)
class Scenario:
    name: str
    category: str
    volume: np.ndarray  # (K, H, W) uint16
    labels: np.ndarray  # (K, H, W) int16 ground-truth ids, 0 = background
    seed: tuple  # x, y, page on a target pixel
    target_ids: tuple


def _base(rng, noise=0.0, texture=0.0):
    s = np.full((K, H, W), BG)
    if noise:
        s += rng.normal(0, noise, s.shape)
    if texture:
        t = ndi.gaussian_filter(rng.normal(0, 1, s.shape), (0, 1.5, 1.5))
        s += t / t.std() * texture
    return s, np.zeros((K, H, W), np.int16)


def _vline(img, lab, y0, y1, x, w, depth, gid):
    x = round(x)
    if x < 0 or x + w > img.shape[1]:
        return
    img[y0:y1, x:x + w] -= depth
    lab[y0:y1, x:x + w] = gid


def _disk(img, lab, cx, cy, r, depth, gid):
    yy, xx = np.ogrid[:img.shape[0], :img.shape[1]]
    m = (yy - cy) ** 2 + (xx - cx) ** 2 < r * r
    img[m] -= depth
    lab[m] = gid


def _finish(name, category, s, g, seed, targets=(1,)):
    return Scenario(name, category, np.clip(s, 0, 65535).astype(np.uint16), g, seed, targets)


def scenarios():
    out = []
    for gap in (1, 2, 3):
        rng = np.random.default_rng(10 + gap)
        s, g = _base(rng, 300)
        for k in range(2, 22):
            if not 12 <= k < 12 + gap:
                _vline(s[k], g[k], 24, 104, 62, 4, 8000, 1)
        out.append(_finish(f"gap_{gap}", "gap", s, g, (63, 64, 6)))
    for v in (3, 6, 10):
        rng = np.random.default_rng(20 + v)
        s, g = _base(rng, 200)
        for k in range(2, 22):
            _vline(s[k], g[k], 24, 104, 8 + v * (k - 2), 3, 9000, 1)
        out.append(_finish(f"drift_{v}px", "drift", s, g, (9 + v * 2, 64, 4)))
    rng = np.random.default_rng(30)
    s, g = _base(rng, 300)
    for k in range(2, 22):
        _vline(s[k], g[k], 24, 104, 62, 4, 8000 * (1 - 0.85 * abs(k - 12) / 10), 1)
    out.append(_finish("fade_15pct", "fade", s, g, (63, 64, 12)))
    for snr in (4, 3, 2):
        rng = np.random.default_rng(40 + snr)
        s, g = _base(rng, texture=1000)
        for k in range(2, 22):
            _vline(s[k], g[k], 24, 104, 62, 4, 1000 * snr, 1)
        out.append(_finish(f"texture_snr{snr}", "texture", s, g, (63, 64, 12)))
    rng = np.random.default_rng(50)
    s, g = _base(rng, 200)
    for k in range(2, 22):
        _vline(s[k], g[k], 24, 104, 30 + 3.5 * (k - 2), 3, 9000, 1)
        _vline(s[k], g[k], 24, 104, 96 - 3.5 * (k - 2), 3, 9000, 2)
    out.append(_finish("crossing", "crossing", s, g, (31, 64, 2)))
    rng = np.random.default_rng(60)
    s, g = _base(rng, 200)
    for k in range(2, 22):
        if k < 12:
            _vline(s[k], g[k], 24, 104, 62, 3, 9000, 1)
        else:
            off = 2.0 * (k - 11)
            _vline(s[k], g[k], 24, 104, 62 - off, 3, 9000, 1)
            _vline(s[k], g[k], 24, 104, 62 + off, 3, 9000, 2)
    out.append(_finish("branching", "branching", s, g, (63, 64, 5), (1, 2)))
    rng = np.random.default_rng(70)
    s, g = _base(rng, 200)
    for k in range(2, 22):
        _vline(s[k], g[k], 69, min(124, 74 + 4 * (k - 2)), 63, 3, 9000, 1)
        if k >= 10:
            _vline(s[k], g[k], max(4, 59 - 4 * (k - 10)), 60, 63, 3, 9000, 3)
        _disk(s[k], g[k], 64, 64, 4, 9000, 2)
    out.append(_finish("dot_touched_by_line", "contact", s, g, (64, 64, 6), (2,)))
    rng = np.random.default_rng(80)
    s, g = _base(rng, 200)
    for k in range(2, 22):
        for n in range(6):
            _vline(s[k], g[k], 24, 104, 38 + 8 * n + 0.5 * (k - 2), 3, 9000, n + 1)
    out.append(_finish("dense_parallel", "dense", s, g, (63, 64, 6), (4,)))
    rng = np.random.default_rng(90)
    s, g = _base(rng, 200)
    gains = 0.4 + 0.6 * np.abs(np.sin(np.arange(K) / 3.0))
    for k in range(2, 22):
        _vline(s[k], g[k], 24, 104, 62, 4, 8000, 1)
    s = s * gains[:, None, None]
    out.append(_finish("page_gain", "gain", s, g, (63, 64, int(np.argmax(gains[2:22]) + 2))))
    rng = np.random.default_rng(100)
    s, g = _base(rng, 250, texture=250)
    for k in range(2, 22):
        jx, jy = rng.uniform(-0.75, 0.75, 2)
        _disk(s[k], g[k], 64 + jx, 64 + jy, 3, 5000 * (1 - 0.6 * abs(k - 12) / 10), 1)
    out.append(_finish("point_jitter_fade", "point", s, g, (64, 64, 12)))
    return out


def _truth_pages(sc):
    return sorted({k for k in range(K) if np.isin(sc.labels[k], sc.target_ids).any()})


def _label_points(labels, points):
    near = ndi.grey_dilation(labels, size=5)
    lab = near[points[:, 1], points[:, 0]]
    values, counts = np.unique(lab, return_counts=True)
    best = int(np.argmax(counts))
    return int(values[best]) if counts[best] >= 0.5 * len(lab) else 0


def _seed_metrics(sc, page_labels):
    """page_labels: {page: gt label of the observation}."""
    truth = set(_truth_pages(sc))
    correct = {p for p, lab in page_labels.items() if lab in sc.target_ids}
    ordered = [page_labels[p] for p in sorted(page_labels)]
    switches = sum(a != b for a, b in itertools.pairwise(ordered))
    return {
        "pages": len(page_labels),
        "page_recall": len(correct & truth) / len(truth),
        "purity": len(correct) / max(1, len(page_labels)),
        "switches": switches,
    }


def run_old(sc, workdir):
    import tifffile

    from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
    from sic_xrt_analyzer.stack3d.defect import trace

    path = Path(workdir) / f"{sc.name}.tif"
    tifffile.imwrite(path, sc.volume, photometric="minisblack")
    x, y, page = sc.seed
    try:
        mesh = trace(OriginalImageSource(path, page), (x, y, page))
    except (ValueError, InterruptedError):
        return _seed_metrics(sc, {})
    labels = {}
    for s in mesh.sections:
        lab = sc.labels[s.page, s.y:s.y + s.height, s.x:s.x + s.width][s.mask()]
        values, counts = np.unique(lab, return_counts=True)
        labels[s.page] = int(values[np.argmax(counts)])
    return _seed_metrics(sc, labels)


def _global_metrics(sc, result, det_label, min_len=3):
    s = result.settings
    in_track = [lk for lk in result.links if lk.kind in ("CONTINUE", "GAP")]
    good = [det_label[lk.source_id] == det_label[lk.target_id] != 0 for lk in in_track]
    ids = sorted(int(i) for i in np.unique(sc.labels) if i)
    track_pages = {}  # (track, label) -> pages
    for t in result.tracks:
        for did, p in zip(t.detection_ids, t.pages):
            track_pages.setdefault((t.id, det_label[did]), set()).add(p)
    truth = {g: sorted({k for k in range(K) if (sc.labels[k] == g).any()}) for g in ids}
    linked = {(det_label[lk.source_id], result.detection(lk.source_id).page,
               result.detection(lk.target_id).page)
              for lk in in_track if det_label[lk.source_id] == det_label[lk.target_id]}
    need = hit = 0
    for g, pages in truth.items():
        for a, b in itertools.pairwise(pages):
            if b - a <= s.max_gap + 1:
                need += 1
                hit += (g, a, b) in linked
    long_tracks = [t for t in result.tracks if len(t.pages) >= min_len]
    m = np.zeros((len(long_tracks), len(ids)))
    for r, t in enumerate(long_tracks):
        for c, g in enumerate(ids):
            m[r, c] = len(track_pages.get((t.id, g), ()))
    idtp = 0.0
    if m.size:
        rr, cc = linear_sum_assignment(-m)
        idtp = float(m[rr, cc].sum())
    denom = sum(len(p) for p in truth.values()) + sum(len(t.pages) for t in long_tracks)
    switches = frags = 0
    for g, pages in truth.items():
        owners = []
        for p in pages:
            owner = [t for (t, lab), ps in track_pages.items() if lab == g and p in ps]
            if owner:
                owners.append(min(owner))
        switches += sum(a != b for a, b in itertools.pairwise(owners))
        frags += max(0, len(set(owners)) - 1)
    return {
        "link_precision": sum(good) / max(1, len(good)),
        "link_recall": hit / max(1, need),
        "idf1": 2 * idtp / max(1, denom),
        "id_switches": switches,
        "fragments": frags,
        "split_merge_candidates": sum(lk.kind in ("SPLIT", "MERGE") for lk in result.links),
    }


def run_new(sc, settings=None):
    result = track_stack(sc.volume, settings or TrackSettings())
    det_label = {d.id: _label_points(sc.labels[d.page], d.points) for d in result.detections}
    x, y, page = sc.seed
    det = nearest_detection(result, page, x, y)
    labels = {}
    if det is not None:
        track = result.track_of(det.id)
        labels = {p: det_label[i] for i, p in zip(track.detection_ids, track.pages)}
    return _seed_metrics(sc, labels), _global_metrics(sc, result, det_label), result


def run_benchmark(workdir=None, names=None):
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for sc in scenarios():
            if names and sc.name not in names:
                continue
            old = run_old(sc, workdir or tmp)
            new, glob, _ = run_new(sc)
            rows.append({"name": sc.name, "category": sc.category, "old": old,
                         "new": new, "global": glob, "truth_pages": len(_truth_pages(sc))})
    return rows


def markdown(rows):
    lines = [
        ("| 시나리오 | GT 페이지 | 기존 page-recall | 기존 purity | 신규 page-recall | 신규 purity "
        "| 신규 seed 전환 | link P | link R | IDF1 | ID 전환 | 조각 | 분기·합류 후보 |"),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        o, n, g = r["old"], r["new"], r["global"]
        lines.append(
            f"| {r['name']} | {r['truth_pages']} | {o['page_recall']:.2f} | {o['purity']:.2f} "
            f"| {n['page_recall']:.2f} | {n['purity']:.2f} | {n['switches']} "
            f"| {g['link_precision']:.2f} | {g['link_recall']:.2f} | {g['idf1']:.2f} "
            f"| {g['id_switches']} | {g['fragments']} | {g['split_merge_candidates']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(markdown(run_benchmark()))

