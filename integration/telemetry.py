# =============================================================================
# integration/telemetry.py
# -----------------------------------------------------------------------------
# Responsible for: The per-frame INPUT FEED for the integration loop — the scripted
#                  CameraPose stream (one pose per frame index) and, for the real-detector
#                  path, a reader that pulls the matching image frame out of a video file.
# Role in project: interfaces.md §3. In a real drone these poses are GPS+IMU+gimbal; for
#                  the demo they are scripted (the locked "script poses" decision). The
#                  detector is geography-blind, so this is the ONLY place that knows where
#                  the camera was for each frame; the GeoReferencer joins it by frame_id.
# Assumptions: Reuses the brain's build_scripted_path (DRY — one source of the flight path
#              for both the src/ demo and integration). cv2 is imported lazily, so the
#              simulator-backed loop (no video) never needs opencv. Footage<->pose alignment
#              is a 1:1 index map clamped at the ends — an honest, tunable approximation
#              (no real footage exists yet; see docs/brain_followups.md).
# =============================================================================

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from src.common.config import BrainConfig
from src.common.grid import GridSpec
from src.demo.mock_stream import ScriptedFrame, build_scripted_path


def build_pose_feed(
    grid: GridSpec, cfg: BrainConfig, offset: Optional[Tuple[int, int]] = None
) -> Tuple[Tuple[float, float], List[ScriptedFrame]]:
    """
    Build the scripted CameraPose feed and the planted ground-truth subject location.

    Args:
        grid: The shared GridSpec.
        cfg: Brain config (LKP, cell size, ...).
        offset: (d_row, d_col) of the subject from the LKP. None -> the synthetic default;
            the real-terrain scenario passes REAL_TERRAIN_SUBJECT_OFFSET.

    Returns:
        (subject_latlon, frames): the ground-truth subject (lat, lon) and the ordered
        ScriptedFrames (each carrying a CameraPose + sensor_type + timestamp).

    Why:
        A thin, named pass-through over the brain's build_scripted_path so the integration
        layer has ONE import point for the pose feed instead of every backend/loop reaching
        into src.demo. Keeping it a wrapper (not a reimplementation) is the DRY choice — the
        flight path is defined once and shared by the src/ demo and this integration loop.
    """
    return build_scripted_path(grid, cfg, offset)


class VideoFrameSource:
    """
    Reads image frames from a video file by frame index (for the real-detector path).

    Why:
        The YoloBackend needs the actual pixels for each scripted frame; this wraps OpenCV's
        VideoCapture behind a tiny by-index reader so the backend stays about detection, not
        I/O. Built lazily (cv2 imported on construction) so nothing here is paid for unless a
        real video is actually used.
    """

    def __init__(self, video_path: str) -> None:
        """
        Open the video and cache its frame count.

        Args:
            video_path: Path to a video file readable by OpenCV (mp4/mov/...).

        Why:
            We open once and seek per index rather than decoding the whole clip into memory,
            which keeps memory flat for long footage. cv2 is imported here (not at module
            top) so the simulator path never requires opencv.
        """
        import cv2  # lazy: only the real-detector path needs opencv

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(video_path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"VideoFrameSource: could not open video {video_path!r}")
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        self.video_path = video_path

    def frame(self, index: int) -> np.ndarray:
        """
        Return the image at a given (clamped) frame index as an (H, W, 3) array.

        Args:
            index: Desired frame index; clamped into [0, frame_count - 1] so a scripted feed
                longer than the clip just re-reads the last frame instead of failing.

        Returns:
            The decoded frame (BGR, as OpenCV returns it — Ultralytics accepts BGR arrays).

        Why:
            Seeking by index (not sequential read) makes the loop reproducible: scripted
            frame i always maps to the same video frame, so re-runs are deterministic. The
            clamp is the honest stand-in for real footage<->pose alignment, which would
            otherwise need timestamps we don't have for synthetic footage.
        """
        if self.frame_count <= 0:
            raise RuntimeError(f"VideoFrameSource: video {self.video_path!r} has no frames")
        idx = max(0, min(index, self.frame_count - 1))
        self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"VideoFrameSource: failed to read frame {idx} of {self.video_path!r}")
        return frame

    def release(self) -> None:
        """Release the underlying VideoCapture. Why: free the file handle when the loop ends."""
        self._cap.release()
