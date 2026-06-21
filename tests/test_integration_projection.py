# =============================================================================
# tests/test_integration_projection.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the brain->dashboard projection (dashboard_projection.py)
#                  emits a dict that satisfies the dashboard's types.ts MapState contract.
# Role in project: Guards the UI seam. If the projection drops a key or emits an
#                  out-of-range position, the React app silently mis-renders; these tests
#                  pin the shape (every types.ts key) and the ranges (positions/intensity in
#                  [0,1]) so drift is caught here, not in the browser.
# Assumptions: We drive a real simulator loop to get a genuine, located MapState (not a
#              hand-built one), so the projection is tested on the actual belief state the
#              dashboard will render.
# =============================================================================

from __future__ import annotations

import json

from integration.dashboard_projection import ProjectionContext, project
from integration.loop import build_simulator_loop
from integration.telemetry import build_pose_feed
from src.common.grid import GridSpec

# The top-level keys the dashboard's types.ts MapState requires.
_REQUIRED_KEYS = {
    "missionName", "region", "startedAt", "loop", "confidenceToDeclare", "declareThreshold",
    "stats", "layers", "detections", "waypoints", "flightPath", "dronePos", "heatBlobs",
    "trend", "recentCommands", "telemetry",
}


def _run_loop_and_context():
    """
    Run the simulator loop to completion and assemble a realistic ProjectionContext.

    Why:
        Every projection test wants the same input: a genuine located MapState plus the
        cross-snapshot context (flown path, last pose, trend, located cell). Factoring it
        keeps each test focused on the assertion, not the setup.
    """
    loop, _ = build_simulator_loop()
    final_state, located_event = loop.run()

    # Recover the last pose from the same scripted feed the loop played (for telemetry).
    cfg = loop.cfg
    grid = GridSpec.from_config(cfg)
    _, frames = build_pose_feed(grid, cfg)
    context = ProjectionContext(
        drone_path=loop.drone_path,
        last_pose=frames[-1].pose,
        trend=[(0.0, 20.0), (90.0, 45.0), (180.0, 100.0)],
        located_cell=located_event.cell if located_event else None,
    )
    return final_state, context, located_event


def test_projection_has_all_required_keys():
    """
    Scenario: project a real located MapState.
    Why it matters: a missing top-level key (e.g. 'heatBlobs') makes the dashboard read
    undefined and crash or render blank. Assert the full types.ts key set is present.
    """
    final_state, context, _ = _run_loop_and_context()
    ui = project(final_state, context)
    assert _REQUIRED_KEYS.issubset(ui.keys()), _REQUIRED_KEYS - ui.keys()


def test_positions_and_intensities_are_normalized():
    """
    Scenario: inspect every normalized position + heat intensity the projection emits.
    Why it matters: the UI assumes 0..1 coordinates (x right, y down) and 0..1 intensity; a
    value outside that draws off-canvas or over-saturates. Check blobs, path, drone, detections.
    """
    final_state, context, _ = _run_loop_and_context()
    ui = project(final_state, context)

    for blob in ui["heatBlobs"]:
        assert 0.0 <= blob["x"] <= 1.0 and 0.0 <= blob["y"] <= 1.0
        assert 0.0 <= blob["intensity"] <= 1.0
    for pt in ui["flightPath"]:
        assert 0.0 <= pt["x"] <= 1.0 and 0.0 <= pt["y"] <= 1.0
    assert 0.0 <= ui["dronePos"]["x"] <= 1.0 and 0.0 <= ui["dronePos"]["y"] <= 1.0
    for det in ui["detections"]:
        assert 0.0 <= det["pos"]["x"] <= 1.0 and 0.0 <= det["pos"]["y"] <= 1.0
        assert 0.0 <= det["confidence"] <= 1.0


def test_projection_is_json_serializable():
    """
    Scenario: json.dumps the whole projected dict.
    Why it matters: FastAPI returns this over HTTP; any non-JSON value (a NumPy scalar, a
    tuple key) would 500 the endpoint. Serializing here catches it in a unit test.
    """
    final_state, context, _ = _run_loop_and_context()
    ui = project(final_state, context)
    encoded = json.dumps(ui)
    assert len(encoded) > 0


