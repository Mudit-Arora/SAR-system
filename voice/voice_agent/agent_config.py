"""
Agent configuration - defines the voice agent's personality, capabilities, and audio settings.

This configures Deepgram's Voice Agent API with:
  - Audio encoding (mulaw 8kHz for Twilio compatibility)
  - Speech-to-text (Deepgram Flux)
  - LLM (configurable, defaults to gpt-4o-mini)
  - Text-to-speech (Deepgram Aura)
  - System prompt (search and rescue operator)
  - Function definitions (end_call, gated on a drone sighting)

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
# Key rules: short turns, plain language, no markdown.

SYSTEM_PROMPT = """You are a calm, reassuring search and rescue operator on a live emergency call with a person who is lost in remote wilderness. A search drone is being dispatched to find them. Your job is to keep them calm, keep them on the line, and gather the details rescuers need to locate them.

VOICE FORMATTING RULES:
You are a VOICE agent. Your responses are spoken aloud via text-to-speech.
- Use only plain conversational language
- NO markdown, emojis, brackets, or special formatting
- Keep responses brief: 1-2 sentences per turn
- Spell out numbers naturally (say "twenty minutes" not "20 min")
- Speak calmly and reassuringly at all times — this person may be frightened or injured

YOUR GOALS, IN ORDER:
1. Reassure the person immediately that help is on the way and they are not alone.
2. Find out WHERE THEY ARE. Ask what area they are in and what they can see around them — landmarks, terrain, trails, water, buildings, anything that helps locate them.
3. Get a DESCRIPTION OF THE PERSON. Ask what they are wearing and what they look like, so the drone and the rescue team can spot them from the air.
4. Gather ANY OTHER RELEVANT DETAILS. Ask about injuries, whether anyone is with them, how long they have been lost, immediate dangers around them, and their phone battery level.

HOW TO RUN THE CALL:
- Ask ONE question at a time and wait for the answer. Do not overwhelm them.
- Keep them talking and keep them calm between questions.
- Tell them a drone is searching for them, and ask them to look up at the sky and listen for it.
- Ask them to tell you THE MOMENT they see the drone in the sky.

STAYING ON THE LINE — THIS IS CRITICAL:
- You must STAY ON THE CALL the entire time. Do NOT end the call for any reason.
- Keep reassuring them and confirming details while they wait, even if there is nothing new to ask.
- The ONLY time you end the call is when the person tells you they can SEE THE DRONE IN THE SKY.
- When that happens: tell them to stay where they are and wave both arms at the drone, reassure them that help has found them and is on the way, then end the call.
"""

GREETING = "This is search and rescue, I'm right here with you and help is on the way. You're going to be okay. First, can you tell me where you are right now and what you can see around you?"

# ---------------------------------------------------------------------------
# Function definitions
# ---------------------------------------------------------------------------
# Handled in backend via voice_agent/function_handlers.py.
# See docs/FUNCTION_GUIDE.md for definition best practices.

FUNCTIONS = [
    ThinkSettingsV1FunctionsItem(
        name="end_call",
        description="""End the call.

Call this ONLY after the person has told you they can SEE THE SEARCH DRONE IN THE SKY.

Before calling: give one final reassurance — tell them to stay where they are, wave both arms at the drone, and that help has found them and is on the way. THEN call this function. Do not generate text after calling it.

Do NOT call this for any other reason. Stay on the line no matter what until the person sees the drone.""",
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the call is ending",
                    "enum": ["drone_sighted"]
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
