# =============================================================================
# georeferencer.py
# -----------------------------------------------------------------------------
# Responsible for: Turning a pixel-space DetectorOutput + a CameraPose into the
#                  ground-referenced Observation the brain consumes — which ground
#                  cells the frame covered (footprint) and where each detection
#                  landed (detections_ground). Geography lives here and nowhere else.
# Role in project: interfaces.md §4. This is "boundary A" (detector -> geo). Because
#                  the detector is a SEPARATE track, geo defends its input the same
#                  way the brain defends its own (sanitize-and-log), and normalizes
#                  via a thin adapter so the contract is a target, not a hard
#                  constraint. sensor_type and confidence pass THROUGH untouched —
#                  the detector's calibration never leaks into geo or the brain.
# Baseline (honest scope): the footprint is a flat-ground rectangle centered at the
#                  drone's nadir point, rotated by heading, with linear pixel->ground
#                  interpolation. It IGNORES terrain elevation and the gimbal-pitch
#                  forward shift (assumes near-nadir). The full perspective projection
#                  is an upgrade behind this same reference() seam.
# =============================================================================

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import numpy as np

from src.common.config import DEFAULT_CONFIG, BrainConfig
from src.common.contracts import (
    CameraPose,
    CellCoverage,
    Detection,
    DetectorOutput,
    GroundDetection,
    Observation,
    SensorType,
)
from src.common.grid import GridSpec

logger = logging.getLogger(__name__)

# k x k sample points per cell when estimating coverage_fraction (edge cells get a
# fractional value). 4 -> 16 samples; cheap given footprints span only a few cells.
_COVERAGE_SUBSAMPLES = 4

# Local meter point as (east, north).
_PointM = Tuple[float, float]


# --- Boundary A defense: adapter + sanitizer (mirror of the brain's input guard) ---


@dataclass(frozen=True)
class DetectorSanitationReport:
    """
    A tally of what sanitize_detector_output had to fix in one frame.

    Args (fields):
        dropped_detections: Detections dropped (NaN fields, or fully off-frame/zero-area).
        clamped: Values pulled back in range (bbox clipped to the image, confidence to [0,1]).

    Why:
        Same honest-defense pattern as the brain's SanitationReport: report what was
        wrong so a real upstream (detector) bug is visible, not silently swallowed.
    """

    dropped_detections: int = 0
    clamped: int = 0

    @property
    def clean(self) -> bool:
        return self.dropped_detections == 0 and self.clamped == 0


def adapt_detector_output(raw: Any) -> DetectorOutput:
    """
    Normalize whatever the detector emits into a DetectorOutput.

    Args:
        raw: The detector's output. Today: a DetectorOutput (ours / the simulator's).

    Returns:
        A DetectorOutput geo can consume.

    Why:
        THE extension point for contract drift. `interfaces.md §2` is the expected
        shape, not a guarantee — the detector is a separate track. When its real output
        differs (dicts, xyxy boxes, normalized coords, a different confidence scale), we
        map it to DetectorOutput HERE and nothing downstream changes. For now the only
        known inputs already are DetectorOutput, so this is a pass-through that fails
        loudly (pointing back here) on an unrecognized shape — rather than guessing.
    """
    if isinstance(raw, DetectorOutput):
        return raw
    raise TypeError(
        f"adapt_detector_output: unrecognized detector output type {type(raw)!r}. "
        "Extend this adapter to map the detector's actual format to DetectorOutput."
    )


