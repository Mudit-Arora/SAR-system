# Local Development Guide

How to develop and test the voice agent without a phone, Twilio account, or tunnel.

## Prerequisites

- Python 3.12+
- A [Deepgram API key](https://console.deepgram.com/) (free tier available)
- A microphone and speakers/headphones

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Dev Client Dependencies

```bash
pip install -r requirements-dev.txt
```

This installs `sounddevice`, `numpy`, and `websockets` on top of the base dependencies.

`sounddevice` requires PortAudio. On most systems it's included, but if you get errors:

```bash
# macOS
brew install portaudio

# Ubuntu/Debian
sudo apt-get install portaudio19-dev

# Windows - usually works out of the box
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your Deepgram API key:

```
DEEPGRAM_API_KEY=your_key_here
```

That's the only required variable for local development.

## Running

Open two terminal windows.

**Terminal 1 - Server:**

```bash
source venv/bin/activate
python main.py
```

**Terminal 2 - Dev Client:**

```bash
source venv/bin/activate
python dev_client.py
```

The dev client will:
1. Connect to `ws://localhost:8080/twilio`
2. Send a synthetic Twilio "start" event
3. Open your microphone
4. Display a terminal UI with call status, transcript, and function calls

Speak into your microphone to have a conversation with the agent.

### Dev Client Options

```bash
python dev_client.py --url ws://localhost:8080/twilio  # Default URL
```

### Ending a Call

Press `Ctrl+C` in the dev client terminal. The server will clean up the session automatically.

## How It Works

The dev client pretends to be Twilio. It sends the exact same WebSocket messages that Twilio would:

1. **Connected event**: `{"event": "connected", "protocol": "Call"}`
2. **Start event**: `{"event": "start", "start": {"callSid": "...", "streamSid": "..."}}`
3. **Media events**: `{"event": "media", "media": {"payload": "<base64 mulaw>"}}`

The server processes these identically to real Twilio traffic. There is no conditional logic or "dev mode" in the server - it genuinely cannot tell the difference.

Audio processing in the dev client:
- Captures from your microphone at 16kHz (better quality for initial capture)
- Resamples to 8kHz mono (Twilio's native format)
- Encodes to mulaw via `audioop`
- Base64-encodes and wraps in Twilio JSON format
- For playback: reverses the process (base64 decode → mulaw → PCM → speakers)

## What You Can Test Locally

- Full agent conversation (greeting, multi-turn dialogue)
- All function calls (check availability, book, check existing, cancel, end call)
- Backend integration (the mock scheduling service runs in-process)
- Prompt iteration - edit `voice_agent/agent_config.py`, restart the server, try again
- Barge-in behavior (interrupt the agent while it's speaking)

## What Requires Twilio

- Real phone audio quality and latency
- Twilio's call setup/teardown flow (SIP, carrier handoff)
- DTMF (touch-tone) handling
- Concurrent calls from different phone numbers

For the fastest path to real phone calls, use the setup wizard:

```bash
python setup.py              # Configures Twilio + deploys to Fly.io
python setup.py --twilio-only  # Configures Twilio, bring your own URL
```

Or see the main [README](../README.md#alternative-tunnel--twilio) for manual Twilio setup instructions.

## Troubleshooting

### "No module named 'sounddevice'"

```bash
pip install sounddevice
```

### "PortAudio not found" or similar

```bash
# macOS
brew install portaudio

# Ubuntu/Debian
sudo apt-get install portaudio19-dev
```

### "Could not connect to the server"

Make sure the server is running in another terminal:

```bash
python main.py
```

### No audio playback / silence

- Check that your speakers/headphones are working
- Check that your microphone is not muted
- Ensure `DEEPGRAM_API_KEY` is set correctly in `.env`
- Check the server terminal for error messages

### "Timeout waiting for settings to be applied"

This means the Deepgram connection was established but the agent configuration was rejected. Check:
- Your `DEEPGRAM_API_KEY` is valid
- The `LLM_MODEL` in `.env` is a model your Deepgram account has access to
- The `VOICE_MODEL` in `.env` is a valid Deepgram Aura voice

### High latency or choppy audio

Local development audio quality depends on your machine and network. If you experience issues:
- Close other applications using the microphone
- Use wired headphones instead of Bluetooth (reduces audio latency)
- Check your internet connection (all audio goes through Deepgram's servers)
