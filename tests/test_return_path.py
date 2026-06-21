# =============================================================================
# tests/test_return_path.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the terrain-aware return-path planner
#                  (src/search/return_path.py) produces a valid, connected route that
#                  prefers walkable ground and routes AROUND impassable terrain.
# Role in project: Guards the routing half of the guide-home feature. If the route cut
#                  through a cliff or water, the "drone leads the subject home" story would
#                  be sending them somewhere they can't walk — so the around-the-barrier
#                  behavior is the key property under test.
# Assumptions: We drive the planner with a tiny FAKE terrain (a hand-built accessibility
#              array) so the obstacle is known exactly — no dependence on the real rasters.
# =============================================================================

from __future__ import annotations

import numpy as np

from src.common.config import BrainConfig
from src.common.grid import GridSpec
from src.search.return_path import _IMPASSABLE_THRESHOLD, neighbors_8, plan_return_path
from src.search.terrain import TerrainLayers


class _FakeTerrain:
    """
    A minimal TerrainProvider backed by a hand-built accessibility array.

    Why:
        The real terrain's obstacles are wherever the rasters say; for a deterministic test we
        need to KNOW exactly where the impassable cells are, so we inject our own accessibility
        grid and check the route dodges it. corridor/visibility are unused by the planner.
    """

    def __init__(self, accessibility: np.ndarray) -> None:
        self._a = accessibility

    def layers(self, grid: GridSpec) -> TerrainLayers:
        return TerrainLayers(accessibility=self._a, corridor=np.ones_like(self._a))

    def visibility(self, grid: GridSpec) -> np.ndarray:
        return np.ones_like(self._a)

    def context(self, grid: GridSpec, cell):
        return {}


def _small_grid(n: int = 20) -> GridSpec:
    """An n x n grid for fast, legible routing tests. Why: keeps obstacles easy to reason about."""
    return GridSpec.from_config(BrainConfig(n_rows=n, n_cols=n, cell_size_m=50.0))


def _assert_valid_path(path, start, home, grid):
    """Shared structural checks: endpoints, 8-adjacency, in-bounds. Why: every route must hold these."""
    assert path[0] == start and path[-1] == home
    for a, b in zip(path, path[1:]):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1, f"non-adjacent step {a}->{b}"
        assert grid.in_bounds(*b)


def test_straight_route_on_uniform_terrain():
    """
    Scenario: uniform easy terrain, route between two cells.
    Why it matters: with no obstacles the planner should still produce a clean, connected,
    8-adjacent path between the endpoints — the baseline the obstacle cases build on.
    """
    grid = _small_grid()
    terrain = _FakeTerrain(np.ones((grid.n_rows, grid.n_cols)))
    start, home = (3, 3), (3, 15)
    path = plan_return_path(grid, terrain, start, home)
    _assert_valid_path(path, start, home, grid)


def test_route_goes_around_an_impassable_wall():
    """
    Scenario: a wall of impassable cells (accessibility 0) at col 10 spanning rows 0-15, with a
    gap at the bottom (rows 16-19). Start and home sit on opposite sides at row 8.
    Why it matters: this is the whole point — a person can't walk through water/cliff, so the
    route must DETOUR through the gap and never step on an impassable cell.
    """
    grid = _small_grid()
    access = np.ones((grid.n_rows, grid.n_cols))
    access[0:16, 10] = 0.0  # vertical wall with a gap at rows 16-19
    terrain = _FakeTerrain(access)
    start, home = (8, 4), (8, 16)

    path = plan_return_path(grid, terrain, start, home)
    _assert_valid_path(path, start, home, grid)
    # The crux: not a single cell on the route is (effectively) impassable.
    for cell in path:
        assert access[cell] >= _IMPASSABLE_THRESHOLD, f"route stepped on impassable cell {cell}"
    # And it actually crossed col 10 via the gap (some path cell at col 10 is in the gap rows).
    crossing_rows = [r for (r, c) in path if c == 10]
    assert crossing_rows and all(r >= 16 for r in crossing_rows), "did not cross through the gap"


def test_route_prefers_easy_ground_over_hard():
    """
    Scenario: two ways from start to home — a short path over HARD ground (low accessibility)
    vs a slightly longer path over easy ground.
    Why it matters: terrain-awareness means the route should trade a few extra cells of easy
    walking for avoiding a hard-but-passable band, not just minimize cell count.
    """
    grid = _small_grid()
    access = np.ones((grid.n_rows, grid.n_cols))
    access[8, 5:15] = 0.1  # a hard (passable) band on the direct row-8 line
    terrain = _FakeTerrain(access)
    start, home = (8, 4), (8, 15)

    path = plan_return_path(grid, terrain, start, home)
    _assert_valid_path(path, start, home, grid)
    # The route should mostly avoid the hard band rather than plow straight along row 8.
    hard_cells = sum(1 for (r, c) in path if access[(r, c)] < 0.5)
    assert hard_cells <= 2, f"route stayed on hard ground for {hard_cells} cells"


def test_same_cell_returns_singleton_and_planner_is_deterministic():
    """
    Scenario: (a) start == home; (b) the same query run twice.
    Why it matters: the guidance sim handles the degenerate "already home" case, and the server
    caches/animates the route, so identical inputs must yield an identical path.
    """
    grid = _small_grid()
    terrain = _FakeTerrain(np.ones((grid.n_rows, grid.n_cols)))
    assert plan_return_path(grid, terrain, (5, 5), (5, 5)) == [(5, 5)]
    p1 = plan_return_path(grid, terrain, (2, 2), (17, 17))
    p2 = plan_return_path(grid, terrain, (2, 2), (17, 17))
    assert p1 == p2


def test_neighbors_8_respects_bounds():
    """
    Scenario: expand a corner cell.
    Why it matters: a corner has only 3 valid neighbours; the iterator must not yield off-grid
    cells (an off-grid index would crash the cost lookup).
    """
    grid = _small_grid()
    corner = list(neighbors_8((0, 0), grid))
    cells = {c for c, _ in corner}
    assert cells == {(0, 1), (1, 0), (1, 1)}
