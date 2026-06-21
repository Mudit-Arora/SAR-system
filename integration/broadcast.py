# =============================================================================
# integration/broadcast.py
# -----------------------------------------------------------------------------
# Responsible for: Composing the SUBJECT BROADCAST — the situation-aware message the drone
#                  speaks to the located person ("we've found you, stay put, help is coming").
# Role in project: The content half of the voice broadcast (interfaces.md §6.3, priority 1).
#                  Pure text composition from the LocatedEvent's terrain_context; the audio is
#                  synthesized separately by Deepgram (integration/deepgram_tts.py) and played
#                  in the dashboard. Kept pure (no network) so it's deterministic + unit-testable.
# Assumptions: terrain_context carries `land_cover` (a WorldCover label like "tree cover" on real
#              terrain; a synthetic label otherwise) and may carry `near_drainage` (synthetic only).
#              Every field is optional — a missing field degrades to a generic phrasing, never a crash.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Tuple

from src.common.contracts import LocatedEvent

# Languages we compose by default. English is the headline (Deepgram Aura is English-first);
# Spanish demonstrates "the message is generated, so a language parameter is nearly free".
_DEFAULT_LANGUAGES: Tuple[str, ...] = ("en", "es")

# Map a land-cover label to a warm, spoken LOCATION phrase, per language. The drone is talking to
# a frightened person — plain, reassuring words, not GIS jargon. Unknown labels fall back to the
# generic phrase, so any future WorldCover/synthetic label still produces a sensible sentence.
_LOCATION_PHRASE: Dict[str, Dict[str, str]] = {
    "en": {
        "tree cover": "in the trees",
        "forest": "in the trees",
        "forested canyon (drainage)": "in the trees near a creek",
        "mixed scrub/forest": "in mixed brush and trees",
        "shrubland": "in the brush",
        "grassland": "in an open grassy area",
        "cropland": "in an open field",
        "bare/sparse": "on open ground",
        "wetland": "near wet ground",
        "water": "near water",
        "steep/cliff": "on steep ground",
        "_default": "where you are",
    },
    "es": {
        "tree cover": "entre los árboles",
        "forest": "entre los árboles",
        "forested canyon (drainage)": "entre los árboles, cerca de un arroyo",
        "mixed scrub/forest": "entre matorrales y árboles",
        "shrubland": "entre los arbustos",
        "grassland": "en una zona de pasto abierta",
        "cropland": "en un campo abierto",
        "bare/sparse": "en terreno despejado",
        "wetland": "cerca de terreno húmedo",
        "water": "cerca del agua",
        "steep/cliff": "en terreno empinado",
        "_default": "donde está",
    },
}

# The full message template per language; {where} is filled from _LOCATION_PHRASE. Short sentences,
# no formatting — these are spoken aloud by TTS.
_TEMPLATE: Dict[str, str] = {
    "en": (
        "We have found you, and you are safe. You appear to be {where}. "
        "Please stay exactly where you are. A rescue team is on the way, and the drone overhead "
        "will guide them right to you. Help is close. Hold on — you are not alone."
    ),
    "es": (
        "Le hemos encontrado y está a salvo. Parece que está {where}. "
        "Por favor, quédese exactamente donde está. Un equipo de rescate está en camino, y el dron "
        "que tiene encima les guiará directamente hasta usted. La ayuda está cerca. Aguante, no está solo."
    ),
}


def _location_phrase(terrain_context: Dict[str, Any], language: str) -> str:
    """
    Pick the spoken location phrase for a language from the terrain context.

    Args:
        terrain_context: The LocatedEvent's terrain_context (may carry `land_cover`,
            `near_drainage`).
        language: A language code present in _LOCATION_PHRASE (e.g. "en", "es").

    Returns:
        A warm location phrase like "in the trees" / "entre los árboles" (or the generic
        fallback if the land cover is missing/unknown).

    Why:
        Centralizes the land-cover -> friendly-phrase mapping so the template stays a clean
        fill-in. Defaults make it impossible for a missing/odd label to break the message.
    """
    phrases = _LOCATION_PHRASE[language]
    label = str(terrain_context.get("land_cover", "")).strip().lower()
    phrase = phrases.get(label, phrases["_default"])
    # If the synthetic near_drainage flag is present and the label didn't already mention water,
    # add a creek cue (real WorldCover terrain has no near_drainage, so this is a no-op there).
    if terrain_context.get("near_drainage") and "creek" not in phrase and "arroyo" not in phrase:
        phrase += " near a creek" if language == "en" else ", cerca de un arroyo"
    return phrase


def compose_broadcast(
    located_event: LocatedEvent, languages: Tuple[str, ...] = _DEFAULT_LANGUAGES
) -> Dict[str, str]:
    """
    Compose the spoken subject-broadcast message in each requested language.

    Args:
        located_event: The brain's LocatedEvent (its terrain_context drives the wording).
        languages: Language codes to compose (defaults to English + Spanish). Unknown codes
            are skipped.

    Returns:
        A {language: message} dict — the text to display and to voice (via Deepgram TTS, with a
        browser-TTS fallback). Always contains at least English.

    Why:
        The broadcast is the demo's emotional high point, and the message is *generated*, so
        producing it per language is nearly free — exactly the "multilingual is the cheap
        stretch" point from the plan. Pure (no network), so it's deterministic and testable.
    """
    ctx = located_event.terrain_context or {}
    messages: Dict[str, str] = {}
    for lang in languages:
        if lang not in _TEMPLATE:
            continue
        messages[lang] = _TEMPLATE[lang].format(where=_location_phrase(ctx, lang))
    # Guarantee English is present even if the caller passed an odd language set.
    if "en" not in messages:
        messages["en"] = _TEMPLATE["en"].format(where=_location_phrase(ctx, "en"))
    return messages
