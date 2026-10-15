from types import SimpleNamespace

import numpy as np

from sic_xrt_analyzer.analysis.desktop_adapter import DesktopResearchAdapter
from sic_xrt_analyzer.analysis.model_adapter import CancellationToken


class Source:
    def __init__(self):
        self.pixels = np.full((800, 500, 3), 120, np.uint8)
        self.pixels[90:710, 245:252] = 35
        # A bright point on a long dark BPD must not become its entire outline.
        self.pixels[395:404, 241:245] = 230
        self.metadata = SimpleNamespace(width=500, height=800)

    def read_region(self, x, y, w, h):
        assert x >= 0 and y >= 0 and x+w <= 500 and y+h <= 800
        return self.pixels[y:y+h, x:x+w].copy()


def test_long_bpd_outline_extends_beyond_classifier_patch():
    source = Source()
    before = source.pixels.copy()
    region = DesktopResearchAdapter._region(source, {"x":243, "y":400, "cx":243, "cy":400}, CancellationToken())
    points = np.asarray(region)
    assert points[:, 1].min() <= 93 and points[:, 1].max() >= 706
    assert points[:, 0].min() >= 244 and points[:, 0].max() <= 252
    assert not region.clipped and region.context > 128
    assert np.array_equal(source.pixels, before)


def test_region_scope_boundary_is_explicitly_reported():
    region = DesktopResearchAdapter._region(Source(), {"x":243, "y":400, "cx":243, "cy":400, "region_bounds":(180,300,160,200)}, CancellationToken())
    assert region.clipped
    assert all(180 <= x < 340 and 300 <= y < 500 for x,y in region)
