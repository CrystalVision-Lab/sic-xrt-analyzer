"""TD07 read-only real Desktop regression: saved JPG exports and four TIFF stacks."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import numpy as np
import tifffile
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from test_analysis_pipeline import spin
from validate_central_sync import worker
from validate_review_workspace import ReviewSession, digest, exports, science, wait

from sic_xrt_analyzer.results import ProjectStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    QQuickStyle.setStyle("Basic")
    p = ProjectStore().load(a.project)
    files = [Path(s.source_reference) for s in p.image_sources] + [
        a.project,
        Path("artifacts/models/research/model.onnx"),
        Path("artifacts/models/research/manifest.json"),
    ]
    before = {str(f): worker(app, lambda f=f: digest(f)) for f in files}
    frozen = science(p)
    report = {"status": "FAIL", "new_inference": 0, "saved_runs": [], "tiff": []}
    s = ReviewSession(app, out)

    def forbidden(*args, **kwargs):
        report["new_inference"] += 1
        raise AssertionError("No new inference allowed in dataset regression")

    s.bridge.pipeline.start = forbidden
    try:
        c = s.bridge.projects
        c.open(str(a.project.resolve()))
        wait(s)
        for run in p.analysis_runs:
            c.selectRun(run.run_id)
            wait(s)
            spin(
                app,
                lambda: (
                    s.bridge.research.saved is not None
                    and not s.bridge.stack_viewer.initial_loading
                ),
                240,
            )
            observations = [o for o in p.observations if o.run_id == run.run_id]
            counts = dict(Counter(o.assigned_class for o in observations))
            expected = (
                {"BPD": 245, "TED": 1398, "TSD": 1303}
                if run.scope.value == "FULL_IMAGE"
                else {"BPD": 3, "TED": 779, "TSD": 9}
            )
            assert counts == expected, (run.scope.value, counts)
            first = exports(s, out / (run.run_id + "-export-a"))
            second = exports(s, out / (run.run_id + "-export-b"))
            assert first == second
            report["saved_runs"].append(
                {
                    "scope": run.scope.value,
                    "candidates": len(observations),
                    "class_counts": counts,
                    "repeat_export_equal": True,
                }
            )
        for source in p.image_sources:
            if Path(source.source_reference).suffix.lower() not in (".tif", ".tiff"):
                continue
            print("TIFF read-only regression " + source.display_name, flush=True)
            c.selectSource(source.source_id, "")
            wait(s)
            stack = s.bridge.stack_viewer
            spin(
                app,
                lambda stack=stack, source=source: (
                    stack.frame is not None
                    and Path(stack.frame.source.path).resolve()
                    == Path(source.source_reference).resolve()
                    and not stack.initial_loading
                ),
                240,
            )
            pages = [0, source.page_count // 2, source.page_count - 1]
            for page in pages:
                assert stack.page(page)
                spin(
                    app,
                    lambda stack=stack, source=source, page=page: (
                        stack.frame is not None
                        and Path(stack.frame.source.path).resolve()
                        == Path(source.source_reference).resolve()
                        and stack.frame.source.page_index == page
                        and not stack.busy
                        and not stack.initial_loading
                    ),
                    120,
                )
                frame = stack.frame
                raw = worker(
                    app, lambda frame=frame: frame.source.read_region(0, 0, 8, 8)
                )

                def original(source=source, page=page):
                    with tifffile.TiffFile(source.source_reference) as t:
                        return t.pages[page].asarray()[:8, :8].copy()

                expected = worker(app, original)
                assert (
                    raw.dtype.kind == "u"
                    and raw.dtype.itemsize == 2
                    and np.array_equal(raw, expected)
                )
                assert (
                    s.bridge.research.saved is None
                    and not s.bridge.reviews.state["ready"]
                )
            report["tiff"].append(
                {
                    "name": source.display_name,
                    "pages_1_based": [n + 1 for n in pages],
                    "uint16_equal": True,
                    "analysis_disabled": True,
                }
            )
        assert report["new_inference"] == 0 and not s.warnings
        assert science(ProjectStore().load(a.project)) == frozen
        after = {str(f): worker(app, lambda f=f: digest(f)) for f in files}
        assert before == after
        report.update(
            status="PASS",
            original_model_project_sha_preserved=True,
            qml_warnings=s.warnings,
        )
        print("Real JPG/TIFF/source/model/project regression PASS", flush=True)
    finally:
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        s.close()


if __name__ == "__main__":
    main()
