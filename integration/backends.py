# =============================================================================
# integration/backends.py
# -----------------------------------------------------------------------------
# Responsible for: The DETECTION SOURCE abstraction — one interface (DetectorBackend)
#                  with two implementations: SimulatorBackend (geometry-driven, the demo
#                  path that locates today) and YoloBackend (the real detector on footage).
# Role in project: The source-agnostic seam. Both backends emit the SAME brain DetectorOutput
#                  (interfaces §2), so everything downstream — GeoReferencer, SearchBrain,
#                  the dashboard — is byte-identical regardless of which source is active.
#                  Swapping simulator -> real footage is choosing a backend, not a rewrite.
# Role/pattern: This is the Strategy pattern — the loop depends on the DetectorBackend
#               interface, and the concrete strategy (simulator vs YOLO) is injected at the
#               edge. It is also the seam the kickoff's "build seams, not futures" calls for:
#               the real detector is built and tested now, but the visible demo keeps running
#               on the simulator until real footage + best.pt arrive.
# Assumptions: SimulatorBackend reuses the brain's DetectorSimulator (src/demo/detector_sim);
#              YoloBackend reuses Unit 1's adapter + Unit 2's VideoFrameSource. The detector
#              deps (ultralytics/cv2) are only touched by YoloBackend, so importing this
#              module is cheap (no torch).
# =============================================================================

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from src.common.contracts import DetectorOutput
from src.demo.detector_sim import DetectorSimulator
from src.demo.mock_stream import ScriptedFrame

from integration import detector_adapter
from integration.telemetry import VideoFrameSource

# Default keep-classes for the real detector — person only (the single subject class). Kept
# here too so a caller configuring a backend doesn't have to import the adapter's internals.
_DEFAULT_KEEP_CLASSES = frozenset({"person"})


@runtime_checkable
class DetectorBackend(Protocol):
    """
    The detection-source contract the loop depends on.

    Why:
        Defining the seam as a Protocol (structural typing) means a backend just needs a
        detect(...) method of the right shape — no base class to inherit, no coupling. The
        loop is written against THIS, so neither backend leaks into the loop's logic.
    """

    def detect(self, frame_index: int, scripted: ScriptedFrame) -> DetectorOutput:
        """
        Produce the DetectorOutput for one frame of the scripted feed.

        Args:
            frame_index: 0-based position of this frame in the scripted feed (lets a video
                backend pick the matching image; the simulator ignores it).
            scripted: The ScriptedFrame (CameraPose + sensor_type + timestamp) for this step.

        Returns:
            A brain DetectorOutput (interfaces §2) — pixel-space, geography-blind.
        """
        ...


class SimulatorBackend:
    """
    Detection source backed by the brain's DetectorSimulator (geometry-driven).

    Why:
        This is the demo path: it produces realistically-noisy detections from the planted
        ground-truth subject + the camera geometry, so the closed loop locates end-to-end
        WITHOUT any footage. It is the source the dashboard renders today; YoloBackend swaps
        in when real footage exists. Injecting the simulator (rather than building it here)
        keeps this testable and mirrors how src/demo/run.py wires it (DRY).
    """

    def __init__(self, simulator: DetectorSimulator) -> None:
        """
        Args:
            simulator: A configured DetectorSimulator (planted subject + visibility + seed).

        Why:
            Dependency injection: the loop builds the simulator from the same scenario it
            builds the brain from, so the subject the simulator plants and the subject the
            scenario plants are guaranteed identical.
        """
        self._sim = simulator

    def detect(self, frame_index: int, scripted: ScriptedFrame) -> DetectorOutput:
        """
        Simulate a DetectorOutput from this frame's pose + sensor mode.

        Args:
            frame_index: Unused (the simulator is driven by geometry, not footage).
            scripted: The ScriptedFrame whose pose/sensor/timestamp drive the simulation.

        Returns:
            The simulated DetectorOutput for this frame.

        Why:
            Delegates straight to the existing, tested simulator so there is no second copy
            of the detection-noise model — the integration layer only adapts, never reimplements.
        """
        return self._sim.simulate(scripted.pose, scripted.sensor_type, scripted.timestamp)


class YoloBackend:
    """
    Detection source backed by the real YOLO detector running on video footage.

    Why:
        The production path: real frames -> Unit 1's adapter -> brain DetectorOutput. Built
        and unit-testable now; exercised end-to-end once real RGB footage with a visible
        person and a fine-tuned best.pt land (today it runs on pretrained yolo11n.pt). Holds
        the model + video together so the loop just calls detect() per frame.
    """

    def __init__(
        self,
        model,
        video: VideoFrameSource,
        *,
        model_id: str,
        conf: float = 0.25,
        imgsz: int = 960,
        keep_classes: Iterable[str] = _DEFAULT_KEEP_CLASSES,
    ) -> None:
        """
        Args:
            model: A loaded Ultralytics YOLO (from detector_adapter.load_detector).
            video: A VideoFrameSource opened on the footage.
            model_id: Provenance string stamped on every DetectorOutput (e.g.
                "yolo11n-pretrained"); becomes "best.pt-finetuned" after the swap.
            conf: YOLO confidence threshold.
            imgsz: YOLO inference image size.
            keep_classes: Class names to keep (person-only by default).

        Why:
            All the real-detector knobs live here, behind the DetectorBackend seam, so the
            loop stays modality- and model-agnostic — switching weights or sensor is a
            construction-time parameter, never a loop edit.
        """
        self._model = model
        self._video = video
        self._model_id = model_id
        self._conf = conf
        self._imgsz = imgsz
        self._keep_classes = keep_classes

    def detect(self, frame_index: int, scripted: ScriptedFrame) -> DetectorOutput:
        """
        Read the footage frame for this step and run the detector on it.

        Args:
            frame_index: Position in the scripted feed; used (clamped) as the video frame
                index. The footage<->pose 1:1 map is the honest approximation noted in
                telemetry.py — finer alignment is a tuning seam, not a redesign.
            scripted: The ScriptedFrame supplying frame_id, sensor_type, and timestamp so the
                DetectorOutput joins correctly to its CameraPose at the geo boundary.

        Returns:
            The real DetectorOutput for this frame (possibly empty -> a non-detection signal).

        Why:
            The pose's frame_id/sensor/timestamp are carried onto the output here (the
            detector itself is geography- and clock-blind), which is exactly what lets the
            GeoReferencer join this back to the right CameraPose downstream.
        """
        frame = self._video.frame(frame_index)
        return detector_adapter.infer(
            self._model,
            frame,
            frame_id=scripted.pose.frame_id,
            timestamp=scripted.timestamp,
            sensor_type=scripted.sensor_type,
            model_id=self._model_id,
            conf=self._conf,
            imgsz=self._imgsz,
            keep_classes=self._keep_classes,
        )
