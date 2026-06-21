# =============================================================================
# return_path.py
# -----------------------------------------------------------------------------
# Responsible for: Planning a TERRAIN-AWARE walking route from the located subject's
#                  cell back to a home/operator cell, over the search grid.
# Role in project: The routing half of the "drone-as-guide" feature — once the subject is
#                  found, this computes the path the drone leads them along to get home.
#                  It reuses the terrain accessibility layer (slope + land cover) as the
#                  traversal cost, so the route prefers walkable ground and avoids
#                  cliffs/water without any new data.
# Role/pattern: Dijkstra's shortest-path on an 8-connected grid where each cell carries a
#               traversal cost (node-weighted grid). No graph library — a heapq priority
#               queue, which is plenty for a 160x160 grid.
# Assumptions: accessibility is the brain's existing per-cell walkability in [0, 1]
#              (0 = impassable). Endpoints are in-bounds and not themselves walled off.
# =============================================================================

from __future__ import annotations

import heapq
import math
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

from src.common.config import BrainConfig
from src.common.contracts import Cell
from src.common.grid import GridSpec
from src.search.terrain import TerrainProvider

# 8-neighbour offsets with the physical step multiplier (diagonals are √2 longer). Listing
# them once keeps the neighbour iteration and the edge-length calculation in agreement.
_NEIGHBORS_8: Tuple[Tuple[int, int, float], ...] = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
)

# Below this accessibility a cell is treated as effectively impassable (water, cliff). We
# don't hard-remove it from the graph — instead we make crossing it enormously expensive, so
# the route goes AROUND when any way around exists, yet a path is still returned if the only
# option is to cross (e.g. the subject starts on a sliver of bad ground).
_IMPASSABLE_THRESHOLD = 0.02
_IMPASSABLE_PENALTY = 1000.0


def neighbors_8(cell: Cell, grid: GridSpec) -> Iterator[Tuple[Cell, float]]:
    """
    Yield the in-bounds 8-neighbours of a cell with each step's length multiplier.

    Args:
        cell: The (row, col) to expand.
        grid: The GridSpec, for the bounds check.

    Yields:
        ((row, col), step_mult) pairs, where step_mult is 1.0 for orthogonal moves and √2
        for diagonal moves (the cell-count length of the step).

    Why:
        The codebase had no neighbour iterator; this is the one place that move set lives, so
        the planner and any future grid walker agree on connectivity (8-connected) and on how
        long a diagonal step is.
    """
    r, c = cell
    for dr, dc, step in _NEIGHBORS_8:
        nr, nc = r + dr, c + dc
        if grid.in_bounds(nr, nc):
            yield (nr, nc), step


def _traversal_cost(accessibility: np.ndarray, eps: float) -> np.ndarray:
    """
    Convert the accessibility layer into a per-cell traversal cost.

    Args:
        accessibility: (n_rows, n_cols) walkability in [0, 1] (0 = impassable).
        eps: The accessibility floor (cfg.accessibility_epsilon); caps the base cost at 1/eps.

    Returns:
        (n_rows, n_cols) cost array: ~1 on easy ground, up to 1/eps on hard-but-passable
        ground, and a huge value on effectively-impassable cells.

    Why:
        Cost is the inverse of walkability, so Dijkstra naturally prefers easy ground. Clipping
        to eps keeps hard ground finite (still crossable if worth it), while the explicit
        impassable penalty makes water/cliffs a near-wall the route bends around.
    """
    cost = 1.0 / np.clip(accessibility, eps, 1.0)
    # Near-zero accessibility -> a near-wall (strongly avoided, not strictly forbidden).
    cost = np.where(accessibility < _IMPASSABLE_THRESHOLD, cost * _IMPASSABLE_PENALTY, cost)
    return cost


