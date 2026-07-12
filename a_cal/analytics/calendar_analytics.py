"""Calendar analytics — ported from zero-calendar's TypeScript analytics.

These functions analyze calendar events to produce insights about busy
times, meeting load, and available slots. They feed into:
  - The analytics panel in the frontend
  - The self-model's pattern memory (auto-learning from synced events)
  - The schedule agent's slot-finding and reschedule suggestions

Ported from zero-calendar/lib/calendar-utils.ts and lib/ai-tools.ts,
adapted to Python with timezone-aware datetime handling.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Day names indexed by weekday() (Monday=0 in Python, vs Sunday=0 in JS)
_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse an ISO datetime string, returning None on failure."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt
    except (ValueError, TypeError):
        return None


def _to_naive(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to naive UTC for comparisons."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def analyze_busy_times(
    events: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Analyze which days of week and hours are busiest.

    Ported from zero-calendar's analyzeBusyTimes. Returns busy-by-day-of-week
    (in hours), event count by day of week, busy-by-hour (event count per
    hour), and the busiest day and hour.

    Args:
        events: List of event dicts with 'start', 'end' ISO strings.
        start: Range start (naive or aware).
        end: Range end (naive or aware).

    Returns:
        Dict with total_events, busy_by_day_of_week (7 floats),
        events_by_day_of_week (7 ints), busy_by_hour (24 ints),
        busiest_day (str), busiest_day_hours (float),
        busiest_hour (int), busiest_hour_count (int).
    """
    start_naive = _to_naive(start)
    end_naive = _to_naive(end)

    busy_by_dow = [0.0] * 7       # hours
    events_by_dow = [0] * 7       # count
    busy_by_hour = [0] * 24       # count

    for evt in events:
        evt_start = _parse_dt(evt.get("start", ""))
        evt_end = _parse_dt(evt.get("end", ""))
        if evt_start is None or evt_end is None:
            continue

        evt_start_n = _to_naive(evt_start)
        evt_end_n = _to_naive(evt_end)

        # Check overlap with range
        if evt_end_n < start_naive or evt_start_n > end_naive:
            continue

        # Skip all-day events (duration >= 24h or flagged)
        duration_hours = (evt_end_n - evt_start_n).total_seconds() / 3600
        if duration_hours >= 24 or evt.get("all_day"):
            continue

        # Python weekday(): Monday=0..Sunday=6
        dow = evt_start_n.weekday()
        busy_by_dow[dow] += duration_hours
        events_by_dow[dow] += 1

        start_hour = evt_start_n.hour
        end_hour = evt_end_n.hour + (1 if evt_end_n.minute > 0 else 0)
        for hour in range(start_hour, min(end_hour, 24)):
            busy_by_hour[hour] += 1

    # Find busiest day
    busiest_day_idx = 0
    busiest_day_hours = 0.0
    for i, hours in enumerate(busy_by_dow):
        if hours > busiest_day_hours:
            busiest_day_idx = i
            busiest_day_hours = hours

    # Find busiest hour
    busiest_hour = 0
    busiest_hour_count = 0
    for hour, count in enumerate(busy_by_hour):
        if count > busiest_hour_count:
            busiest_hour = hour
            busiest_hour_count = count

    return {
        "total_events": sum(events_by_dow),
        "busy_by_day_of_week": busy_by_dow,
        "events_by_day_of_week": events_by_dow,
        "busy_by_hour": busy_by_hour,
        "busiest_day": _DAY_NAMES[busiest_day_idx],
        "busiest_day_hours": round(busiest_day_hours, 1),
        "busiest_hour": busiest_hour,
        "busiest_hour_count": busiest_hour_count,
    }


