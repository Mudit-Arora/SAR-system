"""
Mock scheduling service - in-memory dental appointment system.

This simulates a real scheduling backend (like Dentrix, Open Dental, etc.)
with an async interface that looks like HTTP API calls.  To swap this for
a real backend, replace the method bodies with actual HTTP requests - the
voice agent layer doesn't need to change.

Slots are generated lazily - any future business day gets slots on first
access, so the agent can schedule appointments weeks or months out.
On startup, pre-generates the next 5 business days plus 2 existing patients.
"""
import logging
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

from backend.models import TimeSlot, Patient, Appointment

logger = logging.getLogger(__name__)

# Providers
PROVIDERS = [
    ("Dr. Sarah Chen", ["checkup", "consultation"]),
    ("Dr. Michael Rivera", ["checkup", "consultation"]),
    ("Lisa Thompson RDH", ["cleaning"]),
]

# Slot hours: 9 AM to 4 PM
SLOT_HOURS = list(range(9, 17))


class SchedulingService:
    """In-memory scheduling backend with async methods."""

    def __init__(self):
        self.slots: dict[str, TimeSlot] = {}
        self.appointments: dict[str, Appointment] = {}
        self._generated_dates: set[str] = set()
        self._generate_initial_data()

    def _generate_slots_for_date(self, date_str: str):
        """Generate slots for a single date if not already generated.

        Uses the date string as a random seed so the same date always
        produces the same slots (deterministic across calls).
        """
        if date_str in self._generated_dates:
            return
        self._generated_dates.add(date_str)

        # Seed based on date for deterministic results per date
        rng = random.Random(date_str)

        for provider_name, service_types in PROVIDERS:
            for hour in SLOT_HOURS:
                service_type = rng.choice(service_types)
                slot_id = f"slot-{uuid.uuid4().hex[:8]}"
                slot = TimeSlot(
                    id=slot_id,
                    provider=provider_name,
                    date=date_str,
                    time=f"{hour:02d}:00",
                    duration_minutes=60,
                    service_type=service_type,
                )
                # ~30% chance of being pre-booked
                if rng.random() < 0.3:
                    slot.is_available = False
                self.slots[slot_id] = slot

    def _ensure_slots_for_date(self, date_str: str):
        """Ensure slots exist for a date, generating them if needed.

        Skips weekends - dental offices are closed.
        """
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return
        if dt.weekday() >= 5:  # Weekend
            return
        if dt < datetime.now().date():  # Past date
            return
        self._generate_slots_for_date(date_str)

    def _ensure_slots_for_upcoming(self, num_days: int = 5):
        """Ensure slots exist for the next N business days."""
        today = datetime.now().date()
        current = today + timedelta(days=1)
        generated = 0
        while generated < num_days:
            if current.weekday() < 5:
                self._generate_slots_for_date(current.strftime("%Y-%m-%d"))
                generated += 1
            current += timedelta(days=1)

    def _generate_initial_data(self):
        """Create initial slots and sample patient appointments."""
        # Generate slots for the next 5 business days
        self._ensure_slots_for_upcoming(5)

        # Create 2 existing patients with appointments
        existing_patients = [
            Patient(name="Maria Garcia", phone="555-0101"),
            Patient(name="James Wilson", phone="555-0102"),
        ]

        available = [s for s in self.slots.values() if s.is_available]
        for i, patient in enumerate(existing_patients):
            if i < len(available):
                slot = available[i]
                slot.is_available = False
                appt_id = f"appt-{uuid.uuid4().hex[:8]}"
                self.appointments[appt_id] = Appointment(
                    id=appt_id,
                    patient=patient,
                    slot=slot,
                )

        total = len(self.slots)
        booked = sum(1 for s in self.slots.values() if not s.is_available)
        logger.info(f"[BACKEND] Generated {total} slots ({booked} booked, {total - booked} available)")
        logger.info(f"[BACKEND] {len(self.appointments)} existing appointments")

    # ------------------------------------------------------------------
    # Public API - these are the methods the voice agent calls
    # ------------------------------------------------------------------

    async def get_available_slots(
        self, date: Optional[str] = None, provider: Optional[str] = None
    ) -> dict:
        """Get available appointment slots, optionally filtered by date and/or provider.

        Slots are generated on-the-fly for any future business day, so the
        agent can schedule appointments arbitrarily far in the future.
        """
        # Ensure slots exist for the requested date(s)
        if date:
            self._ensure_slots_for_date(date)
        else:
            self._ensure_slots_for_upcoming(5)

        matches = [
            s for s in self.slots.values()
            if s.is_available
            and (date is None or s.date == date)
            and (provider is None or provider.lower() in s.provider.lower())
        ]

        if not matches:
            if date:
                # Check if it's a weekend
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d").date()
                    if dt.weekday() >= 5:
                        return {
                            "available_slots": [],
                            "message": f"The office is closed on weekends. {date} is a {'Saturday' if dt.weekday() == 5 else 'Sunday'}.",
                        }
                except ValueError:
                    pass
                return {
                    "available_slots": [],
                    "message": f"No available slots for {date}. All slots are booked.",
                }
            return {"available_slots": [], "message": "No available slots found."}

        # Sort by date/time and limit results.  For a voice conversation,
        # 5 options is plenty - nobody wants 10 slots read aloud.
        matches.sort(key=lambda s: (s.date, s.time))
        slots_to_show = matches[:5]

        return {
            "available_slots": [
                {
                    "slot_id": s.id,
                    "provider": s.provider,
                    "date": s.date,
                    "time": s.time,
                    "service_type": s.service_type,
                }
                for s in slots_to_show
            ],
            "total_available": len(matches),
        }

    async def book_appointment(
        self, patient_name: str, patient_phone: str, slot_id: str
    ) -> dict:
        """Book an appointment.  Returns confirmation or error."""
        slot = self.slots.get(slot_id)
        if not slot:
            return {"success": False, "error": "Slot not found. Please check availability again."}

        if not slot.is_available:
            return {"success": False, "error": "That slot is no longer available. Please check availability again."}

        # Book it
        slot.is_available = False
        patient = Patient(name=patient_name, phone=patient_phone)
        appt_id = f"appt-{uuid.uuid4().hex[:8]}"
        appointment = Appointment(id=appt_id, patient=patient, slot=slot)
        self.appointments[appt_id] = appointment

        logger.info(f"[BACKEND] Booked: {appointment.display()}")

        return {
            "success": True,
            "appointment_id": appt_id,
            "confirmation": f"Booked: {slot.display()}",
            "patient_name": patient_name,
        }

    async def check_appointment(
        self, patient_name: Optional[str] = None, patient_phone: Optional[str] = None
    ) -> dict:
        """Look up a patient's existing appointment(s)."""
        if not patient_name and not patient_phone:
            return {"error": "Please provide the patient's name or phone number."}

        matches = []
        for appt in self.appointments.values():
            if patient_name and patient_name.lower() in appt.patient.name.lower():
                matches.append(appt)
            elif patient_phone and patient_phone in appt.patient.phone:
                matches.append(appt)

        if not matches:
            return {
                "found": False,
                "message": "No appointments found for that patient.",
            }

        return {
            "found": True,
            "appointments": [
                {
                    "appointment_id": a.id,
                    "provider": a.slot.provider,
                    "date": a.slot.date,
                    "time": a.slot.time,
                    "service_type": a.slot.service_type,
                    "description": a.slot.display(),
                }
                for a in matches
            ],
        }

    async def cancel_appointment(self, appointment_id: str) -> dict:
        """Cancel an appointment and free up the slot."""
        appt = self.appointments.get(appointment_id)
        if not appt:
            return {"success": False, "error": "Appointment not found."}

        # Free the slot
        appt.slot.is_available = True
        del self.appointments[appointment_id]

        logger.info(f"[BACKEND] Cancelled: {appt.display()}")

        return {
            "success": True,
            "message": f"Cancelled the appointment: {appt.slot.display()}",
        }


# Singleton - created once at import time, shared across all calls.
# In production, you'd replace this with an HTTP client to your real backend.
scheduling_service = SchedulingService()