def _reconstruct(prev: Dict[Cell, Cell], start: Cell, goal: Cell) -> List[Cell]:
    """
    Walk the predecessor map back from goal to start and return the forward path.

    Args:
        prev: Map of cell -> the cell we reached it from (Dijkstra's back-pointers).
        start: The path's start cell.
        goal: The path's goal cell.

    Returns:
        The ordered [start, ..., goal] list of cells.

    Why:
        Dijkstra records how it reached each cell; the route is that chain reversed. Kept
        separate so the search loop stays readable.
    """
    path: List[Cell] = [goal]
    node = goal
    while node != start:
        node = prev[node]
        path.append(node)
    path.reverse()
    return path


def plan_return_path(
    grid: GridSpec,
    terrain: TerrainProvider,
    start_cell: Cell,
    home_cell: Cell,
    *,
    cfg: Optional[BrainConfig] = None,
) -> List[Cell]:
    """
    Plan a terrain-aware walking route from start_cell to home_cell over the grid.

    Args:
        grid: The shared GridSpec.
        terrain: The TerrainProvider whose accessibility layer is the traversal cost.
        start_cell: Where the route begins (the located subject's cell).
        home_cell: Where the route ends (the operator/home cell — the LKP).
        cfg: Brain config, for the accessibility floor (eps). Defaults to BrainConfig().

    Returns:
        The ordered [start_cell, ..., home_cell] list of cells — the route home. A single
        [cell] if start == home.

    Raises:
        ValueError: If either endpoint is out of bounds, or no route exists (should not happen
            with the soft impassable penalty unless the grid is degenerate).

    Why:
        This is Dijkstra over the inverse-accessibility cost: every cell's difficulty (slope,
        canopy, water) already lives in `accessibility`, so the shortest *cost* path is the
        most walkable route home — a real terrain-aware route with no new data, exactly the
        "the drone knows a sensible way back" half of the guide-home feature.
    """
    if not grid.in_bounds(*start_cell) or not grid.in_bounds(*home_cell):
        raise ValueError(f"plan_return_path: endpoint out of bounds (start={start_cell}, home={home_cell})")
    if start_cell == home_cell:
        return [start_cell]

    cfg = cfg or BrainConfig()
    cost = _traversal_cost(terrain.layers(grid).accessibility, cfg.accessibility_epsilon)
    cell_size = grid.cell_size_m

    # Dijkstra: pop the cheapest-so-far cell, relax its neighbours. The edge cost is the
    # physical step length times the mean traversal cost of the two cells (standard for a
    # node-weighted grid), so cost accrues in real "difficulty-weighted meters".
    dist: Dict[Cell, float] = {start_cell: 0.0}
    prev: Dict[Cell, Cell] = {}
    visited: set = set()
    frontier: List[Tuple[float, Cell]] = [(0.0, start_cell)]

    while frontier:
        d, cell = heapq.heappop(frontier)
        if cell in visited:
            continue
        visited.add(cell)
        if cell == home_cell:
            return _reconstruct(prev, start_cell, home_cell)

        c_here = cost[cell]
        for neighbor, step_mult in neighbors_8(cell, grid):
            if neighbor in visited:
                continue
            edge = cell_size * step_mult * 0.5 * (c_here + cost[neighbor])
            nd = d + edge
            if nd < dist.get(neighbor, math.inf):
                dist[neighbor] = nd
                prev[neighbor] = cell
                heapq.heappush(frontier, (nd, neighbor))

    raise ValueError("plan_return_path: no route found between start and home")


def path_length_m(path: List[Cell], grid: GridSpec) -> float:
    """
    Total ground length of a cell path, in meters (straight-line between cell centers).

    Args:
        path: An ordered list of cells.
        grid: The GridSpec (for cell size).

    Returns:
        The summed Euclidean length of the polyline through the cell centers, in meters.

    Why:
        The guidance simulation parameterizes the route by cumulative distance, and the demo
        reports "route length"; computing it from cell centers (×√2 on diagonals via the true
        Euclidean step) keeps it consistent with how the path was built.
    """
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += math.hypot(a[0] - b[0], a[1] - b[1]) * grid.cell_size_m
    return total
