"""Read-only actual RGB/model regression for the additional project contract.

Writes only explicit validation outputs and temporary decode caches. Review events
created here are synthetic test events, never researcher labels or ground truth.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

from sic_xrt_analyzer.analysis.contracts import (
    AnalysisRequest,
    AnalysisScope,
    AnalysisState,
    Region,
    utc_now,
)
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.prepared_image import PreparedPixels
from sic_xrt_analyzer.results import (
    AnalysisProject,
    ProjectStore,
    ReviewRepository,
    import_legacy_result,
)
from sic_xrt_analyzer.results.contracts import ReviewEvent, ReviewStatus, ReviewTarget
from sic_xrt_analyzer.results.reviews import prediction_snapshot
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.results.validation import new_id
from sic_xrt_analyzer.ui.bridge import FileBridge


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roi", type=int, nargs=4)
    parser.add_argument("--expect-baseline", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    model = args.model.resolve()
    # Explicit validation request: streaming hashes, never an implicit per-open TIFF operation.
    originals = (args.image, model / "manifest.json", model / "model.onnx")
    before = {path.name: file_hash(path) for path in originals}
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = FileBridge(
        settings=QSettings(str(args.output / "isolated.ini"), QSettings.IniFormat)
    )
    cache = PreparedPixels()

    def wait(check):
        until = time.monotonic() + 300
        while not check() and time.monotonic() < until:
            app.processEvents()
            time.sleep(0.002)
        if not check():
            raise RuntimeError("Validation operation timed out")

    report = {"synthetic_review_only": True, "results": []}
    try:
        bridge.research.loadModel(str(model))
        wait(lambda: not bridge.research.loading)
        if not bridge.pipeline.adapter or not bridge.pipeline.adapter.available:
            raise ValueError(bridge.research.error)
        source = JpegImageSource(args.image)
        if not cache.jpeg(source, lambda: False, lambda *_: None):
            raise ValueError("Native read-only JPEG cache not prepared")
        object.__setattr__(source, "prepared", cache)
        bridge.pipeline.set_source(source)
        project = AnalysisProject(
            "XRT-RESULT-TD-01 validation; not adjudicated research labels"
        )
        store = ProjectStore()
        target = args.output / "project.json"
        saved_revision = None
        regions = [None] + ([Region(*args.roi)] if args.roi else [])
        for region in regions:
            request = AnalysisRequest(
                source,
                AnalysisScope.ROI if region else AnalysisScope.FULL_IMAGE,
                bridge.pipeline.adapter.model_id,
                bridge.pipeline.adapter.model_version,
                roi=region,
                parameters={"point_mode": "contrast_proposals"},
            )
            assert bridge.pipeline.start(request)
            wait(lambda: bridge.pipeline.state != AnalysisState.RUNNING)
            result = bridge.pipeline.result
            if result is None or result.status != AnalysisState.COMPLETED:
                raise ValueError(str(bridge.pipeline.error))
            assert bridge.research.exportResult(str(args.output / "exports"))
            export = Path(bridge.research.export_path)
            export_before = {
                name: (export / name).read_bytes()
                for name in ("result.json", "predictions.csv")
            }
            project = import_legacy_result(
                project,
                result,
                model_manifest=bridge.pipeline.adapter.classifier.manifest,
            )
            observations = [
                o
                for o in project.observations
                if o.run_id == project.analysis_runs[-1].run_id
            ]
            for detection, observation in zip(
                result.detections, observations, strict=True
            ):
                assert detection.id == observation.source_candidate_id
                assert detection.geometry.points[0] == (observation.x, observation.y)
                assert (
                    detection.class_id == observation.source_class_id
                    and detection.class_name == observation.assigned_class
                )
                assert (
                    tuple(detection.metadata.get("scores", ()))
                    == observation.raw_scores
                )
                assert detection.metadata == observation.metadata
            store.save(target, project, expected_revision=saved_revision)
            saved_revision = project.revision
            assert store.load(target) == project
            assert bridge.research.exportResult(str(args.output / "exports"))
            export = Path(bridge.research.export_path)
            assert {
                name: (export / name).read_bytes() for name in export_before
            } == export_before
            row = {
                "scope": result.scope.value,
                "count": len(observations),
                "counts": dict(Counter(o.assigned_class for o in observations)),
                "ids_coordinates_scores_metadata_preserved": True,
                "legacy_export_bytes_equal": True,
                "run_id": project.analysis_runs[-1].run_id,
            }
            report["results"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        # Test a review on the persisted copy only; does not affect the running UI/model result.
        observation = project.observations[0]
        snapshot, run = prediction_snapshot(
            project, ReviewTarget.OBSERVATION, observation.observation_id
        )
        event = ReviewEvent(
            new_id(),
            ReviewTarget.OBSERVATION,
            observation.observation_id,
            "synthetic-validation-test",
            ReviewStatus.UNCERTAIN,
            snapshot,
            utc_now(),
            1,
            source_run_id=run,
            comment="Synthetic storage validation only; not researcher review or ground truth",
        )
        project = ReviewRepository().append(project, event)
        verified = verify_content_hash(project.image_sources[0])
        project = project.evolve(image_sources=(verified,))
        store.save(target, project, expected_revision=saved_revision)
        assert store.load(target) == project and not project.defect_instances
        assert (
            not ReviewRepository()
            .current(project, event.target_type, event.target_id)
            .assessment.ground_truth_eligible
        )
        source_snapshot = project.analysis_runs[0].source_identity
        assert source_snapshot["canonical_path"] == source.identity.canonical_path
        assert source_snapshot["file_size"] == source.identity.file_size
        assert source_snapshot["mtime_ns"] == source.identity.mtime_ns
        after = {path.name: file_hash(path) for path in originals}
        assert before == after
        if args.expect_baseline:
            assert report["results"][0]["count"] == 2946
            assert report["results"][0]["counts"] == {
                "BPD": 245,
                "TED": 1398,
                "TSD": 1303,
            }
            assert (
                args.roi == [1003, 1011, 1495, 1495]
                and report["results"][1]["count"] == 791
            )
        report.update(
            status="PASS",
            original_hashes=after,
            model_version=bridge.pipeline.adapter.model_version,
            project_roundtrip=True,
            prediction_review_separated=True,
            original_sources_preserved=True,
            schema_version=project.schema_version,
            run_count=len(project.analysis_runs),
            candidate_count=len(project.observations),
            defect_count=len(project.defect_instances),
        )
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            "PASS: actual result conversion, project roundtrip, synthetic review separation, legacy export bytes and original SHA256",
            flush=True,
        )
    finally:
        bridge.waitForLoads()
        cache.close()


if __name__ == "__main__":
    main()
