# Architecture

This document describes the architecture of the inbound telephony voice agent, from the high-level system design down to individual component responsibilities.

## System Overview

The system connects a phone call to an AI voice agent. Three services work together:

1. **Twilio** - Telephony provider. Answers the phone, converts audio to a digital stream, and sends it to our server over WebSocket.
2. **Application Server** - This codebase. Bridges Twilio audio to Deepgram, handles function calls, and manages call lifecycle.
3. **Deepgram Voice Agent API** - AI pipeline. Transcribes speech, runs an LLM, and synthesizes a voice response. All three steps happen in a single managed WebSocket connection.

```
┌──────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│          │     │  Application Server │     │  Deepgram Voice      │
│  Caller  │────►│      (Starlette)    │────►│  Agent API           │
│  (Phone) │◄────│                     │◄────│  (STT → LLM → TTS)   │
│          │     │                     │     │                      │
└──────────┘     └──────────┬──────────┘     └──────────────────────┘
   via Twilio               │
                 ┌──────────▼──────────┐
                 │   Backend Service   │
                 │ (Scheduling API)    │
                 └─────────────────────┘
```

## Call Flow

### 1. Incoming Call

When someone calls the Twilio phone number:

```
Phone ──dial──► Twilio ──POST /incoming-call──► Application Server
                                                      │
                                                returns TwiML XML:
                                                <Response>
                                                  <Connect>
                                                    <Stream url="wss://server/twilio"/>
                                                  </Connect>
                                                </Response>
                                                      │
                Twilio ◄──────────────────────────────┘
                  │
                  │ Opens WebSocket to wss://server/twilio
                  │ Sends "connected" event
                  │ Sends "start" event with callSid, streamSid
                  │ Begins streaming audio as base64 mulaw JSON
                  ▼
           Application Server
```

### 2. Session Setup

When the Twilio WebSocket connects:

```
1. Server accepts WebSocket connection
2. Server waits for Twilio "start" event → extracts callSid, streamSid
3. Server creates a VoiceAgentSession
4. Session opens a WebSocket to Deepgram Voice Agent API
5. Session sends agent configuration (prompt, functions, audio settings)
6. Session waits for SettingsApplied acknowledgment from Deepgram
7. Audio forwarding begins
```

### 3. Audio Pipeline

During the call, two streams run simultaneously:

```
Twilio → Server → Deepgram (caller's voice)
─────────────────────────────────────────────
1. Twilio sends JSON: {"event":"media","media":{"payload":"<base64 mulaw>"}}
2. Server decodes base64 → raw mulaw bytes
3. Server sends raw bytes to Deepgram WebSocket

Deepgram → Server → Twilio (agent's voice)
─────────────────────────────────────────────
1. Deepgram sends raw mulaw bytes
2. Server encodes to base64
3. Server sends JSON: {"event":"media","streamSid":"...","media":{"payload":"<base64>"}}
4. Twilio plays audio to caller
```

### 4. Function Calls

When the agent decides to use a tool:

```
1. Deepgram sends FunctionCallRequest event
   (function name, arguments, call ID)
2. Server dispatches to function_handlers.py
3. function_handlers.py calls the backend scheduling service
4. Server sends FunctionCallResponse back to Deepgram
   (call ID, result as JSON string)
5. Deepgram's LLM incorporates the result into its next response
6. Deepgram sends the spoken response as audio
```

### 5. Barge-In

When the caller starts speaking while the agent is talking:

```
1. Deepgram detects user speech → sends UserStartedSpeaking event
2. Server sends {"event":"clear","streamSid":"..."} to Twilio
3. Twilio immediately stops playing agent audio
4. Deepgram processes the caller's speech normally
```

### 6. Call End

```
1. Caller hangs up
2. Twilio sends "stop" event and closes WebSocket
3. Server detects WebSocket closure
4. VoiceAgentSession.cleanup() runs:
   - Cancels async tasks (audio forwarding, Deepgram listener)
   - Closes Deepgram WebSocket connection
   - Removes session from active sessions dict
```

## Component Details

### `main.py` - Entry Point

Creates the Starlette application with three routes and starts uvicorn. Configures logging.

### `config.py` - Configuration

Loads environment variables from `.env` via python-dotenv. Validates that `DEEPGRAM_API_KEY` is set. All other variables have defaults or are optional.

