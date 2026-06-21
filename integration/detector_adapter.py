# =============================================================================
# integration/detector_adapter.py
# -----------------------------------------------------------------------------
# Responsible for: Turning the vendored YOLO detector's per-frame output into the
#                  brain's DetectorOutput contract (interfaces.md §2). Pixel-space in,
#                  pixel-space out — no geography here (that is the GeoReferencer's job).
# Role in project: Boundary A, the detector->brain seam. This is the adapter the brain's
#                  geo boundary (adapt_detector_output / sanitize_detector_output) was
#                  designed for: we produce a clean DetectorOutput, geo consumes it, and
#                  swapping the simulator for the real model is wiring, not redesign.
# Assumptions: The model is an Ultralytics YOLO (yolo11n.pt today, best.pt later — a
#              model_id/weights swap). We keep ONLY person-class boxes (single-class demo)
#              and convert xyxy -> xywh. sensor_type / model_id are PARAMETERS, so the
#              pipeline stays modality-agnostic (color now, thermal later) per the kickoff.
#              ultralytics/cv2 are imported lazily so importing this module needs no torch.
# =============================================================================

from __future__ import annotations

import time
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from src.common.contracts import Detection, DetectorOutput, SensorType

# Class names we treat as a subject. The weekend is person-focused (interfaces §2), and a
# fine-tuned best.pt is typically single-class person anyway, so this is the only filter we
# need. Lower-cased for case-insensitive matching against the model's class names.
_DEFAULT_KEEP_CLASSES = frozenset({"person"})


def load_detector(weights: str, device: Optional[str] = None):
    """
    Load an Ultralytics YOLO model from a weights file.

    Args:
        weights: Path to the YOLO weights (e.g. "yolo11n.pt" pretrained, or a fine-tuned
            "best.pt"). The COCO-pretrained nets include a "person" class, so they work
            for the demo until best.pt lands.
        device: Optional Ultralytics device string ("cpu", "0", ...). None lets Ultralytics
            choose (CPU on this Mac).

    Returns:
        An ultralytics.YOLO model ready for .predict().

    Why:
        Isolating the ONE torch-dependent call here keeps the rest of the module (the
        xyxy->Detection conversion) pure and unit-testable without installing torch. The
        import is lazy so merely importing this module — e.g. for the simulator-backed loop
        that never touches YOLO — does not pull the heavy detector stack.
    """
    # Lazy import: ultralytics drags in torch (~hundreds of MB), so we only pay for it when
    # a real model is actually loaded, not on `import integration.detector_adapter`.
    from ultralytics import YOLO

    model = YOLO(weights)
    if device is not None:
        model.to(device)
    return model


def xyxy_to_detections(
    xyxy: np.ndarray,
    confidences: Sequence[float],
    class_ids: Sequence[int],
    names: dict,
    keep_classes: Iterable[str] = _DEFAULT_KEEP_CLASSES,
) -> List[Detection]:
    """
    Convert raw YOLO boxes (xyxy pixel corners) into brain Detection objects.

    Args:
        xyxy: (n, 4) array of pixel-space boxes as [x1, y1, x2, y2] (top-left, bottom-right).
        confidences: Length-n raw detector scores in [0, 1].
        class_ids: Length-n integer class ids, indexing into `names`.
        names: The model's {class_id: class_name} map (Ultralytics `model.names`).
        keep_classes: Class names (case-insensitive) to keep; everything else is dropped.
            Defaults to {"person"} — the single subject class for the weekend.

    Returns:
        A list of brain Detection(bbox_xywh, confidence, class_name), one per kept box,
        with boxes converted from xyxy corners to (x, y, w, h) top-left + size.

    Why:
        This is the pure heart of the adapter: no torch, no Ultralytics objects, just array
        math, so the unit test exercises the xyxy->xywh conversion and the person filter
        directly. The brain expects xywh (interfaces §2); the detector emits xyxy — this is
        exactly the one conversion the seam exists to do.
    """
    keep = {name.lower() for name in keep_classes}
    detections: List[Detection] = []

    # zip is safe even if the arrays are empty (an empty frame -> no detections), which is
    # the meaningful non-detection signal the brain lowers probability on.
    for box, conf, cls_id in zip(xyxy, confidences, class_ids):
        class_name = names.get(int(cls_id), str(int(cls_id)))
        if class_name.lower() not in keep:
            continue
        x1, y1, x2, y2 = (float(v) for v in box)
        # xyxy (corners) -> xywh (top-left + size). max(0, ...) guards against a degenerate
        # box where x2 < x1; the brain's sanitizer also drops non-positive-area boxes, but
        # not emitting a negative width keeps this layer's output well-formed on its own.
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        detections.append(
            Detection(bbox_xywh=(x1, y1, w, h), confidence=float(conf), class_name=class_name)
        )
    return detections


