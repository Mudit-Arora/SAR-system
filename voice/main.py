"""
Telephony Voice Agent - Entry Point

Starts a Starlette web server that handles:
  - POST /incoming-call  → Twilio webhook (returns TwiML)
  - WS   /twilio         → Twilio audio stream (or dev_client.py)
  - WS   /transcript     → live call transcript for the SAR dashboard

Usage:
  python main.py

For local development without Twilio:
  Terminal 1:  python main.py
  Terminal 2:  python dev_client.py
"""
import logging

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.responses import PlainTextResponse
from starlette.websockets import WebSocketDisconnect

from config import (
    SERVER_HOST,
    SERVER_PORT,
    SERVER_EXTERNAL_URL,
    DEEPGRAM_API_KEY,
    SENTRY_DSN,
    SENTRY_ENVIRONMENT,
    SENTRY_TRACES_SAMPLE_RATE,
)
from telephony.routes import incoming_call, twilio_websocket
from transcript_hub import transcript_hub

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentry (optional, additive) - error monitoring for the Fly-deployed agent
# ---------------------------------------------------------------------------
# Initialized at MODULE level so it runs whether the app starts via `python main.py`
# (the Dockerfile CMD on Fly) or `uvicorn main:app`. With no SENTRY_DSN the SDK is
# never initialized, so the agent behaves exactly as before. sentry-sdk auto-enables
# its Starlette + asyncio + logging integrations, so unhandled errors in the HTTP/WS
# routes are reported without per-route wiring; session.py adds call_sid context to
# the in-call failures it currently swallows.
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    logger.info("Sentry initialized (environment=%s)", SENTRY_ENVIRONMENT)
else:
    logger.info("Sentry not configured (SENTRY_DSN unset) - monitoring OFF")


async def dashboard(request):
    return PlainTextResponse(
        "Telephony Voice Agent is running.\n"
        "Call your Twilio number or use `python dev_client.py` to test locally."
    )


async def transcript_websocket(websocket):
    """Stream the live call transcript to a dashboard client.

    Subscribes the connecting client to the transcript hub and forwards every
    published message (call_started / turn / call_ended) as JSON. Cross-origin
    is fine: browser WebSockets aren't subject to CORS, so the dashboard (on a
    different port) can connect directly.

    Why a fixed path (no token): the dashboard's LiveTranscript connects to a
    single /transcript URL and auto-reconnects; this is a read-only fan-out of
    what's already spoken on the call, so it needs no per-client auth here.
    """
    await websocket.accept()
    queue = transcript_hub.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # client went away mid-send, etc.
        logger.debug(f"Transcript client disconnected: {exc}")
    finally:
        transcript_hub.unsubscribe(queue)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Starlette(
    routes=[
        Route("/incoming-call/{token:path}", incoming_call, methods=["POST"]),
        Route("/incoming-call", incoming_call, methods=["POST"]),
        WebSocketRoute("/twilio/{token:path}", twilio_websocket),
        WebSocketRoute("/twilio", twilio_websocket),
        WebSocketRoute("/transcript", transcript_websocket),
        Route("/", dashboard),
    ],
)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info(f"Deepgram API key: {'configured' if DEEPGRAM_API_KEY else 'MISSING'}")
    if SERVER_EXTERNAL_URL:
        logger.info(f"External URL: {SERVER_EXTERNAL_URL}")
        logger.info(f"Twilio webhook: {SERVER_EXTERNAL_URL}/incoming-call")
    else:
        logger.info("Running in local-only mode (no SERVER_EXTERNAL_URL set)")
        logger.info("Use dev_client.py to test - no Twilio or tunnel needed")

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=int(SERVER_PORT),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
