# =============================================================================
# test_geo_integration.py
# -----------------------------------------------------------------------------
# Responsible for: The geo + brain integration on the FULL chain (scripted pose ->
#                  detector simulator -> GeoReferencer -> brain) — that the subject
#                  is located at ~the right cell, and that an off-grid detection is
#                  caught by the brain's boundary (defense in depth).
# Role in project: This is the Geo Unit 4 milestone made into a regression test: the
#                  subject's cell EMERGES from projection and the loop still locates.
# =============================================================================

import logging

import math
import pytest

from src.common.config import BrainConfig
from src.common.contracts import (
    CameraPose,
    Detection,
    DetectorOutput,
    SensorType,
)
from src.common.grid import GridSpec
from src.geo.georeferencer import GeoReferencer
from src.search.brain import SearchBrain
from src.search.terrain import SyntheticTerrain
from src.demo.detector_sim import DetectorSimulator
from src.demo.mock_stream import build_scripted_path


def test_full_chain_locates_the_planted_subject():
    """
    Scenario: the whole demo chain — scripted flight path, simulated detector (seeded),
    real GeoReferencer, real brain — run end to end.
    Why it matters: the integration milestone. Despite geo's baseline error, canopy
    misses, and a possible false positive, the brain must locate the planted subject at
    (or within a cell of) its true cell — and the located cell must EMERGE from the
    projection, not be hand-placed.
    """
    cfg = BrainConfig(located_concentration_ratio=3.5)  # the demo's calibrated floor
    grid = GridSpec.from_config(cfg)
    terrain = SyntheticTerrain(cfg)
    brain = SearchBrain(cfg, terrain)

    subject_latlon, frames = build_scripted_path(grid, cfg)
    subject = grid.latlon_to_cell(*subject_latlon)
    visibility = terrain.visibility(grid)
    geo = GeoReferencer(grid, visibility=visibility, config=cfg)
    sim = DetectorSimulator(grid, subject_latlon, visibility, config=cfg, seed=0, false_positive_rate=0.01)

    located = None
    for f in frames:
        obs = geo.reference(sim.simulate(f.pose, f.sensor_type, f.timestamp), f.pose)
        ev = brain.step(obs)
        located = located or ev

    assert located is not None, "the full chain failed to locate the subject"
    err_cells = math.hypot(located.cell[0] - subject[0], located.cell[1] - subject[1])
    assert err_cells <= 1.5, f"located {located.cell} too far from true subject {subject}"
    # mass invariant survived the whole run
    assert brain.posterior.sum() + brain.p_out == pytest.approx(1.0)


def test_edge_detection_flows_through_chain_and_is_sanitized(caplog):
    """
    Scenario: a detection near the region edge whose box center projects OFF-grid, fed
    through geo -> brain.
    Why it matters: the layered defense end to end — geo emits the off-grid cell, and the
    brain's sanitizer drops it (no crash, mass preserved, warning counted). This is the
    boundary the hardening pass built, exercised by the real geo producer.
    """
    cfg = BrainConfig(n_rows=160, n_cols=160)
    grid = GridSpec.from_config(cfg)
    geo = GeoReferencer(grid)
    brain = SearchBrain(cfg, SyntheticTerrain(cfg))

    # Drone over the SW corner, a left-edge box -> projects west of the origin (off-grid).
    lat, lon = grid.cell_to_latlon(0, 0)
    pose = CameraPose("E1", (lat, lon), 100.0, 0.0, -90.0, (70.0, 40.0), (1920, 1080))
    det = DetectorOutput("E1", 1.0, [Detection((0.0, 539.0, 2.0, 2.0), 0.9)], "sim", SensorType.COLOR)

    obs = geo.reference(det, pose)
    # geo emitted an off-grid detection cell (it projects, doesn't filter)
    assert any(not grid.in_bounds(*d.cell) for d in obs.detections_ground)

    with caplog.at_level(logging.WARNING):
        brain.step(obs)  # must not raise
    assert brain.input_warning_count >= 1                       # the brain dropped it and logged
    assert brain.posterior.sum() + brain.p_out == pytest.approx(1.0)
