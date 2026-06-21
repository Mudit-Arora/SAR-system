# =============================================================================
# guide_home.py
# -----------------------------------------------------------------------------
# Responsible for: The REAL-TERRAIN animated showcase of the drone-as-guide feature —
#                  run the closed loop to a locate, plan a terrain-aware route back to the
#                  operators (LKP), then animate the drone LEADING the subject home (staying
#                  within sight) over a DEM hillshade, prior find still glowing for context.
# Role in project: The feasibility artifact for "act 2": after the find, the drone guides the
#                  mobile subject out instead of dispatching rangers to carry them. Mirrors
#                  src/demo/showcase.py's render/animation machinery (reused, not re-built).
# Run: PYTHONPATH=. .venv/bin/python -m src.demo.guide_home
# Assumptions: real DEM + WorldCover rasters in data/terrain/ (errors clearly if absent).
#              The detector is SIMULATED; geo, the brain, the route planner, and the guidance
#              sim are the real code. Subject-follows-beacon is a feasibility simplification.
# =============================================================================

from __future__ import annotations

import pathlib
from typing import List

import matplotlib

matplotlib.use("Agg")  # headless: render frames without a display server
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from src.search.guide import GuidanceResult, GuideState, simulate_guidance
from src.search.return_path import path_length_m, plan_return_path
# Reuse the showcase's loop driver + render machinery (DRY — one hillshade/belief/GIF stack).
from src.demo.showcase import (
    _OUTPUT_DIR,
    _frame_to_image,
    draw_belief_layer,
    drive_loop,
    hillshade,
)

# Keep the GIF watchable: the guidance sim emits hundreds of ticks, so we sample down to about
# this many motion frames (plus held intro/outro beats). A display concern, not a sim change.
_TARGET_MOTION_FRAMES = 48


def _sample_states(states: List[GuideState]) -> List[GuideState]:
    """
    Down-sample the guidance ticks to a watchable number of motion frames (last kept).

    Args:
        states: All GuideStates from the sim (can be hundreds).

    Returns:
        A strided subset, always including the final (arrival) state.

    Why:
        The sim runs at a fine dt for smooth kinematics; the GIF only needs ~50 frames to read
        as continuous motion. Striding keeps the animation small without re-running the sim coarsely.
    """
    if len(states) <= _TARGET_MOTION_FRAMES:
        return states
    stride = max(1, len(states) // _TARGET_MOTION_FRAMES)
    sampled = states[::stride]
    if sampled[-1] is not states[-1]:
        sampled.append(states[-1])
    return sampled


def _render_guide_frame(ax, grid, posterior, hill, result: GuidanceResult, lkp_cell, fs: GuideState) -> None:
    """
    Draw one guide-home frame: terrain + faded find + route + home + drone leading the subject.

    Args:
        ax: The matplotlib axis (cleared and redrawn per frame).
        grid: The shared GridSpec.
        posterior: The located posterior (faded backdrop — where the subject was found).
        hill: Precomputed hillshade.
        result: The GuidanceResult (route + home + sight distance).
        lkp_cell: The operators/home cell (drawn prominently).
        fs: The GuideState to render (subject + drone positions this frame).

    Why:
        One function the animation calls per frame. The route is the planned walkable path; the
        drone (lime diamond) leads, the subject (red dot) follows, and a yellow tether makes the
        "within sight, follow me" relationship literal. The faded posterior keeps the find in
        view so the story reads as one continuous arc: located -> guided home.
    """
    ax.clear()
    draw_belief_layer(ax, posterior, hill)  # gray hillshade + faded find glow

    # The search region boundary (matches the showcase framing).
    ax.add_patch(Rectangle((-0.5, -0.5), grid.n_cols, grid.n_rows, fill=False,
                           edgecolor="lime", linewidth=2.0, clip_on=False))

    # The planned route home (subject -> operators), and the portion already walked.
    rows = [c[0] for c in result.path]
    cols = [c[1] for c in result.path]
    ax.plot(cols, rows, "--", color="#7CFC00", lw=1.6, alpha=0.55, label="planned route home")

    # Operators / home marker (where the rangers are).
    ax.scatter([lkp_cell[1]], [lkp_cell[0]], marker="s", s=150, c="deepskyblue",
               edgecolors="white", linewidths=1.4, zorder=7, label="operators (home)")
    ax.annotate("operators", (lkp_cell[1], lkp_cell[0]), textcoords="offset points",
                xytext=(8, 6), color="white", fontsize=8, fontweight="bold")

    # The line of sight tether: the subject follows the drone, the drone stays within sight.
    sr, sc = fs.subject_pos
    dr, dc = fs.drone_pos
    ax.plot([sc, dc], [sr, dr], "-", color="gold", lw=1.4, alpha=0.9, zorder=8)

    # The subject (follower) and the drone (leader).
    ax.scatter([sc], [sr], marker="o", s=120, c="red", edgecolors="white", linewidths=1.2,
               zorder=9, label="subject (following)")
    ax.scatter([dc], [dr], marker="D", s=120, c="lime", edgecolors="black", linewidths=1.2,
               zorder=9, label="drone (leading)")

    remaining_m = max(0.0, result.total_length_m - fs.subject_s)
    if fs.subject_s >= result.total_length_m:
        title = "★ HOME — subject guided back to the operators"
    else:
        title = "GUIDING HOME — drone leads the subject back to the rangers"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.text(0.5, -0.07,
            f"{remaining_m:,.0f} m to go   ·   route {result.total_length_m:,.0f} m   ·   "
            f"drone lead ≤ {result.sight_distance_m:.0f} m (in sight)",
            transform=ax.transAxes, ha="center", va="top", fontsize=9)
    ax.set_xlabel("column (50 m cells)")
    ax.set_ylabel("row (50 m cells)")
    ax.legend(loc="upper right", fontsize=7)


def _frame_duration_ms(index: int, n_frames: int) -> int:
    """Hold the opening plan and the arrival; brisk in between. Why: paces the story for a viewer."""
    if index == 0:
        return 1600          # let the planned route + the find register
    if index == n_frames - 1:
        return 2800          # dwell on the safe arrival
    return 150               # steady walking motion


def build_guide_animation(grid, posterior, result: GuidanceResult, lkp_cell, out_path: pathlib.Path) -> None:
    """
    Render the guidance phase to an animated GIF.

    Args:
        grid: The shared GridSpec.
        posterior: The located posterior (faded backdrop).
        result: The GuidanceResult to animate.
        lkp_cell: The operators/home cell.
        out_path: Where to write the .gif.

    Why:
        Same PIL-frame + per-frame-duration approach as the showcase (computing the hillshade
        once), so the guide-home artifact matches the look and pacing of showcase.gif.
    """
    hill = hillshade(grid)
    frames = _sample_states(result.states)
    fig, ax = plt.subplots(figsize=(8.0, 8.5), dpi=90)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.10)

    images = []
    durations = []
    for i, fs in enumerate(frames):
        _render_guide_frame(ax, grid, posterior, hill, result, lkp_cell, fs)
        images.append(_frame_to_image(fig))
        durations.append(_frame_duration_ms(i, len(frames)))
    plt.close(fig)

    images[0].save(str(out_path), save_all=True, append_images=images[1:],
                   duration=durations, loop=0, disposal=2, optimize=False)


