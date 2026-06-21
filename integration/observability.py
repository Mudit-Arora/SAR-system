# =============================================================================
# integration/observability.py
# -----------------------------------------------------------------------------
# Responsible for: One shared place to initialize Sentry error/performance monitoring
#                  for the PYTHON BACKEND components on the laptop side — the FastAPI
#                  integration server (integration/server.py) and the loop CLI
#                  (integration/loop.py). Both call init_sentry() so they share one
#                  identical, env-gated init config (DSN gating, sample rate, tag).
# Role in project: Optional reliability layer (sponsor: Sentry). It is ADDITIVE and
#                  OFF by default: with no SENTRY_DSN in the environment (or repo-root
#                  .env), init_sentry() is a no-op and nothing about the demo or the
#                  test suite changes. With a DSN set, sentry-sdk auto-enables its
#                  Threading, FastAPI/Starlette, and stdlib-logging integrations, so
#                  unhandled exceptions (including in the server's stepper THREAD) and
#                  ERROR-level logs are reported without any per-call-site wiring.
# Assumptions: sentry-sdk is installed (see requirements.txt). The DSN comes from the
#              SENTRY_DSN env var, falling back to the gitignored repo-root .env — the
#              same precedence the Deepgram key uses (integration/deepgram_tts.py).
#              The Fly-deployed voice agent (voice/) is a SEPARATE deployable with its
#              own deps; it initializes Sentry itself rather than importing this module.
# =============================================================================

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

import sentry_sdk

logger = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _value_from_dotenv(key: str) -> Optional[str]:
    """
    Read a single KEY=value from the gitignored repo-root .env, if present.

    Args:
        key: The environment variable name to look for (e.g. "SENTRY_DSN").

    Returns:
        The value string (quotes/whitespace stripped), or None if the .env is
        absent or doesn't define the key.

    Why:
        The project deliberately doesn't depend on python-dotenv, but keys live in a
        gitignored repo-root .env so `uvicorn integration.server:app` can pick them up
        without the user exporting them first. This mirrors deepgram_tts._key_from_dotenv;
        it is a tiny, intentional duplication (two readers) — if a THIRD reader appears,
        unify these into one shared env helper (rule of three), not before.
    """
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return None
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if line.startswith(f"{key}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                return value or None
    except OSError:
        return None
    return None


def _resolve_dsn() -> Optional[str]:
    """
    The Sentry DSN from the environment, falling back to the repo-root .env.

    Returns:
        The DSN string, or None if not configured anywhere (-> monitoring stays off).

    Why:
        One place decides "do we have a DSN?", with the usual precedence (environment
        wins over .env). Split out from init_sentry() so it is pure and unit-testable
        without touching global Sentry state.
    """
    return os.environ.get("SENTRY_DSN") or _value_from_dotenv("SENTRY_DSN")


def init_sentry(component: str) -> bool:
    """
    Initialize Sentry for a backend component, but only if a DSN is configured.

    Args:
        component: A short tag identifying this process (e.g. "integration-server",
            "loop-cli"). Attached to every event as a `component` tag so events are
            attributable to the right surface when several report to one project.

    Returns:
        True if Sentry was initialized (a DSN was present); False if it was skipped
        (no DSN -> the SDK stays uninitialized and every sentry_sdk call is a no-op,
        so the caller behaves exactly as before).

    Why:
        The FastAPI server and the loop CLI need the SAME init, so centralizing it here
        keeps it DRY and gives one place to tune. We rely on sentry-sdk's DEFAULT
        auto-enabled integrations (Threading for the stepper thread, FastAPI/Starlette
        for request context, Logging to turn ERROR logs into events) rather than passing
        integration objects explicitly — it is equivalent and far simpler. Returning a
        bool lets callers log whether monitoring is active without re-reading the env.
    """
    dsn = _resolve_dsn()
    if not dsn:
        # No DSN -> stay a no-op. This is the additive-safety guarantee: the demo and
        # the test suite run identically whether or not Sentry is configured.
        return False

    sentry_sdk.init(
        dsn=dsn,
        # Tag the deployment so demo/staging/prod events are separable in the Sentry UI.
        environment=os.environ.get("SENTRY_ENVIRONMENT", "demo"),
        # Performance tracing is sampled (not every request) to keep overhead/quota low;
        # 0.2 = 20% of transactions. Tunable live via env without a code change.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
        # This is a backend service with no end-user PII worth attaching to events.
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("Sentry initialized for component=%s", component)
    return True
