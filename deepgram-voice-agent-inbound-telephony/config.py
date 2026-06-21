"""
Configuration - environment variable management and validation.

All configuration is loaded from environment variables (via .env file).
Only DEEPGRAM_API_KEY is required. Everything else has sensible defaults
or is optional depending on your setup:

  Local dev:    Just DEEPGRAM_API_KEY
  Telephony:    + SERVER_EXTERNAL_URL (set by setup.py or manually)
  Production:   Same as telephony, deployed behind a real domain
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Required
# ---------------------------------------------------------------------------
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))

# Optional - tunnel or production URL (e.g. https://xxxx.ngrok.io).
# Set automatically by setup.py, or manually for tunnel-based workflows.
# When set, the /incoming-call webhook uses this to tell Twilio where to
# stream audio.  When not set, the server runs in local-only mode.
SERVER_EXTERNAL_URL = os.getenv("SERVER_EXTERNAL_URL")

# ---------------------------------------------------------------------------
# Voice Agent
# ---------------------------------------------------------------------------
VOICE_MODEL = os.getenv("VOICE_MODEL", "aura-2-thalia-en")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ---------------------------------------------------------------------------
# Twilio (optional - used by setup.py wizard and for request validation)
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# ---------------------------------------------------------------------------
# Security (optional - set by setup.py when deploying to Fly.io)
# ---------------------------------------------------------------------------
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if not DEEPGRAM_API_KEY:
    raise ValueError(
        "Missing required environment variable: DEEPGRAM_API_KEY\n"
        "Get a free key at https://console.deepgram.com"
    )
