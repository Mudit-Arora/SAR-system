# Inbound Telephony Voice Agent

A reference implementation for building a secure inbound telephony voice agent using [Deepgram's Voice Agent API](https://developers.deepgram.com/docs/voice-agent) and [Twilio](https://www.twilio.com/). Uses [Deepgram Flux](https://developers.deepgram.com/docs/models-overview) for speech-to-text with native turn-taking optimized for real-time voice agent conversations. Includes webhook endpoint protection and Twilio request signature validation out of the box.

Callers dial a phone number and talk to an AI receptionist that can check appointment availability, book appointments, look up existing appointments, and cancel appointments, all through natural voice conversation.

## Architecture

```
                    ┌──────────────┐
                    │  Phone Call  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    Twilio    │
                    │ Media Stream │
                    └──────┬───────┘
                           │ WebSocket (mulaw audio as base64 JSON)
                           │
              ┌────────────▼────────────────┐
              │     Application Server      │
              │         (Starlette)         │
              │                             │
              │  POST /incoming-call        │  ← Twilio webhook (returns TwiML)
              │  WS   /twilio               │  ← Audio stream
              │                             │
              │  ┌───────────────────────┐  │
              │  │  VoiceAgentSession    │  │  ← One per call
              │  │                       │  │
              │  │  Twilio ←→ Deepgram   │  │  ← Audio bridge
              │  │  audio       audio    │  │
              │  │  (base64)    (raw)    │  │
              │  └───────────┬───────────┘  │
              │              │              │
              │  ┌───────────▼───────────┐  │
              │  │  Function Handlers    │  │  ← Routes agent tool calls
              │  └───────────┬───────────┘  │
              └──────────────┼──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Backend Service           │
              │   (Mock Scheduling API)     │
              │                             │
              │   - Check available slots   │
              │   - Book appointments       │
              │   - Look up appointments    │
              │   - Cancel appointments     │
              └─────────────────────────────┘
```

### Audio Flow

1. Caller speaks into their phone
2. Twilio captures the audio and streams it as base64-encoded mulaw over WebSocket
3. The application server decodes the base64 and sends raw mulaw bytes to Deepgram's Voice Agent API
4. Deepgram handles the full pipeline: speech-to-text, LLM reasoning, text-to-speech
5. Deepgram sends back raw mulaw audio bytes
6. The application server encodes to base64 and sends as JSON to Twilio
7. Twilio plays the audio to the caller

### Key Technical Concepts

**Single WebSocket bridge**: The core of the system is `VoiceAgentSession`, which bridges two WebSocket connections (one to Twilio, one to Deepgram). It translates between Twilio's JSON-based protocol and Deepgram's binary audio protocol.

**Barge-in**: When the Deepgram Voice Agent detects that the user started speaking, the server sends a Twilio "clear" event to immediately stop playing agent audio. This prevents the agent from talking over the caller.

**Function calls**: The Deepgram Voice Agent API supports tool use. When the LLM decides to call a function (like checking appointment availability), Deepgram sends a function call event. The server executes it against the backend service and sends the result back to Deepgram, which incorporates it into the agent's next response.

**Protocol-agnostic server**: The server doesn't know whether audio comes from a real Twilio call or from the local development client (`dev_client.py`). Both send identical WebSocket messages. This means you can develop and test without a phone or Twilio account.

For a deeper look at the call flow, session lifecycle, and component details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick Start

The fastest path to a working telephony voice agent is the setup wizard, which configures Twilio and deploys to [Fly.io](https://fly.io).

### Prerequisites

- Python 3.12+
- A [Deepgram account](https://console.deepgram.com/) and [API key](https://developers.deepgram.com/docs/create-additional-api-keys#create-an-api-key-using-the-deepgram-console)
  - $200 free credits, no credit card required
- A [Twilio account](https://www.twilio.com/try-twilio)
  - New accounts come with trial credits.
- A [Fly.io account](https://fly.io/app/sign-up) and [flyctl](https://fly.io/docs/flyctl/install/) installed and authenticated (`flyctl auth login`). 
  - Fly.io's [free allowance](https://fly.io/docs/about/free-trial/) is more than enough for this reference implementation with the default suspend-on-idle configuration.

Note: Twilio trial accounts play a short disclaimer before connecting callers.

### 1. Clone and Install

```bash
git clone https://github.com/deepgram-devs/deepgram-voice-agent-inbound-telephony.git
cd deepgram-voice-agent-inbound-telephony

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and add your Deepgram API key:

```
DEEPGRAM_API_KEY=your_key_here
```

### 3. Run the Setup Wizard

```bash
python setup.py
```

The wizard will:
1. Prompt for your [Twilio account credentials](https://help.twilio.com/articles/14726256820123-What-is-a-Twilio-Account-SID-and-where-can-I-find-it-) (from [console.twilio.com](https://www.twilio.com/console))
2. Let you pick an existing phone number or purchase a new one
3. Deploy your voice agent to Fly.io
4. Automatically configure Twilio to route calls to your deployed voice agent

When it's done, call your phone number and talk to your agent.

```bash
# Other setup wizard modes:
python setup.py --twilio-only       # Skip Fly.io, provide your own URL
python setup.py --update-url URL    # Quick Twilio webhook URL update
python setup.py --status            # Show current config
python setup.py --teardown          # Clean up deployment
```

### Viewing Logs

After deployment, view your application logs with:

```bash
flyctl logs --app <your-app-name>
```

The app name is shown in the setup wizard output and in `python setup.py --status`.

### Cold Starts

The default configuration uses Fly.io's suspend mode. Your server suspends when idle and wakes in 1-3 seconds on incoming requests.

If you want instant response times for demos or production use, set `min_machines_running = 1` in `fly.toml` and redeploy to keep one VM always warm:

```toml
# fly.toml
min_machines_running = 1
```

See [Fly.io pricing](https://fly.io/docs/about/pricing/) for details.

### Twilio Regulatory Requirements

Depending on your region, Twilio may require address verification before you can purchase a phone number. The setup wizard will surface any errors from Twilio. Follow the instructions in the [Twilio console](https://www.twilio.com/console) if prompted.

## Alternative: Tunnel + Twilio

If you prefer to run the server locally instead of deploying to Fly.io, you can use a tunnel to expose your locally running voice agent server via a public URL.

### 1. Start a Tunnel

```bash
# ngrok
ngrok http 8080

# or zrok
zrok share public localhost:8080
```

Copy the public URL (e.g., `https://xxxx.ngrok.io`).

### 2. Update Configuration

Add to your `.env`:

```
SERVER_EXTERNAL_URL=https://xxxx.ngrok.io
```

### 3. Start the Server

```bash
python main.py
```

### 4. Configure Twilio

You can use the setup wizard with `--twilio-only` to handle Twilio configuration:

```bash
python setup.py --twilio-only
```

Or configure manually:

1. Get a Twilio phone number at [twilio.com/console](https://www.twilio.com/console)
2. In the phone number settings, set the webhook for incoming calls to:
   ```
   https://xxxx.ngrok.io/incoming-call
   ```
   Method: HTTP POST
3. Call your Twilio number from any phone

The server logs will show the call connecting in your terminal.

## Local Development (No Twilio Required)

You can test the full voice agent conversation without a phone or Twilio account using `dev_client.py`, which connects to the server over WebSocket and streams audio from your microphone.

```bash
pip install -r requirements-dev.txt  # Adds sounddevice, numpy, websockets

# Terminal 1:
python main.py

# Terminal 2:
python dev_client.py
```

Speak into your microphone to have a conversation with the agent. See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for more details and troubleshooting.

> **Note:** `dev_client.py` is for local development only. If you've deployed to Fly.io, call the phone number directly instead.

## Example Conversation

```
Agent: "Thank you for calling Bright Smile Dental! How can I help you today?"

Caller: "Hi, I'd like to schedule a cleaning."

Agent: "I'd be happy to help you schedule a cleaning. Do you have a preferred
        date or day of the week?"

Caller: "How about next Tuesday?"

  [Agent calls check_available_slots(date="2026-03-03")]

Agent: "I have a few openings next Tuesday with Lisa Thompson, our hygienist.
        There's a slot at 10 AM and another at 2 PM. Which would work better
        for you?"

Caller: "10 AM works."

Agent: "Great, a cleaning with Lisa Thompson on Tuesday March 3rd at 10 AM.
        Can I get your name and phone number to book that?"

Caller: "Sure, it's Maria Garcia, 555-0199."

Agent: "I have a cleaning with Lisa Thompson on Tuesday March 3rd at 10 AM
        for Maria Garcia. Shall I go ahead and book that?"

Caller: "Yes please."

  [Agent calls book_appointment(patient_name="Maria Garcia",
                                patient_phone="555-0199",
                                slot_id="slot-abc123")]

Agent: "You're all set! Your cleaning is booked for Tuesday March 3rd at
        10 AM with Lisa Thompson. Is there anything else I can help with?"

Caller: "No, that's all. Thanks!"

Agent: "You're welcome! We'll see you on Tuesday. Have a great day!"

  [Agent calls end_call(reason="appointment_booked")]
```

## Project Structure

```
telephony-voice-agent/
├── main.py                          # Entry point, Starlette app + uvicorn
├── config.py                        # Environment variable management
├── setup.py                         # Setup wizard (Twilio + Fly.io)
├── dev_client.py                    # Local dev client (mic/speaker, no Twilio needed)
├── requirements.txt                 # Python dependencies
├── requirements-dev.txt             # Dev-only dependencies (sounddevice, websockets)
├── .env.example                     # Environment variable template
├── Dockerfile                       # Container config for Fly.io deployment
├── fly.toml                         # Fly.io app config
│
├── telephony/
│   └── routes.py                    # POST /incoming-call, WS /twilio
│
├── voice_agent/
│   ├── session.py                   # VoiceAgentSession, Deepgram connection + audio bridge
│   ├── agent_config.py              # Agent prompt, functions, audio/model settings
│   └── function_handlers.py         # Routes function calls to backend service
│
├── backend/
│   ├── models.py                    # Data models (TimeSlot, Patient, Appointment)
│   └── scheduling_service.py        # Mock scheduling API (in-memory)
│
└── docs/
    ├── ARCHITECTURE.md              # Detailed architecture and data flows
    ├── PROMPT_GUIDE.md              # Voice agent prompt best practices
    ├── FUNCTION_GUIDE.md            # Function definition best practices
    └── LOCAL_DEVELOPMENT.md         # Local dev setup guide
```

## Customization

### Change the Agent's Personality

Edit the `SYSTEM_PROMPT` in `voice_agent/agent_config.py`. This is where you define who the agent is, what it knows, and how it behaves. See [docs/PROMPT_GUIDE.md](docs/PROMPT_GUIDE.md) for voice-specific prompt best practices.

### Add or Modify Functions

1. Define the function in `voice_agent/agent_config.py` (in the `FUNCTIONS` list)
2. Add the handler in `voice_agent/function_handlers.py`
3. Implement the backend logic in `backend/scheduling_service.py`

See [docs/FUNCTION_GUIDE.md](docs/FUNCTION_GUIDE.md) for function definition best practices.

### Swap the LLM or Voice

Set environment variables in `.env`:

```
LLM_MODEL=gpt-4o          # Default: gpt-4o-mini
VOICE_MODEL=aura-2-orion-en  # Default: aura-2-thalia-en
```

### Multilingual Support

This reference implementation is configured for English using Deepgram Flux (`flux-general-en`) for STT, which provides native turn-taking optimized for voice agents. For building voice agents in other languages, see the [Deepgram multilingual voice agent guide](https://developers.deepgram.com/docs/multilingual-voice-agent).

### Replace the Mock Backend

The `backend/` directory contains an in-memory mock. To connect to a real scheduling system:

1. Keep the same method signatures in `scheduling_service.py`
2. Replace the method bodies with HTTP calls to your real API
3. The voice agent layer doesn't need to change

The function dispatch in `voice_agent/function_handlers.py` uses lazy imports, making the boundary between voice agent and backend explicit.

## Additional Resources

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Detailed architecture, data flow diagrams, and component details
- [docs/PROMPT_GUIDE.md](docs/PROMPT_GUIDE.md) - Best practices for writing voice agent prompts
- [docs/FUNCTION_GUIDE.md](docs/FUNCTION_GUIDE.md) - Best practices for defining agent functions
- [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) - Step-by-step local development setup
- [Deepgram Voice Agent API Docs](https://developers.deepgram.com/docs/voice-agent) - Official API documentation
