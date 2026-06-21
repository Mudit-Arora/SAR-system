# =============================================================================
# tests/test_search_and_guide.py
# -----------------------------------------------------------------------------
# Responsible for: An acceptance check of the COMBINED demo pipeline — multi-drone search
#                  locates the subject AND the guide-home phase walks them back to the operators.
# Role in project: Guards the combined artifact (src/demo/search_and_guide.py) end to end on
#                  real terrain. Rendering is verified by running the module; this pins the data.
# Assumptions: Real DEM + WorldCover rasters present; otherwise the module is skipped.
# =============================================================================

from __future__ import annotations

import pathlib

import pytest

from src.search.terrain_raster import _DEFAULT_DEM

pytestmark = pytest.mark.skipif(
    not pathlib.Path(_DEFAULT_DEM).exists(), reason="real DEM raster not present in data/terrain/"
)


def test_combined_search_then_guide_home_reaches_operators():
    """
    Scenario: run the 3-drone search, then plan + simulate the guide-home phase.
    Why it matters: this is the combined story's promise — the fleet finds the subject and the
    finder leads them home. Assert it locates, and the guidance arrives at the operators cell.
    """
    from src.demo.search_and_guide import run_combined

    combined = run_combined(seed=0, n_drones=3)
    assert combined is not None, "multi-drone search did not locate"
    result, guidance = combined

    assert result.located_event is not None
    assert guidance.arrived, "subject was not guided all the way home"
    lkp = result.grid.latlon_to_cell(*result.cfg.lkp_latlon)
    assert guidance.states[-1].subject_cell == lkp
    # The within-sight promise holds across the whole guided walk.
    for st in guidance.states:
        assert st.drone_s - st.subject_s <= guidance.sight_distance_m + 1e-6