def sanitize_detector_output(
    out: DetectorOutput, image_size_px: Tuple[int, int]
) -> Tuple[DetectorOutput, DetectorSanitationReport]:
    """
    Clean a DetectorOutput: clamp boxes to the image, drop NaN/degenerate detections.

    Args:
        out: The (adapted) DetectorOutput.
        image_size_px: (width, height) the projection uses — the POSE's image size, the
            authoritative frame the bbox pixels must be expressed in.

    Returns:
        (clean_out, report): a DetectorOutput whose detections are finite and inside the
        image, plus a report of the fixes.

    Why:
        Boundary A defense. A box partly off-frame, a NaN confidence, or a zero-area box
        would otherwise produce a garbage or NaN ground cell. We clamp/drop here so the
        projection can assume sane pixel boxes — the symmetric counterpart to the brain
        sanitizing its Observations.
    """
    width, height = float(image_size_px[0]), float(image_size_px[1])
    dropped = 0
    clamped = 0
    clean_detections: List[Detection] = []

    for det in out.detections:
        x, y, w, h = det.bbox_xywh
        if not all(math.isfinite(v) for v in (x, y, w, h)) or not math.isfinite(det.confidence):
            dropped += 1
            continue
        # Clip the box to the image rectangle.
        x0, y0 = max(0.0, x), max(0.0, y)
        x1, y1 = min(width, x + w), min(height, y + h)
        if x1 <= x0 or y1 <= y0:
            dropped += 1          # fully off-frame or non-positive area
            continue
        # Count a clamp only if an edge was ACTUALLY outside the image — comparing the
        # rebuilt box to the original would false-positive on float round-off (x+w-x != w).
        box_clipped = (x < 0.0) or (y < 0.0) or (x + w > width) or (y + h > height)
        new_box = (x0, y0, x1 - x0, y1 - y0) if box_clipped else (x, y, w, h)
        conf = min(max(det.confidence, 0.0), 1.0)
        if box_clipped or conf != det.confidence:
            clamped += 1
        clean_detections.append(Detection(bbox_xywh=new_box, confidence=conf, class_name=det.class_name))

    clean_out = DetectorOutput(
        frame_id=out.frame_id,
        timestamp=out.timestamp,
        detections=clean_detections,
        model_id=out.model_id,
        sensor_type=out.sensor_type,
        inference_ms=out.inference_ms,
    )
    return clean_out, DetectorSanitationReport(dropped_detections=dropped, clamped=clamped)


# --- Baseline projection math (flat ground, nadir-centered, linear interpolation) ---


def _ground_half_extents_m(pose: CameraPose) -> Tuple[float, float]:
    """
    Half-width (cross-track) and half-height (along-track) of the ground footprint.

    Args:
        pose: The camera pose (altitude + FOV).

    Returns:
        (half_cross_m, half_along_m): half the footprint's cross-track and along-track
        extent, in meters.

    Why:
        For a nadir camera over flat ground, the footprint is 2*alt*tan(fov/2) on a side.
        Image WIDTH maps to cross-track (hfov); image HEIGHT to along-track (vfov).
    """
    hfov_deg, vfov_deg = pose.fov_deg
    alt = pose.altitude_agl_m
    half_cross = alt * math.tan(math.radians(hfov_deg) / 2.0)
    half_along = alt * math.tan(math.radians(vfov_deg) / 2.0)
    return half_cross, half_along


