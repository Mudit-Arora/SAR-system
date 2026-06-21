"""
Transcript store - writes the full conversation transcript for each call to a
plain .txt file.

This is a temporary persistence layer for the SAR operator agent; it will be
replaced by a database later.  One file per call, named by timestamp + call_sid,
written under the transcripts/ directory at the project root.
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# transcripts/ lives at the project root (one level up from backend/).
TRANSCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transcripts")


class TranscriptStore:
    """Appends one call's conversation turns to a .txt file."""

    def __init__(self, call_sid: str):
        os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
        started = datetime.now()
        safe_sid = call_sid.replace("/", "_")
        filename = f"{started.strftime('%Y%m%d-%H%M%S')}_{safe_sid}.txt"
        self.path = os.path.join(TRANSCRIPT_DIR, filename)

        with open(self.path, "w", encoding="utf-8") as f:
            f.write("SAR operator call transcript\n")
            f.write(f"Call SID: {call_sid}\n")
            f.write(f"Started: {started.isoformat(timespec='seconds')}\n")
            f.write("-" * 50 + "\n")
        logger.info(f"[TRANSCRIPT] Logging call {call_sid} to {self.path}")

    def append(self, role: str, content: str):
        """Append a single conversation turn (e.g. role='user'/'assistant')."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{role.upper()}: {content}\n")

    def close(self):
        """Mark the end of the call in the transcript file."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("-" * 50 + "\n")
            f.write(f"Ended: {datetime.now().isoformat(timespec='seconds')}\n")
