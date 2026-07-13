"""Calendar analytics module — ported from zero-calendar's analytics logic.

Provides busy-time analysis, meeting statistics, multi-day free-slot search,
and reschedule suggestions. These power the analytics panel and feed into
the self-model's pattern memory.
"""

from a_cal.analytics.calendar_analytics import (
    analyze_busy_times,
    get_calendar_analytics,
    find_free_time_slots_range,
    suggest_rescheduling,
)

__all__ = [
    "analyze_busy_times",
    "get_calendar_analytics",
    "find_free_time_slots_range",
    "suggest_rescheduling",
]
