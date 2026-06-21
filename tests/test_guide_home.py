# =============================================================================
# tests/test_guide_home.py
# -----------------------------------------------------------------------------
# Responsible for: An acceptance check of the guide-home pipeline end to end on real
#                  terrain — search locates, a route home to the operators is planned, and
#                  the guidance sim walks the subject all the way to the operators in sight.
# Role in project: Proves the "act 2" feasibility claim with the REAL loop + REAL terrain
#                  (the rendering itself is exercised by running `python -m src.demo.guide_home`).
# Assumptions: Real DEM + WorldCover rasters present; otherwise the whole module is skipped
#              (CI / a fresh clone without data/). The detector is simulated; everything else
#              (geo, brain, route, guidance) is the production code.
# =============================================================================

from __future__ import annotations

import pathlib

import pytest

from src.search.terrain_raster import _DEFAULT_DEM

pytestmark = pytest.mark.skipif(
    not pathlib.Path(_DEFAULT_DEM).exists(), reason="real DEM raster not present in data/terrain/"
)


def test_guide_home_pipeline_reaches_the_operators():
    """
    Scenario: run drive_loop to a locate, plan the route to the LKP, simulate guidance.
    Why it matters: this is the feature's whole promise on real data — after the find, the
    drone can lead the (mobile) subject all the way back to the operators, staying in sight.
    Assert it locates, the route ends at the operators cell, and the subject ARRIVES there.
    """
    from src.demo.guide_home import drive_loop
    from src.search.guide import simulate_guidance
    from src.search.return_path import plan_return_path

    result = drive_loop(seed=0)
    assert result.located_event is not None, "search did not locate — no one to guide home"

    grid, cfg, terrain = result.grid, result.cfg, result.terrain
    lkp_cell = grid.latlon_to_cell(*cfg.lkp_latlon)
    path = plan_return_path(grid, terrain, result.subject, lkp_cell, cfg=cfg)

    assert path[0] == result.subject and path[-1] == lkp_cell  # route connects find -> operators

    guidance = simulate_guidance(grid, terrain, path)
    assert guidance.arrived, "subject did not reach the operators"
    assert guidance.states[-1].subject_cell == lkp_cell
    # Re-affirm the within-sight invariant on the real route (the core behavioral claim).
    for st in guidance.states:
        assert st.drone_s - st.subject_s <= guidance.sight_distance_m + 1e-6
