"""
Quick test: send an SMS from your Twilio number to your personal number.

Reads TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER from .env.
The destination number must be VERIFIED in the Twilio console while on a trial
account (Phone Numbers -> Manage -> Verified Caller IDs).

Usage:
  python send_test_sms.py                # texts the default number below
  python send_test_sms.py +1XXXXXXXXXX   # texts a different number
"""
import sys

from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER

# Default destination (E.164 format). Pass a different number as argv[1].
DEFAULT_TO = "+16025457387"


def main():
    to_number = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TO

    missing = [
        name
        for name, val in [
            ("TWILIO_ACCOUNT_SID", TWILIO_ACCOUNT_SID),
            ("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN),
            ("TWILIO_PHONE_NUMBER", TWILIO_PHONE_NUMBER),
        ]
        if not val
    ]
    if missing:
        print("Missing required env vars in .env: " + ", ".join(missing))
        print("Run `python setup.py --status` to see your current Twilio config.")
        sys.exit(1)

    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    print(f"Sending SMS from {TWILIO_PHONE_NUMBER} to {to_number} ...")
    try:
        msg = client.messages.create(
            from_=TWILIO_PHONE_NUMBER,
            to=to_number,
            body="SAR test: this is a test alert from your search and rescue voice agent.",
        )
    except Exception as e:
        print(f"Failed to send: {e}")
        print(
            "Common causes: the destination number isn't verified (trial accounts "
            "can only text verified numbers), the number isn't in +1XXXXXXXXXX format, "
            "or your Twilio number isn't SMS-capable."
        )
        sys.exit(1)

    print(f"Queued OK. Message SID: {msg.sid}, status: {msg.status}")
    print("Check your phone. If it doesn't arrive, look up the SID in the Twilio console logs.")


if __name__ == "__main__":
    main()
