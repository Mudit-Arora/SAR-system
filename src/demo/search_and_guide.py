# =============================================================================
# search_and_guide.py
# -----------------------------------------------------------------------------
# Responsible for: The COMBINED showcase — multi-drone sectorized search (C1) finds the
#                  subject, then the locating drone GUIDES the subject home (the pathfinding
#                  feature) — rendered as one continuous animated GIF over real Marin terrain.
# Role in project: Stitches the two flagship behaviors into one story: coordinated search ->
#                  locate -> guide-home. Reuses src/demo/search_demo.py's multi-drone loop +
#                  renderer (act 1) and src/search return-path + guidance (act 2). Pure glue,
#                  no new search/guidance logic.
# Run: PYTHONPATH=. .venv/bin/python -m src.demo.search_and_guide [--drones N] [--seed S]
# Assumptions: real DEM + WorldCover rasters in data/terrain/ (errors clearly if absent).
#              Detector simulated; geo, brain, planner, route, guidance are the real code.
# =============================================================================

from __future__ import annotations

import argparse
import math
import pathlib
from typing import List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from PIL import Image

from src.common.contracts import Cell
from src.common.grid import GridSpec
from src.search.guide import GuidanceResult, GuideState, simulate_guidance
from src.search.return_path import plan_return_path
from src.search.terrain_raster import RasterTerrain
# Reuse act 1 (multi-drone search) wholesale, and the shared hillshade/belief/GIF stack.
from src.demo.search_demo import (
    PlannerResult,
    _DRONE_COLORS,
    _OUTPUT_DIR,
    render_planner_frame,
    run_multi_drone,
)
from src.demo.showcase import _frame_to_image, draw_belief_layer, hillshade

# Down-sample the (hundreds of) guidance ticks to a watchable count for act 2.
_TARGET_GUIDE_FRAMES = 40


def _guiding_drone_id(drones, subject: Cell) -> int:
    """
    Pick the drone that found the subject — the one whose final position is nearest the find.

    Args:
        drones: The DroneViews from the last search frame (each with a flown path).
        subject: The located subject cell.

    Returns:
        The drone_id that will lead the subject home (cosmetic — its color carries the story).

    Why:
        PlannerResult doesn't record "located_by", but the confirming drone ends its sweep
        loitering over the subject, so the drone whose last path cell is closest to the find IS
        the locator. Using its color in act 2 makes the narrative continuous: the drone that
        found them now leads them out.
    """
    best_id, best_d = 0, math.inf
    for d in drones:
        if not d.path:
            continue
        last = d.path[-1]
        dist = math.hypot(last[0] - subject[0], last[1] - subject[1])
        if dist < best_d:
            best_id, best_d = d.drone_id, dist
    return best_id