def _pixel_to_ground_local(px: float, py: float, pose: CameraPose, grid: GridSpec) -> _PointM:
    """
    Project an image pixel to a ground point in local meters (east, north).

    Args:
        px, py: Pixel coordinates (origin top-left, x right, y down).
        pose: The camera pose.
        grid: GridSpec, for the drone's nadir point in local meters.

    Returns:
        (east_m, north_m) of the ground point.

    Why:
        Baseline linear mapping: place the pixel within the footprint rectangle
        (cross-track from image x, along-track from image y with the top = forward),
        rotate by heading so the image aligns to the ground, and offset from the nadir.
        Heading convention: 0 = north, 90 = east; forward = (sinθ, cosθ), right =
        (cosθ, -sinθ) (90° clockwise of forward).
    """
    width, height = pose.image_size_px
    half_cross, half_along = _ground_half_extents_m(pose)

    cross_frac = (px / width) - 0.5     # +0.5 at the right image edge
    along_frac = 0.5 - (py / height)    # +0.5 at the top image edge (= forward)
    cross_m = cross_frac * (2.0 * half_cross)
    along_m = along_frac * (2.0 * half_along)

    theta = math.radians(pose.heading_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    east = along_m * sin_t + cross_m * cos_t      # forward_e=sinθ, right_e=cosθ
    north = along_m * cos_t - cross_m * sin_t     # forward_n=cosθ, right_n=-sinθ

    nadir_e, nadir_n = grid.latlon_to_local_m(*pose.drone_latlon)
    return nadir_e + east, nadir_n + north


def _point_in_convex_quad(point: _PointM, quad: List[_PointM]) -> bool:
    """
    Whether a point lies inside a convex quadrilateral (the rotated footprint).

    Args:
        point: (east, north) to test.
        quad: 4 ordered (east, north) corners (a convex quad).

    Returns:
        True if the point is inside or on the boundary.

    Why:
        Coverage estimation samples cell points against the rotated footprint. The
        sign-of-cross-product test works for any winding (all cross products share a
        sign), so we don't depend on which way the projection orders the corners.
    """
    sign = 0
    px, py = point
    for i in range(4):
        ax, ay = quad[i]
        bx, by = quad[(i + 1) % 4]
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        if cross > 1e-9:
            if sign < 0:
                return False
            sign = 1
        elif cross < -1e-9:
            if sign > 0:
                return False
            sign = -1
        # cross ~ 0 -> on the edge, allowed
    return True


class GeoReferencer:
    """
    Projects pixel-space detections and frame coverage onto the shared grid.

    Why:
        A single place where geography enters the pipeline (interfaces.md decision #1).
        Constructed with an optional per-cell visibility array so the geometry (here)
        and the visibility weighting (Geo Unit 3, fed from terrain) stay decoupled.
    """

    def __init__(
        self,
        grid: GridSpec,
        visibility: Optional[np.ndarray] = None,
        config: Optional[BrainConfig] = None,
    ) -> None:
        """
        Args:
            grid: The shared GridSpec.
            visibility: Optional (n_rows, n_cols) base visibility in [0, 1] (canopy lowers
                it). None -> treated as all 1.0 (fully visible). Fed from
                TerrainProvider.visibility(grid).
            config: Tunables (the sensor visibility factor). Defaults to DEFAULT_CONFIG.
        Why:
            Injecting the visibility ARRAY (not a TerrainProvider) keeps geo independent
            of the terrain implementation — geo does geometry + a config lookup, terrain
            supplies the layer.
        """
        self._grid = grid
        self._visibility = visibility
        self._cfg = config or DEFAULT_CONFIG

    def _visibility_weight(self, cell: Tuple[int, int], sensor_type: SensorType) -> float:
        """
        The visibility_weight for a footprint cell: base canopy visibility x sensor factor.

        Args:
            cell: (row, col).
            sensor_type: COLOR or THERMAL.

        Returns:
            visibility_weight in [0, 1].

        Why:
            visibility_weight = base_visibility(cell) * sensor_factor(sensor). The base
            comes from terrain (canopy), the factor from config (thermal sees better under
            canopy). Clamped to [0, 1] so a thermal boost can't exceed full visibility.
        """
        base = 1.0 if self._visibility is None else float(self._visibility[cell[0], cell[1]])
        factor = self._cfg.visibility_factor_for(sensor_type.value)
        return min(max(base * factor, 0.0), 1.0)

    def _footprint(self, pose: CameraPose, sensor_type: SensorType) -> List[CellCoverage]:
        """
        Rasterize the ground footprint to grid cells with coverage_fraction.

        Args:
            pose: The camera pose.
            sensor_type: Carried through for the visibility weight.

        Returns:
            A list of CellCoverage for the in-bounds cells the frame overlapped.

        Why:
            Project the four image corners to the ground, find the cells in their bounding
            box, and estimate each cell's coverage by subsampling against the rotated
            footprint quad. Drives the brain's non-detection clearing.
        """
        corners = [
            _pixel_to_ground_local(cx, cy, pose, self._grid)
            for (cx, cy) in [(0.0, 0.0), (pose.image_size_px[0], 0.0),
                             (pose.image_size_px[0], pose.image_size_px[1]),
                             (0.0, pose.image_size_px[1])]
        ]
        cell = self._grid.cell_size_m
        easts = [p[0] for p in corners]
        norths = [p[1] for p in corners]
        c_lo, c_hi = int(math.floor(min(easts) / cell)), int(math.floor(max(easts) / cell))
        r_lo, r_hi = int(math.floor(min(norths) / cell)), int(math.floor(max(norths) / cell))

        k = _COVERAGE_SUBSAMPLES
        footprint: List[CellCoverage] = []
        for r in range(max(0, r_lo), min(self._grid.n_rows - 1, r_hi) + 1):
            for c in range(max(0, c_lo), min(self._grid.n_cols - 1, c_hi) + 1):
                inside = 0
                for i in range(k):
                    for j in range(k):
                        e = (c + (i + 0.5) / k) * cell
                        n = (r + (j + 0.5) / k) * cell
                        if _point_in_convex_quad((e, n), corners):
                            inside += 1
                frac = inside / (k * k)
                if frac > 0.0:
                    footprint.append(
                        CellCoverage(
                            cell=(r, c),
                            coverage_fraction=frac,
                            visibility_weight=self._visibility_weight((r, c), sensor_type),
                        )
                    )
        return footprint

    def _project_detections(self, out: DetectorOutput, pose: CameraPose) -> List[GroundDetection]:
        """
        Project each detection's box center to a ground cell.

        Args:
            out: The sanitized DetectorOutput.
            pose: The camera pose.

        Returns:
            A list of GroundDetection (cell + confidence). Cells MAY be off-grid (a
            detection near the region edge) — geo emits them as computed; the brain's
            sanitizer is the safety net that drops them (defense in depth).

        Why:
            Geo's job is to place the box; deciding what to do with an off-region
            detection is the brain's boundary, already hardened. Keeping geo simple
            (project, don't filter) is what makes the layered defense testable.
        """
        ground: List[GroundDetection] = []
        for det in out.detections:
            x, y, w, h = det.bbox_xywh
            cx, cy = x + w / 2.0, y + h / 2.0
            east_m, north_m = _pixel_to_ground_local(cx, cy, pose, self._grid)
            cell = self._grid.local_m_to_cell(east_m, north_m)
            ground.append(GroundDetection(cell=cell, confidence=det.confidence))
        return ground

    def reference(self, detector_output: Any, camera_pose: CameraPose) -> Observation:
        """
        Fuse a DetectorOutput + CameraPose into the Observation the brain consumes.

        Args:
            detector_output: The detector's output for a frame (adapted internally).
            camera_pose: The telemetry for the SAME frame (joined by frame_id).

        Returns:
            An Observation: footprint cells + ground detections + sensor_type.

        Why:
            The whole boundary in one call. Adapt (drift tolerance) -> verify the
            frame_id join -> sanitize (defense) -> project geometry. sensor_type and
            confidence pass through to the brain unchanged.
        """
        out = adapt_detector_output(detector_output)

        # Frame fusion guard: the detector output and telemetry must be the same frame.
        if out.frame_id != camera_pose.frame_id:
            raise ValueError(
                f"frame_id mismatch fusing detector ({out.frame_id!r}) and pose "
                f"({camera_pose.frame_id!r}); they must describe the same frame."
            )

        clean, report = sanitize_detector_output(out, camera_pose.image_size_px)
        if not report.clean:
            logger.warning(
                "geo sanitized frame %s: dropped=%d clamped=%d",
                clean.frame_id, report.dropped_detections, report.clamped,
            )

        sensor_type = clean.sensor_type
        # Degenerate pose (can't see ground): emit an empty footprint rather than NaN math.
        if camera_pose.altitude_agl_m <= 0.0 or min(camera_pose.fov_deg) <= 0.0:
            logger.warning(
                "geo: degenerate pose for frame %s (alt=%.1f, fov=%s); empty footprint",
                clean.frame_id, camera_pose.altitude_agl_m, camera_pose.fov_deg,
            )
            return Observation(clean.frame_id, clean.timestamp, [], [], sensor_type)

        footprint = self._footprint(camera_pose, sensor_type)
        detections_ground = self._project_detections(clean, camera_pose)
        return Observation(
            frame_id=clean.frame_id,
            timestamp=clean.timestamp,
            footprint=footprint,
            detections_ground=detections_ground,
            sensor_type=sensor_type,
        )
