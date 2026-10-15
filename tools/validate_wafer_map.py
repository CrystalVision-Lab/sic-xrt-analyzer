"""Local synthetic scale tests or read-only actual-study map experiment. No physical truth created."""

import argparse
import copy
import hashlib
import json
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import psutil
from PIL import Image
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_result_domain import MANIFEST, legacy
from test_wafer_map import placement

from sic_xrt_analyzer.analysis.contracts import AnalysisScope, Region
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.adapter import import_legacy_result
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.workspace import add_source, publish_dependencies
from sic_xrt_analyzer.wafer_map import assets
from sic_xrt_analyzer.wafer_map.mapping import footprint, layout
from sic_xrt_analyzer.wafer_map.scene import Scene


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def bench(p, a, tiles, width=1400, height=800):
    active = copy.deepcopy(a)
    active["placements"] = active["placements"][:tiles]
    bounds = np.asarray(
        [
            xy
            for place in active["placements"]
            for xy in footprint(place["matrix"], *place["size"])
        ]
    )
    lo = bounds.min(0)
    hi = bounds.max(0)
    centre = ((lo + hi) / 2).tolist()
    zoom = float(min(width / (hi[0] - lo[0]), height / (hi[1] - lo[1])) * 0.8)
    scene = Scene()
    initial = time.perf_counter()
    f = scene.render(p, active, centre, zoom, width, height)
    initial_ms = (time.perf_counter() - initial) * 1000
    repeated = []
    for n in range(10):
        z = zoom * (1 + 0.02 * (n % 3))
        c = [centre[0] + n / z, centre[1] - n / z]
        start = time.perf_counter()
        f = scene.render(p, active, c, z, width, height)
        repeated.append((time.perf_counter() - start) * 1000)
    assert len(scene.previews) <= 20
    return {
        "tiles": tiles,
        "initial_ms": initial_ms,
        "pan_zoom_wall_ms": repeated,
        "preview_ms": scene.preview_ms,
        "preview_decodes": scene.decode_count,
        "cache_items": len(scene.previews),
        "cache_bytes": sum(v[1].sizeInBytes() for v in scene.previews.values()),
        "selected_run_ids": active["runs"],
        "summary": f["summary"],
        "review_summary": f["review_summary"],
        "display_paths": len(f["paths"]),
        "scientific_counts_unchanged_by_display": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QGuiApplication([])
    report = {
        "status": "FAIL",
        "physical_mapping": "PHYSICAL_WAFER_MAPPING_NOT_READY",
        "automatic_inference": 0,
        "automatic_sync": 0,
        "real_physical_coordinates_created": False,
        "benchmarks": [],
    }
    samples = []
    stop = threading.Event()
    process = psutil.Process()

    def sample():
        while not stop.wait(0.02):
            samples.append(process.memory_info().rss)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        with TemporaryDirectory(dir=args.output.resolve()) as tmp:
            folder = Path(tmp)
            if args.project:
                p = ProjectStore().load(args.project)
                originals = [Path(s.source_reference) for s in p.image_sources] + [
                    args.project,
                    Path("artifacts/models/research/model.onnx"),
                    Path("artifacts/models/research/manifest.json"),
                ]
                before = {str(f): sha(f) for f in originals}
                report["input"] = "actual_private_project"
            else:
                report["input"] = "synthetic_1_10_50_tiles"
                p = AnalysisProject("QA synthetic map")
                for n in range(50):
                    pixels = np.random.default_rng(116 + n).integers(
                        10, 240, (512, 640, 3), dtype=np.uint8
                    )
                    path = folder / (str(n) + ".jpg")
                    Image.fromarray(pixels).save(path, quality=90)
                    source = JpegImageSource(path)
                    if n == 0:
                        p = import_legacy_result(
                            p, legacy(source, count=2946), model_manifest=MANIFEST
                        )
                        roi_result = legacy(source, count=791)
                        roi_result = replace(
                            roi_result,
                            request=replace(
                                roi_result.request,
                                scope=AnalysisScope.ROI,
                                roi=Region(0, 0, 640, 512),
                            ),
                        )
                        p = import_legacy_result(p, roi_result, model_manifest=MANIFEST)
                    else:
                        p, _ = add_source(p, source)
                originals = [Path(s.source_reference) for s in p.image_sources]
                before = {str(f): sha(f) for f in originals}
            science = {
                name: getattr(p, name)
                for name in (
                    "analysis_runs",
                    "observations",
                    "predictions",
                    "geometries",
                    "defect_instances",
                    "review_events",
                    "model_provenance",
                    "image_relationships",
                )
            }
            sources = [
                verify_content_hash(s)
                if s.acquisition_metadata.get("format") == "JPEG"
                else s
                for s in p.image_sources
            ]
            p = p.evolve(image_sources=tuple(sources))
            a = assets.blank(p)
            a["revision"] = 1
            a["editor"] = "QA temporary-layout experiment"
            jpgs = [
                s for s in sources if s.acquisition_metadata.get("format") == "JPEG"
            ]
            for n, s in enumerate(jpgs):
                scale = 160 / max(s.width, s.height)
                a["placements"].append(
                    placement(
                        s,
                        layout(
                            (n % 8) * 190, (n // 8) * 150, 5 * (n % 3), scale, scale
                        ),
                    )
                )
                full = [
                    r
                    for r in p.analysis_runs
                    if r.source_id == s.source_id
                    and r.scope.value == "FULL_IMAGE"
                    and r.run_status.value == "COMPLETED"
                ]
                a["runs"][s.source_id] = full[-1].run_id if full else ""
            for count in (1, 10, 50) if not args.project else (len(jpgs),):
                result = bench(p, a, count)
                assert (
                    sum(result["summary"].get(k, 0) for k in ("BPD", "TED", "TSD"))
                    == 2946
                )
                report["benchmarks"].append(result)
            if args.project:
                from sic_xrt_analyzer.registration import assets as registration_assets

                rejected = []
                for rel in p.image_relationships:
                    if rel.transform_reference and rel.transform_reference.startswith(
                        registration_assets.PREFIX
                    ):
                        r = registration_assets.read(
                            args.project, rel.transform_reference, p
                        )
                        if r["status"] == "REJECTED":
                            rejected.append(r["registration_id"])
                report["td10_rejected_registrations_not_used"] = rejected
                report["temporary_positions_explicit_qa_not_physical"] = [
                    {"source_id": r["source_id"], "matrix": r["matrix"]}
                    for r in a["placements"]
                ]
            for source in jpgs:
                roi = next(
                    (
                        r
                        for r in reversed(p.analysis_runs)
                        if r.source_id == source.source_id
                        and r.scope.value == "ROI"
                        and r.run_status.value == "COMPLETED"
                    ),
                    None,
                )
                if roi:
                    b = copy.deepcopy(a)
                    b["runs"][source.source_id] = roi.run_id
                    report["roi_benchmark"] = bench(p, b, len(jpgs))
                    assert (
                        sum(
                            report["roi_benchmark"]["summary"].get(k, 0)
                            for k in ("BPD", "TED", "TSD")
                        )
                        == 791
                    )
                    break
            path = args.output / "project.json"
            if args.project:
                publish_dependencies(path, p, [], args.project)
            start = time.perf_counter()
            q = assets.append(p, a, path)
            ProjectStore().save(path, q)
            report["save_ms"] = (time.perf_counter() - start) * 1000
            reopened = []
            for _ in range(5):
                start = time.perf_counter()
                restored = ProjectStore().load(path)
                reopened.append((time.perf_counter() - start) * 1000)
            report["reopen_ms"] = reopened
            assert restored == q
            report["science_preserved"] = {
                name: getattr(restored, name) == value
                for name, value in science.items()
            }
            assert all(report["science_preserved"].values())
            assert all(sha(Path(f)) == digest for f, digest in before.items())
            report["original_model_project_sha_preserved"] = True
            report["tiff_placements"] = sum(
                s.acquisition_metadata.get("format") == "TIFF"
                and s.wafer_placement.alignment_reference is not None
                for s in restored.image_sources
            )
            assert report["tiff_placements"] == 0
            report["status"] = "PASS"
    finally:
        stop.set()
        thread.join()
        samples.append(process.memory_info().rss)
        report["peak_rss_mib"] = max(samples) / 1024**2
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "status": report["status"],
                "input": report["input"],
                "peak_rss_mib": report["peak_rss_mib"],
                "physical_mapping": report["physical_mapping"],
            }
        )
    )
    app.quit()


if __name__ == "__main__":
    main()
