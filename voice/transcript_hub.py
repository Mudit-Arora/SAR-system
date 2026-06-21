# =============================================================================
# transcript_hub.py
# -----------------------------------------------------------------------------
# Responsible for: An in-process pub/sub bus that carries the live call
#                  transcript from the voice agent session to any connected
#                  dashboard WebSocket(s).
# Role in project: The bridge the Deepgram template lacks. The agent session
#                  (the single publisher) pushes call_started / turn /
#                  call_ended; the /transcript WS route in main.py subscribes
#                  dashboard clients and forwards what it publishes.
# How it fits: One asyncio event loop runs the whole Starlette app (uvicorn),
#                  and the Deepgram session tasks run in that same loop, so this
#                  needs no threading lock — plain set/Queue operations are safe.
# Message shapes (must match the dashboard's useTranscript.ts):
#                  {"type": "turn", "role": "user"|"assistant", "content": str, "ts": str}
#                  {"type": "call_started"}   {"type": "call_ended"}
# =============================================================================
"""In-process transcript pub/sub bridging the voice agent to the dashboard."""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TranscriptHub:
    """
    A minimal fan-out bus: one publisher (the call), many subscribers (clients).

    Why a hub rather than wiring the session straight to the socket:
        the call session and the dashboard connection have independent
        lifecycles (clients connect/reconnect mid-call, and there may be more
        than one), so a small broadcast bus decouples them — the session just
        publishes, and whoever is listening receives.
    """

    def __init__(self) -> None:
        # One unbounded queue per connected subscriber. A set gives O(1)
        # add/remove and there are only a handful of dashboard clients.
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        """
        Register a subscriber and get its message queue.

        Returns:
            An asyncio.Queue that will receive every subsequently published
            message dict.

        Why:
            The /transcript route awaits this queue and forwards each message to
            its WebSocket client. Per-subscriber queues mean a slow client can
            never drop another client's messages.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Remove a subscriber (on client disconnect). Safe if already gone.

        Args:
            queue: The queue returned by an earlier subscribe() call.

        Why:
            Stops fanning messages to a socket that has closed, so the
            subscriber set doesn't grow without bound across calls.
        """
        self._subscribers.discard(queue)

    def publish(self, message: dict) -> None:
        """
        Fan a message out to every current subscriber.

        Args:
            message: A JSON-serializable dict in one of the documented shapes.

        Why:
            put_nowait is non-blocking and safe here because the queues are
            unbounded — publishing never awaits, so it can be called from any
            point in the session's message handling without stalling audio.
        """
        # Iterate a snapshot: a subscriber could be removed concurrently by its
        # own disconnect handler between calls.
        for queue in list(self._subscribers):
            queue.put_nowait(message)

    def publish_turn(self, role: str, content: str, ts: str | None = None) -> None:
        """
        Publish one conversation turn, normalized for the dashboard.

        Args:
            role: The Deepgram role — "user" (the caller) or "agent" (the SAR
                voice). "agent" is mapped to "assistant".
            content: What was said.
            ts: Optional timestamp string; defaults to the current UTC time.

        Why:
            The dashboard renders speaker bubbles by role in {"user",
            "assistant"}, but Deepgram emits "agent". Mapping it here keeps the
            session hook a one-liner and the contract correct in one place.
        """
        normalized_role = "assistant" if role == "agent" else role
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        self.publish({
            "type": "turn",
            "role": normalized_role,
            "content": content,
            "ts": ts,
        })

    def publish_call_started(self) -> None:
        """Signal a new call (the dashboard clears the transcript and marks it active)."""
        self.publish({"type": "call_started"})

    def publish_call_ended(self) -> None:
        """Signal the call ended (the dashboard marks the transcript inactive)."""
        self.publish({"type": "call_ended"})


# Module-level singleton: one bus shared by the session and the /transcript route
# (they live in the same process). Importers use `from transcript_hub import transcript_hub`.
transcript_hub = TranscriptHub()
