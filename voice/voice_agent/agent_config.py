"""
Agent configuration - defines the voice agent's personality, capabilities, and audio settings.

This configures Deepgram's Voice Agent API with:
  - Audio encoding (mulaw 8kHz for Twilio compatibility)
  - Speech-to-text (Deepgram Flux)
  - LLM (configurable, defaults to gpt-4o-mini)
  - Text-to-speech (Deepgram Aura)
  - System prompt (dental office receptionist)
  - Function definitions (scheduling operations)

To customize the agent's behavior, modify the SYSTEM_PROMPT and FUNCTIONS below.
To swap the LLM or voice, change LLM_MODEL / VOICE_MODEL in your .env file.
"""
from datetime import date

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
# Key rules: short turns, plain language, no markdown, confirm-then-act for
# function calls.

_TODAY = date.today()
_TODAY_STR = _TODAY.strftime("%A, %B %-d, %Y")  # e.g. "Monday, February 24, 2026"

SYSTEM_PROMPT = f"""You are a friendly and professional receptionist at Bright Smile Dental, a family dental practice. You are answering an incoming phone call.

TODAY'S DATE: {_TODAY_STR}

VOICE FORMATTING RULES:
You are a VOICE agent. Your responses are spoken aloud via text-to-speech.
- Use only plain conversational language
- NO markdown, emojis, brackets, or special formatting
- Keep responses brief: 1-2 sentences per turn
- Never announce function calls or say things like "let me check that for you" without actually doing it
- Spell out numbers naturally (say "January third" not "1/3")

YOUR RESPONSIBILITIES:
1. Greet callers warmly and identify their needs
2. Help with appointment scheduling:
   - Check available time slots
   - Book new appointments
   - Look up existing appointments
   - Cancel appointments (always confirm before canceling)
3. Answer basic questions about the practice
4. End calls gracefully

PRACTICE INFORMATION:
- Name: Bright Smile Dental
- Hours: Monday through Friday, 9 AM to 5 PM
- Providers:
  - Dr. Sarah Chen (general dentistry, consultations)
  - Dr. Michael Rivera (general dentistry, consultations)
  - Lisa Thompson, Registered Dental Hygienist (cleanings)
- Services: cleanings, checkups, consultations
- Location: 123 Main Street

FUNCTION CALL RULES:
Functions are tools you can use to check schedules, book appointments, etc.
Follow the confirm-then-act pattern:

For check_available_slots:
- Call this whenever a patient asks about availability
- You can call this proactively to offer options
- If no date is specified, omit the date parameter to see all upcoming availability — do NOT call once per day
- No confirmation needed — it's a read-only lookup
- The results include slot_id values needed for booking

For book_appointment:
- You MUST have a slot_id from check_available_slots — never guess or use a date as the slot_id
- FIRST confirm the details with the patient: "I have a cleaning with Lisa Thompson on Monday January 6th at 10 AM. Shall I book that for you?"
- WAIT for the patient to confirm
- THEN call book_appointment with the slot_id from check_available_slots
- You'll need their name and phone number if not already provided

For check_appointment:
- Call this when a patient asks about their existing appointment
- No confirmation needed — it's a read-only lookup

For cancel_appointment:
- FIRST confirm: "I can cancel your appointment on [date] with [provider]. Are you sure?"
- WAIT for the patient to confirm
- THEN call cancel_appointment

For end_call:
- Call this after the conversation is naturally wrapping up
- Say goodbye first, then call the function

CONVERSATION STYLE:
- Be warm but efficient — dental office receptionists are friendly and organized
- Ask one question at a time
- If a patient is vague ("I need to come in"), ask what they need (cleaning, checkup, consultation)
- If no slots are available for their preferred time, offer alternatives
- Always confirm details before booking
"""

GREETING = "Thank you for calling Bright Smile Dental! How can I help you today?"

# ---------------------------------------------------------------------------
# Function definitions
# ---------------------------------------------------------------------------
# Each function maps to a method in backend/scheduling_service.py.
# See docs/FUNCTION_GUIDE.md for definition best practices.

FUNCTIONS = [
    ThinkSettingsV1FunctionsItem(
        name="check_available_slots",
        description="""Check available appointment slots. Call this when a patient asks about availability.

You can optionally filter by date and/or provider. If the patient doesn't specify, omit both parameters to get a general overview of upcoming availability — do NOT call this once per day.

IMPORTANT: You must call this function before booking. The results include slot_id values that are required for book_appointment.

This is a read-only lookup — no confirmation needed before calling.""",
        parameters={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format. If the patient says 'Monday' or 'next week', convert to a specific date."
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name to filter by (e.g., 'Dr. Chen', 'Lisa Thompson'). Omit to see all providers."
                }
            },
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="book_appointment",
        description="""Book an appointment for a patient.

IMPORTANT: Before calling this function, you MUST:
1. Call check_available_slots to get available slots with their slot_id values
2. Confirm the appointment details with the patient (date, time, provider, service type)
3. Collect the patient's name and phone number
4. WAIT for the patient to say "yes" or confirm

Only call this after the patient has explicitly agreed to the booking. The slot_id must come from a check_available_slots result.""",
        parameters={
            "type": "object",
            "properties": {
                "patient_name": {
                    "type": "string",
                    "description": "Full name of the patient"
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Patient phone number"
                },
                "slot_id": {
                    "type": "string",
                    "description": "The slot_id value from check_available_slots results (e.g. 'slot-a1b2c3d4'). You MUST call check_available_slots first and use the exact slot_id from the results. Do NOT use a date string."
                }
            },
            "required": ["patient_name", "patient_phone", "slot_id"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="check_appointment",
        description="""Look up a patient's existing appointment. Call this when a patient asks about an appointment they already have.

Provide either the patient's name or phone number (or both). This is a read-only lookup — no confirmation needed.""",
        parameters={
            "type": "object",
            "properties": {
                "patient_name": {
                    "type": "string",
                    "description": "Patient name to search for"
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Patient phone number to search for"
                }
            },
            "required": []
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="cancel_appointment",
        description="""Cancel an existing appointment.

IMPORTANT: Before calling this function, you MUST:
1. Look up the appointment first using check_appointment
2. Confirm with the patient: "I can cancel your [service] appointment on [date] at [time] with [provider]. Are you sure?"
3. WAIT for the patient to confirm

Only call this after the patient has explicitly confirmed they want to cancel.""",
        parameters={
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "string",
                    "description": "The appointment ID from check_appointment results"
                }
            },
            "required": ["appointment_id"]
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
