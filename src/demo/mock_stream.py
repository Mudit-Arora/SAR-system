# =============================================================================
# mock_stream.py
# -----------------------------------------------------------------------------
# Responsible for: The scripted FLIGHT PATH for the demo — an ordered list of
#                  CameraPose frames (a SW lawnmower sweep, then an overflight of
#                  the subject), plus the planted ground-truth subject location.
# Role in project: Drives the real chain now: scripted pose -> detector simulator
#                  (detector_sim.py) -> GeoReferencer -> brain. Replaces the old
#                  direct-Observation mock; the subject's map cell now EMERGES from
#                  the projection instead of being hand-placed. When the real
#                  GeoReferencer/detector exist, this scripted path is the same
#                  CameraPose feed a real flight would provide.
# Assumptions: Near-nadir gimbal; sweep frames are positioned so the subject is NOT
#              in their footprint (clean non-detections); overflight frames sit over
#              the subject so it falls in frame.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from src.common.config import BrainConfig
from src.common.contracts import CameraPose, SensorType
from src.common.grid import GridSpec

# Subject ~1.8 km SW of the LKP (demo_scenario §4): moderate prior, partial canopy.
_SUBJECT_OFFSET_ROWS = -26
_SUBJECT_OFFSET_COLS = -23
_FRAME_DT_S = 9.0

# Camera/flight constants (plausible drone parameters).
_FOV_DEG = (70.0, 40.0)
_IMAGE_PX = (1920, 1080)
_SWEEP_ALT_M = 140.0      # higher sweep => larger footprint => clears the corridor more
_SUBJECT_ALT_M = 90.0     # descend over the subject for detail
_SWEEP_PITCH = -88.0      # near nadir
_COLOR_PITCH = -80.0      # slightly oblique over the subject (exposes geo's baseline error)
_THERMAL_PITCH = -75.0
_COLOR_FRAMES = 6         # loiter long enough that canopy misses still leave >= N detections
_THERMAL_FRAMES = 4


@dataclass(frozen=True)
class ScriptedFrame:
    """
    One frame of the scripted flight: telemetry + which sensor mode + sim clock time.

    Args (fields):
        pose: The CameraPose (telemetry) for this frame.
        sensor_type: COLOR or THERMAL (the camera mode this frame).
        timestamp: Sim-clock time, carried onto the DetectorOutput/Observation.

    Why:
        CameraPose (interfaces §3) carries no timestamp or sensor mode; the demo needs
        both per frame, so this small record pairs them without bending the contract.
    """

    pose: CameraPose
    sensor_type: SensorType
    timestamp: float


def subject_cell(grid: GridSpec, cfg: BrainConfig) -> Tuple[int, int]:
    """
    The subject's true cell, ~1.8 km SW of the LKP near the drainage.

    Args:
        grid: The shared GridSpec.
        cfg: Brain config (for the LKP).

    Returns:
        (row, col) of the planted subject (ground truth).

    Why:
        Placed (per demo §4) where the prior is MODERATE and the canopy partial, so the
        update must do real work and the thermal pass earns its corroboration.
    """
    lkp_r, lkp_c = grid.latlon_to_cell(*cfg.lkp_latlon)
    return (lkp_r + _SUBJECT_OFFSET_ROWS, lkp_c + _SUBJECT_OFFSET_COLS)


def _pose(grid: GridSpec, cell, frame_id, heading, alt, pitch) -> CameraPose:
    """A CameraPose whose nadir (drone position) is the center of `cell`."""
    lat, lon = grid.cell_to_latlon(*cell)
    return CameraPose(
        frame_id=frame_id,
        drone_latlon=(lat, lon),
        altitude_agl_m=alt,
        heading_deg=heading,
        gimbal_pitch_deg=pitch,
        fov_deg=_FOV_DEG,
        image_size_px=_IMAGE_PX,
    )


def build_scripted_path(grid: GridSpec, cfg: BrainConfig) -> Tuple[Tuple[float, float], List[ScriptedFrame]]:
    """
    Build the scripted flight path and the planted subject location.

    Args:
        grid: The shared GridSpec.
        cfg: Brain config (LKP).

    Returns:
        (subject_latlon, frames): the ground-truth subject position and the ordered
        ScriptedFrames — a SW lawnmower sweep (clean), then a subject overflight
        (color, then thermal).

    Why:
        The path is map-directed: sweep the high-prior corridor (clearing it via clean
        non-detections), then loiter over the subject's slope. The detector simulator
        decides per frame whether the subject is in view, so detections EMERGE from the
        geometry rather than being scripted.
    """
    lkp_r, lkp_c = grid.latlon_to_cell(*cfg.lkp_latlon)
    subject = subject_cell(grid, cfg)
    subject_latlon = grid.cell_to_latlon(*subject)

    frames: List[ScriptedFrame] = []
    t = 0.0
    frame_no = 1

    # --- Sweep: a boustrophedon over the high-prior corridor band, short of the subject ---
    row_top = lkp_r + 2
    row_bottom = subject[0] + 6        # stay clear of the subject's neighborhood
    col_left = subject[1] - 2
    col_right = lkp_c + 4
    serpentine = True
    for row_c in range(row_top, row_bottom - 1, -4):
        cols = list(range(col_left, col_right + 1, 5))
        heading = 90.0 if serpentine else 270.0   # east-going vs west-going pass
        if not serpentine:
            cols = cols[::-1]
        serpentine = not serpentine
        for col_c in cols:
            frames.append(ScriptedFrame(
                pose=_pose(grid, (row_c, col_c), f"F{frame_no:04d}", heading, _SWEEP_ALT_M, _SWEEP_PITCH),
                sensor_type=SensorType.COLOR,
                timestamp=t,
            ))
            frame_no += 1
            t += _FRAME_DT_S

    # --- Overflight: loiter over the subject. Color first, then a thermal pass. ---
    heading_down_canyon = 225.0  # SW, following the drainage
    for _ in range(_COLOR_FRAMES):    # color frames (partial canopy -> some misses expected)
        frames.append(ScriptedFrame(
            pose=_pose(grid, subject, f"F{frame_no:04d}", heading_down_canyon, _SUBJECT_ALT_M, _COLOR_PITCH),
            sensor_type=SensorType.COLOR,
            timestamp=t,
        ))
        frame_no += 1
        t += _FRAME_DT_S
    for _ in range(_THERMAL_FRAMES):  # thermal corroboration (sees better under canopy)
        frames.append(ScriptedFrame(
            pose=_pose(grid, subject, f"F{frame_no:04d}", heading_down_canyon, _SUBJECT_ALT_M, _THERMAL_PITCH),
            sensor_type=SensorType.THERMAL,
            timestamp=t,
        ))
        frame_no += 1
        t += _FRAME_DT_S

    return subject_latlon, frames
