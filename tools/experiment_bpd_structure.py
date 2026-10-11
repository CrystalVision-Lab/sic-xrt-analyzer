"""Explicit local research experiment; no ground truth, model inference or default UI changes.

Run python tools/experiment_bpd_structure.py --help for the reproducible route.
Outputs contain private image crops; use ignored artifacts/, never commit them.
"""

import argparse
import hashlib
import json
import os
import threading
from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import perf_counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import psutil
import tifffile
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.analysis.bpd_samples import SYNTHETIC_CASES, synthetic_sample
from sic_xrt_analyzer.analysis.bpd_structure import StructureSettings, detect_structures
from sic_xrt_analyzer.analysis.contracts import Region
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.bpd_experiment import (
    attach_experiment,
    comparison_image,
    load_experiment_bundle,
    save_experiment_bundle,
)
from sic_xrt_analyzer.results.serialization import dumps, plain


class MemorySample:
    """10 ms process RSS sampling, includes native arrays; transient peaks may be missed."""

    def __enter__(self):
        self.process = psutil.Process()
        self.before = self.peak = self.process.memory_info().rss
        self.stop = threading.Event()

        def sample():
            while not self.stop.wait(0.01):
                self.peak = max(self.peak, self.process.memory_info().rss)

        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.peak = max(self.peak, self.process.memory_info().rss)
        self.stop.set()
        self.thread.join()
        self.after = self.process.memory_info().rss


def pilot_settings():
    # Explicit starting experiment profile, not validated XRT operating thresholds.
    return StructureSettings(
        "sato", "both", (1, 2), 0.10, 0.25, 0.005, 8, 12, 20, 12, 3, 4
    )


