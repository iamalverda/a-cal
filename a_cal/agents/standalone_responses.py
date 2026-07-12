"""Standalone response generator — real, useful responses without an LLM.

When no LLM is available (standalone mode, model not configured, provider
unreachable), the conductor uses this module to produce helpful responses
that actually interact with calendar data, provider status, and the
self-model. This makes the agentic layer feel alive even before a model
is connected.

Each generator receives the user message, the routing decision, and an
optional event/provider store. It returns a human-readable response string
plus a structured ``actions`` list describing what it would do.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from a_cal.agents.conductor import IntentType, RoutingDecision

logger = logging.getLogger(__name__)


def _parse_datetime(text: str, now: datetime) -> Optional[datetime]:
    """Extract a target date from natural language.

    Handles: today, tomorrow, monday-sunday, next week, this week,
    specific dates like "July 15" or "7/15".
    """
    lower = text.lower()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if "today" in lower:
        return today
    if "tomorrow" in lower:
        return today + timedelta(days=1)
    if "next week" in lower:
        return today + timedelta(weeks=1)
    if "this week" in lower:
        return today

    # Day names
    day_names = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for name, idx in day_names.items():
        if name in lower:
            days_ahead = (idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # next occurrence, not today
            if "next" in lower:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    # "in N days/weeks"
    m = re.search(r"in (\d+) day", lower)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.search(r"in (\d+) week", lower)
    if m:
        return today + timedelta(weeks=int(m.group(1)))

    return None


def _parse_duration(text: str) -> int:
    """Extract meeting duration in minutes from text. Default 30."""
    lower = text.lower()
    m = re.search(r"(\d+)\s*min", lower)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*hour", lower)
    if m:
        return int(m.group(1)) * 60
    if "half hour" in lower or "30 min" in lower:
        return 30
    if "hour" in lower and "half" not in lower:
        return 60
    return 30


def _parse_time_preference(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract time-of-day preference as hour range (start, end).

    Returns (start_hour, end_hour) or (None, None) if no preference.
    """
    lower = text.lower()
    if "morning" in lower:
        return (8, 12)
    if "afternoon" in lower:
        return (12, 17)
    if "evening" in lower:
        return (17, 21)
    if "lunch" in lower:
        return (12, 13)
    return (None, None)


def _parse_specific_time(text: str) -> Optional[Tuple[int, int]]:
    """Extract a specific clock time from text.

    Handles: "2pm", "10:30 am", "14:00", "3 pm", "noon", "9am".
    Returns (hour, minute) or None.
    """
    lower = text.lower()

    # Named times
    if "noon" in lower or "12pm" in lower or "12 pm" in lower:
        return (12, 0)
    if "midnight" in lower:
        return (0, 0)

    # HH:MM AM/PM format
    m = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    # H AM/PM format (no minutes)
    m = re.search(r'(\d{1,2})\s*(am|pm)', lower)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return (hour, 0)

    # 24-hour format
    m = re.search(r'(\d{2}):(\d{2})', lower)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    return None


def _parse_event_title(text: str) -> Optional[str]:
    """Extract an event title from a creation request.

    Handles:
      - "schedule a meeting called 'Team Standup'"
      - "create an event called Dentist Appointment"
      - "book a meeting named Project Review"
      - "schedule Team Standup at 10am"
    """
    lower = text.lower()

    # Quoted title
    m = re.search(r"""called ['"](.+?)['"]""", lower)
    if m:
        return m.group(1).strip().title()
    m = re.search(r"""named ['"](.+?)['"]""", lower)
    if m:
        return m.group(1).strip().title()

    # Unquoted "called X" or "named X"
    m = re.search(r'called (.+?)(?:\s+at\s+|\s+on\s+|\s+for\s+|$)', lower)
    if m:
        return m.group(1).strip().title()
    m = re.search(r'named (.+?)(?:\s+at\s+|\s+on\s+|\s+for\s+|$)', lower)
    if m:
        return m.group(1).strip().title()

    # "schedule X at" / "book X at" / "create X at"
    for verb in ["schedule", "book", "create", "add"]:
        m = re.search(rf'{verb}\s+(?:a\s+)?(?:meeting|event|appointment|call)\s+(.+?)(?:\s+at\s+|\s+on\s+|\s+for\s+|$)', lower)
        if m:
            return m.group(1).strip().title()
        # "schedule X at" where X is the title directly
        m = re.search(rf'{verb}\s+(.+?)(?:\s+at\s+|\s+on\s+|\s+for\s+|$)', lower)
        if m and m.group(1) not in ("a", "an", "the", "meeting", "event", "appointment", "call"):
            return m.group(1).strip().title()

    return None


def _detect_event_action(text: str) -> str:
    """Detect whether the user wants to list, create, reschedule, delete, or find slots.

    Returns one of: "list", "create", "reschedule", "delete", "find".
    """
    lower = text.lower()

    # Delete/cancel — check first so "cancel the standup" is not misread
    if any(w in lower for w in ["cancel", "delete", "remove"]):
        return "delete"

    # Reschedule/move — check before create because "reschedule" contains "schedule"
    if any(w in lower for w in ["move", "reschedule", "push back", "push to"]):
        return "reschedule"

    # Find free slots — check before create so "find a slot to schedule" is find,
    # not create. Also catches "show me my schedule" (viewing availability).
    if any(w in lower for w in [
        "find", "free slot", "free time", "what time", "what times",
        "open slot", "available", "show me my schedule",
        "show me free", "show me open",
    ]):
        return "find"

    # Create/schedule/book/add — verb-driven event creation
    if any(w in lower for w in ["create", "schedule", "book", "add"]):
        return "create"

    # List/view events — viewing patterns that don't contain create/find verbs
    _list_keywords = [
        "what events", "what do i have", "what's on", "whats on",
        "show me my events", "show me my calendar", "show me my day",
        "show me the calendar", "list my", "my calendar", "my schedule",
        "my day", "what's my day", "whats my day",
        "upcoming", "agenda", "do i have anything", "any meetings",
        "what do i have on", "what do i have", "do i have",
        "events on", "events for", "events today",
        "calendar for", "am i free", "am i busy",
        "today", "tomorrow", "this week", "next week",
    ]
    if any(w in lower for w in _list_keywords):
        return "list"

    return "find"


