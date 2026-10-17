"""Issue #182: locked cache cleanup, hyperstack ROI positions, all-NaN pages, deferred captures."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from roifile import ROI_TYPE, ImagejRoi
from test_analysis_pipeline import spin
from test_project_save_guard import make_bridge

from sic_xrt_analyzer.imaging import prepared_image
from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.imagej_roi import decode_roi
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.imaging.tiff_stack import TiffStack
from sic_xrt_analyzer.results import AnalysisProject
from sic_xrt_analyzer.ui import project_controller
from sic_xrt_analyzer.ui.stack_controller import StackController


def _jpeg(path):
    from PIL import Image
    Image.fromarray(np.full((48, 64, 3), 90, np.uint8)).save(path, quality=95)
    return path


def test_locked_prepared_cache_close_is_best_effort_and_deferred(tmp_path, monkeypatch):
    source = JpegImageSource(_jpeg(tmp_path / "image.jpg"))
    cache = prepared_image.PreparedPixels()
    assert cache.jpeg(source, lambda: False, lambda *args: None)
    directory = Path(cache.directory.name)

    def locked():
        # Simulates the ImageJ worker still mapping decoded.rgb (WinError 32).
        raise PermissionError(32, "The process cannot access the file")
    monkeypatch.setattr(cache.directory, "cleanup", locked)
    real_remove = prepared_image._remove_tree
    monkeypatch.setattr(prepared_image, "_remove_tree", lambda path: False)
    cache.close()
    assert cache.pixels is None and cache.directory is None
    assert str(directory) in prepared_image._deferred_paths
    assert prepared_image.retry_deferred_cleanup() >= 1

    monkeypatch.setattr(prepared_image, "_remove_tree", real_remove)
    prepared_image.retry_deferred_cleanup()
    assert str(directory) not in prepared_image._deferred_paths and not directory.exists()
    cache.close()  # idempotent


def test_close_prepared_frame_releases_every_cache_even_when_one_fails():
    closed = []

    class Owner:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        def close(self):
            closed.append(self.name)
            if self.fail:
                raise PermissionError(1224, "mapped section open")

    source = SimpleNamespace(display_group=Owner("group", fail=True), display_pyramid=Owner("pyramid"),
                             prepared=Owner("prepared", fail=True))
    StackController._close_prepared_frame(SimpleNamespace(frame=SimpleNamespace(source=source)))
    assert closed == ["group", "pyramid", "prepared"]


@pytest.fixture
def zstack_meta(tmp_path):
    path = tmp_path / "zstack.tif"
    tifffile.imwrite(path, np.zeros((5, 200, 200), np.uint16), imagej=True, metadata={"axes": "ZYX"})
    return OriginalImageSource(path).metadata


def hyperstack_roi(c, z, t):
    roi = ImagejRoi.frompoints([[40, 50], [100, 120], [160, 80]])
    roi.roitype = ROI_TYPE.POINT
    roi.position = 0
    roi.c_position, roi.z_position, roi.t_position = c, z, t
    return ImagejRoi.frombytes(roi.tobytes()).tobytes()


@pytest.mark.parametrize("frames", [0, 1])
def test_hyperstack_roi_on_z_stack_maps_to_slice(zstack_meta, frames):
    assert zstack_meta.page_count == 5
    record = decode_roi(hyperstack_roi(1, 3, 1), "z.roi", zstack_meta, frames=frames, slices=5)
    assert record.page_index == 2


def test_hyperstack_roi_on_time_series_and_size_one_axes(zstack_meta):
    record = decode_roi(hyperstack_roi(1, 1, 4), "t.roi", zstack_meta, frames=5, slices=1)
    assert record.page_index == 3
    record = decode_roi(hyperstack_roi(1, 1, 1), "first.roi", zstack_meta, frames=0, slices=0)
    assert record.page_index == 0


@pytest.mark.parametrize("c,z,t,frames,slices", [(1, 2, 3, 3, 5), (2, 3, 1, 0, 5), (1, 2, 2, 0, 0)])
def test_ambiguous_multi_axis_roi_positions_rejected(zstack_meta, c, z, t, frames, slices):
    with pytest.raises(ValueError, match="C/Z/T|구성"):
        decode_roi(hyperstack_roi(c, z, t), "bad.roi", zstack_meta, frames=frames, slices=slices)


def test_all_nan_float_page_with_imagej_display_range(tmp_path):
    path = tmp_path / "nan.tif"
    pixels = np.full((2, 32, 48), np.nan, np.float32)
    pixels[1, 4:8, 4:8] = 5
    tifffile.imwrite(path, pixels, imagej=True, metadata={"axes": "TYX", "min": 0.0, "max": 10.0})
    stack = TiffStack(path)
    try:
        frame = stack.frame(0)
        assert (frame.low, frame.high) == (0.0, 10.0)
        assert np.isfinite([frame.range_min, frame.range_max]).all() and frame.range_max > frame.range_min
        assert np.isnan(frame.pixels).all()
    finally:
        stack.close()


def test_deferred_captures_drain_after_error_and_keep_error_visible(qt_app, tmp_path, bridge_factory, monkeypatch):
    bridge = make_bridge(bridge_factory, tmp_path)
    c = bridge.project_controller
    c.project = AnalysisProject("Study")
    captured = []

    def fake_capture(snapshot, result, manifest):
        captured.append(result)
        return AnalysisProject(f"after-{result}")
    monkeypatch.setattr(project_controller, "capture_live", fake_capture)
    finished = []
    c.operationFinished.connect(lambda job, ok: finished.append((job, ok)))

    c.busy, c.job, c.callback = True, "capture", lambda value: None
    c.deferred = [("r1", None), ("r2", None)]
    c._ready(None, "캡처 실패")
    assert finished == [("capture", False)] and c.error == "캡처 실패"
    spin(qt_app, lambda: not c.busy and not c.deferred)
    spin(qt_app, lambda: not c.busy)
    assert captured == ["r1", "r2"] and c.project.project_name == "after-r2"
    assert c.error == "캡처 실패"
    assert finished[1:] == [("capture", True), ("capture", True)]
