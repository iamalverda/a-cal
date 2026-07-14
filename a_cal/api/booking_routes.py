"""Booking API routes for public booking pages and booking management.

Provides the Calendly/cal.com-style booking flow:
- GET  /booking/{slug}      — public event type info (no auth)
- GET  /booking/{slug}/slots — available time slots (no auth)
- POST /booking/{slug}      — create a booking (no auth)
- GET  /bookings             — list bookings for the current user
- PATCH /bookings/{id}       — update booking (cancel, add notes)
- DELETE /bookings/{id}      — delete a booking
- POST /bookings/{id}/send-confirmation — send confirmation email

Also extends the event type endpoints with the new scheduling fields.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from a_cal.db.store import PersistentStore

# Phase 5: webhook dispatch + workflow triggers (lazy import to avoid circular deps)
def _dispatch_webhook(event_type: str, payload: dict, owner_user_id: str) -> None:
    """Fire a webhook event to the resource owner's webhooks only.

    ``owner_user_id`` scopes delivery to the event-type owner so a public
    booking never dispatches to another tenant's webhook endpoints.
    """
    try:
        from a_cal.integrations.webhooks import dispatch_event
        dispatch_event(event_type, payload, owner_user_id)
    except Exception as exc:
        logger.warning("webhook dispatch for %s failed: %s", event_type, exc)

def _trigger_workflows(trigger: str, context: dict) -> None:
    """Run workflows matching the given trigger.

    Maps booking lifecycle triggers to workflow trigger types. Booking
    events map to ``schedule_change`` which is the closest workflow trigger.
    """
    try:
        from a_cal.workflows.store import WorkflowStore
        from a_cal.workflows.runner import WorkflowRunner
        store = WorkflowStore(_db)
        wfs = store.list_workflows()
        # Map booking_created -> schedule_change workflow trigger
        wf_trigger = "schedule_change" if trigger == "booking_created" else trigger
        matching = [w for w in wfs if w.trigger == wf_trigger]
        if not matching:
            return
        # Workflows require a conductor — skip if not available
        from a_cal.api.agent_routes import _store as _agent_store
        from a_cal.auth.session import get_current_user_id
        conductor = _agent_store.get_conductor(get_current_user_id())
        runner = WorkflowRunner(conductor)
        import asyncio
        loop = asyncio.get_event_loop()
        for wf in matching:
            loop.create_task(
                runner.run(wf, initial_message=str(context))
            )
    except Exception as exc:
        logger.warning("workflow trigger %r failed: %s", trigger, exc)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-booking"])

_db = PersistentStore()


# --- models ----------------------------------------------------------------

class CustomQuestion(BaseModel):
    """A custom question on a booking form."""
    id: str
    label: str
    type: str = "text"  # text | textarea | select | phone | checkbox
    required: bool = False
    options: list[str] = Field(default_factory=list)
    placeholder: str = ""


class EventTypeExtendedRequest(BaseModel):
    """Payload for creating/updating an event type with scheduling fields."""
    title: str = "30 Minute Meeting"
    slug: str = "30-min"
    duration_minutes: int = 30
    description: str = ""
    scheduling_type: str = "collective"
    availability: dict[str, Any] = Field(default_factory=dict)
    color: str = "#3B82F6"
    metadata: dict[str, Any] = Field(default_factory=dict)
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    min_notice_hours: int = 24
    max_booking_days: int = 60
    recurring_pattern: str = "none"
    recurring_interval: int = 1
    custom_questions: list[dict[str, Any]] = Field(default_factory=list)
    video_provider: str = ""
    reminder_enabled: bool = True
    reminder_minutes_before: int = 60
    confirmation_email_enabled: bool = True
    confirmation_template: str | None = None
    # Phase 5: Team & Payments
    team_id: str | None = None
    assignment_strategy: str = "collective"
    routing_form_id: str | None = None
    is_paid: bool = False
    price_cents: int = 0
    currency: str = "USD"
    stripe_product_id: str | None = None


class BookingCreateRequest(BaseModel):
    """Public booking form submission."""
    attendee_name: str
    attendee_email: str
    attendee_timezone: str = "UTC"
    start_time: datetime
    answers: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class BookingOut(BaseModel):
    """Serialized booking returned to the frontend."""
    id: str
    event_type_id: str
    attendee_name: str
    attendee_email: str
    attendee_timezone: str = "UTC"
    start_time: datetime
    end_time: datetime
    status: str
    answers: dict[str, Any] = Field(default_factory=dict)
    video_link: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class BookingUpdateRequest(BaseModel):
    """Payload for updating a booking."""
    status: str | None = None
    notes: str | None = None
    video_link: str | None = None


# --- public booking endpoints (no auth) ------------------------------------

@router.get("/booking/{slug}")
def get_public_event_type(slug: str) -> dict[str, Any]:
    """Get event type info for a public booking page.

    This endpoint is unauthenticated — anyone with the slug can view the
    booking page. Returns only the fields needed for the booking UI.
    """
    et = _db.get_event_type_by_slug(slug)
    if et is None:
        raise HTTPException(status_code=404, detail="Booking page not found")
    return et


@router.get("/booking/{slug}/slots")
def get_booking_slots(
    slug: str,
    date: str = Query(..., description="ISO date to get slots for (YYYY-MM-DD)"),
    tz: str = Query("UTC", description="Attendee timezone"),
) -> dict[str, Any]:
    """Get available time slots for a given date.

    Computes free slots based on the event type's availability schedule,
    buffer times, min notice, max booking window, and existing bookings.
    """
    et = _db.get_event_type_by_slug(slug)
    if et is None:
        raise HTTPException(status_code=404, detail="Booking page not found")

    try:
        target_date = datetime.fromisoformat(date).replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    now = datetime.now(UTC)
    min_notice = timedelta(hours=et.get("min_notice_hours", 24))
    max_window = timedelta(days=et.get("max_booking_days", 60))

    if target_date.date() < now.date():
        return {"slots": [], "reason": "past_date"}
    if target_date > now + max_window:
        return {"slots": [], "reason": "outside_booking_window"}

    duration = et.get("duration_minutes", 30)
    buffer_before = et.get("buffer_before_minutes", 0)
    buffer_after = et.get("buffer_after_minutes", 0)

    # Get the availability schedule for this weekday
    availability = et.get("availability", {})
    days = availability.get("days", [])
    # Default schedule if none configured
    if not days or len(days) != 7:
        days = [
            [{"start": "09:00", "end": "17:00"}],  # Mon
            [{"start": "09:00", "end": "17:00"}],  # Tue
            [{"start": "09:00", "end": "17:00"}],  # Wed
            [{"start": "09:00", "end": "17:00"}],  # Thu
            [{"start": "09:00", "end": "17:00"}],  # Fri
            [],  # Sat
            [],  # Sun
        ]

    # weekday(): Monday=0..Sunday=6 (matches our schedule index)
    weekday = target_date.weekday()
    day_hours = days[weekday] if 0 <= weekday < 7 else []
    if not day_hours:
        return {"slots": [], "reason": "no_availability"}

    slots: list[dict[str, str]] = []
    for hours in day_hours:
        start_str = hours.get("start", "09:00")
        end_str = hours.get("end", "17:00")
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))

        slot_start = target_date.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        slot_end_of_day = target_date.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

        # Generate slots with buffer
        total_needed = duration + buffer_before + buffer_after
        current = slot_start

        while current + timedelta(minutes=total_needed) <= slot_end_of_day:
            # Apply min notice: skip slots that are too soon
            if current + timedelta(minutes=buffer_before) < now + min_notice:
                current += timedelta(minutes=15)
                continue

            # Check if this slot conflicts with existing bookings
            booking_start = current + timedelta(minutes=buffer_before)
            booking_end = booking_start + timedelta(minutes=duration)
            if _db.check_slot_available(et["id"], booking_start, booking_end):
                slots.append({
                    "start": booking_start.isoformat(),
                    "end": booking_end.isoformat(),
                })

            current += timedelta(minutes=15)  # 15-min slot granularity

    return {
        "event_type_id": et["id"],
        "date": date,
        "duration_minutes": duration,
        "slots": slots,
        "timezone": et.get("availability", {}).get("timezone", "UTC"),
    }


@router.post("/booking/{slug}")
def create_public_booking(slug: str, body: BookingCreateRequest) -> dict[str, Any]:
    """Create a booking from the public booking page.

    Validates the slot is available, generates a video link if configured,
    and sends a confirmation email if enabled.
    """
    et = _db.get_event_type_by_slug(slug)
    if et is None:
        raise HTTPException(status_code=404, detail="Booking page not found")

    duration = et.get("duration_minutes", 30)
    buffer_before = et.get("buffer_before_minutes", 0)
    end_time = body.start_time + timedelta(minutes=duration)

    # Re-check slot availability at booking time
    booking_start = body.start_time
    if not _db.check_slot_available(et["id"], booking_start, end_time):
        raise HTTPException(status_code=409, detail="This time slot is no longer available")

    # Generate video link if a provider is configured
    video_link = _generate_video_link(et.get("video_provider", ""))

    # Phase 5: Round-robin team member assignment
    assigned_member_id = None
    team_id = et.get("team_id")
    strategy = et.get("assignment_strategy", "collective")
    if team_id and strategy == "round_robin":
        member = _db.get_next_round_robin_member(team_id)
        if member:
            assigned_member_id = member["id"]

    # Phase 5: Payment status for paid events
    payment_status = "paid" if not et.get("is_paid") else "pending_payment"

    booking = _db.create_booking({
        "event_type_id": et["id"],
        "attendee_name": body.attendee_name,
        "attendee_email": body.attendee_email,
        "attendee_timezone": body.attendee_timezone,
        "start_time": body.start_time,
        "end_time": end_time,
        "answers": body.answers,
        "video_link": video_link,
        "notes": body.notes,
        "assigned_member_id": assigned_member_id,
        "payment_status": payment_status,
    })

    # Send confirmation email if enabled
    if et.get("confirmation_email_enabled", True):
        try:
            _send_confirmation_email(et, booking)
        except Exception as exc:
            logger.warning("Confirmation email failed for booking %s: %s", booking["id"], exc)

    # Phase 5: Dispatch webhook event — only to the event-type owner's
    # webhooks. booking["user_id"] is stamped from the event type's owner
    # in create_booking, so a public booking never reaches other tenants.
    _dispatch_webhook("booking.created", {
        "booking_id": booking["id"],
        "event_type_id": et["id"],
        "event_type_title": et.get("title", ""),
        "attendee_name": body.attendee_name,
        "attendee_email": body.attendee_email,
        "start_time": booking["start_time"],
        "assigned_member_id": assigned_member_id,
        "is_paid": et.get("is_paid", False),
    }, booking["user_id"])

    # Phase 5: Trigger booking-related workflows
    _trigger_workflows("booking_created", {
        "booking_id": booking["id"],
        "event_type": et.get("title", ""),
    })

    return {
        "status": "confirmed" if payment_status == "paid" else "pending_payment",
        "booking_id": booking["id"],
        "start_time": booking["start_time"],
        "end_time": booking["end_time"],
        "video_link": video_link,
        "event_type_title": et.get("title", ""),
        "assigned_member_id": assigned_member_id,
        "payment_status": payment_status,
        "price_cents": et.get("price_cents", 0) if et.get("is_paid") else 0,
        "currency": et.get("currency", "USD"),
    }


# --- authenticated booking management endpoints ----------------------------

@router.get("/bookings", response_model=list[dict[str, Any]])
def list_bookings(
    event_type_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List bookings for the current user."""
    return _db.list_bookings(event_type_id)


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> dict[str, Any]:
    """Get a single booking by ID."""
    b = _db.get_booking(booking_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return b


@router.patch("/bookings/{booking_id}")
def update_booking(booking_id: str, body: BookingUpdateRequest) -> dict[str, Any]:
    """Update a booking (cancel, add notes, update video link)."""
    patch: dict[str, Any] = {}
    if body.status is not None:
        patch["status"] = body.status
    if body.notes is not None:
        patch["notes"] = body.notes
    if body.video_link is not None:
        patch["video_link"] = body.video_link

    result = _db.update_booking(booking_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return result


@router.delete("/bookings/{booking_id}")
def delete_booking(booking_id: str) -> dict[str, str]:
    """Delete a booking."""
    if not _db.delete_booking(booking_id):
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"status": "deleted", "booking_id": booking_id}


@router.post("/bookings/{booking_id}/send-confirmation")
def send_booking_confirmation(booking_id: str) -> dict[str, Any]:
    """Resend a booking confirmation email."""
    b = _db.get_booking(booking_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    et = _db.get_event_type(b.get("event_type_id", ""))
    if et is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    _send_confirmation_email(et, b)
    return {"status": "sent", "booking_id": booking_id}


# --- event type extended endpoints -----------------------------------------

@router.put("/event-types/{event_type_id}")
def update_event_type(event_type_id: str, body: EventTypeExtendedRequest) -> dict[str, Any]:
    """Update an event type with full scheduling configuration."""
    result = _db.update_event_type(event_type_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    return result


# --- helpers ---------------------------------------------------------------

def _generate_video_link(provider: str) -> str | None:
    """Generate a video conference link for the given provider.

    Creates a deterministic-but-unique room URL. In production this would
    call the provider's API to create a real meeting; in standalone mode
    we generate a plausible link.

    Args:
        provider: "zoom", "meet", "teams", or "" (none).

    Returns:
        A video link URL, or None if no provider is configured.
    """
    room_id = secrets.token_hex(5)
    if provider == "zoom":
        return f"https://zoom.us/j/{room_id}{secrets.token_hex(3)}"
    elif provider == "meet":
        # Google Meet style: xxx-xxxx-xxx
        parts = [secrets.token_hex(3), secrets.token_hex(2), secrets.token_hex(3)]
        return f"https://meet.google.com/{'-'.join(parts)}"
    elif provider == "teams":
        return f"https://teams.microsoft.com/l/meetup-join/19:meeting_{room_id}"
    return None


def _send_confirmation_email(event_type: dict[str, Any], booking: dict[str, Any]) -> None:
    """Send a booking confirmation email to the attendee.

    Uses the user's connected email provider to send the confirmation.
    Falls back to logging if no email provider is available.

    Args:
        event_type: The event type dict.
        booking: The booking dict.
    """
    title = event_type.get("title", "Meeting")
    start_str = booking.get("start_time", "")
    if isinstance(start_str, str) and start_str:
        try:
            dt = datetime.fromisoformat(start_str)
            start_str = dt.strftime("%A, %B %d at %I:%M %p UTC")
        except Exception:
            pass

    template = event_type.get("confirmation_template") or (
        f"Hi {booking.get('attendee_name', '')},\n\n"
        f"Your booking is confirmed!\n\n"
        f"Event: {title}\n"
        f"When: {start_str}\n"
        f"Duration: {event_type.get('duration_minutes', 30)} minutes\n"
    )
    if booking.get("video_link"):
        template += f"\nJoin the meeting: {booking['video_link']}\n"
    template += "\nWe look forward to meeting with you.\n\nA-Cal"

    # Try to send via connected email provider
    try:
        from a_cal.providers.factory import build_email_provider

        all_providers = _db.list_providers()
        email_providers = [
            p for p in all_providers
            if p["provider_type"] in ("imap_smtp", "gmail")
            and p.get("status") == "connected"
        ]
        if email_providers:
            provider = build_email_provider(email_providers[0])
            # Fire-and-forget — we can't await in a sync function.
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(provider.send_message(
                    to=[booking.get("attendee_email", "")],
                    subject=f"Confirmed: {title}",
                    body_text=template,
                ))
            else:
                loop.run_until_complete(provider.send_message(
                    to=[booking.get("attendee_email", "")],
                    subject=f"Confirmed: {title}",
                    body_text=template,
                ))
        else:
            logger.info("No email provider connected — confirmation email logged only")
            logger.info("Confirmation for %s: %s", booking.get("attendee_email"), template[:100])
    except Exception as exc:
        logger.warning("Confirmation email send failed: %s", exc)
        logger.info("Confirmation content: %s", template[:200])
