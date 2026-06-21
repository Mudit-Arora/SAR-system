"""
Transcript broadcaster - fans out live conversation turns to connected
dashboard clients over WebSocket.

The voice agent session publishes each turn (and call start/end events) here;
any dashboard connected to the /transcript WebSocket receives them in real time.
This is a read-only output surface - dashboards consume, they never write back.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TranscriptBroadcaster:
    """Holds the set of connected dashboards and pushes events to all of them."""

    def __init__(self):
        self._clients: set = set()
        self._lock = asyncio.Lock()

    async def register(self, ws):
        async with self._lock:
            self._clients.add(ws)
        logger.info(f"[TRANSCRIPT-WS] Dashboard connected ({len(self._clients)} total)")

    async def unregister(self, ws):
        async with self._lock:
            self._clients.discard(ws)
        logger.info(f"[TRANSCRIPT-WS] Dashboard disconnected ({len(self._clients)} total)")

    async def publish(self, event: dict):
        """Send an event to every connected dashboard, dropping dead ones."""
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                await self.unregister(ws)


# Single shared instance - imported by the session (publisher) and the
# /transcript route (consumer registration).
broadcaster = TranscriptBroadcaster()
