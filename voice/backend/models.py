"""
Data models for the scheduling backend.

These are plain dataclasses - no ORM, no database.  They define the shape
of the data that flows between the voice agent and the scheduling service.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TimeSlot:
    """An available appointment slot."""
    id: str
    provider: str
    date: str           # YYYY-MM-DD
    time: str           # HH:MM (24h)
    duration_minutes: int
    service_type: str   # "cleaning", "checkup", "consultation"
    is_available: bool = True

    def display(self) -> str:
        """Human-readable description for the agent to read aloud."""
        # Convert 24h time to 12h for natural speech
        hour, minute = map(int, self.time.split(":"))
        period = "AM" if hour < 12 else "PM"
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        time_str = f"{display_hour}:{minute:02d} {period}" if minute else f"{display_hour} {period}"
        return f"{self.service_type.title()} with {self.provider} on {self.date} at {time_str}"


@dataclass
class Patient:
    """A patient record."""
    name: str
    phone: str


@dataclass
class Appointment:
    """A booked appointment."""
    id: str
    patient: Patient
    slot: TimeSlot
    booked_at: datetime = field(default_factory=datetime.now)

    def display(self) -> str:
        return f"{self.slot.display()} - Patient: {self.patient.name}"
