# =============================================================================
# integration/deepgram_tts.py
# -----------------------------------------------------------------------------
# Responsible for: Synthesizing speech with DEEPGRAM's Text-to-Speech (Aura) — turning the
#                  composed broadcast text into audio bytes for the dashboard to play.
# Role in project: The voice of the subject broadcast (the sponsor tech). Deepgram is the
#                  primary path; when no key is configured the function returns None so the
#                  caller falls back to the browser's Web Speech API (the panel never goes silent).
# Assumptions: DEEPGRAM_API_KEY is provided via the environment OR the gitignored repo-root .env
#              (we read it ourselves — python-dotenv isn't a dependency). httpx (already installed)
#              makes the one REST call. No SDK needed; Deepgram Speak is a simple POST.
# =============================================================================

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

import httpx
import sentry_sdk

logger = logging.getLogger(__name__)

# Deepgram Speak (TTS) REST endpoint + the default Aura voice (the same the vendored voice agent
# uses). The model is selected by query param; the text goes in the JSON body.
_DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"
_DEFAULT_VOICE = "aura-2-thalia-en"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _key_from_dotenv() -> Optional[str]:
    """
    Read DEEPGRAM_API_KEY from the repo-root .env, if present (a minimal parser, no dependency).

    Returns:
        The key string, or None if the .env is absent or doesn't define it.

    Why:
        The project doesn't use python-dotenv, but the key lives in a gitignored .env; a tiny
        line scan lets `uvicorn integration.server:app` pick it up without the user having to
        export it first. Values may be quoted; we strip quotes/whitespace.
    """
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return None
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if line.startswith("DEEPGRAM_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                return value or None
    except OSError:
        return None
    return None


def deepgram_api_key() -> Optional[str]:
    """
    The Deepgram API key from the environment, falling back to the repo-root .env.

    Returns:
        The key, or None if not configured anywhere.

    Why:
        One place decides "do we have a key?", so both synthesize() and the server's /broadcast.mp3
        404 logic agree. Environment wins over .env (the usual precedence).
    """
    return os.environ.get("DEEPGRAM_API_KEY") or _key_from_dotenv()


def synthesize(text: str, voice: str = _DEFAULT_VOICE, timeout: float = 15.0) -> Optional[bytes]:
    """
    Synthesize `text` to speech audio via Deepgram TTS.

    Args:
        text: The message to speak.
        voice: The Deepgram Aura model (e.g. "aura-2-thalia-en").
        timeout: HTTP timeout in seconds.

    Returns:
        Audio bytes (Deepgram returns MP3 for Aura models), or None if there's no API key or the
        call fails — in which case the caller should fall back to browser TTS.

    Why:
        This is the single Deepgram call for the broadcast. Returning None (rather than raising)
        on a missing key or a transient error keeps the dashboard robust: it just speaks via the
        browser instead of going silent. Hermetic-by-design: with no key, it never touches the
        network, so tests can force the fallback path without a live call.
    """
    key = deepgram_api_key()
    if not key:
        return None  # no key -> signal the caller to fall back to browser speechSynthesis
    try:
        response = httpx.post(
            f"{_DEEPGRAM_SPEAK_URL}?model={voice}",
            headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
            json={"text": text},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.content
    except Exception as exc:  # network error, bad key, Deepgram outage -> fall back, don't crash
        # Behavior is unchanged (we still log + return None + fall back to browser TTS); we just
        # also report to Sentry so this otherwise-swallowed failure is visible. No-op without a DSN.
        sentry_sdk.capture_exception(exc)
        logger.warning("Deepgram TTS failed (%s); falling back to browser TTS", exc)
        return None