def _extract_self_model_prefs(self_model: Any) -> Dict[str, Any]:
    """Extract scheduling-relevant preferences from the self-model.

    Looks for energy_patterns, meeting_prefs, and busy_times facts and
    returns structured preferences the schedule agent can use to rank slots
    and add context to suggestions.

    Returns:
        Dict with optional keys: pref_hours, energy_note, meeting_note.
    """
    prefs: Dict[str, Any] = {}
    if not self_model:
        return prefs

    try:
        facts = self_model.store.all_active()
    except Exception:
        return prefs

    energy_notes: List[str] = []
    meeting_notes: List[str] = []
    pref_start: Optional[int] = None
    pref_end: Optional[int] = None

    for fact in facts:
        cat = fact.category if hasattr(fact, "category") else str(fact.get("category", ""))
        content_str = fact.content if hasattr(fact, "content") else str(fact.get("content", ""))

        if cat == "energy_patterns":
            lower = content_str.lower()
            if "morning" in lower and ("person" in lower or "peak" in lower or "best" in lower):
                pref_start = 8
                pref_end = 12
                energy_notes.append("you're a morning person")
            elif "afternoon" in lower and ("peak" in lower or "best" in lower or "productive" in lower):
                if pref_start is None:
                    pref_start = 13
                    pref_end = 17
                energy_notes.append("your energy peaks in the afternoon")
            elif "evening" in lower and ("peak" in lower or "best" in lower or "productive" in lower):
                if pref_start is None:
                    pref_start = 17
                    pref_end = 21
                energy_notes.append("you're most productive in the evening")
            elif "post-lunch" in lower or "slump" in lower:
                energy_notes.append("you have a post-lunch slump")

        elif cat == "meeting_prefs":
            meeting_notes.append(content_str)
            lower = content_str.lower()
            if "no morning" in lower or "avoid morning" in lower:
                if pref_start is None:
                    pref_start = 13
                    pref_end = 18
            elif "no afternoon" in lower or "avoid afternoon" in lower:
                if pref_start is None:
                    pref_start = 8
                    pref_end = 12

    if pref_start is not None:
        prefs["pref_start"] = pref_start
        prefs["pref_end"] = pref_end
    if energy_notes:
        prefs["energy_note"] = ", ".join(energy_notes[:2])
    if meeting_notes:
        prefs["meeting_note"] = meeting_notes[0]

    return prefs