def _write_still(grid, posterior, result: GuidanceResult, lkp_cell, out_path: pathlib.Path) -> None:
    """Write a single PNG of the arrival frame. Why: a slide-friendly still of the safe return."""
    fig, ax = plt.subplots(figsize=(8.0, 8.5), dpi=130)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.10)
    hill = hillshade(grid)
    _render_guide_frame(ax, grid, posterior, hill, result, lkp_cell, result.states[-1])
    fig.savefig(out_path)
    plt.close(fig)


def main(seed: int = 0) -> None:
    """
    Run search -> locate -> plan route -> guide home, and write the GIF + arrival still.

    Args:
        seed: Detector-simulator seed (the run is deterministic per seed).

    Why:
        One command for the act-2 artifact: on real Marin terrain, the drone finds the subject
        and then LEADS them back to the operators along a walkable route, staying in sight the
        whole way. Errors clearly if the rasters are absent.
    """
    _OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        result_loop = drive_loop(seed=seed)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        print("[!] guide_home needs the real DEM + WorldCover rasters in data/terrain/.")
        return
    if result_loop.located_event is None:
        print("[!] Loop finished WITHOUT locating — nothing to guide home.")
        return

    grid = result_loop.grid
    cfg = result_loop.cfg
    terrain = result_loop.terrain
    subject = result_loop.subject
    posterior = result_loop.frames[-1].posterior
    lkp_cell = grid.latlon_to_cell(*cfg.lkp_latlon)

    path = plan_return_path(grid, terrain, subject, lkp_cell, cfg=cfg)
    guidance = simulate_guidance(grid, terrain, path)

    print(f"Guide-home on real terrain: found at {subject}, operators at {lkp_cell}.")
    print(f"  route: {len(path)} cells / {path_length_m(path, grid):,.0f} m  ·  "
          f"sim time {guidance.states[-1].t/60:.1f} min  ·  arrived = {guidance.arrived}")

    gif_path = _OUTPUT_DIR / "guide_home.gif"
    still_path = _OUTPUT_DIR / "guide_home_arrived.png"
    build_guide_animation(grid, posterior, guidance, lkp_cell, gif_path)
    _write_still(grid, posterior, guidance, lkp_cell, still_path)
    print(f"\nGIF written to:   {gif_path}")
    print(f"Still written to: {still_path}")


if __name__ == "__main__":
    main()
