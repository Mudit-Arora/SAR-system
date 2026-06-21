# =============================================================================
# test_geo.py
# -----------------------------------------------------------------------------
# Responsible for: The GeoReferencer — that a pixel box lands on the correct
#                  ground cell (nadir, heading rotation), that the footprint covers
#                  the right cells, and that boundary A (detector -> geo) is
#                  defended (adapter, sanitizer, frame fusion, degenerate pose).
# Role in project: Geo is the new producer of Observations; a projection bug would
#                  misplace every detection, and a boundary bug would crash on the
#                  separate-track detector's messy output.
# =============================================================================

import logging
import math

import numpy as np
import pytest

from src.common.config import BrainConfig
from src.common.contracts import (
    CameraPose,
    Detection,
    DetectorOutput,
    SensorType,
)
from src.common.grid import GridSpec
from src.geo.georeferencer import (
    DetectorSanitationReport,
    GeoReferencer,
    adapt_detector_output,
    sanitize_detector_output,
)


@pytest.fixture
def grid() -> GridSpec:
    return GridSpec.from_config(BrainConfig(n_rows=160, n_cols=160))


@pytest.fixture
def geo(grid) -> GeoReferencer:
    return GeoReferencer(grid)


def _pose(grid, cell, heading=0.0, alt=100.0, hfov=70.0, vfov=40.0, wh=(1920, 1080), frame_id="F1"):
    """A CameraPose whose nadir (drone position) is the center of `cell`."""
    lat, lon = grid.cell_to_latlon(*cell)
    return CameraPose(
        frame_id=frame_id,
        drone_latlon=(lat, lon),
        altitude_agl_m=alt,
        heading_deg=heading,
        gimbal_pitch_deg=-90.0,
        fov_deg=(hfov, vfov),
        image_size_px=wh,
    )


def _det_output(bbox, conf=0.7, frame_id="F1", sensor=SensorType.COLOR):
    return DetectorOutput(
        frame_id=frame_id,
        timestamp=1.0,
        detections=[Detection(bbox_xywh=bbox, confidence=conf)],
        model_id="sim",
        sensor_type=sensor,
    )


# --- projection correctness ---


def test_center_pixel_projects_to_nadir_cell(geo, grid):
    """
    Scenario: a detection box centered in the image, camera straight down.
    Why it matters: the most basic projection invariant — a center pixel must land on
    the drone's own ground cell, regardless of footprint size.
    """
    nadir = (80, 80)
    w, h = 1920, 1080
    box = (w / 2 - 10, h / 2 - 10, 20, 20)  # 20x20 box centered at image center
    obs = geo.reference(_det_output(box), _pose(grid, nadir))
    assert len(obs.detections_ground) == 1
    assert obs.detections_ground[0].cell == nadir


def test_heading_north_right_pixel_lands_east(geo, grid):
    """
    Scenario: a detection on the RIGHT edge of the image, heading north (0°).
    Why it matters: image-right must map to the ground direction 90° clockwise of the
    heading — east when facing north — or detections rotate the wrong way.
    """
    nadir = (80, 80)
    w, h = 1920, 1080
    box = (w - 21, h / 2 - 10, 20, 20)  # box center near the right edge
    obs = geo.reference(_det_output(box), _pose(grid, nadir, heading=0.0))
    r, c = obs.detections_ground[0].cell
    assert r == 80          # no north/south shift
    assert c > 80           # shifted EAST (col increases)


def test_heading_east_right_pixel_lands_south(geo, grid):
    """
    Scenario: same right-edge detection, but heading EAST (90°).
    Why it matters: confirms the rotation actually uses heading — image-right is now
    south (90° clockwise of east), so the same pixel lands in a different ground dir.
    """
    nadir = (80, 80)
    w, h = 1920, 1080
    box = (w - 21, h / 2 - 10, 20, 20)
    obs = geo.reference(_det_output(box), _pose(grid, nadir, heading=90.0))
    r, c = obs.detections_ground[0].cell
    assert c == 80          # no east/west shift
    assert r < 80           # shifted SOUTH (row decreases)


