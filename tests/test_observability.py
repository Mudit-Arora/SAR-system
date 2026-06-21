# =============================================================================
# tests/test_observability.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the shared Sentry init helper (integration/observability.py)
#                  WITHOUT ever initializing a real Sentry client or hitting the network.
# Role in project: Guards the "additive-safety" contract of the Sentry integration — with no
#                  SENTRY_DSN, init_sentry() must be a no-op (so the demo + the rest of the
#                  suite behave identically), and with a DSN it must initialize exactly once
#                  with that DSN. Also covers that the Deepgram fallback reports the otherwise
#                  swallowed exception to Sentry.
# Assumptions (hermeticity): a real SENTRY_DSN may exist in the env / repo-root .env on this
#              machine, so every test FORCES the DSN state via monkeypatch and stubs
#              sentry_sdk.init — no test ever creates a live Sentry client.
# =============================================================================

from __future__ import annotations

import integration.observability as obs


def test_resolve_dsn_prefers_env_over_dotenv(monkeypatch):
    """
    Scenario: SENTRY_DSN is set in the environment AND a (different) value sits in .env.
    Why it matters: pins the documented precedence — the environment wins — so a shell export
    reliably overrides a stale .env on any machine.
    """
    monkeypatch.setenv("SENTRY_DSN", "https://env@example/1")
    # Even if .env had a value, the env var must win; force the .env reader to a sentinel.
    monkeypatch.setattr(obs, "_value_from_dotenv", lambda key: "https://dotenv@example/2")
    assert obs._resolve_dsn() == "https://env@example/1"


def test_resolve_dsn_falls_back_to_dotenv(monkeypatch):
    """
    Scenario: no SENTRY_DSN in the environment, but one is present in the repo-root .env.
    Why it matters: `uvicorn integration.server:app` must pick up the DSN from .env without the
    user exporting it first (the same convenience the Deepgram key relies on).
    """
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(obs, "_value_from_dotenv", lambda key: "https://dotenv@example/2")
    assert obs._resolve_dsn() == "https://dotenv@example/2"


def test_init_sentry_is_noop_without_dsn(monkeypatch):
    """
    Scenario: no DSN configured anywhere.
    Why it matters: THE core additive-safety guarantee — init must return False and must NOT call
    sentry_sdk.init, so the demo and tests run exactly as if Sentry didn't exist. We fail loudly
    if init is even attempted.
    """
    monkeypatch.setattr(obs, "_resolve_dsn", lambda: None)

    def _boom(*args, **kwargs):  # initializing with no DSN is a bug
        raise AssertionError("init_sentry() called sentry_sdk.init() despite no DSN")

    monkeypatch.setattr(obs.sentry_sdk, "init", _boom)
    assert obs.init_sentry("integration-server") is False


def test_init_sentry_initializes_once_with_dsn(monkeypatch):
    """
    Scenario: a DSN IS configured; stub sentry_sdk.init to capture the call (no real client).
    Why it matters: confirms init happens with the resolved DSN and the component tag is set —
    the path that actually turns monitoring on — without creating global Sentry state in the suite.
    """
    monkeypatch.setattr(obs, "_resolve_dsn", lambda: "https://abc@example/1")
    captured = {}

    def _fake_init(*args, **kwargs):
        captured["dsn"] = kwargs.get("dsn")
        captured["traces"] = kwargs.get("traces_sample_rate")

    tags = {}
    monkeypatch.setattr(obs.sentry_sdk, "init", _fake_init)
    monkeypatch.setattr(obs.sentry_sdk, "set_tag", lambda k, v: tags.__setitem__(k, v))

    assert obs.init_sentry("loop-cli") is True
    assert captured["dsn"] == "https://abc@example/1"
    assert tags["component"] == "loop-cli"


def test_deepgram_failure_reports_to_sentry(monkeypatch):
    """
    Scenario: Deepgram TTS errors with a key present.
    Why it matters: the failure was previously only logged + swallowed; we now also report it to
    Sentry. Verify capture_exception is invoked AND behavior is unchanged (still returns None so
    the dashboard falls back to browser TTS).
    """
    import integration.deepgram_tts as tts

    monkeypatch.setattr(tts, "deepgram_api_key", lambda: "fake-key-123")
    monkeypatch.setattr(tts.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    captured = {}
    monkeypatch.setattr(tts.sentry_sdk, "capture_exception", lambda exc: captured.setdefault("exc", exc))

    assert tts.synthesize("Help is close.") is None  # behavior unchanged
    assert isinstance(captured.get("exc"), RuntimeError)  # and the failure was reported
