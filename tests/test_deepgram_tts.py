# =============================================================================
# tests/test_deepgram_tts.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the Deepgram TTS client (integration/deepgram_tts.py) — the
#                  no-key fallback path and the request construction — WITHOUT ever making a
#                  live Deepgram call.
# Role in project: Guards the voice synthesis seam. The critical safety property: with no key
#                  configured, synthesize() returns None (so the dashboard falls back to browser
#                  TTS) and never hits the network.
# Assumptions (hermeticity): a real DEEPGRAM_API_KEY may exist in the environment / .env on this
#              machine, so every test FORCES the key state via monkeypatch and stubs httpx — no
#              test ever calls the real API.
# =============================================================================

from __future__ import annotations

import integration.deepgram_tts as tts


def test_no_key_returns_none_without_network(monkeypatch):
    """
    Scenario: force "no API key" (regardless of the real env/.env on this machine).
    Why it matters: the no-key path is the fallback contract — it must return None and NOT touch
    the network. We also fail loudly if httpx.post is even attempted.
    """
    monkeypatch.setattr(tts, "deepgram_api_key", lambda: None)

    def _boom(*args, **kwargs):  # any network attempt is a bug in the no-key path
        raise AssertionError("synthesize() hit the network with no key")

    monkeypatch.setattr(tts.httpx, "post", _boom)
    assert tts.synthesize("We have found you.") is None


def test_with_key_posts_to_deepgram_and_returns_audio(monkeypatch):
    """
    Scenario: a key IS present; stub httpx.post to capture the request and return fake audio.
    Why it matters: pins the Deepgram request shape (the Speak URL + model, the Token auth header,
    the text body) and that synthesize returns the response bytes — all without a live call.
    """
    monkeypatch.setattr(tts, "deepgram_api_key", lambda: "fake-key-123")
    captured = {}

    class _Resp:
        content = b"FAKE_MP3_BYTES"

        def raise_for_status(self):
            return None

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(tts.httpx, "post", _fake_post)

    audio = tts.synthesize("Stay where you are.", voice="aura-2-thalia-en")
    assert audio == b"FAKE_MP3_BYTES"
    assert "api.deepgram.com/v1/speak" in captured["url"]
    assert "aura-2-thalia-en" in captured["url"]
    assert captured["headers"]["Authorization"] == "Token fake-key-123"
    assert captured["json"]["text"] == "Stay where you are."


def test_network_error_falls_back_to_none(monkeypatch):
    """
    Scenario: a key is present but Deepgram errors (timeout, bad key, outage).
    Why it matters: a transient failure must degrade to None (browser TTS), never crash the
    server request that triggered it.
    """
    monkeypatch.setattr(tts, "deepgram_api_key", lambda: "fake-key-123")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated Deepgram outage")

    monkeypatch.setattr(tts.httpx, "post", _raise)
    assert tts.synthesize("Help is close.") is None
