# =============================================================================
# tests/test_integration_loop.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the integration loop (integration/loop.py) runs the real
#                  closed chain end to end on the simulator backend and locates the subject
#                  while preserving the brain's core invariant.
# Role in project: Guards the convergence point of Milestone 1 — that detector backend ->
#                  GeoReferencer -> SearchBrain wiring (a) keeps probability mass conserved
#                  every step and (b) actually trips the locate trigger. If this passes, the
#                  dashboard (Units 4-6) is rendering a loop that genuinely works.
# Assumptions: Uses the simulator backend (no footage/torch needed), the demo config, and
#              the default synthetic scenario — the same setup src/demo/run.py locates on.
# =============================================================================

from __future__ import annotations

import json

from src.common.contracts import MapState, Status
from integration.loop import build_simulator_loop


def test_loop_conserves_probability_mass_every_step():
    """
    Scenario: step the whole simulator-backed loop one frame at a time.
    Why it matters: the brain's central invariant is posterior.sum() + p_out == 1. A single
    bad update (a NaN, a missed renormalization) would break it and silently corrupt the map.
    We assert it holds after EVERY step, not just at the end, so a transient break is caught.
    """
    loop, _ = build_simulator_loop()

    while not loop.is_done:
        map_state, _ = loop.step()
        total = float(map_state.posterior.sum()) + map_state.p_out
        # Float renormalization won't be exact; a tight tolerance still catches real leaks.
        assert abs(total - 1.0) < 1e-9, f"mass not conserved at frame {loop.frame_index}: {total}"


def test_loop_locates_subject_at_ground_truth():
    """
    Scenario: run the simulator-backed loop to completion on the default synthetic scenario.
    Why it matters: the whole point of the loop is to LOCATE. We assert it both trips the
    trigger and lands on (or very near) the planted subject cell — proving real detections
    flowing through geo concentrate the posterior onto the right ground, not just somewhere.
    """
    loop, _ = build_simulator_loop()
    final_state, located_event = loop.run()

    assert located_event is not None, "loop finished without locating"
    assert final_state.status is Status.LOCATED
    # Located cell should coincide with the planted subject (the simulator path is clean
    # enough that run.py reports 0-cell error; allow a 2-cell slack for robustness).
    dr = abs(located_event.cell[0] - loop.subject_cell[0])
    dc = abs(located_event.cell[1] - loop.subject_cell[1])
    assert dr <= 2 and dc <= 2, f"located {located_event.cell} far from subject {loop.subject_cell}"


def test_loop_publishes_serializable_mapstate():
    """
    Scenario: take the final MapState and round-trip it through to_dict() + json.dumps.
    Why it matters: the dashboard consumes MapState across an HTTP boundary (Unit 5), so the
    published snapshot must be JSON-serializable as-is. This catches any non-serializable
    field (e.g. a stray NumPy scalar) before the projection layer depends on it.
    """
    loop, _ = build_simulator_loop()
    final_state, _ = loop.run()

    assert isinstance(final_state, MapState)
    as_dict = final_state.to_dict()
    encoded = json.dumps(as_dict)  # raises if anything is not JSON-serializable
    assert len(encoded) > 0
    # Spot-check the centerpiece survived the round trip as a 2D list.
    assert len(as_dict["posterior"]) == loop.grid.n_rows
    assert len(as_dict["posterior"][0]) == loop.grid.n_cols
