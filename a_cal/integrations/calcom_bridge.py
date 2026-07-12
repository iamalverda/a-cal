"""cal.com integration bridge — scheduling concepts ported to Python.

Ports cal.com's event type system, availability schedules, and scheduling
types (round robin, collective, managed) into A-Cal's data model. This lets
A-Cal users define booking pages (like Calendly) with configurable event
types, working hours, and multi-participant scheduling.

Ported from cal.com/packages/platform/enums/event-types/scheduling-type.ts
and cal.com/packages/lib/availability.ts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional


class SchedulingType(str, enum.Enum):
    """How participants are selected for an event type.

    Ported from cal.com's SchedulingType enum.
    """

    ROUND_ROBIN = "round_robin"
    COLLECTIVE = "collective"
    MANAGED = "managed"


class EventStatus(str, enum.Enum):
    """Event type active/inactive status."""

    ACTIVE = "active"
    INACTIVE = "inactive"


# Default schedule: Mon-Fri 9-5, weekends off
# Indexed by weekday() (Monday=0..Sunday=6)
DEFAULT_SCHEDULE: List[List[Dict[str, str]]] = [
    [{"start": "09:00", "end": "17:00"}],  # Monday
    [{"start": "09:00", "end": "17:00"}],  # Tuesday
    [{"start": "09:00", "end": "17:00"}],  # Wednesday
    [{"start": "09:00", "end": "17:00"}],  # Thursday
    [{"start": "09:00", "end": "17:00"}],  # Friday
    [],                                      # Saturday
    [],                                      # Sunday
]

_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


@dataclass
class TimeRange:
    """A start/end time pair within a day (HH:MM format)."""

    start: str  # "09:00"
    end: str    # "17:00"


@dataclass
class AvailabilitySchedule:
    """Weekly working hours schedule.

    A list of 7 lists (one per day, Monday=0), each containing TimeRange
    dicts with 'start' and 'end' in HH:MM format. Empty list = day off.
    """

    days: List[List[Dict[str, str]]] = field(default_factory=lambda: [[dict(r) for r in d] for d in DEFAULT_SCHEDULE])
    timezone: str = "UTC"

    def is_available_on(self, weekday: int) -> bool:
        """Check if there are working hours on a given weekday (0=Monday)."""
        return len(self.days[weekday]) > 0

    def get_hours_for_day(self, weekday: int) -> List[Dict[str, str]]:
        """Get working hours for a specific weekday."""
        return self.days[weekday] if 0 <= weekday < 7 else []

    def to_dict(self) -> Dict[str, Any]:
        return {"days": self.days, "timezone": self.timezone}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AvailabilitySchedule":
        days = data.get("days")
        if not days or len(days) != 7:
            days = [list(d) for d in DEFAULT_SCHEDULE]
        return cls(days=days, timezone=data.get("timezone", "UTC"))


@dataclass
class EventType:
    """A bookable event type (like Calendly's event types).

    Ported from cal.com's event type concept. Users define event types with
    a title, duration, scheduling type, and availability schedule. Other
    users can then book time slots based on the event type's rules.

    Args:
        id: Unique identifier.
        title: Display name (e.g. "30 Minute Meeting").
        slug: URL-friendly identifier.
        duration_minutes: Default meeting length.
        description: Optional description.
        scheduling_type: How participants are selected.
        availability: Working hours schedule.
        status: Active or inactive.
        color: Optional calendar color.
        metadata: Extra configuration (location, price, etc.).
    """

    id: str = ""
    title: str = "30 Minute Meeting"
    slug: str = "30-min"
    duration_minutes: int = 30
    description: str = ""
    scheduling_type: SchedulingType = SchedulingType.COLLECTIVE
    availability: AvailabilitySchedule = field(default_factory=AvailabilitySchedule)
    status: EventStatus = EventStatus.ACTIVE
    color: str = "#3B82F6"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "duration_minutes": self.duration_minutes,
            "description": self.description,
            "scheduling_type": self.scheduling_type.value,
            "availability": self.availability.to_dict(),
            "status": self.status.value,
            "color": self.color,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventType":
        sched_type = data.get("scheduling_type", SchedulingType.COLLECTIVE.value)
        try:
            sched_type = SchedulingType(sched_type)
        except ValueError:
            sched_type = SchedulingType.COLLECTIVE

        status = data.get("status", EventStatus.ACTIVE.value)
        try:
            status = EventStatus(status)
        except ValueError:
            status = EventStatus.ACTIVE

        return cls(
            id=data.get("id", ""),
            title=data.get("title", "30 Minute Meeting"),
            slug=data.get("slug", "30-min"),
            duration_minutes=data.get("duration_minutes", 30),
            description=data.get("description", ""),
            scheduling_type=sched_type,
            availability=AvailabilitySchedule.from_dict(data.get("availability", {})),
            status=status,
            color=data.get("color", "#3B82F6"),
            metadata=dict(data.get("metadata", {})),
        )


def get_aggregated_availability(
    participants: List[AvailabilitySchedule],
    scheduling_type: SchedulingType,
) -> List[List[Dict[str, str]]]:
    """Compute the intersection of multiple participants' availability.

    Ported from cal.com's getAggregatedAvailability. For collective events,
    all participants must be available (intersection). For round robin,
    at least one participant must be available (union). For managed events,
    the first participant's schedule is used.

    Args:
        participants: List of AvailabilitySchedule objects.
        scheduling_type: How to combine the schedules.

    Returns:
        A 7-day availability schedule (list of lists of time ranges).
    """
    if not participants:
        return [list(d) for d in DEFAULT_SCHEDULE]

    if scheduling_type == SchedulingType.MANAGED:
        return participants[0].days

    result: List[List[Dict[str, str]]] = []
    for day_idx in range(7):
        if scheduling_type == SchedulingType.COLLECTIVE:
            # Intersection: all must be available
            day_ranges: List[Dict[str, str]] = []
            all_available = True
            for p in participants:
                hours = p.get_hours_for_day(day_idx)
                if not hours:
                    all_available = False
                    break
                day_ranges.extend(hours)
            if not all_available:
                result.append([])
            else:
                # Simple intersection: take the latest start and earliest end
                if day_ranges:
                    latest_start = max(r["start"] for r in day_ranges)
                    earliest_end = min(r["end"] for r in day_ranges)
                    if latest_start < earliest_end:
                        result.append([{"start": latest_start, "end": earliest_end}])
                    else:
                        result.append([])
                else:
                    result.append([])

        elif scheduling_type == SchedulingType.ROUND_ROBIN:
            # Union: at least one must be available
            union_ranges: List[Dict[str, str]] = []
            for p in participants:
                union_ranges.extend(p.get_hours_for_day(day_idx))
            if union_ranges:
                # Merge overlapping ranges
                union_ranges.sort(key=lambda r: r["start"])
                merged: List[Dict[str, str]] = [dict(union_ranges[0])]
                for r in union_ranges[1:]:
                    if r["start"] <= merged[-1]["end"]:
                        merged[-1]["end"] = max(merged[-1]["end"], r["end"])
                    else:
                        merged.append(dict(r))
                result.append(merged)
            else:
                result.append([])

    return result
