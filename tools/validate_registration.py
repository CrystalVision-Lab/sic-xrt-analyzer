"""Explicit local actual-JPG experiment. No ground-truth accuracy or expert approval claimed."""

import argparse
import hashlib
import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import psutil
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.registration import assets
from sic_xrt_analyzer.registration.comparison import ComparisonSession
from sic_xrt_analyzer.registration.engine import estimate, fit_landmarks, refine
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.workspace import add_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("새 검증 폴더를 지정하세요")
    args.output.mkdir(parents=True)
    app = QGuiApplication([])
    process = psutil.Process()
    samples = []
    stop = threading.Event()

    def sample():
        while not stop.wait(0.02):
            samples.append(process.memory_info().rss)

    thread = threading.Thread(target=sample)
    thread.start()
    report = {
        "science_status": "REAL_REGISTRATION_PRELIMINARY",
        "same_wafer_same_area_confirmed": False,
        "expert_landmarks": False,
        "automatic_defect_changes": False,
        "algorithms": [],
        "viewer": [],
    }

    def digest(p):
        h = hashlib.sha256()
        with p.open("rb") as s:
            for b in iter(lambda: s.read(1024**2), b""):
                h.update(b)
        return h.hexdigest()

    originals = {str(p): digest(p) for p in (args.before, args.after)}
    p = AnalysisProject("TD114 actual JPG experimental comparison")
    p, a = add_source(p, JpegImageSource(args.before))
    p, b = add_source(p, JpegImageSource(args.after))
    session = None
    try:
        session = ComparisonSession(a, b)
        a, b = session.records
        p = p.evolve(image_sources=(a, b))
        p = assets.assign_roles(p, a.source_id, b.source_id)
        path = args.output / "project.json"
        ProjectStore().save(path, p)
        report["source"] = [
            {
                "id": s.source_id,
                "name": s.display_name,
                "size": [s.width, s.height],
                "sha256": s.content_hash.value,
                "role": s.role.value,
            }
            for s in p.image_sources
        ]
        report["prepare_ms"] = session.prepare_ms
        report["decode_count"] = session.decode_count
        sizes = [(s.width, s.height) for s in session.records]
        chosen = None
        for method in ("sift", "orb", "phase", "ecc"):
            ts = time.perf_counter()
            try:
                result = estimate(
                    *session.previews, *sizes, method=method, model="auto"
                )
                result = refine(result, *session.sources)
                asset = assets.make_asset(p, a, b, result)
                assets.publish(path, asset)
                new = assets.append(p, asset)
                ProjectStore().save(path, new, expected_revision=p.revision)
                p = new
                report["algorithms"].append(
                    {
                        "method": method,
                        **result,
                        "elapsed_ms": (time.perf_counter() - ts) * 1000,
                    }
                )
                if result["status"] == "NEEDS_REVIEW" and chosen is None:
                    chosen = asset
            except (ValueError, OSError, cv2.error) as exc:
                report["algorithms"].append(
                    {
                        "method": method,
                        "status": "FAILED",
                        "error": str(exc),
                        "elapsed_ms": (time.perf_counter() - ts) * 1000,
                    }
                )
                from sic_xrt_analyzer.registration.engine import VERSION

                failed = {
                    "algorithm": method,
                    "algorithm_version": VERSION,
                    "model": "similarity",
                    "matrix": None,
                    "landmarks": [],
                    "quality": {"reasons": [str(exc)]},
                    "timings": {"elapsed_ms": (time.perf_counter() - ts) * 1000},
                    "status": "REJECTED",
                }
                asset = assets.make_asset(p, a, b, failed)
                assets.publish(path, asset)
                new = assets.append(p, asset)
                ProjectStore().save(path, new, expected_revision=p.revision)
                p = new
        report["accepted_automatically"] = False
        if chosen:
            matrix = chosen["matrix"]
            # Algorithm-proposed correspondences exercise manual solver; never expert labels.
            rows = [r for r in chosen["landmarks"] if r["inlier"]]
            if len(rows) >= 3:
                manual = fit_landmarks(
                    [r["before"] for r in rows[:20]],
                    [r["after"] for r in rows[:20]],
                    *sizes,
                    chosen["model"],
                )
                report["manual_solver_proposal_only"] = manual
        else:
            matrix = None
        for zoom in (0.065, 1, 2, 4):
            elapsed = []
            cpu = []
            for iteration in range(5):
                centre = [b.width / 2 + iteration * 20, b.height / 2 - iteration * 12]
                t = time.perf_counter()
                c = process.cpu_times()
                frame = session.render(centre, zoom, 1000, 700, matrix)
                elapsed.append((time.perf_counter() - t) * 1000)
                cc = process.cpu_times()
                cpu.append((cc.user + cc.system - c.user - c.system) * 1000)
                if iteration == 0:
                    for key in ("before", "after", "difference"):
                        frame[key].save(str(args.output / f"{key}-{zoom}.png"))
            report["viewer"].append(
                {
                    "zoom": zoom,
                    "count": 5,
                    "viewport": [1000, 700],
                    "wall_ms": elapsed,
                    "cpu_process_ms": cpu,
                    "levels": frame["levels"],
                    "cache_hit_repeat": session.render(centre, zoom, 1000, 700, matrix)[
                        "cache_hit"
                    ],
                }
            )
        report["reopen"] = ProjectStore().load(path) == p
        report["original_hash_preserved"] = all(
            digest(Path(k)) == v for k, v in originals.items()
        )
        report["asset_count"] = len(p.image_relationships)
        report["source_crop_checks"] = []
        report["engine_peak_rss_mib"] = max(samples) / 1024**2
        report["oracle_memory_in_total_peak"] = True
        # Native pixel oracle: exact cache sample is compared with existing JPEG original Reader.
        for source in session.sources:
            x, y = source.metadata.width // 2, source.metadata.height // 2
            from PIL import Image

            with Image.open(source.path) as image:
                pixel = np.array(image.crop((x, y, x + 32, y + 32)))
            cached = source.read_region(x, y, 32, 32)
            report["source_crop_checks"].append(
                {
                    "name": Path(source.path).name,
                    "pixel_equal_pillow": bool(np.array_equal(pixel, cached)),
                }
            )
        report["engineering_experiment"] = (
            "PASS"
            if report["reopen"]
            and report["original_hash_preserved"]
            and all(r["pixel_equal_pillow"] for r in report["source_crop_checks"])
            else "FAIL"
        )
    finally:
        if session:
            session.close()
        stop.set()
        thread.join()
        report["peak_rss_mib"] = (
            max(samples, default=process.memory_info().rss) / 1024**2
        )
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        del app
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "engineering_experiment",
                    "science_status",
                    "prepare_ms",
                    "peak_rss_mib",
                    "original_hash_preserved",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
