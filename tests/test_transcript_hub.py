# =============================================================================
# test_transcript_hub.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the in-process transcript bus (voice/transcript_hub.py)
#                  fans the right message shapes to subscribers, including the
#                  Deepgram "agent" -> dashboard "assistant" role mapping.
# Role in project: The live phone call can't run in CI, but the hub is the seam
#                  that gets the transcript to the dashboard, so its contract is
#                  unit-testable on its own.
# Assumptions: Pure asyncio, no network, no Deepgram. voice/ is put on the path
#                  so this imports the same module the agent does.
# =============================================================================
"""Tests for the transcript pub/sub hub bridging the agent to the dashboard."""
import asyncio
import pathlib
import sys

_VOICE_DIR = pathlib.Path(__file__).parent.parent / "voice"
sys.path.insert(0, str(_VOICE_DIR))

from transcript_hub import TranscriptHub  # noqa: E402


def test_subscriber_receives_published_turn():
    """A published turn reaches a subscriber with the exact dashboard shape."""
    async def scenario():
        hub = TranscriptHub()
        queue = hub.subscribe()
        # A caller turn passes through with role "user".
        hub.publish_turn("user", "Where should we search?", ts="T0")
        return await asyncio.wait_for(queue.get(), timeout=1.0)

    msg = asyncio.run(scenario())
    assert msg == {
        "type": "turn",
        "role": "user",
        "content": "Where should we search?",
        "ts": "T0",
    }


def test_agent_role_is_mapped_to_assistant():
    """Deepgram emits role 'agent'; the dashboard renders 'assistant' — map it here."""
    async def scenario():
        hub = TranscriptHub()
        queue = hub.subscribe()
        hub.publish_turn("agent", "Focus near the Pantoll trailhead.", ts="T1")
        return await asyncio.wait_for(queue.get(), timeout=1.0)

    msg = asyncio.run(scenario())
    assert msg["role"] == "assistant"  # NOT "agent"
    assert msg["content"] == "Focus near the Pantoll trailhead."


def test_call_started_and_ended_signals():
    """The call lifecycle signals carry exactly their type, in order."""
    async def scenario():
        hub = TranscriptHub()
        queue = hub.subscribe()
        hub.publish_call_started()
        hub.publish_call_ended()
        first = await asyncio.wait_for(queue.get(), timeout=1.0)
        second = await asyncio.wait_for(queue.get(), timeout=1.0)
        return first, second

    first, second = asyncio.run(scenario())
    assert first == {"type": "call_started"}
    assert second == {"type": "call_ended"}


def test_fans_out_to_multiple_subscribers():
    """Every connected dashboard client gets its own copy of each message."""
    async def scenario():
        hub = TranscriptHub()
        q1 = hub.subscribe()
        q2 = hub.subscribe()
        hub.publish_turn("user", "Did we find them?", ts="T2")
        m1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        m2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        return m1, m2

    m1, m2 = asyncio.run(scenario())
    assert m1 == m2
    assert m1["content"] == "Did we find them?"


def test_unsubscribe_stops_delivery():
    """After unsubscribe, a client receives no further messages."""
    async def scenario():
        hub = TranscriptHub()
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub.publish_turn("user", "still there?", ts="T3")
        # Nothing should have been queued for the removed subscriber.
        return queue.qsize()

    assert asyncio.run(scenario()) == 0


def test_default_timestamp_is_stamped_when_omitted():
    """When no ts is given, the hub stamps one so the message is always complete."""
    async def scenario():
        hub = TranscriptHub()
        queue = hub.subscribe()
        hub.publish_turn("user", "hello")  # no ts
        return await asyncio.wait_for(queue.get(), timeout=1.0)

    msg = asyncio.run(scenario())
    assert isinstance(msg["ts"], str) and msg["ts"]  # non-empty string