The `SERVER_EXTERNAL_URL` variable controls whether the server runs in local-only mode or telephony mode. When not set, the `/incoming-call` endpoint uses the request's Host header, which works for `dev_client.py` but not for real Twilio calls.

### `telephony/routes.py` - Twilio Integration

Two endpoints:

**`POST /incoming-call`** - Returns TwiML XML that tells Twilio to stream audio to our WebSocket endpoint. This is the webhook URL you configure on your Twilio phone number.

**`WS /twilio`** - Handles the audio stream. Accepts the WebSocket, waits for the Twilio "start" event, creates a `VoiceAgentSession`, and delegates everything to it. Cleanup happens in a `finally` block.

When deployed via the setup wizard, both endpoints are protected by a URL path token and Twilio request signature validation.

### `voice_agent/session.py` - VoiceAgentSession

The core of the system. One instance per active call. Manages:

- **Deepgram connection lifecycle**: Connect, configure, listen, cleanup
- **Audio forwarding**: Twilio base64 ↔ Deepgram raw bytes
- **Event dispatch**: Routes Deepgram events to appropriate handlers
- **Function calls**: Dispatches to `function_handlers.py`, sends results back
- **Barge-in**: Sends Twilio "clear" events on user speech detection

Key implementation details:

- Uses manual `__aenter__()` / `__aexit__()` for the Deepgram connection because it outlives any single function scope
- The Deepgram SDK's `on(EventType.MESSAGE, handler)` callback is synchronous - async work (sending to Twilio) is wrapped in `asyncio.create_task()`
- The `run()` method uses `asyncio.wait(FIRST_COMPLETED)` on two tasks: audio forwarding and Deepgram listening. Whichever finishes first (usually the Twilio WebSocket closing) ends the call.
- Must wait for `SettingsApplied` from Deepgram before forwarding audio - audio sent before settings are applied is silently dropped

### `voice_agent/agent_config.py` - Agent Configuration

Defines the agent's personality, capabilities, and technical settings:

- **System prompt**: Dental office receptionist with voice-specific formatting rules
- **Functions**: 5 tools (check availability, book, check existing, cancel, end call)
- **Audio settings**: mulaw encoding at 8kHz (Twilio's native format)
- **Models**: Configurable LLM and TTS voice via environment variables

### `voice_agent/function_handlers.py` - Function Dispatch

Maps function names from agent config to backend service methods. Uses lazy imports to keep the boundary between voice agent and backend layers explicit. Adding a new function requires: (1) define it in `agent_config.py`, (2) add a dispatch case here, (3) implement the backend logic.

### `backend/models.py` - Data Models

Plain dataclasses: `TimeSlot`, `Patient`, `Appointment`. Each has a `display()` method that returns a human-readable string suitable for the agent to read aloud.

### `backend/scheduling_service.py` - Mock Scheduling Service

An in-memory scheduling system that simulates a real backend API. On startup, generates realistic sample data: 3 providers, time slots for the next 5 business days, ~30% pre-booked slots, and 2 existing patients with appointments.

The async method signatures (`get_available_slots`, `book_appointment`, etc.) are designed to look like HTTP API calls. To connect to a real scheduling system, replace the method bodies with actual HTTP requests - the voice agent layer doesn't need to change.

### `dev_client.py` - Local Development Client

A standalone script that pretends to be Twilio. Captures microphone audio, resamples to 8kHz mulaw, wraps in Twilio's JSON message format, and sends over WebSocket. Receives agent audio and plays through speakers. Includes a terminal UI showing transcript and function calls.

Not included in `requirements.txt` - requires `sounddevice` and `websockets` as dev-only dependencies.

## Audio Encoding

Twilio uses mulaw (u-law) encoding at 8kHz mono - a telephony standard. The Deepgram Voice Agent API is configured to match:

```python
audio=AgentV1SettingsAudio(
    input=AgentV1SettingsAudioInput(encoding="mulaw", sample_rate=8000),
    output=AgentV1SettingsAudioOutput(encoding="mulaw", sample_rate=8000, container="none"),
)
```

This means no transcoding is needed - audio passes through the server as-is. The only transformation is between Twilio's base64 JSON format and Deepgram's raw binary format.

