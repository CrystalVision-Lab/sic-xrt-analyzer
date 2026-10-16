"""Synthetic regression evidence, not a claim of real-world detection accuracy."""
import numpy as np
import tifffile

from sic_xrt_analyzer.imaging.original_source import OriginalImageSource
from sic_xrt_analyzer.stack3d.continuity import continue_line
from sic_xrt_analyzer.stack3d.defect import trace


def test_growing_thin_tip_is_not_a_merge(tmp_path):
    data = np.full((9, 240, 180), 60000, np.uint16)
    for k in range(1, 8):
        data[k, 90-k*9:110+k*9, 85:90] = 2000
    path = tmp_path/'tip.tif'
    tifffile.imwrite(path, data, photometric='minisblack')
    mesh = trace(OriginalImageSource(path, 1), (87, 100, 1))
    assert [s.page for s in mesh.sections] == list(range(1, 8))
    assert mesh.voxels == np.count_nonzero(data == 2000)


def test_crossing_follows_local_direction_without_transverse_arm():
    reference = np.zeros((140, 140), bool)
    reference[15:125, 67:72] = True
    crossing = reference.copy()
    crossing[67:72, 15:125] = True
    selected, resolved = continue_line(crossing, (40, 69), reference)
    assert resolved
    assert selected[20:120, 69].all()
    assert not selected[69, 20] and not selected[69, 120]
    assert np.all(~selected | crossing)


def test_equal_y_fork_stays_ambiguous():
    from scipy.ndimage import binary_dilation
    reference = np.zeros((120, 120), bool)
    reference[60:110, 60] = True
    crossing = reference.copy()
    for y in range(15, 61):
        crossing[y, 60-(60-y)] = True
        crossing[y, 60+(60-y)] = True
    reference = binary_dilation(reference, iterations=2)
    crossing = binary_dilation(crossing, iterations=2)
    _, resolved = continue_line(crossing, (90, 60), reference)
    assert not resolved


def test_crossing_in_next_slice_tracks_only_same_vertical_line(tmp_path):
    data = np.full((7, 140, 140), 60000, np.uint16)
    data[1:6, 15:125, 67:72] = 2000
    data[3:5, 67:72, 15:125] = 2000
    path = tmp_path/'cross.tif'
    tifffile.imwrite(path, data, photometric='minisblack')
    mesh = trace(OriginalImageSource(path, 2), (69, 40, 2))
    assert [s.page for s in mesh.sections] == list(range(1, 6))
    for s in mesh.sections:
        assert s.width < 20
        assert np.all(data[s.page, s.y:s.y+s.height, s.x:s.x+s.width][s.mask()] == 2000)


def test_small_intensity_notch_keeps_observed_arms_without_filling_gap():
    reference = np.zeros((140, 140), bool)
    reference[15:125, 64:76] = True
    component = reference.copy()
    component[15:42, 69:71] = False
    selected, resolved = continue_line(component, (90, 69), reference)
    assert resolved
    assert selected[20, 66] and selected[20, 73]
    assert not selected[20, 69]
    assert np.all(~selected | component)


def test_unbranched_curve_is_not_rejected_for_bending():
    from scipy.ndimage import binary_dilation
    component = np.zeros((140, 140), bool)
    for y in range(15, 125):
        component[y, int(60 + 15*np.sin(y/25))] = True
    component = binary_dilation(component, iterations=2)
    selected, resolved = continue_line(component, (85, 56))
    assert resolved and np.array_equal(selected, component)


def test_small_page_translation_preserves_only_observed_pixels(tmp_path):
    data = np.full((7, 140, 140), 60000, np.uint16)
    for k in range(1, 6):
        data[k, 40:100, 50+k*5:53+k*5] = 2000
    path = tmp_path/'translated.tif'
    tifffile.imwrite(path, data, photometric='minisblack')
    mesh = trace(OriginalImageSource(path, 3), (66, 70, 3))
    assert [s.page for s in mesh.sections] == list(range(1, 6))
    assert mesh.voxels == np.count_nonzero(data == 2000)
    for section in mesh.sections:
        pixels = data[section.page, section.y:section.y+section.height,
                      section.x:section.x+section.width]
        assert np.all(pixels[section.mask()] == 2000)


def test_translation_rejects_equal_neighbours_and_large_jumps():
    from sic_xrt_analyzer.stack3d.continuity import translated_reference
    reference = np.zeros((80, 80), bool)
    reference[20:60, 39:42] = True
    labels = np.zeros((80, 80), int)
    labels[20:60, 34:37] = 1
    labels[20:60, 44:47] = 2
    aligned, reason = translated_reference(reference, labels)
    assert aligned is None and reason == 'AMBIGUOUS_BRANCH'
    labels[:] = 0
    labels[20:60, 52:55] = 1
    assert translated_reference(reference, labels)[0] is None
