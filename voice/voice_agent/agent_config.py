"""
Agent configuration - defines the voice agent's personality, capabilities, and audio settings.

This configures Deepgram's Voice Agent API with:
  - Audio encoding (mulaw 8kHz for Twilio compatibility)
  - Speech-to-text (Deepgram Flux)
  - LLM (configurable, defaults to gpt-4o-mini)
  - Text-to-speech (Deepgram Aura)
  - System prompt (Search & Rescue operations-support dispatcher)
  - Function definitions (read-only SAR status lookups)

To customize the agent's behavior, modify the SYSTEM_PROMPT and FUNCTIONS below.
To swap the LLM or voice, change LLM_MODEL / VOICE_MODEL in your .env file.
"""
from config import VOICE_MODEL, LLM_MODEL
from deepgram.agent.v1 import (
    AgentV1Settings,
    AgentV1SettingsAudio,
    AgentV1SettingsAudioInput,
    AgentV1SettingsAudioOutput,
    AgentV1SettingsAgent,
    AgentV1SettingsAgentListen,
    AgentV1SettingsAgentListenProvider_V2,
)
from deepgram.types.think_settings_v1 import ThinkSettingsV1
from deepgram.types.think_settings_v1provider import ThinkSettingsV1Provider_OpenAi
from deepgram.types.think_settings_v1functions_item import ThinkSettingsV1FunctionsItem
from deepgram.types.speak_settings_v1 import SpeakSettingsV1
from deepgram.types.speak_settings_v1provider import SpeakSettingsV1Provider_Deepgram

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# This prompt follows voice-specific best practices from docs/PROMPT_GUIDE.md.
# Key rules: short turns, plain language, no markdown, report-don't-guess for
# function calls.

SYSTEM_PROMPT = """You are the voice of a Search and Rescue operations support system. A field operator or incident commander is calling in by phone to ask about an active search for a missing person. You answer their questions using live data from the search system.

VOICE FORMATTING RULES:
You are a VOICE agent. Your responses are spoken aloud via text-to-speech.
- Use only plain conversational language
- NO markdown, emojis, brackets, or special formatting
- Keep responses brief: 1-2 sentences per turn
- Never announce function calls or say things like "let me check that for you" without actually doing it
- Spell out numbers naturally (say "forty percent" not "40%")

YOUR ROLE:
You report what the search system currently knows. You do NOT fly drones or change the search yourself — you read off the live status, like a calm emergency dispatcher reading a status board. Be factual and concise.

WHAT YOU CAN ANSWER — each maps to a tool. ALWAYS call the matching tool and answer from its result. NEVER invent coordinates, percentages, or a "found" status.
1. Overall search status (how it's going, how many drones, how long) — use get_search_status
2. Where to focus next / the highest-probability area to search — use get_highest_probability_area
3. How much ground has been covered so far — use get_coverage
4. Whether the missing person has been found yet — use get_located_status

FUNCTION CALL RULES:
- These are all read-only lookups. Call the matching tool whenever the operator asks; no confirmation needed.
- After a tool returns, relay the key fact in one or two spoken sentences.
- When reporting a location, prefer the landmark description the tool gives you (for example, "near the Pantoll trailhead") over raw latitude and longitude numbers. Only read coordinates aloud if the operator explicitly asks for them.
- If the operator asks something these tools don't cover, say you can report the search status, the priority search area, how much has been covered, and whether the subject has been located.

For end_call:
- Call this after the conversation is naturally wrapping up
- Say goodbye first, then call the function

CONVERSATION STYLE:
- Calm, clear, and efficient, like an emergency dispatcher
- Give one piece of information at a time
- If the operator is vague, ask whether they want search status, the priority area, coverage, or whether the person has been found
"""

GREETING = "S A R command, go ahead."

# ---------------------------------------------------------------------------
# Function definitions
# ---------------------------------------------------------------------------
# Each function maps to a method in backend/sar_service.py.
# All SAR lookups are read-only and take no parameters — they report the
# current state of the one active search.

FUNCTIONS = [
    ThinkSettingsV1FunctionsItem(
        name="get_search_status",
        description="""Get an overall status summary of the active search: whether it is still in progress or the person has been found, how many drones are flying, and how long the search has been running.

Call this when the operator asks a general question like "what's the status", "how's the search going", or "give me an update". This is a read-only lookup — call it immediately, no confirmation needed.""",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="get_highest_probability_area",
        description="""Get the area the search system currently judges most likely to contain the missing person — where the operator should focus next. Returns a spoken-friendly landmark description (and coordinates if needed).

Call this when the operator asks "where should we search", "where's the best place to look", or "what's the highest probability area". Read-only — call it immediately, no confirmation needed. Prefer the landmark description over raw coordinates when you answer.""",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="get_coverage",
        description="""Get how much of the search area has been covered so far, as a percentage and an approximate area.

Call this when the operator asks "how much have we covered", "how much ground have we searched", or similar. Read-only — call it immediately, no confirmation needed.""",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="get_located_status",
        description="""Check whether the missing person has been found yet. If found, returns where they are (a landmark description and the terrain they're in) and the system's confidence.

Call this when the operator asks "did we find them", "have we located the subject", or "any sign of them". Read-only — call it immediately, no confirmation needed.""",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="end_call",
        description="""End the phone call gracefully.

Call this after:
- The patient says goodbye
- The conversation has naturally concluded
- You've said your closing remarks

Say goodbye FIRST, then call this function. Do not generate text after calling it.""",
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the call is ending",
                    "enum": ["appointment_booked", "customer_goodbye", "no_action_needed"]
                }
            },
            "required": ["reason"]
        }
    ),
]


# ---------------------------------------------------------------------------
# Build the settings message
# ---------------------------------------------------------------------------

def get_agent_config() -> AgentV1Settings:
    """Build the Voice Agent settings message for Deepgram.

    This is sent once per call when the Deepgram connection is established.
    It configures STT, LLM, TTS, and the agent's prompt and tools.
    """
    return AgentV1Settings(
        type="Settings",
        audio=AgentV1SettingsAudio(
            input=AgentV1SettingsAudioInput(
                encoding="mulaw",
                sample_rate=8000,
            ),
            output=AgentV1SettingsAudioOutput(
                encoding="mulaw",
                sample_rate=8000,
                container="none",
            ),
        ),
        agent=AgentV1SettingsAgent(
            listen=AgentV1SettingsAgentListen(
                provider=AgentV1SettingsAgentListenProvider_V2(
                    version="v2",
                    type="deepgram",
                    model="flux-general-en",
                ),
            ),
            think=ThinkSettingsV1(
                provider=ThinkSettingsV1Provider_OpenAi(
                    type="open_ai",
                    model=LLM_MODEL,
                ),
                prompt=SYSTEM_PROMPT,
                functions=FUNCTIONS,
            ),
            speak=SpeakSettingsV1(
                provider=SpeakSettingsV1Provider_Deepgram(
                    type="deepgram",
                    model=VOICE_MODEL,
                ),
            ),
            greeting=GREETING,
        ),
    )
