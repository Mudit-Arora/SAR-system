# =============================================================================
# test_detector_sim.py
# -----------------------------------------------------------------------------
# Responsible for: The detector simulator — that it projects the subject into the
#                  frame correctly, MODELS the pitch shift geo ignores (the non-
#                  tautology), misses more under canopy, and is deterministic.
# Role in project: The simulator is the only simulated piece of the feasibility
#                  harness; these tests keep its realism honest and reproducible.
# =============================================================================

import numpy as np
import pytest

from src.common.config import BrainConfig
from src.common.contracts import SensorType
from src.common.grid import GridSpec
from src.demo.detector_sim import DetectorSimulator


@pytest.fixture
def grid() -> GridSpec:
    return GridSpec.from_config(BrainConfig(n_rows=160, n_cols=160))


def _pose(grid, drone_cell, heading=0.0, alt=100.0, pitch=-90.0, frame_id="F1"):
    from src.common.contracts import CameraPose
    lat, lon = grid.cell_to_latlon(*drone_cell)
    return CameraPose(frame_id, (lat, lon), alt, heading, pitch, (70.0, 40.0), (1920, 1080))


def _sim(grid, subject_cell, vis_value=0.9, **kw):
    vis = np.full((grid.n_rows, grid.n_cols), vis_value)
    sub_latlon = grid.cell_to_latlon(*subject_cell)
    return DetectorSimulator(grid, sub_latlon, vis, **kw)


def test_subject_under_nadir_projects_near_image_center(grid):
    """
    Scenario: drone directly over the subject, true nadir (pitch -90).
    Why it matters: with no pitch shift, the subject must land at the image center —
    the baseline both sim and geo agree on.
    """
    subject = (80, 80)
    sim = _sim(grid, subject)
    px, py = sim._subject_to_pixel(_pose(grid, subject, pitch=-90.0))
    assert px == pytest.approx(1920 / 2, abs=1.0)
    assert py == pytest.approx(1080 / 2, abs=1.0)


def test_pitch_shift_moves_subject_off_center(grid):
    """
    Scenario: drone over the subject, but the camera pitched 15° off nadir (pitch -75).
    Why it matters: THE non-tautology. The footprint center shifts forward, so a subject
    at nadir appears BELOW image center — an effect geo's baseline ignores. This is the
    error the feasibility harness measures; if it were zero, the test would be circular.
    """
    subject = (80, 80)
    sim = _sim(grid, subject)
    _, py_nadir = sim._subject_to_pixel(_pose(grid, subject, pitch=-90.0))
    _, py_pitched = sim._subject_to_pixel(_pose(grid, subject, pitch=-75.0))
    assert py_pitched > py_nadir + 50    # clearly shifted toward the bottom of the frame


def test_subject_out_of_frame_yields_no_detection(grid):
    """
    Scenario: drone far from the subject (subject not in the footprint).
    Why it matters: a frame that doesn't see the subject must be a clean non-detection
    (the sweep frames rely on this), so the map can clear that area.
    """
    sim = _sim(grid, (40, 40), false_positive_rate=0.0)
    out = sim.simulate(_pose(grid, (120, 120)), SensorType.COLOR, timestamp=1.0)
    assert out.detections == []


def test_thermal_misses_less_than_color_under_canopy(grid):
    """
    Scenario: subject under canopy (base visibility 0.5); run many frames each sensor.
    Why it matters: thermal lifts visibility, so it should detect on more frames than
    color — the mechanism behind the demo's "thermal corroborates" beat.
    """
    subject = (80, 80)
    n = 300
    # Use ONE simulator per sensor so the seeded RNG advances across frames.
    color_sim = _sim(grid, subject, vis_value=0.5, seed=1, false_positive_rate=0.0)
    thermal_sim = _sim(grid, subject, vis_value=0.5, seed=1, false_positive_rate=0.0)
    color_hits = sum(bool(color_sim.simulate(_pose(grid, subject), SensorType.COLOR, t).detections) for t in range(n))
    thermal_hits = sum(bool(thermal_sim.simulate(_pose(grid, subject), SensorType.THERMAL, t).detections) for t in range(n))
    assert thermal_hits > color_hits
    assert color_hits > 0  # color still detects on some frames


def test_simulator_is_deterministic_with_seed(grid):
    """
    Scenario: two simulators, same seed, same frame.
    Why it matters: the demo and any feasibility numbers must be reproducible — the
    realism is noise, but seeded noise.
    """
    subject = (80, 80)
    a = _sim(grid, subject, vis_value=0.6, seed=5).simulate(_pose(grid, subject), SensorType.COLOR, 1.0)
    b = _sim(grid, subject, vis_value=0.6, seed=5).simulate(_pose(grid, subject), SensorType.COLOR, 1.0)
    assert len(a.detections) == len(b.detections)
    if a.detections:
        assert a.detections[0].bbox_xywh == b.detections[0].bbox_xywh
        assert a.detections[0].confidence == b.detections[0].confidence
