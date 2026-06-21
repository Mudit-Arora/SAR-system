"""
Telephony Voice Agent - Entry Point

Starts a Starlette web server that handles:
  - POST /incoming-call  → Twilio webhook (returns TwiML)
  - WS   /twilio         → Twilio audio stream (or dev_client.py)

Usage:
  python main.py

For local development without Twilio:
  Terminal 1:  python main.py
  Terminal 2:  python dev_client.py
"""
import logging
import os

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.responses import FileResponse, PlainTextResponse
from starlette.websockets import WebSocket

from config import SERVER_HOST, SERVER_PORT, SERVER_EXTERNAL_URL, DEEPGRAM_API_KEY
from telephony.routes import incoming_call, twilio_websocket
from voice_agent.transcript_broadcast import broadcaster

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")


async def dashboard(request):
    """Serve the live transcript dashboard.

    The page opens a WebSocket to /transcript and renders each conversation
    turn (and call start/end events) in real time.
    """
    if os.path.exists(DASHBOARD_HTML):
        return FileResponse(DASHBOARD_HTML)
    return PlainTextResponse(
        "Telephony Voice Agent is running.\n"
        "Call your Twilio number or use `python dev_client.py` to test locally."
    )


async def transcript_feed(websocket: WebSocket):
    """Live transcript feed for the dashboard.

    The dashboard connects here and receives each conversation turn (and
    call start/end events) as JSON, in real time.  Read-only: we don't
    expect any messages from the dashboard, we just keep the socket open.
    """
    await websocket.accept()
    await broadcaster.register(websocket)
    try:
        while True:
            # Block on receive purely to detect disconnect.
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await broadcaster.unregister(websocket)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Starlette(
    routes=[
        Route("/incoming-call/{token:path}", incoming_call, methods=["POST"]),
        Route("/incoming-call", incoming_call, methods=["POST"]),
        WebSocketRoute("/twilio/{token:path}", twilio_websocket),
        WebSocketRoute("/twilio", twilio_websocket),
        WebSocketRoute("/transcript", transcript_feed),
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
