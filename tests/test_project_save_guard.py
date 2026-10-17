"""Issue #175: saves own the project file; inputs fail loudly instead of silently."""
from threading import Event

import numpy as np
import tifffile
from PySide6.QtCore import QSettings
from test_analysis_pipeline import spin
from test_desktop_research import Classifier, create_jpeg_source

from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore


def make_bridge(bridge_factory, tmp_path):
    return bridge_factory(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))


def saved_project(qt_app, bridge, tmp_path):
    c = bridge.project_controller
    c.project = AnalysisProject("Study")
    path = tmp_path / "study.json"
    c.save(str(path), "")
    spin(qt_app, lambda: not c.busy)
    assert not c.error, c.error
    return c, path


def test_foreign_save_blocks_edits_and_defers_analysis(qt_app, tmp_path, bridge_factory):
    bridge = make_bridge(bridge_factory, tmp_path)
    c, _path = saved_project(qt_app, bridge, tmp_path)
    before = c.project
    bridge.wafer_map_controller.job = "save"

    c.rename("Changed", "")
    assert c.project is before and "Wafer Map 배치 저장" in c.error
    c.save("", "")
    assert c.project is before and not c.busy

    c._capture(object(), None)
    assert len(c.deferred) == 1 and not c.busy
    assert not bridge.review_controller.commit(False)
    assert "작성 중인 검수는 유지됩니다" in bridge.review_controller.error

    bridge.wafer_map_controller.job = ""
    c.error = ""
    c.rename("Changed", "")
    assert c.project.project_name == "Changed" and c.dirty


def test_project_save_waits_for_registration(qt_app, tmp_path, bridge_factory):
    bridge = make_bridge(bridge_factory, tmp_path)
    c, path = saved_project(qt_app, bridge, tmp_path)
    c.rename("Changed", "")
    before = path.read_bytes()
    bridge.registration_controller.busy = True
    c.save("", "")
    assert "정합 작업" in c.error and not c.busy and c.dirty
    assert path.read_bytes() == before


def test_save_publish_keeps_newer_in_memory_project(qt_app, tmp_path, bridge_factory, monkeypatch):
    bridge = make_bridge(bridge_factory, tmp_path)
    c, path = saved_project(qt_app, bridge, tmp_path)
    c.rename("Saved", "")
    release, entered = Event(), Event()
    real_save = ProjectStore.save

    def slow_save(self, *args, **kwargs):
        entered.set()
        release.wait(10)
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(ProjectStore, "save", slow_save)
    c.save("", "")
    assert entered.wait(10)
    newer = c.project.evolve(project_name="Newer")
    c.project = newer  # A change that reached memory while the write was in flight.
    release.set()
    spin(qt_app, lambda: not c.busy)

    assert c.project is newer and c.dirty and c.error
    assert c.saved_snapshot.project_name == "Saved"
    assert ProjectStore().load(path).project_name == "Saved"


def test_wafer_save_result_for_replaced_project_still_refreshes(qt_app, tmp_path, bridge_factory):
    bridge = make_bridge(bridge_factory, tmp_path)
    wafer = bridge.wafer_map_controller
    emitted = []
    wafer.changed.connect(lambda: emitted.append(True))
    wafer.callback = (object(), lambda value: None)
    wafer.busy, wafer.job = True, "save"

    wafer._ready(None, "")

    assert emitted and not wafer.busy and wafer.job == ""
    assert "다시 여세요" in wafer.error


def test_stack3d_save_result_for_replaced_project_still_refreshes(qt_app, tmp_path, bridge_factory):
    bridge = make_bridge(bridge_factory, tmp_path)
    stack = bridge.stack3d_controller
    emitted = []
    stack.changed.connect(lambda: emitted.append(True))
    stack.callback = (object(), lambda value: None)
    stack.busy, stack.job = True, "save"

    stack._ready(None, "")

    assert emitted and not stack.busy and stack.job == ""
    assert "다시 여세요" in stack.error


def test_compressed_page_is_decoded_once_per_source(tmp_path, monkeypatch):
    path = tmp_path / "compressed.tif"
    image = np.arange(256 * 256 * 3, dtype=np.uint32).reshape(256, 256, 3).astype(np.uint8)
    tifffile.imwrite(path, image, photometric="rgb", compression="zlib")
    source = OriginalImageSource(path)
    calls = []
    real = tifffile.TiffPage.asarray

    def counting(self, *args, **kwargs):
        calls.append(True)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(tifffile.TiffPage, "asarray", counting)
    for x, y in ((0, 0), (64, 32), (128, 128), (200, 10)):
        region = source.read_region(x, y, 32, 32)
        assert np.array_equal(region, image[y:y + 32, x:x + 32])
        region[:] = 0  # Callers own their copy; the cached page stays intact.
    assert len(calls) == 1
    assert np.array_equal(source.read_full(), image)


def test_coordinate_csv_short_row_reports_line(qt_app, tmp_path, bridge_factory):
    bridge = make_bridge(bridge_factory, tmp_path)
    bridge.pipeline.adapter = DesktopResearchAdapter(None, Classifier())
    bridge.pipeline.set_source(create_jpeg_source(tmp_path))
    research = bridge.research_controller
    good = tmp_path / "good.csv"
    good.write_text("point_id,x,y\n,10,12\np2,20,22\n", encoding="utf-8")
    research.setCoordinates(str(good))
    assert not research.error
    assert [p["point_id"] for p in research.points] == ["0", "p2"]

    short = tmp_path / "short.csv"
    short.write_text("point_id,x,y\np1,10,12\np2\n", encoding="utf-8")
    research.setCoordinates(str(short))
    assert "3행" in research.error
    assert [p["point_id"] for p in research.points] == ["0", "p2"]
