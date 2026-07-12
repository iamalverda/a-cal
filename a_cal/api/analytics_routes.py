"""Analytics and event-type API routes for A-Cal.

These endpoints expose the calendar analytics engine (ported from
zero-calendar) and the event-type/availability system (ported from
cal.com) to the frontend.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from a_cal.analytics.calendar_analytics import (
    analyze_busy_times,
    find_free_time_slots_range,
    get_calendar_analytics,
    suggest_rescheduling,
)
from a_cal.integrations.calcom_bridge import (
    AvailabilitySchedule,
    EventStatus,
    SchedulingType,
    get_aggregated_availability,
)
from a_cal.integrations.zero_calendar_bridge import CALENDAR_TOOLS, get_enhanced_schedule_prompt
from a_cal.db.store import PersistentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-analytics"])

_db = PersistentStore()


def _fetch_events(days: int = 30) -> List[Dict[str, Any]]:
    """Fetch unified calendar events from the store."""
    try:
        events = _db.get_unified_calendar(days)
        return events if isinstance(events, list) else []
    except Exception as exc:
        logger.debug("event fetch failed: %s", exc)
        return []


# --- analytics endpoints ---------------------------------------------------

class AnalyticsSummaryResponse(BaseModel):
    """Combined analytics summary for the dashboard."""
    busy_times: Dict[str, Any]
    meeting_stats: Dict[str, Any]
    period_days: int


@router.get("/analytics/summary")
def get_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
):
    """Get a combined analytics summary (busy times + meeting stats).

    Returns both busy-time analysis (which days/hours are busiest) and
    meeting statistics (total hours, meeting count, averages) for the
    specified lookback period.
    """
    events = _fetch_events(days)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    busy = analyze_busy_times(events, start, now)
    stats = get_calendar_analytics(events, start, now)

    return AnalyticsSummaryResponse(
        busy_times=busy,
        meeting_stats=stats,
        period_days=days,
    ).model_dump()


@router.get("/analytics/busy-times")
def get_busy_times(
    days: int = Query(30, ge=1, le=365),
):
    """Get busy-time analysis (busiest days of week and hours)."""
    events = _fetch_events(days)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return analyze_busy_times(events, start, now)


@router.get("/analytics/meeting-stats")
def get_meeting_stats(
    days: int = Query(30, ge=1, le=365),
):
    """Get meeting statistics (count, duration, categories)."""
    events = _fetch_events(days)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return get_calendar_analytics(events, start, now)


@router.get("/analytics/free-slots")
def get_free_slots(
    start_date: str = Query(..., description="ISO start date"),
    end_date: str = Query(..., description="ISO end date"),
    min_duration: int = Query(30, ge=5, le=480, description="Minimum slot duration in minutes"),
    work_start: int = Query(9, ge=0, le=23, description="Working hours start"),
    work_end: int = Query(17, ge=1, le=24, description="Working hours end"),
):
    """Find free time slots across a date range (multi-day)."""
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

    # Fetch events covering the full range
    range_days = max(1, (end - start).days + 1)
    events = _fetch_events(range_days + 7)  # extra buffer
    slots = find_free_time_slots_range(
        events, start, end, min_duration, work_start, work_end,
    )
    return {"free_slots": slots, "total": len(slots)}


@router.post("/analytics/suggest-reschedule")
def suggest_reschedule(body: SuggestRescheduleRequest):
    """Suggest alternative time slots for an existing event."""
    events = _fetch_events(30)
    return suggest_rescheduling(events, body.event_id, body.look_ahead_days)


class SuggestRescheduleRequest(BaseModel):
    """Request body for reschedule suggestions."""
    event_id: str
    look_ahead_days: int = 14


# --- event type endpoints (cal.com integration) ---------------------------

class EventTypeRequest(BaseModel):
    """Payload for creating/updating an event type."""
    title: str = "30 Minute Meeting"
    slug: str = "30-min"
    duration_minutes: int = 30
    description: str = ""
    scheduling_type: str = "collective"
    availability: Dict[str, Any] = Field(default_factory=dict)
    color: str = "#3B82F6"
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/event-types")
def list_event_types():
    """List all event types (cal.com-style booking pages)."""
    return _db.list_event_types()


@router.post("/event-types")
def create_event_type(body: EventTypeRequest):
    """Create a new event type and persist it to the database."""
    return _db.create_event_type(body.model_dump())


@router.delete("/event-types/{event_type_id}")
def delete_event_type(event_type_id: str):
    """Delete an event type."""
    _db.delete_event_type(event_type_id)
    return {"deleted": event_type_id}


@router.get("/event-types/{event_type_id}")
def get_event_type(event_type_id: str):
    """Get a single event type by ID."""
    from fastapi import HTTPException
    et = _db.get_event_type(event_type_id)
    if et is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    return et


# --- availability endpoints ------------------------------------------------

@router.get("/availability/schedule")
def get_availability_schedule():
    """Get the default availability schedule (working hours per day)."""
    return AvailabilitySchedule().to_dict()


@router.post("/availability/aggregated")
def get_aggregated_availability_endpoint(body: AggregatedAvailabilityRequest):
    """Compute aggregated availability across multiple participants.

    Uses cal.com's scheduling logic: collective = intersection of all,
    round_robin = union of all, managed = first participant's schedule.
    """
    schedules = [AvailabilitySchedule.from_dict(s) for s in body.schedules]
    try:
        sched_type = SchedulingType(body.scheduling_type)
    except ValueError:
        sched_type = SchedulingType.COLLECTIVE
    aggregated = get_aggregated_availability(schedules, sched_type)
    return {"days": aggregated, "scheduling_type": sched_type.value}


class AggregatedAvailabilityRequest(BaseModel):
    """Request body for aggregated availability."""
    schedules: List[Dict[str, Any]] = Field(default_factory=list)
    scheduling_type: str = "collective"


# --- zero-calendar tool catalog -------------------------------------------

@router.get("/calendar-tools")
def list_calendar_tools():
    """List the available calendar AI tools (ported from zero-calendar)."""
    return {"tools": CALENDAR_TOOLS, "count": len(CALENDAR_TOOLS)}


@router.get("/schedule-prompt")
def get_schedule_prompt(timezone: str = Query("UTC")):
    """Get the enhanced schedule agent system prompt (zero-calendar patterns)."""
    return {"prompt": get_enhanced_schedule_prompt(user_timezone=timezone)}
