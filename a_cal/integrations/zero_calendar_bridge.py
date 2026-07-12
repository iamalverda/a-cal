"""zero-calendar integration bridge — AI tool catalog + prompt patterns.

Ports zero-calendar's calendar tool definitions and system prompt patterns
into A-Cal's agent system. These tools can be used by the conductor when
dispatching to the schedule agent, and the prompt patterns improve the
LLM's calendar reasoning.

Ported from zero-calendar/lib/ai-tools.ts and lib/system-prompts.tsx.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Tool catalog — defines the tools available to the schedule agent.
# Each tool has a name, description, and parameter schema. The conductor
# can use these to augment the LLM's capabilities.
CALENDAR_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "getEvents",
        "description": "Get calendar events within a date range.",
        "parameters": {
            "start_date": {"type": "string", "description": "ISO start date"},
            "end_date": {"type": "string", "description": "ISO end date"},
        },
    },
    {
        "name": "getTodayEvents",
        "description": "Get all events scheduled for today.",
        "parameters": {},
    },
    {
        "name": "createEvent",
        "description": "Create a new calendar event. Validates conflicts.",
        "parameters": {
            "title": {"type": "string", "required": True},
            "start_time": {"type": "string", "required": True, "description": "ISO datetime"},
            "end_time": {"type": "string", "required": True, "description": "ISO datetime"},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
    },
    {
        "name": "updateEvent",
        "description": "Update an existing event.",
        "parameters": {
            "event_id": {"type": "string", "required": True},
            "title": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
    },
    {
        "name": "deleteEvent",
        "description": "Delete a calendar event.",
        "parameters": {
            "event_id": {"type": "string", "required": True},
        },
    },
    {
        "name": "findEvents",
        "description": "Search events by keyword.",
        "parameters": {
            "query": {"type": "string", "required": True},
        },
    },
    {
        "name": "findAvailableTimeSlots",
        "description": "Find free time slots on a specific date.",
        "parameters": {
            "date": {"type": "string", "required": True, "description": "ISO date"},
            "duration_minutes": {"type": "integer", "default": 30},
        },
    },
    {
        "name": "findFreeTimeSlots",
        "description": "Find free time slots across a date range (multi-day).",
        "parameters": {
            "start_date": {"type": "string", "required": True},
            "end_date": {"type": "string", "required": True},
            "min_duration_minutes": {"type": "integer", "default": 30},
        },
    },
    {
        "name": "checkForConflicts",
        "description": "Check if a time range conflicts with existing events.",
        "parameters": {
            "start_time": {"type": "string", "required": True},
            "end_time": {"type": "string", "required": True},
        },
    },
    {
        "name": "analyzeBusyTimes",
        "description": "Analyze which days and hours are busiest over a range.",
        "parameters": {
            "start_date": {"type": "string", "required": True},
            "end_date": {"type": "string", "required": True},
        },
    },
    {
        "name": "getCalendarAnalytics",
        "description": "Get meeting statistics (count, duration, categories) over a range.",
        "parameters": {
            "start_date": {"type": "string", "required": True},
            "end_date": {"type": "string", "required": True},
        },
    },
    {
        "name": "suggestRescheduling",
        "description": "Suggest alternative time slots for an existing event.",
        "parameters": {
            "event_id": {"type": "string", "required": True},
        },
    },
]


def get_enhanced_schedule_prompt(
    user_timezone: str = "UTC",
    current_date: str = "",
) -> str:
    """Generate an enhanced system prompt for the schedule agent.

    Ported from zero-calendar's system prompt patterns. Adds timezone
    awareness, mutation rules, and anti-hallucination directives that
    complement A-Cal's existing conductor prompt.

    Args:
        user_timezone: The user's IANA timezone.
        current_date: Optional ISO date string for context.

    Returns:
        A system prompt string to prepend to the schedule agent's prompt.
    """
    from datetime import datetime, timezone as tz

    now = datetime.now(tz.utc) if not current_date else datetime.fromisoformat(current_date)
    current_date_formatted = now.strftime("%A, %B %d, %Y")
    current_time_formatted = now.strftime("%I:%M %p")

    return (
        f"Current context:\n"
        f"- Current date: {current_date_formatted}\n"
        f"- Current time: {current_time_formatted}\n"
        f"- User timezone: {user_timezone}\n"
        f"- Current ISO datetime: {now.isoformat()}\n\n"
        f"Calendar assistant rules:\n"
        f"- Never invent calendar state. Use the system context for factual claims.\n"
        f"- Be concise, direct, and useful.\n"
        f"- Use the user's timezone for all date and time reasoning.\n"
        f"- Resolve relative time phrases (today, tomorrow, next week) from current context.\n"
        f"- If a request is ambiguous, ask a focused follow-up instead of guessing.\n"
        f"- Only create, update, or delete events when the user clearly intends that action.\n"
        f"- Do not claim a mutation succeeded unless the system context confirms it.\n"
        f"- If a requested time conflicts, explain the conflict and suggest alternatives.\n"
        f"- Keep responses to 2-4 sentences. The user wants answers, not essays.\n"
    )
