# =============================================================================
# tests/test_broadcast.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the subject-broadcast composer (integration/broadcast.py)
#                  produces a sensible, reassuring, situation-aware message — robustly.
# Role in project: Guards the content of the demo's emotional high point. The message must
#                  reflect the located terrain, reassure ("stay put / help is close"), exist in
#                  each language, and never crash on a sparse/odd terrain_context.
# Assumptions: Pure text composition — no network, no Deepgram — so these run fast and offline.
# =============================================================================

from __future__ import annotations

from src.common.contracts import LocatedEvent
from integration.broadcast import compose_broadcast


def _event(terrain_context: dict) -> LocatedEvent:
    """A minimal LocatedEvent carrying a given terrain_context. Why: the composer only reads that."""
    return LocatedEvent(
        cell=(93, 80), latlon=(37.91, -122.61), confidence=0.9,
        terrain_context=terrain_context, timestamp=123.0,
    )


def test_message_reflects_land_cover_and_reassures():
    """
    Scenario: a real-terrain locate in 'tree cover'.
    Why it matters: the broadcast should mention the location naturally ("in the trees") AND
    carry the core reassurance the subject needs — stay put + help coming. Both are asserted.
    """
    msg = compose_broadcast(_event({"land_cover": "tree cover"}))["en"].lower()
    assert "trees" in msg
    assert "stay" in msg
    assert "help" in msg or "rescue" in msg


def test_both_languages_present_and_distinct():
    """
    Scenario: compose the default languages.
    Why it matters: multilingual is the cheap stretch — English + Spanish must both be produced,
    be non-empty, and actually differ (a real translation, not the same string twice).
    """
    msgs = compose_broadcast(_event({"land_cover": "shrubland"}))
    assert set(msgs.keys()) >= {"en", "es"}
    assert msgs["en"] and msgs["es"]
    assert msgs["en"] != msgs["es"]
    assert "árboles" in msgs["es"] or "arbustos" in msgs["es"]  # Spanish wording present


def test_missing_or_unknown_land_cover_is_handled():
    """
    Scenario: (a) an empty terrain_context; (b) an unknown land-cover label.
    Why it matters: terrain_context fields are optional and labels evolve; the composer must
    degrade to a generic but still-reassuring message, never raise or leave a "{where}" hole.
    """
    for ctx in ({}, {"land_cover": "some-future-label"}):
        msg = compose_broadcast(_event(ctx))["en"]
        assert "{where}" not in msg          # template fully filled
        assert "stay" in msg.lower()
        assert msg.strip()


def test_synthetic_near_drainage_adds_a_creek_cue():
    """
    Scenario: a synthetic-terrain context with near_drainage True.
    Why it matters: when the (synthetic) drainage flag is present, the message should add a creek
    cue for ground-team context; real WorldCover terrain has no such flag, so this never fires there.
    """
    msg = compose_broadcast(_event({"land_cover": "mixed scrub/forest", "near_drainage": True}))["en"]
    assert "creek" in msg.lower()