def test_located_state_reads_as_declared():
    """
    Scenario: the loop located the subject, so status is LOCATED.
    Why it matters: the confidence gauge must agree with the brain — it snaps to 100 (==
    declareThreshold) exactly when located, a person is found, the loop ribbon shows Detect
    done, and the primary detection is flagged. This is the demo's emotional payoff rendered.
    """
    final_state, context, located_event = _run_loop_and_context()
    assert located_event is not None  # precondition: the scenario locates
    ui = project(final_state, context)

    assert ui["confidenceToDeclare"] == 100
    assert ui["confidenceToDeclare"] >= ui["declareThreshold"]
    assert ui["stats"]["personsFound"] == 1
    assert ui["loop"][2]["label"] == "Detect" and ui["loop"][2]["status"] == "done"
    assert any(det["isPrimary"] for det in ui["detections"]), "no primary detection flagged"


def test_detection_rows_match_ui_shape():
    """
    Scenario: check each detection row carries every field the UI Detection type needs.
    Why it matters: DetectionsList reads persistence.seen/of, label, distanceM, thumbnailHue,
    pos — a missing nested field breaks that card. Pin the per-row shape.
    """
    final_state, context, _ = _run_loop_and_context()
    ui = project(final_state, context)
    assert ui["detections"], "expected at least one detection after locating"
    for det in ui["detections"]:
        assert set(det.keys()) == {
            "id", "timestamp", "confidence", "persistence", "label",
            "distanceM", "isPrimary", "pos", "thumbnailHue",
        }
        assert set(det["persistence"].keys()) == {"seen", "of"}
        assert set(det["pos"].keys()) == {"x", "y"}


def test_guidance_fields_default_to_searching():
    """
    Scenario: project with no guidance context (the search phase).
    Why it matters: the guide-home fields are additive — during search they must be null/
    "searching" so the dashboard's guidance overlay stays hidden and nothing else changes.
    """
    loop, _ = build_simulator_loop()
    ui = project(loop.brain.map_state())  # default context
    assert ui["guidancePath"] is None
    assert ui["subjectPos"] is None
    assert ui["operatorPos"] is None
    assert ui["guidanceStatus"] == "searching"
    # The Guide Home ribbon step exists and is not yet active.
    guide_step = next(s for s in ui["loop"] if s["label"] == "Guide Home")
    assert guide_step["status"] == "next"


def test_guidance_fields_populate_during_guiding():
    """
    Scenario: project with a guidance context (route + subject + home, status "guiding").
    Why it matters: when the server enters guidance, the dashboard needs the route, the moving
    subject, and the operator marker — all normalized to [0,1] — plus a live Guide Home step.
    """
    loop, _ = build_simulator_loop()
    final_state, _ = loop.run()
    grid = final_state.grid_spec
    route = [(10, 10), (12, 14), (15, 18)]
    ctx = ProjectionContext(
        drone_path=loop.drone_path,
        guidance_path=route,
        subject_cell=(11, 12),
        home_cell=(15, 18),
        guidance_status="guiding",
    )
    ui = project(final_state, ctx)

    assert ui["guidanceStatus"] == "guiding"
    assert len(ui["guidancePath"]) == len(route)
    for pt in ui["guidancePath"] + [ui["subjectPos"], ui["operatorPos"]]:
        assert 0.0 <= pt["x"] <= 1.0 and 0.0 <= pt["y"] <= 1.0
    guide_step = next(s for s in ui["loop"] if s["label"] == "Guide Home")
    assert guide_step["status"] == "live"


def test_empty_context_renders_valid_state_at_t0():
    """
    Scenario: project the prior (t0) MapState with NO context (no path, no pose yet).
    Why it matters: the dashboard polls from the first instant; the projection must produce a
    valid, complete state before any frame is flown — not crash on an empty path/pose.
    """
    loop, _ = build_simulator_loop()
    prior_state = loop.brain.map_state()  # before any step()
    ui = project(prior_state)  # default (empty) context

    assert _REQUIRED_KEYS.issubset(ui.keys())
    assert ui["flightPath"] == []
    assert ui["stats"]["personsFound"] == 0
    json.dumps(ui)  # still serializable