def _sample_guide(states: List[GuideState]) -> List[GuideState]:
    """Stride the guidance states to ~_TARGET_GUIDE_FRAMES (keeping the last). Why: a small GIF."""
    if len(states) <= _TARGET_GUIDE_FRAMES:
        return states
    stride = max(1, len(states) // _TARGET_GUIDE_FRAMES)
    sampled = states[::stride]
    if sampled[-1] is not states[-1]:
        sampled.append(states[-1])
    return sampled


def _render_guide_phase(
    ax, grid: GridSpec, hill, posterior, guidance: GuidanceResult,
    guiding_color: str, context_drones, lkp: Cell, fs: GuideState,
) -> None:
    """
    Render one act-2 frame: located posterior + faded search paths + the guide-home overlay.

    Args:
        ax: The axis (cleared per frame).
        grid: Shared GridSpec.
        hill: Precomputed hillshade.
        posterior: The located posterior (the find still glowing — continuity from act 1).
        guidance: The GuidanceResult (route + home + sight distance).
        guiding_color: The locating drone's color (the leader).
        context_drones: The other drones' final DroneViews (faded paths, for continuity).
        lkp: The operators/home cell.
        fs: The GuideState to draw.

    Why:
        Keeps the multi-drone context on screen (faded search tracks + the find) while the
        leader/follower guide-home plays out, so act 2 reads as the SAME mission continuing, not
        a separate clip.
    """
    ax.clear()
    draw_belief_layer(ax, posterior, hill)
    ax.add_patch(Rectangle((-0.5, -0.5), grid.n_cols, grid.n_rows, fill=False,
                           edgecolor="lime", linewidth=2.0, clip_on=False))

    # Faded search tracks from act 1 (where the fleet swept).
    for d in context_drones:
        color = _DRONE_COLORS[d.drone_id % len(_DRONE_COLORS)]
        if d.path:
            ax.plot([c for _, c in d.path], [r for r, _ in d.path], "-",
                    color=color, lw=1.0, alpha=0.30, zorder=3)

    # The planned walkable route home, the operators, the tether, and the leader + follower.
    rows = [c[0] for c in guidance.path]
    cols = [c[1] for c in guidance.path]
    ax.plot(cols, rows, "--", color="#7CFC00", lw=1.8, alpha=0.65, zorder=5, label="route home")
    # White marker for the operators so it never collides with the guiding drone's color (the
    # locating drone could be any color in the fleet palette, including deepskyblue).
    ax.scatter([lkp[1]], [lkp[0]], marker="s", s=150, c="white", edgecolors="black",
               linewidths=1.4, zorder=7, label="operators (home)")
    ax.annotate("operators", (lkp[1], lkp[0]), textcoords="offset points", xytext=(8, 6),
                color="white", fontsize=8, fontweight="bold")

    sr, sc = fs.subject_pos
    dr, dc = fs.drone_pos
    ax.plot([sc, dc], [sr, dr], "-", color="gold", lw=1.4, alpha=0.9, zorder=8)
    # Drone (leader) below the subject so the red follower stays visible when the lead is short.
    ax.scatter([dc], [dr], marker="D", s=140, c=guiding_color, edgecolors="black", linewidths=1.2,
               zorder=9, label="guiding drone (leading)")
    ax.scatter([sc], [sr], marker="o", s=120, c="red", edgecolors="white", linewidths=1.2,
               zorder=10, label="subject (following)")

    remaining = max(0.0, guidance.total_length_m - fs.subject_s)
    if fs.subject_s >= guidance.total_length_m:
        title = "★ HOME — subject guided back to the operators"
    else:
        title = "GUIDING HOME — the drone that found them now leads them out"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.text(0.5, -0.10,
            f"{remaining:,.0f} m to go   ·   route {guidance.total_length_m:,.0f} m   ·   "
            f"drone lead ≤ {guidance.sight_distance_m:.0f} m (in sight)",
            transform=ax.transAxes, ha="center", va="top", fontsize=9)
    ax.set_xlabel("column (50 m cells)")
    ax.set_ylabel("row (50 m cells)  •  full frame = 8 km × 8 km")
    ax.legend(loc="upper right", fontsize=7)


def _search_duration_ms(frame, is_last_of_search: bool) -> int:
    """Pace act 1 (search). Why: brisk sweep, linger on prior + the locate hand-off."""
    if frame.update_count == 0:
        return 1500
    if is_last_of_search or frame.located_now or "CONTACT" in frame.caption:
        return 650
    return 200


def _guide_duration_ms(index: int, n: int) -> int:
    """Pace act 2 (guide). Why: steady walk, dwell on the safe arrival."""
    if index == n - 1:
        return 3000
    return 150


def build_combined_animation(result: PlannerResult, guidance: GuidanceResult, out_path: pathlib.Path) -> None:
    """
    Render the two acts (search, then guide-home) into one continuous GIF.

    Args:
        result: The recorded multi-drone search (act 1 frames + the located outcome).
        guidance: The guide-home result (act 2 states).
        out_path: Where to write the .gif.

    Why:
        One figure, one frame list: act 1 uses the multi-drone renderer, act 2 uses the
        guide-phase renderer with the search context faded in behind — so the output is a single
        story (search → locate → guide home), not two stitched clips.
    """
    grid = result.grid
    hill = hillshade(grid)
    lkp = grid.latlon_to_cell(*result.cfg.lkp_latlon)
    located_posterior = result.frames[-1].posterior
    context_drones = result.frames[-1].drones
    guiding_id = _guiding_drone_id(context_drones, result.subject)
    guiding_color = _DRONE_COLORS[guiding_id % len(_DRONE_COLORS)]
    guide_states = _sample_guide(guidance.states)

    fig, ax = plt.subplots(figsize=(8.0, 8.5), dpi=90)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.12)
    images: List[Image.Image] = []
    durations: List[int] = []

    # Act 1 — multi-drone sector search.
    for i, frame in enumerate(result.frames):
        render_planner_frame(ax, result, hill, frame)
        images.append(_frame_to_image(fig))
        durations.append(_search_duration_ms(frame, is_last_of_search=(i == len(result.frames) - 1)))

    # Act 2 — guide home.
    for j, fs in enumerate(guide_states):
        _render_guide_phase(ax, grid, hill, located_posterior, guidance,
                            guiding_color, context_drones, lkp, fs)
        images.append(_frame_to_image(fig))
        durations.append(_guide_duration_ms(j, len(guide_states)))

    plt.close(fig)
    images[0].save(str(out_path), save_all=True, append_images=images[1:],
                   duration=durations, loop=0, disposal=2, optimize=False)


