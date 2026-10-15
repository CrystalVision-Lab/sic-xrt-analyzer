"""One-page TIFF is analyzable; page-axis stacks and derived stack copies are not."""

import hashlib

import numpy as np
import tifffile
from test_analysis_pipeline import spin
from test_context_panel import choose
from test_ui_analysis_contract import invoke

pytest_plugins = ("test_toolbar",)


def test_single_rgb_tiff_analysis_and_roi_preserve_original(workbench, tmp_path):
    w = workbench
    from test_result_explorer import ManyCandidates

    from sic_xrt_analyzer.analysis.contracts import (
        AdapterOutput,
        CoordinateSpace,
        Detection,
        Geometry,
        GeometryKind,
    )

    class BoundedAdapter(ManyCandidates):
        def analyze_source(self, request, token):
            return AdapterOutput(
                (
                    Detection(
                        "test-point",
                        0,
                        "BPD",
                        0.8,
                        Geometry(
                            GeometryKind.POINT,
                            ((request.roi.x + 8, request.roi.y + 12),),
                            coordinate_space=CoordinateSpace.ORIGINAL,
                        ),
                    ),
                ),
                {},
                {},
            )

    w.bridge.pipeline.adapter = BoundedAdapter()
    raw = np.full((320, 320, 3), 128, np.uint8)
    path = tmp_path / "actual-signature.jpg"
    tifffile.imwrite(path, raw, photometric="rgb")
    before = hashlib.sha256(path.read_bytes()).digest()
    w.open(path)
    assert w.state.property("tiffMode")
    assert w.state.property("analysisEligible")
    assert w.item("imagePrepareAnalysis").property("visible")
    choose(w, "analysis")
    assert w.state.property("canAnalyze")
    assert w.bridge.requestAnalysis("ROI", 40, 50, 128, 128, {})
    spin(w.app, lambda: w.bridge.pipeline.state.value not in ("RUNNING",), 30)
    assert w.bridge.pipeline.state.value == "COMPLETED"
    assert w.bridge.pipeline.result is not None
    assert w.bridge.pipeline.result.roi.x == 40
    np.testing.assert_array_equal(
        w.bridge.original_source.read_region(40, 50, 128, 128), raw[50:178, 40:168]
    )
    assert hashlib.sha256(path.read_bytes()).digest() == before
    spin(w.app, lambda: not w.bridge.projects.busy, 30)
    assert len(w.bridge.projects.project.analysis_runs) == 1
    saved = tmp_path / "two-dimensional-project.json"
    w.bridge.projects.save(str(saved), "2D TIFF result")
    spin(w.app, lambda: not w.bridge.projects.busy, 30)
    assert not w.bridge.projects.error, w.bridge.projects.error
    from sic_xrt_analyzer.results import ProjectStore

    p = ProjectStore().load(saved)
    assert p.image_sources[0].page_count == 1 and p.image_sources[0].content_hash
    w.bridge.projects.selectRun(p.analysis_runs[0].run_id)
    spin(w.app, lambda: not w.bridge.projects.busy, 30)
    assert not w.bridge.projects.error


def test_stack_rejects_analysis_even_if_model_compatible(workbench, tmp_path):
    w = workbench
    path = tmp_path / "stack.jpg"
    tifffile.imwrite(path, np.full((3, 64, 64, 3), 128, np.uint8), photometric="rgb")
    w.open(path)
    assert w.state.property("pageCount") == 3
    assert not w.state.property("analysisEligible")
    assert not w.item("imagePrepareAnalysis").property("visible")
    assert not invoke(w.window, "requestContext", "analysis", "MANUAL")
    assert not w.bridge.requestAnalysis("FULL_IMAGE", 0, 0, 0, 0, {})
    assert w.bridge.pipeline.result is None
