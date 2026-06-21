# =============================================================================
# test_grid.py
# -----------------------------------------------------------------------------
# Responsible for: The GridSpec meters<->cell primitives, especially the new
#                  local_m_to_cell the GeoReferencer relies on to land a projected
#                  pixel on the right ground cell.
# Role in project: These conversions are the shared spatial contract; a bug here
#                  would misplace every detection and footprint cell.
# =============================================================================

import pytest

from src.common.config import BrainConfig
from src.common.grid import GridSpec


@pytest.fixture
def grid() -> GridSpec:
    return GridSpec.from_config(BrainConfig(n_rows=160, n_cols=160))


def test_local_m_to_cell_round_trips_with_cell_centers(grid):
    """
    Scenario: take a cell, compute its center in local meters, map back to a cell.
    Why it matters: the meters->cell step must be the exact inverse of cell-center
    placement, or projected detections land one cell off.
    """
    for (r, c) in [(0, 0), (50, 73), (159, 159), (77, 96)]:
        east_m = (c + 0.5) * grid.cell_size_m
        north_m = (r + 0.5) * grid.cell_size_m
        assert grid.local_m_to_cell(east_m, north_m) == (r, c)


def test_local_m_to_cell_is_consistent_with_latlon_to_cell(grid):
    """
    Scenario: convert a lat/lon two ways — directly, and via local meters.
    Why it matters: latlon_to_cell now delegates to local_m_to_cell; the two paths must
    agree so geo (which works in meters) and telemetry (which is lat/lon) never disagree.
    """
    lat, lon = 37.9008, -122.6105
    direct = grid.latlon_to_cell(lat, lon)
    via_meters = grid.local_m_to_cell(*grid.latlon_to_local_m(lat, lon))
    assert direct == via_meters


def test_local_m_to_cell_does_not_clamp_off_region(grid):
    """
    Scenario: a point west/south of the origin (negative meters).
    Why it matters: off-region points must produce out-of-range indices (so in_bounds can
    catch them), not silently clamp to the edge — geo/sanitizer rely on detecting this.
    """
    rc = grid.local_m_to_cell(east_m=-25.0, north_m=-25.0)
    assert rc == (-1, -1)
    assert not grid.in_bounds(*rc)
