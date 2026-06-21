"""
Fly logs -> dashboard bridge (temporary hack).

The deployed Fly app (golden-seastar-977) doesn't expose the /transcript
WebSocket route, so the dashboard can't connect to it directly (it gets a
403).  This script works around that without a redeploy:

  1. Tails `flyctl logs --app <APP>` as a subprocess.
  2. Parses the voice-agent transcript lines (USER:/ASSISTANT:) and call
     start/end lines out of the log stream.
  3. Re-broadcasts them over a local /transcript WebSocket in the exact JSON
     shape the dashboard's useTranscript hook already expects.

Point the dashboard at this bridge by setting in dashboard/.env:

    VITE_AGENT_WS_URL=ws://localhost:8765/transcript

Then run:

    python log_bridge.py

This only works while this command is running on your machine.  The proper
fix is to redeploy the Fly app with the /transcript route.
"""
import asyncio
import json
import logging
import re
from collections import deque
from datetime import datetime

import uvicorn
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FLY_APP = "golden-seastar-977"
HOST = "0.0.0.0"
PORT = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("log_bridge")

# ---------------------------------------------------------------------------
# Log line patterns (match the formats emitted by voice_agent / telephony)
# ---------------------------------------------------------------------------
TURN_RE = re.compile(r"\[SESSION:(?P<sid>[^\]]+)\]\s+(?P<role>USER|ASSISTANT):\s*(?P<content>.*)$")
CALL_START_RE = re.compile(r"\[TELEPHONY\]\s+Call started - callSid=(?P<sid>\S+)")
CALL_END_RE = re.compile(r"\[TELEPHONY\]\s+Call\s+(?P<sid>\S+)\s+ended")

# ---------------------------------------------------------------------------
# Connected dashboard clients
# ---------------------------------------------------------------------------
_clients: set = set()
_clients_lock = asyncio.Lock()

# Dedup: flyctl can replay recent lines (e.g. on reconnect).  Track recently
# seen raw log lines so we don't push the same turn twice.
_seen = deque(maxlen=1000)
_seen_set: set = set()


def _already_seen(raw: str) -> bool:
    if raw in _seen_set:
        return True
    if len(_seen) == _seen.maxlen:
        _seen_set.discard(_seen[0])
    _seen.append(raw)
    _seen_set.add(raw)
    return False


async def _broadcast(event: dict):
    data = json.dumps(event)
    async with _clients_lock:
        targets = list(_clients)
    dead = []
    for ws in targets:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    if dead:
        async with _clients_lock:
            for ws in dead:
                _clients.discard(ws)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def _handle_line(raw: str):
    """Parse a single flyctl log line and broadcast any transcript event."""
    m = CALL_START_RE.search(raw)
    if m:
        if _already_seen(raw):
            return
        logger.info(f"call_started ({m.group('sid')})")
        await _broadcast({"type": "call_started", "call_sid": m.group("sid"), "ts": _now()})
        return

    m = CALL_END_RE.search(raw)
    if m:
        if _already_seen(raw):
            return
        logger.info(f"call_ended ({m.group('sid')})")
        await _broadcast({"type": "call_ended", "call_sid": m.group("sid"), "ts": _now()})
        return

    m = TURN_RE.search(raw)
    if m:
        if _already_seen(raw):
            return
        role = "user" if m.group("role") == "USER" else "assistant"
        content = m.group("content").strip()
        if not content:
            return
        logger.info(f"{role}: {content}")
        await _broadcast({
            "type": "turn",
            "call_sid": m.group("sid"),
            "role": role,
            "content": content,
            "ts": _now(),
        })


async def _tail_logs():
    """Run `flyctl logs` and feed each output line to the parser; restart if it dies."""
    while True:
        logger.info(f"Starting `flyctl logs --app {FLY_APP}`")
        try:
            proc = await asyncio.create_subprocess_exec(
                "flyctl", "logs", "--app", FLY_APP,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            logger.error("`flyctl` not found on PATH. Install the Fly CLI and retry.")
            return

        assert proc.stdout is not None
        async for raw_bytes in proc.stdout:
            line = raw_bytes.decode("utf-8", "replace").rstrip()
            if line:
                await _handle_line(line)

        await proc.wait()
        logger.warning("flyctl logs exited; reconnecting in 2s...")
        await asyncio.sleep(2)


async def transcript_feed(websocket: WebSocket):
    """Dashboard connects here; we push parsed transcript events. Read-only."""
    await websocket.accept()
    async with _clients_lock:
        _clients.add(websocket)
    logger.info(f"Dashboard connected ({len(_clients)} total)")
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        async with _clients_lock:
            _clients.discard(websocket)
        logger.info(f"Dashboard disconnected ({len(_clients)} total)")


app = Starlette(routes=[WebSocketRoute("/transcript", transcript_feed)])


@app.on_event("startup")
async def _on_startup():
    asyncio.create_task(_tail_logs())


if __name__ == "__main__":
    logger.info(f"Bridge listening on ws://localhost:{PORT}/transcript")
    logger.info(f"Set dashboard/.env -> VITE_AGENT_WS_URL=ws://localhost:{PORT}/transcript")
    uvicorn.run(app, host=HOST, port=PORT)