def _hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--image", type=Path)
    inputs.add_argument("--synthetic", action="store_true")
    parser.add_argument(
        "--page",
        type=int,
        default=0,
        help="Zero based TIFF page; frames are not assumed spatial Z",
    )
    parser.add_argument(
        "--roi",
        type=int,
        nargs=4,
        action="append",
        help="Original x y width height; repeat for ROI sizes",
    )
    parser.add_argument("--project", type=Path)
    grouping = parser.add_mutually_exclusive_group()
    grouping.add_argument("--run-id")
    grouping.add_argument("--grouping-scope", choices=("FULL_IMAGE", "ROI"))
    config = parser.add_mutually_exclusive_group(required=True)
    config.add_argument("--settings", type=Path, help="Explicit StructureSettings JSON")
    config.add_argument("--preset", choices=("pilot-v1",))
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=("local_contrast", "sato", "frangi"),
        default=["local_contrast", "sato", "frangi"],
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New local directory, ideally artifacts/",
    )
    parser.add_argument(
        "--verify-original-sha",
        action="store_true",
        help="Explicit full-file streaming SHA, not automatic TIFF per-open hashing",
    )
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("repeats must be 1..5")
    if args.image and not args.roi:
        parser.error(
            "real source requires explicit ROI; no full image or stack traversal"
        )
    if args.synthetic and (
        args.project or args.roi or args.run_id or args.grouping_scope
    ):
        parser.error("synthetic mode has no real project/grouping/ROI")
    args.output.mkdir(parents=True, exist_ok=False)
    # Keep the Qt object alive for authoritative original JPEG decoding.
    app = QGuiApplication.instance() or QGuiApplication([])
    base = (
        StructureSettings(**json.loads(args.settings.read_text(encoding="utf-8")))
        if args.settings
        else pilot_settings()
    )
    project = (
        ProjectStore().load(args.project)
        if args.project
        else AnalysisProject("Experimental BPD structures; no ground truth")
    )
    frozen_before = dumps(project)
    project_bytes_before = args.project.read_bytes() if args.project else None
    original_before = (
        _hash(args.image) if args.image and args.verify_original_sha else None
    )
    baseline_counts = Counter(o.assigned_class for o in project.observations)
    cases = []
    if args.synthetic:
        for name in SYNTHETIC_CASES:
            path = args.output / "synthetic-inputs" / (name + ".tif")
            path.parent.mkdir(exist_ok=True)
            tifffile.imwrite(path, synthetic_sample(name), photometric="minisblack")
            cases.append((name, OriginalImageSource(path), Region(0, 0, 160, 160)))
    else:
        source = (
            JpegImageSource(args.image)
            if args.image.suffix.lower() in (".jpg", ".jpeg")
            else OriginalImageSource(args.image, args.page)
        )
        if source.page_index != args.page:
            parser.error("JPEG has only page0")
        cases = [
            ("roi-" + str(i), source, Region(*roi)) for i, roi in enumerate(args.roi, 1)
        ]
    run_id = args.run_id
    if args.grouping_scope:
        source = cases[0][1]
        options = [
            r
            for r in project.analysis_runs
            if r.scope.value == args.grouping_scope
            and r.page_index == source.page_index
            and r.source_identity["canonical_path"] == source.identity.canonical_path
            and r.source_identity["file_size"] == source.identity.file_size
            and r.source_identity["mtime_ns"] == source.identity.mtime_ns
        ]
        if len(options) != 1:
            parser.error(
                "Choose explicit run-id; grouping scope does not identify one exact source/page run"
            )
        run_id = options[0].run_id
    report = {
        "status": "PARTIAL",
        "technical_status": "PENDING",
        "quality_status": "PRELIMINARY_NO_GROUND_TRUTH",
        "ground_truth_available": False,
        "precision": None,
        "recall": None,
        "f1": None,
        "iou": None,
        "settings_profile": "pilot-v1" if args.preset else str(args.settings),
        "baseline_counts": dict(baseline_counts),
        "original_sha_before": original_before,
        "rss_sampling_ms": 10,
        "rows": [],
        "notes": [
            "Single source page, no ONNX or stack-wide traversal",
            "Mask/skeleton components are unreviewed image-supported proposals; no physical BPD identity claim",
            "Timings include original ROI reading; OS file cache/Qt decoder/library warmup affect repetitions",
        ],
    }
    for name, source, roi in cases:
        for method in args.methods:
            for repeat in range(args.repeats):
                settings = replace(base, method=method)
                try:
                    with MemorySample() as memory:
                        experiment = detect_structures(source, roi, settings)
                        started = perf_counter()
                        attached = attach_experiment(project, experiment, run_id=run_id)
                        adapter_s = perf_counter() - started
                    assert attached.project.observations == project.observations
                    assert attached.project.predictions == project.predictions
                    assert attached.project.analysis_runs == project.analysis_runs
                    assert attached.project.review_events == project.review_events
                    assert dumps(project) == frozen_before
                    target = args.output / (name + "-" + method + "-" + str(repeat + 1))
                    save_experiment_bundle(
                        target,
                        attached,
                        comparison_image(experiment, project, attached),
                    )
                    loaded, manifest = load_experiment_bundle(target)
                    assert loaded == attached.project
                    metrics = {
                        **manifest["metrics"],
                        "adapter_wall_s": adapter_s,
                        "rss_before_bytes": memory.before,
                        "peak_rss_bytes": memory.peak,
                        "rss_after_bytes": memory.after,
                    }
                    instances = loaded.defect_instances[len(project.defect_instances) :]
                    primary = {g.geometry_id: g for g in loaded.geometries}
                    flags = [flag for p in experiment.proposals for flag in p.flags]
                    row = {
                        "case": name,
                        "method": method,
                        "repeat": repeat + 1,
                        "roi": plain(roi),
                        "status": "PASS",
                        "structure_count": len(instances),
                        "linear_count": sum(
                            primary[i.geometry_id].kind.value == "POLYLINE"
                            for i in instances
                        ),
                        "graph_count": sum(
                            primary[i.geometry_id].kind.value == "BRANCHED_GRAPH"
                            for i in instances
                        ),
                        "roi_boundary_count": flags.count("TRUNCATED_AT_ROI_BOUNDARY"),
                        "image_boundary_count": flags.count(
                            "TRUNCATED_AT_IMAGE_BOUNDARY"
                        ),
                        "ambiguous_count": sum(
                            i.instance_status == "AMBIGUOUS" for i in instances
                        ),
                        "link_count": sum(
                            len(i.linked_observations) for i in instances
                        ),
                        "proposed_without_observation_count": sum(
                            not i.linked_observations for i in instances
                        ),
                        "flags": dict(Counter(flags)),
                        "metrics": metrics,
                        "bundle": target.name,
                    }
                except (ValueError, OSError) as error:
                    row = {
                        "case": name,
                        "method": method,
                        "repeat": repeat + 1,
                        "roi": plain(roi),
                        "status": "ERROR",
                        "error": str(error),
                    }
                report["rows"].append(row)
                print(
                    json.dumps(
                        {k: v for k, v in row.items() if k != "metrics"},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    after = _hash(args.image) if original_before else None
    if original_before:
        assert original_before == after
    report["original_sha_after"] = after
    report["existing_project_bytes_preserved"] = (
        not args.project or args.project.read_bytes() == project_bytes_before
    )
    if args.project:
        assert ProjectStore().load(args.project) == project
    report["technical_status"] = (
        "PASS" if all(r["status"] == "PASS" for r in report["rows"]) else "PARTIAL"
    )
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(
        "Technical "
        + report["technical_status"]
        + "; real BPD quality PRELIMINARY, Ground Truth metrics N/A",
        flush=True,
    )
    _ = app
    if report["technical_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