def run_combined(seed: int = 0, n_drones: int = 3) -> Optional[Tuple[PlannerResult, GuidanceResult]]:
    """
    Run multi-drone search to a locate, then plan + simulate the guide-home phase.

    Args:
        seed: Detector-sim seed.
        n_drones: Fleet size for the search phase.

    Returns:
        (search_result, guidance) if it located, else None.

    Why:
        The data half of the combined demo, separated from rendering so a test can assert the
        end-to-end behavior (search locates AND the subject is guided home) without drawing.
    """
    result = run_multi_drone(seed=seed, n_drones=n_drones)
    if result.located_event is None:
        return None
    terrain = RasterTerrain(result.cfg)
    lkp = result.grid.latlon_to_cell(*result.cfg.lkp_latlon)
    path = plan_return_path(result.grid, terrain, result.subject, lkp, cfg=result.cfg)
    guidance = simulate_guidance(result.grid, terrain, path)
    return result, guidance


def main(seed: int = 0, n_drones: int = 3) -> None:
    """
    Produce the combined search→locate→guide-home GIF on real terrain.

    Args:
        seed: Detector-sim seed.
        n_drones: Fleet size (defaults to 3 — the multi-drone coordination showcase).

    Why:
        One command for the headline combined artifact: the fleet finds the subject, then the
        finder leads them home — the system's whole arc in a single animation.
    """
    _OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        combined = run_combined(seed=seed, n_drones=n_drones)
    except FileNotFoundError as exc:
        print(f"[!] {exc}\n[!] This demo needs the DEM + WorldCover rasters in data/terrain/.")
        return
    if combined is None:
        print("[!] Search finished WITHOUT locating — nothing to guide home.")
        return

    result, guidance = combined
    ev = result.located_event
    print(f"Combined demo ({n_drones} drones): located at {ev.cell}, guiding home to "
          f"{result.grid.latlon_to_cell(*result.cfg.lkp_latlon)}.")
    print(f"  route {guidance.total_length_m:,.0f} m  ·  sim time {guidance.states[-1].t/60:.1f} min  "
          f"·  arrived = {guidance.arrived}")

    out = _OUTPUT_DIR / f"search_and_guide_{n_drones}drones.gif"
    build_combined_animation(result, guidance, out)
    print(f"\nGIF written to: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combined multi-drone search + guide-home demo.")
    parser.add_argument("--drones", type=int, default=3, help="fleet size for the search phase")
    parser.add_argument("--seed", type=int, default=0, help="detector-sim seed")
    args = parser.parse_args()
    main(seed=args.seed, n_drones=args.drones)