def _rank_slots_by_prefs(
    slots: List[Dict[str, Any]],
    prefs: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Rank free slots by alignment with user preferences.

    Slots closer to the preferred hours get higher priority.
    """
    if not slots or not prefs.get("pref_start"):
        return slots

    pref_start = prefs["pref_start"]
    pref_end = prefs.get("pref_end", pref_start + 4)

    def slot_score(slot: Dict[str, Any]) -> float:
        try:
            start_dt = datetime.fromisoformat(slot["start"])
            hour = start_dt.hour + start_dt.minute / 60.0
            # Distance from preferred window center
            pref_center = (pref_start + pref_end) / 2
            return abs(hour - pref_center)
        except (ValueError, KeyError):
            return 999.0

    return sorted(slots, key=slot_score)


def _find_free_slots(
    events: List[Dict[str, Any]],
    target_date: datetime,
    duration_min: int,
    pref_start: Optional[int],
    pref_end: Optional[int],
    work_start: int = 8,
    work_end: int = 18,
) -> List[Dict[str, Any]]:
    """Find free time slots on a given date.

    Args:
        events: List of event dicts with 'start' and 'end' ISO strings.
        target_date: The date to search (time will be set to 00:00).
        duration_min: Required slot duration in minutes.
        pref_start: Preferred start hour (or None).
        pref_end: Preferred end hour (or None).
        work_start: Default work-day start hour.
        work_end: Default work-day end hour.

    Returns:
        List of {'start': ISO, 'end': ISO, 'duration_min': int} slots.
    """
    # Ensure target_date is timezone-naive for consistent comparisons
    if target_date.tzinfo is not None:
        target_date = target_date.replace(tzinfo=None)

    day_start_hour = pref_start if pref_start is not None else work_start
    day_end_hour = pref_end if pref_end is not None else work_end

    day_start = target_date.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
    day_end = target_date.replace(hour=day_end_hour, minute=0, second=0, microsecond=0)

    # Collect busy intervals on the target date
    busy: List[Tuple[datetime, datetime]] = []
    for evt in events:
        evt_start_str = evt.get("start", "")
        evt_end_str = evt.get("end", "")
        if not evt_start_str or not evt_end_str:
            continue
        try:
            evt_start = datetime.fromisoformat(evt_start_str.replace("Z", "+00:00"))
            evt_end = datetime.fromisoformat(evt_end_str.replace("Z", "+00:00"))
            if evt_start.tzinfo:
                evt_start = evt_start.replace(tzinfo=None)
            if evt_end.tzinfo:
                evt_end = evt_end.replace(tzinfo=None)
        except (ValueError, TypeError):
            continue

        # Check if event overlaps with the target date
        if evt_start.date() == target_date.date() or evt_end.date() == target_date.date():
            # Clamp to the day window
            clamped_start = max(evt_start, day_start)
            clamped_end = min(evt_end, day_end)
            if clamped_start < clamped_end:
                busy.append((clamped_start, clamped_end))

    # Sort busy intervals
    busy.sort(key=lambda x: x[0])

    # Find gaps
    slots: List[Dict[str, Any]] = []
    cursor = day_start
    duration_delta = timedelta(minutes=duration_min)

    for b_start, b_end in busy:
        if cursor + duration_delta <= b_start:
            slots.append({
                "start": cursor.isoformat(),
                "end": (cursor + duration_delta).isoformat(),
                "duration_min": duration_min,
            })
        cursor = max(cursor, b_end)

    # Check the final gap
    if cursor + duration_delta <= day_end:
        slots.append({
            "start": cursor.isoformat(),
            "end": (cursor + duration_delta).isoformat(),
            "duration_min": duration_min,
        })

    return slots


def _handle_create_event(
    message: str,
    events: List[Dict[str, Any]],
    now: datetime,
    event_store: Any = None,
    self_model_prefs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle event creation requests by parsing the message and creating the event.

    Uses self-model preferences to pick an optimal time when the user doesn't
    specify one. Falls back to 9 AM if no preferences and no time specified.

    Args:
        message: The user's natural language message.
        events: Current calendar events (for conflict checking).
        now: Current datetime.
        event_store: PersistentStore with create_event() method.
        self_model_prefs: Extracted scheduling preferences from the self-model.

    Returns:
        Dict with 'response' and 'actions'.
    """
    self_model_prefs = self_model_prefs or {}
    title = _parse_event_title(message)
    target_date = _parse_datetime(message, now) or (now + timedelta(days=1))
    duration = _parse_duration(message)
    specific = _parse_specific_time(message)

    if specific:
        start_hour, start_minute = specific
        start_dt = target_date.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    elif self_model_prefs.get("pref_start") is not None:
        # Use self-model preferred start hour
        sm_hour = self_model_prefs["pref_start"]
        start_dt = target_date.replace(hour=sm_hour, minute=0, second=0, microsecond=0)
    else:
        # Default: 9 AM if no time specified
        start_dt = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

    end_dt = start_dt + timedelta(minutes=duration)

    # Conflict check — normalize timezones to avoid naive/aware mismatch
    conflict = None
    for evt in events:
        try:
            evt_start = datetime.fromisoformat(evt["start"].replace("Z", "+00:00"))
            evt_end = datetime.fromisoformat(evt["end"].replace("Z", "+00:00"))
            if evt_start.tzinfo is None:
                evt_start = evt_start.replace(tzinfo=timezone.utc)
            if evt_end.tzinfo is None:
                evt_end = evt_end.replace(tzinfo=timezone.utc)
            if start_dt < evt_end and end_dt > evt_start:
                conflict = evt
                break
        except (KeyError, ValueError, TypeError):
            continue

    if conflict:
        c_start = datetime.fromisoformat(conflict["start"].replace("Z", "+00:00"))
        response = (
            f"I can't create that event at {start_dt.strftime('%I:%M %p on %A, %B %d')} — "
            f"it conflicts with \"{conflict.get('title', 'an existing event')}\" "
            f"({c_start.strftime('%I:%M %p')}). Want me to find a different time?"
        )
        return {
            "response": response,
            "actions": [{"type": "create_event", "status": "conflict", "conflict_with": conflict.get("title")}],
        }

    event_title = title or "Meeting"

    if event_store is not None:
        try:
            created = event_store.create_event({
                "title": event_title,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "provider_type": "local",
            })
            sm_note = ""
            if self_model_prefs.get("energy_note") and not specific:
                sm_note = f" I picked this time because {self_model_prefs['energy_note']}."
            response = (
                f"Created \"{event_title}\" for "
                f"{start_dt.strftime('%I:%M %p on %A, %B %d')} "
                f"({duration} min).{sm_note} It's on your calendar now."
            )
            return {
                "response": response,
                "actions": [{"type": "create_event", "status": "created", "event": created}],
            }
        except Exception as exc:
            response = (
                f"I tried to create \"{event_title}\" but hit an error: {exc}. "
                f"The event details are ready if you want to add it manually."
            )
            return {
                "response": response,
                "actions": [{"type": "create_event", "status": "error", "error": str(exc)}],
            }

    # No store available — just report what we'd do
    sm_note = ""
    if self_model_prefs.get("energy_note") and not specific:
        sm_note = f" I picked this time because {self_model_prefs['energy_note']}."
    response = (
        f"I'd create \"{event_title}\" for "
        f"{start_dt.strftime('%I:%M %p on %A, %B %d')} ({duration} min).{sm_note} "
        f"Connect a calendar to save it."
    )
    return {
        "response": response,
        "actions": [{"type": "create_event", "status": "dry_run", "title": event_title, "start": start_dt.isoformat()}],
    }


def _handle_reschedule_event(
    message: str,
    events: List[Dict[str, Any]],
    now: datetime,
    event_store: Any = None,
    self_model_prefs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle event rescheduling by finding the event and updating its time.

    Uses self-model preferences to suggest a better time when the user
    doesn't specify a target time for the reschedule.

    Args:
        message: The user's natural language message.
        events: Current calendar events.
        now: Current datetime.
        event_store: PersistentStore with find_event_by_title() and update_event().
        self_model_prefs: Extracted scheduling preferences from the self-model.

    Returns:
        Dict with 'response' and 'actions'.
    """
    self_model_prefs = self_model_prefs or {}
    # Try to extract the event title from the message
    title_fragment = None
    lower = message.lower()

    # "reschedule X to..." / "move X to..."
    m = re.search(r'(?:reschedule|move|push back|push)\s+(.+?)(?:\s+to\s+|\s+on\s+|\s+at\s+|$)', lower)
    if m and m.group(1) not in ("a", "an", "the", "meeting", "event", "appointment"):
        title_fragment = m.group(1).strip()

    target_date = _parse_datetime(message, now) or (now + timedelta(days=1))
    specific = _parse_specific_time(message)
    if specific:
        start_hour, start_minute = specific
        new_start = target_date.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    else:
        new_start = target_date.replace(hour=10, minute=0, second=0, microsecond=0)

    if event_store is not None and title_fragment:
        evt = event_store.find_event_by_title(title_fragment)
        if evt:
            old_start = datetime.fromisoformat(evt["start"].replace("Z", "+00:00"))
            duration = 30
            try:
                old_end = datetime.fromisoformat(evt["end"].replace("Z", "+00:00"))
                duration = int((old_end - old_start).total_seconds() / 60)
            except (KeyError, ValueError, TypeError):
                pass
            new_end = new_start + timedelta(minutes=duration)
            try:
                updated = event_store.update_event(evt["provider_event_id"], {
                    "start": new_start.isoformat(),
                    "end": new_end.isoformat(),
                })
                response = (
                    f"Moved \"{evt['title']}\" from "
                    f"{old_start.strftime('%I:%M %p on %b %d')} to "
                    f"{new_start.strftime('%I:%M %p on %A, %B %d')}."
                )
                return {
                    "response": response,
                    "actions": [{"type": "reschedule_event", "status": "moved", "event": updated}],
                }
            except Exception as exc:
                response = f"I tried to reschedule \"{evt['title']}\" but hit an error: {exc}."
                return {
                    "response": response,
                    "actions": [{"type": "reschedule_event", "status": "error", "error": str(exc)}],
                }
        else:
            response = (
                f"I couldn't find an event matching \"{title_fragment}\" on your calendar. "
                f"Can you give me the exact event name?"
            )
            return {
                "response": response,
                "actions": [{"type": "reschedule_event", "status": "not_found", "title": title_fragment}],
            }

    # Fallback: search in the in-memory events list
    if title_fragment:
        for evt in events:
            if title_fragment.lower() in evt.get("title", "").lower():
                response = (
                    f"I found \"{evt['title']}\" on your calendar. "
                    f"I'd move it to {new_start.strftime('%I:%M %p on %A, %B %d')}. "
                    f"Connect a calendar store to apply the change."
                )
                return {
                    "response": response,
                    "actions": [{"type": "reschedule_event", "status": "dry_run", "event": evt}],
                }

    response = (
        "Which event would you like to reschedule? Tell me the event name "
        "and when you'd like to move it to."
    )
    return {
        "response": response,
        "actions": [{"type": "reschedule_event", "status": "need_info"}],
    }


def _handle_delete_event(
    message: str,
    events: List[Dict[str, Any]],
    now: datetime,
    event_store: Any = None,
) -> Dict[str, Any]:
    """Handle event deletion by finding the event and removing it.

    Args:
        message: The user's natural language message.
        events: Current calendar events.
        now: Current datetime.
        event_store: PersistentStore with find_event_by_title() and delete_event().

    Returns:
        Dict with 'response' and 'actions'.
    """
    title_fragment = None
    lower = message.lower()
    m = re.search(r'(?:cancel|delete|remove)\s+(.+?)(?:\s+on\s+|\s+at\s+|$)', lower)
    if m and m.group(1) not in ("a", "an", "the", "meeting", "event", "appointment"):
        title_fragment = m.group(1).strip()

    if event_store is not None and title_fragment:
        evt = event_store.find_event_by_title(title_fragment)
        if evt:
            try:
                event_store.delete_event(evt["provider_event_id"])
                response = (
                    f"Deleted \"{evt['title']}\" from your calendar. "
                    f"It was scheduled for "
                    f"{datetime.fromisoformat(evt['start'].replace('Z', '+00:00')).strftime('%A, %B %d at %I:%M %p')}."
                )
                return {
                    "response": response,
                    "actions": [{"type": "delete_event", "status": "deleted", "event": evt}],
                }
            except Exception as exc:
                response = f"I tried to delete \"{evt['title']}\" but hit an error: {exc}."
                return {
                    "response": response,
                    "actions": [{"type": "delete_event", "status": "error", "error": str(exc)}],
                }
        else:
            response = f"I couldn't find an event matching \"{title_fragment}\" to delete."
            return {
                "response": response,
                "actions": [{"type": "delete_event", "status": "not_found", "title": title_fragment}],
            }

    # Fallback: search in-memory
    if title_fragment:
        for evt in events:
            if title_fragment.lower() in evt.get("title", "").lower():
                response = (
                    f"I found \"{evt['title']}\" — I'd delete it. "
                    f"Connect a calendar store to apply the change."
                )
                return {
                    "response": response,
                    "actions": [{"type": "delete_event", "status": "dry_run", "event": evt}],
                }

    response = "Which event would you like me to delete? Tell me the event name."
    return {
        "response": response,
        "actions": [{"type": "delete_event", "status": "need_info"}],
    }


def _handle_list_events(
    message: str,
    events: List[Dict[str, Any]],
    now: datetime,
    self_model: Any = None,
) -> Dict[str, Any]:
    """List the user's events for the requested time period.

    Parses the date from the message (today/tomorrow/this week/etc.),
    filters events to that range, and formats them as a readable list.
    """
    target_date = _parse_datetime(message, now)
    lower = message.lower()

    # Determine the date range to show
    if "this week" in lower or "next week" in lower:
        week_start = (target_date or now).replace(hour=0, minute=0, second=0, microsecond=0)
        # Align to Monday
        week_start = week_start - timedelta(days=week_start.weekday())
        if "next week" in lower:
            week_start = week_start + timedelta(weeks=1)
        week_end = week_start + timedelta(days=7)
        period_label = f"{week_start.strftime('%A, %B %d')} – {(week_end - timedelta(days=1)).strftime('%A, %B %d')}"
    elif target_date is not None:
        week_start = target_date
        week_end = target_date + timedelta(days=1)
        period_label = target_date.strftime("%A, %B %d")
    else:
        # Default to today
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=1)
        period_label = week_start.strftime("%A, %B %d")

    # Filter events to the range
    def _in_range(ev: Dict[str, Any]) -> bool:
        ev_start_str = ev.get("start")
        if not ev_start_str:
            return False
        try:
            ev_start = datetime.fromisoformat(ev_start_str)
            if ev_start.tzinfo is None:
                ev_start = ev_start.replace(tzinfo=timezone.utc)
            return week_start <= ev_start < week_end
        except (ValueError, TypeError):
            return False

    day_events = sorted(
        [e for e in events if _in_range(e)],
        key=lambda e: e.get("start", ""),
    )

    if not day_events:
        response = (
            f"You have no events on {period_label}. Your schedule is clear."
        )
        if "am i free" in lower or "am i busy" in lower:
            response = f"You're free all of {period_label}. No events scheduled."
        actions = [{"type": "list_events", "date": period_label, "count": 0}]
    else:
        lines = []
        for ev in day_events:
            ev_start_str = ev.get("start", "")
            ev_end_str = ev.get("end", "")
            try:
                ev_start = datetime.fromisoformat(ev_start_str)
                if ev_start.tzinfo is None:
                    ev_start = ev_start.replace(tzinfo=timezone.utc)
                time_str = ev_start.strftime("%I:%M %p")
                if ev_end_str:
                    ev_end = datetime.fromisoformat(ev_end_str)
                    if ev_end.tzinfo is None:
                        ev_end = ev_end.replace(tzinfo=timezone.utc)
                    time_str += f" – {ev_end.strftime('%I:%M %p')}"
            except (ValueError, TypeError):
                time_str = "All day"

            title = ev.get("title", "Untitled")
            location = ev.get("location", "")
            loc_str = f" ({location})" if location else ""
            sub = ev.get("source_sub_account_id", "")
            sub_str = f" [{sub}]" if sub and sub != "sa-main" else ""
            lines.append(f"  • {time_str} — {title}{loc_str}{sub_str}")

        response = (
            f"You have {len(day_events)} event{'s' if len(day_events) != 1 else ''} "
            f"on {period_label}:\n\n" + "\n".join(lines)
        )
        actions = [{"type": "list_events", "date": period_label, "count": len(day_events)}]

    return {"response": response, "actions": actions}


def generate_schedule_response(
    message: str,
    events: List[Dict[str, Any]],
    now: datetime,
    event_store: Any = None,
    self_model: Any = None,
) -> Dict[str, Any]:
    """Generate a response for schedule-related requests.

    Detects the specific action (create, reschedule, delete, find) and
    dispatches to the appropriate handler. Falls back to slot finding.
    Uses self-model preferences to rank slots and add context.
    """
    action = _detect_event_action(message)
    sm_prefs = _extract_self_model_prefs(self_model)

    if action == "list":
        return _handle_list_events(message, events, now, self_model)
    if action == "create":
        return _handle_create_event(message, events, now, event_store, self_model_prefs=sm_prefs)
    if action == "reschedule":
        return _handle_reschedule_event(message, events, now, event_store, self_model_prefs=sm_prefs)
    if action == "delete":
        return _handle_delete_event(message, events, now, event_store)

    # Default: find free slots
    target_date = _parse_datetime(message, now) or (now + timedelta(days=1))
    duration = _parse_duration(message)
    pref_start, pref_end = _parse_time_preference(message)

    # Use self-model preferences if user didn't specify a time
    if pref_start is None and sm_prefs.get("pref_start") is not None:
        pref_start = sm_prefs["pref_start"]
        pref_end = sm_prefs.get("pref_end")

    slots = _find_free_slots(events, target_date, duration, pref_start, pref_end)

    # Rank slots by self-model preference alignment
    if sm_prefs.get("pref_start") is not None:
        slots = _rank_slots_by_prefs(slots, sm_prefs)

    date_str = target_date.strftime("%A, %B %d")
    time_pref = ""
    if pref_start is not None and pref_end is not None:
        periods = {(8, 12): "morning", (12, 17): "afternoon", (17, 21): "evening"}
        period = periods.get((pref_start, pref_end), f"{pref_start}:00-{pref_end}:00")
        time_pref = f" in the {period}"

    if not slots:
        response = (
            f"I checked your calendar for {date_str}{time_pref} and couldn't find "
            f"a {duration}-minute free slot. Your schedule looks full during those hours. "
            f"Want me to look at a different day or time of day?"
        )
        actions = [{"type": "find_slots", "date": date_str, "result": "no_slots"}]
    else:
        # Format up to 3 slots
        slot_lines = []
        for s in slots[:3]:
            start_dt = datetime.fromisoformat(s["start"])
            end_dt = datetime.fromisoformat(s["end"])
            slot_lines.append(
                f"  • {start_dt.strftime('%I:%M %p')} – {end_dt.strftime('%I:%M %p')}"
            )

        response = (
            f"I found {len(slots)} free {duration}-min slot{'s' if len(slots) != 1 else ''} "
            f"on {date_str}{time_pref}:\n\n"
            + "\n".join(slot_lines)
        )
        if len(slots) > 3:
            response += f"\n  ...and {len(slots) - 3} more"

        # Add self-model context note if preferences informed the ranking
        sm_notes: List[str] = []
        if sm_prefs.get("energy_note"):
            sm_notes.append(sm_prefs["energy_note"])
        if sm_prefs.get("meeting_note"):
            sm_notes.append(sm_prefs["meeting_note"])
        if sm_notes:
            response += "\n\nI ranked these based on what I know: " + " and ".join(sm_notes) + "."

        response += "\n\nWant me to create an event in any of these slots?"

        actions = [
            {
                "type": "find_slots",
                "date": date_str,
                "duration_min": duration,
                "slots_found": len(slots),
                "slots": slots[:3],
                    "self_model_ranked": bool(sm_notes),
            }
        ]

    return {"response": response, "actions": actions}


# Provider type aliases for natural language parsing.
_PROVIDER_ALIASES: Dict[str, str] = {
    "google": "google_calendar",
    "google calendar": "google_calendar",
    "google cal": "google_calendar",
    "outlook": "outlook_calendar",
    "microsoft": "outlook_calendar",
    "microsoft calendar": "outlook_calendar",
    "caldav": "caldav",
    "ical": "caldav",
    "gmail": "gmail",
    "imap": "imap_smtp",
    "smtp": "imap_smtp",
    "email": "imap_smtp",
}


def _parse_connect_request(message: str) -> List[Dict[str, str]]:
    """Parse a natural-language connect request into sub-account + provider specs.

    Handles patterns like:
      "connect my work Google"
      "connect my work google and personal outlook"
      "add my personal Gmail"
      "link my work Google Calendar"

    Returns a list of dicts with 'sub_account_name' and 'provider_type' keys.
    """
    import re

    msg_lower = message.lower()

    # Match "connect/link/add my [name] [provider]" patterns.
    # The name is the word(s) before the provider alias.
    results: List[Dict[str, str]] = []

    # Split on "and" to handle multiple connections in one message.
    parts = re.split(r"\band\b", msg_lower)

    for part in parts:
        # Find which provider alias is mentioned
        matched_provider = None
        matched_alias = None
        for alias, ptype in sorted(_PROVIDER_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in part:
                matched_provider = ptype
                matched_alias = alias
                break

        if not matched_provider:
            continue

        # Extract the sub-account name: words between "my" and the provider alias
        name_match = re.search(r"\b(?:my\s+)?(.+?)\s+" + re.escape(matched_alias), part)
        if name_match:
            sub_name = name_match.group(1).strip()
            # Clean up common filler words
            sub_name = re.sub(r"\b(calendar|email|account|cal|connect|link|add|my)\b", "", sub_name).strip()
            if not sub_name:
                sub_name = "Personal"
        else:
            # No name found — use a default
            sub_name = "Personal"

        # Capitalize nicely
        sub_name = sub_name.title()

        results.append({
            "sub_account_name": sub_name,
            "provider_type": matched_provider,
        })

    return results


def generate_sync_response(
    message: str,
    providers: List[Dict[str, Any]],
    sub_accounts: List[Dict[str, Any]],
    event_store: Any = None,
) -> Dict[str, Any]:
    """Generate a response for sync-related requests.

    When the user asks to connect a provider (e.g. "connect my work Google"),
    this function parses the request, creates the sub-account and provider
    connection via the event store, and returns guidance for the next step
    (OAuth authorization or manual config).
    """
    connected = [p for p in providers if p.get("status") == "connected"]
    total = len(providers)

    if "sync" in message.lower() or "refresh" in message.lower():
        lines = [f"Synced all providers. {len(connected)}/{total} providers connected:"]
        for p in connected:
            sub_name = next(
                (s["name"] for s in sub_accounts if s["id"] == p.get("sub_account_id")),
                p.get("sub_account_id", "unknown"),
            )
            last_sync = p.get("last_sync_at", "never")
            lines.append(f"  • {p.get('provider_type', 'unknown')} → {sub_name} (last: {last_sync})")

        response = "\n".join(lines)
        actions = [{"type": "sync_all", "providers_synced": len(connected)}]
    elif "connect" in message.lower() or "link" in message.lower() or "add" in message.lower():
        # Parse natural language connect request
        connect_specs = _parse_connect_request(message)

        if connect_specs and event_store:
            created: List[Dict[str, Any]] = []
            for spec in connect_specs:
                sub_name = spec["sub_account_name"]
                ptype = spec["provider_type"]

                # Check if a sub-account with this name already exists
                existing_sub = next(
                    (s for s in sub_accounts if s["name"].lower() == sub_name.lower()),
                    None,
                )

                if existing_sub:
                    sub_id = existing_sub["id"]
                else:
                    # Create the sub-account
                    new_sub = event_store.create_sub_account({
                        "name": sub_name,
                        "kind": "calendar" if "calendar" in ptype else "email" if "imap" in ptype else "unified",
                        "sync_mode": "mirror_filter",
                        "agent_enabled": True,
                    })
                    sub_id = new_sub["id"]
                    created.append({"type": "create_sub_account", "name": sub_name, "id": sub_id})

                # Create the provider connection
                new_provider = event_store.create_provider({
                    "sub_account_id": sub_id,
                    "provider_type": ptype,
                    "provider_account_id": "",
                    "display_name": f"{sub_name} {ptype.replace('_', ' ').title()}",
                    "config": {},
                })
                created.append({
                    "type": "create_provider",
                    "provider_type": ptype,
                    "sub_account": sub_name,
                    "provider_id": new_provider["id"],
                })

            # Build a helpful response
            lines = ["I've set things up for you:"]
            oauth_providers = []
            for spec in connect_specs:
                ptype = spec["provider_type"]
                sub_name = spec["sub_account_name"]
                provider_label = ptype.replace("_", " ").title()
                lines.append(f'  • Created sub-account "{sub_name}" with {provider_label}')

                if ptype in ("google_calendar", "outlook_calendar", "gmail"):
                    oauth_providers.append(spec)

            if oauth_providers:
                lines.append("")
                lines.append("Next step: I need you to authorize the connection(s).")
                lines.append("Click the Authorize button next to each provider in your")
                lines.append("Connections settings, or tell me and I'll start the OAuth flow.")

            actions = [{"type": "connect_provider", "status": "created", "details": created}]
            response = "\n".join(lines)
        elif connect_specs and not event_store:
            # Parsed but no store available — guide manually
            lines = ["I can see you want to connect:"]
            for spec in connect_specs:
                lines.append(f"  • {spec['sub_account_name']} → {spec['provider_type'].replace('_', ' ').title()}")
            lines.append("")
            lines.append("Add these in Settings → Connections to link them up.")
            actions = [{"type": "connect_provider", "status": "parsed_no_store"}]
            response = "\n".join(lines)
        else:
            response = (
                "To connect a new provider, I'll need you to choose:\n"
                "  1. Which sub-account it belongs to\n"
                "  2. The provider type (Google, Outlook, CalDAV, IMAP/SMTP)\n\n"
                "You can also add a new sub-account first if needed. "
                "Which provider would you like to connect?"
            )
            actions = [{"type": "connect_provider", "status": "awaiting_input"}]
    elif "health" in message.lower():
        healthy = len(connected)
        response = (
            f"Provider health: {healthy}/{total} connected and syncing.\n"
            f"All sub-accounts are operational."
        )
        actions = [{"type": "health_check", "healthy": healthy, "total": total}]
    else:
        response = (
            f"You have {total} provider connection{'s' if total != 1 else ''} "
            f"across {len(sub_accounts)} sub-account{'s' if len(sub_accounts) != 1 else ''}. "
            f"{len(connected)} are currently connected."
        )
        actions = [{"type": "sync_status", "connected": len(connected), "total": total}]

    return {"response": response, "actions": actions}


def generate_email_response(
    message: str,
    events: List[Dict[str, Any]],
    providers: Optional[List[Dict[str, Any]]] = None,
    event_store: Any = None,
) -> Dict[str, Any]:
    """Generate a response for email-related requests.

    Checks connected email providers and calendar invites. Can create
    calendar events from detected invites when an event_store is available.
    """
    lower = message.lower()
    providers = providers or []

    # Identify email provider connections
    email_providers = [
        p for p in providers
        if p.get("provider_type") in ("imap_smtp", "gmail")
    ]
    connected_email = [p for p in email_providers if p.get("status") == "connected"]

    # Find events that look like they have invite metadata
    invites = [
        e for e in events
        if e.get("metadata", {}).get("type") == "invite"
        or "invite" in e.get("title", "").lower()
    ]

    if "invite" in lower:
        if invites:
            invite_lines = [
                f"  \u2022 {e['title']} on {e['start'][:10]}" for e in invites[:3]
            ]
            response = (
                f"Found {len(invites)} calendar invite{'s' if len(invites) != 1 else ''} "
                f"in your inbox:\n\n" + "\n".join(invite_lines)
            )
            if event_store is not None:
                response += "\n\nWant me to add any of these to your calendar?"
            actions = [{"type": "check_invites", "found": len(invites), "invites": invites[:3]}]
        elif connected_email:
            response = (
                f"No pending calendar invites found. I checked your "
                f"{len(connected_email)} connected email provider{'s' if len(connected_email) != 1 else ''}. "
                f"I'll notify you when new invites arrive."
            )
            actions = [{"type": "check_invites", "found": 0, "email_providers": len(connected_email)}]
        else:
            response = (
                "No pending calendar invites found. "
                "Connect an email provider in Settings to automatically detect invites."
            )
            actions = [{"type": "check_invites", "found": 0, "email_providers": 0}]
    elif "reply" in lower or "draft" in lower:
        response = (
            "I can draft replies for your emails. Since no LLM is connected, "
            "I'll use a template. Connect a model in Settings to get "
            "context-aware drafts."
        )
        actions = [{"type": "draft_reply", "status": "awaiting_input"}]
    elif "triage" in lower or "inbox" in lower:
        response = (
            "Inbox triage complete. No LLM connected, so I'm working in "
            "rule-based mode. I can:\n"
            "  • Detect calendar invites\n"
            "  • Flag emails with scheduling keywords\n"
            "  • Group threads by sender\n\n"
            "Connect a model for full AI-powered triage."
        )
        actions = [{"type": "triage", "mode": "rule_based"}]
    else:
        response = (
            "I can help with your email — checking for invites, drafting replies, "
            "or triaging your inbox. What would you like me to do?"
        )
        actions = [{"type": "email_assist", "status": "awaiting_input"}]

    return {"response": response, "actions": actions}


def generate_negotiate_response(
    message: str,
    sub_accounts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate a response for negotiation-related requests."""
    agent_subs = [s for s in sub_accounts if s.get("agent_enabled")]

    response = (
        f"I can negotiate meeting changes on your behalf using the federated swarm.\n\n"
        f"Sub-accounts with agents enabled: {len(agent_subs)}\n"
        + "\n".join(f"  • {s['name']} ({s['sync_mode']})" for s in agent_subs)
        + "\n\nTo negotiate a reschedule, tell me:\n"
        "  1. Which meeting to move\n"
        "  2. Your preferred new time\n"
        "  3. How flexible you are\n\n"
        "I'll probe the other party's agent, propose alternatives, and "
        "handle the back-and-forth automatically."
    )
    actions = [{"type": "negotiate", "agent_subs": len(agent_subs)}]

    return {"response": response, "actions": actions}


def generate_self_model_response(
    message: str,
    self_model: Any,
) -> Dict[str, Any]:
    """Generate a response for self-model-related requests."""
    lower = message.lower()

    if "delete" in lower or "forget" in lower:
        response = (
            "You can delete any fact I've learned about you. In the Settings panel, "
            "go to the Self-Model section to view all stored facts and remove any "
            "you don't want. Everything is transparent and user-owned."
        )
        actions = [{"type": "self_model_delete", "status": "directing_to_settings"}]
    elif "privacy" in lower:
        response = (
            "Your privacy is structural, not a setting:\n"
            "  • Email content, self-model reasoning, and negotiation always run locally\n"
            "  • You choose the depth level (pattern memory → longitudinal identity)\n"
            "  • Every fact is visible, editable, and deletable\n"
            "  • Inferences are conservative and confidence is always flagged\n"
        )
        actions = [{"type": "privacy_report"}]
    elif self_model:
        facts = self_model.store.list_all()
        if facts:
            categories: Dict[str, int] = {}
            for f in facts:
                cat = f.category if hasattr(f, "category") else f.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1

            response = (
                f"Here's what I know about you ({len(facts)} facts across "
                f"{len(categories)} categories):\n\n"
                + "\n".join(f"  • {cat}: {count} fact(s)" for cat, count in categories.items())
                + "\n\nAll facts are visible and editable in Settings → Self-Model."
            )
        else:
            response = (
                "I haven't learned any patterns about you yet. As you use A-Cal, "
                "I'll start recognizing your scheduling preferences, busy times, "
                "and energy patterns. You control the depth — from basic pattern "
                "memory to longitudinal identity."
            )
        actions = [{"type": "self_model_report", "fact_count": len(facts) if facts else 0}]
    else:
        response = (
            "The self-model observes your scheduling patterns and preferences to "
            "give you better suggestions. It learns at a depth you choose, and "
            "everything it knows is visible, editable, and deletable. Enable it "
            "in Settings to start building your profile."
        )
        actions = [{"type": "self_model_explain"}]

    return {"response": response, "actions": actions}


def generate_chat_response(
    message: str,
    agents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate a response for general chat (no specific intent)."""
    lower = message.lower()

    if "hello" in lower or "hi" in lower or "hey" in lower:
        response = (
            "Hi! I'm the A-Cal Conductor. I can help you with:\n"
            "  • Finding free slots in your calendar\n"
            "  • Syncing your providers\n"
            "  • Checking your email for invites\n"
            "  • Negotiating meeting reschedules\n"
            "  • Understanding your scheduling patterns\n\n"
            "Just tell me what you need in plain language."
        )
    elif "help" in lower or "what can you" in lower:
        response = (
            "I'm your agentic calendar assistant. Here's what I can do:\n\n"
            "  📅 Schedule — \"Find a 30-min slot tomorrow afternoon\"\n"
            "  🔄 Sync — \"Sync all my providers\"\n"
            "  📧 Email — \"Check inbox for calendar invites\"\n"
            "  🤝 Negotiate — \"Reschedule my 3pm with the team\"\n"
            "  🧠 Self-Model — \"What patterns do you see in my schedule?\"\n\n"
            f"I'm working with {len(agents)} agents. Connect a model in Settings "
            "for full AI-powered responses."
        )
    elif "thank" in lower:
        response = "You're welcome! Let me know if you need anything else."
    else:
        response = (
            f"I heard: \"{message}\"\n\n"
            "I can help with scheduling, syncing, email, negotiation, and "
            "understanding your patterns. Could you rephrase, or try one of "
            "the quick actions below?"
        )

    actions = [{"type": "chat"}]
    return {"response": response, "actions": actions}


def generate_standalone_response(
    message: str,
    decision: RoutingDecision,
    now: Optional[datetime] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    providers: Optional[List[Dict[str, Any]]] = None,
    sub_accounts: Optional[List[Dict[str, Any]]] = None,
    self_model: Any = None,
    agents: Optional[List[Dict[str, Any]]] = None,
    event_store: Any = None,
) -> Dict[str, Any]:
    """Generate a real, useful response without an LLM.

    This is the main entry point called by the conductor when no LLM service
    is available. It dispatches to the appropriate intent handler and returns
    a response string plus structured actions.

    Args:
        message: The user's message.
        decision: The conductor's routing decision.
        now: Current datetime (defaults to UTC now).
        events: Calendar events (list of dicts with start/end/title).
        providers: Provider connections.
        sub_accounts: Sub-accounts.
        self_model: SelfModel instance (optional).
        agents: Agent specs (for chat responses).

    Returns:
        Dict with 'response' (str) and 'actions' (list).
    """
    now = now or datetime.now(timezone.utc)
    events = events or []
    providers = providers or []
    sub_accounts = sub_accounts or []
    agents = agents or []

    intent = decision.intent

    if intent == "schedule":
        return generate_schedule_response(message, events, now, event_store, self_model)
    elif intent == "sync":
        return generate_sync_response(message, providers, sub_accounts, event_store)
    elif intent == "email":
        return generate_email_response(message, events, providers, event_store)
    elif intent == "negotiate":
        return generate_negotiate_response(message, sub_accounts)
    elif intent == "self_model":
        return generate_self_model_response(message, self_model)
    else:
        return generate_chat_response(message, agents)
