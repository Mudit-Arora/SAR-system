# =============================================================================
# tests/test_integration_detector_adapter.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the detector->brain seam (integration/detector_adapter.py)
#                  converts raw YOLO boxes into a well-formed DetectorOutput.
# Role in project: Guards Boundary A. The conversion is the one thing that can silently
#                  corrupt every downstream cell (a wrong xyxy->xywh puts the person in the
#                  wrong place), so it gets a focused, torch-free test.
# Assumptions: We test the PURE conversion (xyxy_to_detections) and the result-extraction
#              against a tiny fake Ultralytics result, so no torch / no real model / no
#              weights are needed — the test stays fast and runs in the brain's light venv.
# =============================================================================

from __future__ import annotations

import numpy as np

from integration.detector_adapter import _extract_boxes, xyxy_to_detections
from src.common.contracts import Detection


# COCO-style class map: person is id 0, with some non-person classes to prove they're dropped.
_NAMES = {0: "person", 2: "car", 16: "dog"}


def test_xyxy_to_xywh_conversion_is_correct():
    """
    Scenario: one person box given as pixel corners [x1, y1, x2, y2] = [10, 20, 50, 140].
    Why it matters: the brain consumes xywh (top-left + size); a wrong conversion shifts the
    person's ground cell. Expect x=10, y=20, w=40, h=120 and the confidence carried through.
    """
    xyxy = np.array([[10.0, 20.0, 50.0, 140.0]])
    detections = xyxy_to_detections(xyxy, [0.9], [0], _NAMES)

    assert len(detections) == 1
    det = detections[0]
    assert isinstance(det, Detection)
    assert det.bbox_xywh == (10.0, 20.0, 40.0, 120.0)  # w = x2-x1, h = y2-y1
    assert det.confidence == 0.9
    assert det.class_name == "person"


def test_non_person_classes_are_dropped():
    """
    Scenario: three boxes — a person, a car, a dog — from a COCO model.
    Why it matters: the demo is person-focused (interfaces §2); a car/animal must NOT become
    evidence of a subject. Only the person box should survive the default keep-filter.
    """
    xyxy = np.array(
        [
            [0.0, 0.0, 10.0, 30.0],   # person
            [100.0, 100.0, 160.0, 140.0],  # car
            [200.0, 50.0, 230.0, 90.0],    # dog
        ]
    )
    detections = xyxy_to_detections(xyxy, [0.8, 0.95, 0.7], [0, 2, 16], _NAMES)

    assert len(detections) == 1
    assert detections[0].class_name == "person"
    assert detections[0].confidence == 0.8


def test_empty_frame_yields_no_detections():
    """
    Scenario: a frame YOLO found nothing in (empty box arrays).
    Why it matters: an empty detection list is the *meaningful* non-detection signal that
    lets the map lower probability over the covered area — it must be a clean [], not a crash.
    """
    empty = np.empty((0, 4))
    detections = xyxy_to_detections(empty, [], [], _NAMES)
    assert detections == []


def test_extract_boxes_handles_empty_result():
    """
    Scenario: an Ultralytics-style result whose `.boxes` is empty.
    Why it matters: _extract_boxes is the only place touching the tensor API; it must return
    empty NumPy arrays (not None) on a no-detection frame so the pure conversion can run.
    A minimal fake result stands in for a real Ultralytics Results object (no torch needed).
    """

    class _FakeBoxes:
        def __len__(self):
            return 0

    class _FakeResult:
        boxes = _FakeBoxes()

    xyxy, conf, cls = _extract_boxes(_FakeResult())
    assert xyxy.shape == (0, 4)
    assert conf.shape == (0,)
    assert cls.shape == (0,)


def test_degenerate_box_does_not_emit_negative_size():
    """
    Scenario: a malformed box where x2 < x1 (corner order swapped / projection glitch).
    Why it matters: the adapter should never hand the brain a negative width/height; we clamp
    to 0 here (the brain's sanitizer then drops the zero-area box). Defense in depth at the seam.
    """
    xyxy = np.array([[50.0, 60.0, 10.0, 60.0]])  # x2 < x1, and y2 == y1
    detections = xyxy_to_detections(xyxy, [0.5], [0], _NAMES)

    assert len(detections) == 1
    _, _, w, h = detections[0].bbox_xywh
    assert w == 0.0 and h == 0.0