def _extract_boxes(result) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Pull (xyxy, confidence, class_id) NumPy arrays out of one Ultralytics result.

    Args:
        result: A single ultralytics Results object (model.predict(...)[0]).

    Returns:
        (xyxy, confidences, class_ids): an (n, 4) box array and two length-n arrays. All
        empty (shape (0, 4) / (0,)) when the frame had no detections.

    Why:
        Mirrors the vendored detector's parse_results() box extraction, kept as a tiny
        separate function so it is the ONLY place that touches Ultralytics' tensor API.
        Everything downstream is plain NumPy, which is what makes the conversion testable.
    """
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return np.empty((0, 4)), np.empty((0,)), np.empty((0,), dtype=int)
    xyxy = boxes.xyxy.cpu().numpy()
    confidences = boxes.conf.cpu().numpy()
    class_ids = boxes.cls.cpu().numpy().astype(int)
    return xyxy, confidences, class_ids


def infer(
    model,
    frame: np.ndarray,
    *,
    frame_id: str,
    timestamp: float,
    sensor_type: SensorType,
    model_id: str,
    conf: float = 0.25,
    imgsz: int = 960,
    keep_classes: Iterable[str] = _DEFAULT_KEEP_CLASSES,
) -> DetectorOutput:
    """
    Run the detector on one frame and return a brain DetectorOutput (interfaces §2).

    Args:
        model: A loaded Ultralytics YOLO model (from load_detector).
        frame: One image as an (H, W, 3) BGR/RGB NumPy array (an OpenCV frame).
        frame_id: Stable handle for this frame; the join key to its CameraPose.
        timestamp: Sim/wall-clock time the frame was captured.
        sensor_type: COLOR or THERMAL — carried through; the brain's recall depends on it.
            A parameter (not inferred) so the same code path serves either modality.
        model_id: Provenance string (e.g. "yolo11n-pretrained"); lets the brain A/B the
            fine-tuned swap.
        conf: Confidence threshold passed to YOLO; boxes below it are not emitted.
        imgsz: Inference image size passed to YOLO.
        keep_classes: Class names to keep (default person-only).

    Returns:
        A DetectorOutput with the kept detections (possibly empty), tagged with the model_id,
        sensor_type, and the measured inference latency.

    Why:
        This is the per-frame call the loop makes. It wraps the torch-touching predict()
        plus the pure conversion into the single contract the GeoReferencer consumes, so the
        loop never sees Ultralytics types — only DetectorOutput.
    """
    t0 = time.perf_counter()
    # verbose=False silences Ultralytics' per-frame console spam in the loop.
    results = model.predict(frame, conf=conf, imgsz=imgsz, verbose=False)
    inference_ms = (time.perf_counter() - t0) * 1000.0

    result = results[0]
    xyxy, confidences, class_ids = _extract_boxes(result)
    names = {int(k): str(v) for k, v in model.names.items()}
    detections = xyxy_to_detections(xyxy, confidences, class_ids, names, keep_classes)

    return DetectorOutput(
        frame_id=frame_id,
        timestamp=timestamp,
        detections=detections,
        model_id=model_id,
        sensor_type=sensor_type,
        inference_ms=inference_ms,
    )