def test_footprint_size_matches_fov_geometry(geo, grid):
    """
    Scenario: a clean frame (no detections), known altitude/FOV, near-nadir.
    Why it matters: the footprint must span roughly 2*alt*tan(fov/2) on the ground; we
    check the covered extent is in the right ballpark (a few cells), not empty or huge.
    """
    nadir = (80, 80)
    obs = geo.reference(
        DetectorOutput("F1", 1.0, [], "sim", SensorType.COLOR),
        _pose(grid, nadir, heading=0.0, alt=100.0, hfov=70.0, vfov=40.0),
    )
    cols = [c for (_, c) in (cc.cell for cc in obs.footprint)]
    rows = [r for (r, _) in (cc.cell for cc in obs.footprint)]
    # ground width 2*100*tan35 ~ 140 m ~ 3 cells; height 2*100*tan20 ~ 73 m ~ 2 cells
    assert obs.footprint, "footprint should not be empty"
    assert 2 <= (max(cols) - min(cols) + 1) <= 4
    assert 1 <= (max(rows) - min(rows) + 1) <= 3
    assert all(0.0 < cc.coverage_fraction <= 1.0 for cc in obs.footprint)


def test_interior_cell_is_fully_covered(geo, grid):
    """
    Scenario: a wide footprint (high altitude), inspect the center cell.
    Why it matters: a cell entirely inside the footprint must report coverage_fraction
    ~1.0, while edge cells are partial — the basis of principled clearing.
    """
    nadir = (80, 80)
    obs = geo.reference(
        DetectorOutput("F1", 1.0, [], "sim", SensorType.COLOR),
        _pose(grid, nadir, heading=0.0, alt=300.0),  # big footprint
    )
    by_cell = {cc.cell: cc.coverage_fraction for cc in obs.footprint}
    assert by_cell[(80, 80)] == pytest.approx(1.0)


def test_visibility_array_flows_into_footprint(grid):
    """
    Scenario: inject a visibility array with a known low value at the nadir cell.
    Why it matters: the visibility seam (filled by Unit 3) must reach the Observation's
    visibility_weight, since that drives d_i in the brain.
    """
    vis = np.ones((grid.n_rows, grid.n_cols))
    vis[80, 80] = 0.3
    geo = GeoReferencer(grid, visibility=vis)
    obs = geo.reference(DetectorOutput("F1", 1.0, [], "sim", SensorType.COLOR),
                        _pose(grid, (80, 80), alt=300.0))
    by_cell = {cc.cell: cc.visibility_weight for cc in obs.footprint}
    assert by_cell[(80, 80)] == pytest.approx(0.3)


def test_thermal_lifts_visibility_over_color_and_clamps(grid):
    """
    Scenario: the same canopy cell (base visibility 0.5) seen by color vs thermal.
    Why it matters: thermal must lift visibility (it sees better under canopy), and the
    lift must clamp at 1.0 so an already-open cell can't exceed full visibility.
    """
    vis = np.full((grid.n_rows, grid.n_cols), 0.5)
    vis[80, 80] = 0.5     # canopy cell (nadir)
    vis[80, 82] = 0.9     # near-open cell within the footprint (0.9 * 1.4 must clamp to 1.0)
    geo = GeoReferencer(grid, visibility=vis)

    clean = DetectorOutput("F1", 1.0, [], "sim", SensorType.COLOR)
    thermal = DetectorOutput("F1", 1.0, [], "sim", SensorType.THERMAL)
    color_obs = geo.reference(clean, _pose(grid, (80, 80), alt=300.0))
    thermal_obs = geo.reference(thermal, _pose(grid, (80, 80), alt=300.0))

    color_vis = {cc.cell: cc.visibility_weight for cc in color_obs.footprint}
    thermal_vis = {cc.cell: cc.visibility_weight for cc in thermal_obs.footprint}
    assert thermal_vis[(80, 80)] > color_vis[(80, 80)]          # thermal helps under canopy
    assert thermal_vis[(80, 80)] == pytest.approx(0.7)          # 0.5 * 1.4
    assert thermal_vis[(80, 82)] == pytest.approx(1.0)          # 0.9 * 1.4 clamped to 1.0


# --- boundary A: adapter, sanitizer, fusion guard, degenerate pose ---