def get_calendar_analytics(
    events: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Compute comprehensive meeting statistics over a date range.

    Ported from zero-calendar's getCalendarAnalytics. Returns total meeting
    minutes/hours, meeting count, average meeting length, average daily
    meeting time, category breakdown, and busiest day.

    Args:
        events: List of event dicts with 'start', 'end', optional 'metadata'.
        start: Range start.
        end: Range end.

    Returns:
        Dict with total_meeting_minutes, total_meeting_hours, meeting_count,
        average_meeting_length, average_daily_meeting_minutes,
        average_daily_meeting_hours, category_counts, busiest_day,
        busiest_day_minutes, busiest_day_hours, daily_meeting_minutes.
    """
    start_naive = _to_naive(start)
    end_naive = _to_naive(end)

    total_minutes = 0.0
    meeting_count = 0
    category_counts: Dict[str, int] = defaultdict(int)
    daily_minutes: Dict[str, float] = defaultdict(float)

    for evt in events:
        evt_start = _parse_dt(evt.get("start", ""))
        evt_end = _parse_dt(evt.get("end", ""))
        if evt_start is None or evt_end is None:
            continue

        evt_start_n = _to_naive(evt_start)
        evt_end_n = _to_naive(evt_end)

        if evt_end_n < start_naive or evt_start_n > end_naive:
            continue

        duration_hours = (evt_end_n - evt_start_n).total_seconds() / 3600
        if duration_hours >= 24 or evt.get("all_day"):
            continue

        duration_min = duration_hours * 60
        total_minutes += duration_min
        meeting_count += 1

        # Category from metadata or default
        metadata = evt.get("metadata", {})
        if isinstance(metadata, dict):
            cats = metadata.get("categories", [])
        else:
            cats = []
        if cats:
            for cat in cats:
                category_counts[str(cat)] += 1
        else:
            category_counts["Uncategorized"] += 1

        date_key = evt_start_n.strftime("%Y-%m-%d")
        daily_minutes[date_key] += duration_min

    day_count = max(1, (end_naive - start_naive).days)
    avg_daily = total_minutes / day_count

    busiest_day = ""
    busiest_day_minutes = 0.0
    for date, minutes in daily_minutes.items():
        if minutes > busiest_day_minutes:
            busiest_day = date
            busiest_day_minutes = minutes

    return {
        "total_meeting_minutes": round(total_minutes),
        "total_meeting_hours": round(total_minutes / 60, 1),
        "meeting_count": meeting_count,
        "average_meeting_length": round(total_minutes / meeting_count) if meeting_count > 0 else 0,
        "average_daily_meeting_minutes": round(avg_daily),
        "average_daily_meeting_hours": round(avg_daily / 60, 1),
        "category_counts": dict(category_counts),
        "busiest_day": busiest_day,
        "busiest_day_minutes": round(busiest_day_minutes),
        "busiest_day_hours": round(busiest_day_minutes / 60, 1),
        "daily_meeting_minutes": {k: round(v) for k, v in daily_minutes.items()},
    }


def find_free_time_slots_range(
    events: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
    min_duration_minutes: int = 30,
    work_start_hour: int = 9,
    work_end_hour: int = 17,
) -> List[Dict[str, Any]]:
    """Find free time slots across a multi-day range.

    Ported from zero-calendar's findFreeTimeSlots. Iterates each day in the
    range, applies working hours, and finds gaps between events that are at
    least min_duration_minutes long.

    Args:
        events: List of event dicts with 'start', 'end' ISO strings.
        start: Range start.
        end: Range end.
        min_duration_minutes: Minimum slot duration.
        work_start_hour: Working hours start (default 9).
        work_end_hour: Working hours end (default 17).

    Returns:
        List of {'start': ISO, 'end': ISO, 'duration': int} slots.
    """
    start_naive = _to_naive(start)
    end_naive = _to_naive(end)

    # Collect and sort all events in range
    busy_intervals: List[Tuple[datetime, datetime]] = []
    for evt in events:
        evt_start = _parse_dt(evt.get("start", ""))
        evt_end = _parse_dt(evt.get("end", ""))
        if evt_start is None or evt_end is None:
            continue
        evt_start_n = _to_naive(evt_start)
        evt_end_n = _to_naive(evt_end)
        if evt_end_n < start_naive or evt_start_n > end_naive:
            continue
        busy_intervals.append((evt_start_n, evt_end_n))

    busy_intervals.sort(key=lambda x: x[0])

    slots: List[Dict[str, Any]] = []
    min_delta = timedelta(minutes=min_duration_minutes)

    current_day = start_naive.replace(hour=0, minute=0, second=0, microsecond=0)

    while current_day <= end_naive:
        day_start = current_day.replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
        day_end = current_day.replace(hour=work_end_hour, minute=0, second=0, microsecond=0)

        # Skip days outside range
        if day_end < start_naive or day_start > end_naive:
            current_day += timedelta(days=1)
            continue

        effective_start = max(day_start, start_naive)
        effective_end = min(day_end, end_naive)

        # Find events overlapping this day's work window
        day_busy = []
        for b_start, b_end in busy_intervals:
            clamped_start = max(b_start, effective_start)
            clamped_end = min(b_end, effective_end)
            if clamped_start < clamped_end:
                day_busy.append((clamped_start, clamped_end))

        day_busy.sort(key=lambda x: x[0])

        # Find gaps
        cursor = effective_start
        for b_start, b_end in day_busy:
            if cursor + min_delta <= b_start:
                slots.append({
                    "start": cursor.isoformat(),
                    "end": b_start.isoformat(),
                    "duration": int((b_start - cursor).total_seconds() / 60),
                })
            cursor = max(cursor, b_end)

        if cursor + min_delta <= effective_end:
            slots.append({
                "start": cursor.isoformat(),
                "end": effective_end.isoformat(),
                "duration": int((effective_end - cursor).total_seconds() / 60),
            })

        current_day += timedelta(days=1)

    return slots


def suggest_rescheduling(
    events: List[Dict[str, Any]],
    event_id: str,
    look_ahead_days: int = 14,
    work_start_hour: int = 9,
    work_end_hour: int = 17,
) -> Dict[str, Any]:
    """Suggest alternative time slots for an existing event.

    Ported from zero-calendar's suggestRescheduling. Finds the target event,
    calculates its duration, searches for free slots in the next N days
    (excluding the event's current day), and returns up to 3 alternatives.

    Args:
        events: List of event dicts.
        event_id: The provider_event_id of the event to reschedule.
        look_ahead_days: How many days ahead to search.
        work_start_hour: Working hours start.
        work_end_hour: Working hours end.

    Returns:
        Dict with success, event (title/start/end/duration), alternative_slots.
    """
    target = None
    for evt in events:
        if evt.get("provider_event_id") == event_id or evt.get("id") == event_id:
            target = evt
            break

    if target is None:
        return {"success": False, "message": "Event not found"}

    evt_start = _parse_dt(target.get("start", ""))
    evt_end = _parse_dt(target.get("end", ""))
    if evt_start is None or evt_end is None:
        return {"success": False, "message": "Event has invalid times"}

    evt_start_n = _to_naive(evt_start)
    evt_end_n = _to_naive(evt_end)
    duration_min = int((evt_end_n - evt_start_n).total_seconds() / 60)

    now = datetime.utcnow()
    future = now + timedelta(days=look_ahead_days)

    free_slots = find_free_time_slots_range(
        events=events,
        start=now,
        end=future,
        min_duration_minutes=duration_min,
        work_start_hour=work_start_hour,
        work_end_hour=work_end_hour,
    )

    # Exclude slots on the same day as the current event
    alternatives = [
        s for s in free_slots
        if not _to_naive(_parse_dt(s["start"]) or datetime.utcnow()).date()
        == evt_start_n.date()
    ][:3]

    return {
        "success": True,
        "event": {
            "id": event_id,
            "title": target.get("title", "Untitled"),
            "start": evt_start.isoformat(),
            "end": evt_end.isoformat(),
            "duration": duration_min,
        },
        "alternative_slots": alternatives,
    }