def test_adapter_passes_through_and_rejects_unknown():
    """
    Scenario: a real DetectorOutput vs an unrecognized type.
    Why it matters: the adapter is the drift seam — it must pass our shape through and
    fail LOUDLY (pointing back to itself) on an unknown one, not silently mishandle it.
    """
    out = _det_output((0, 0, 10, 10))
    assert adapt_detector_output(out) is out
    with pytest.raises(TypeError):
        adapt_detector_output({"frame_id": "F1"})  # a dict isn't mapped yet


def test_sanitizer_clamps_box_and_drops_bad_detections():
    """
    Scenario: one box overflowing the image, one fully off-frame, one with NaN confidence.
    Why it matters: boundary A must clip a partly-off box, drop the off-frame and NaN
    ones, and report it — so projection never sees garbage pixels.
    """
    dets = [
        Detection((1900, 1060, 100, 100), 0.8),   # overflows 1920x1080 -> clamp
        Detection((5000, 5000, 50, 50), 0.8),     # fully off-frame -> drop
        Detection((10, 10, 20, 20), float("nan")),  # NaN confidence -> drop
    ]
    out = DetectorOutput("F1", 1.0, dets, "sim", SensorType.COLOR)
    clean, report = sanitize_detector_output(out, image_size_px=(1920, 1080))
    assert len(clean.detections) == 1                       # only the clamped one survives
    x, y, w, h = clean.detections[0].bbox_xywh
    assert x + w <= 1920 and y + h <= 1080                  # clipped inside the image
    assert report.dropped_detections == 2 and report.clamped >= 1
    assert not report.clean


def test_in_bounds_box_is_not_falsely_reported_as_clamped():
    """
    Scenario: a detection box fully inside the image (no clipping needed).
    Why it matters: regression — counting a clamp via box-inequality false-positived on
    float round-off ((x+w)-x != w), spuriously warning on every clean frame. A box that
    was never clipped must report clamped=0 and pass through byte-identical.
    """
    box = (945.9, 791.0, 22.9, 24.7)  # well inside 1920x1080
    out = DetectorOutput("F1", 1.0, [Detection(box, 0.7)], "sim", SensorType.COLOR)
    clean, report = sanitize_detector_output(out, image_size_px=(1920, 1080))
    assert report.clamped == 0 and report.clean
    assert clean.detections[0].bbox_xywh == box


def test_frame_id_mismatch_raises(geo, grid):
    """
    Scenario: a DetectorOutput and CameraPose with different frame_ids.
    Why it matters: fusing a detection with the wrong frame's telemetry would silently
    misplace it; the join guard must fail loudly instead.
    """
    out = _det_output((100, 100, 20, 20), frame_id="F1")
    pose = _pose(grid, (80, 80), frame_id="F2")
    with pytest.raises(ValueError):
        geo.reference(out, pose)


def test_degenerate_pose_yields_empty_footprint(geo, grid, caplog):
    """
    Scenario: a pose with zero altitude (can't see the ground).
    Why it matters: must not do NaN/divide-by-zero footprint math — emit an empty
    footprint and warn, so the loop survives a bad telemetry frame.
    """
    out = _det_output((100, 100, 20, 20))
    pose = _pose(grid, (80, 80), alt=0.0)
    with caplog.at_level(logging.WARNING):
        obs = geo.reference(out, pose)
    assert obs.footprint == []
    assert any("degenerate pose" in r.message for r in caplog.records)


def test_edge_detection_emits_offgrid_cell_for_brain_to_drop(grid):
    """
    Scenario: a detection near the region edge whose box center projects off-grid.
    Why it matters: geo emits the off-grid cell AS COMPUTED (defense in depth) — the
    brain's sanitizer is the safety net. This pins the layered-defense contract: geo
    projects, the brain filters.
    """
    geo = GeoReferencer(grid)
    corner = (0, 0)  # drone over the SW corner; nadir is ~25 m from the origin
    w, h = 1920, 1080
    # box hard against the LEFT image edge, heading north -> image-left maps to west,
    # pushing the center ~70 m west of nadir, past the origin into a negative column.
    box = (0.0, h / 2 - 1, 2.0, 2.0)
    obs = geo.reference(_det_output(box), _pose(grid, corner, heading=0.0))
    assert len(obs.detections_ground) == 1
    r, c = obs.detections_ground[0].cell
    assert not grid.in_bounds(r, c)   # geo emitted an off-grid cell (col < 0), unfiltered
