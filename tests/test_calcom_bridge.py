"""Tests for cal.com integration bridge.

Tests SchedulingType, EventStatus, EventType, AvailabilitySchedule,
and get_aggregated_availability (collective intersection, round robin
union, managed first-participant).
"""

from __future__ import annotations

import pytest

from a_cal.integrations.calcom_bridge import (
    DEFAULT_SCHEDULE,
    AvailabilitySchedule,
    EventStatus,
    EventType,
    SchedulingType,
    get_aggregated_availability,
)


class TestSchedulingType:
    """Tests for the SchedulingType enum."""

    def test_enum_values(self):
        """Scheduling types have correct string values."""
        assert SchedulingType.ROUND_ROBIN.value == "round_robin"
        assert SchedulingType.COLLECTIVE.value == "collective"
        assert SchedulingType.MANAGED.value == "managed"

    def test_enum_from_string(self):
        """Enum can be constructed from string value."""
        assert SchedulingType("collective") == SchedulingType.COLLECTIVE
        assert SchedulingType("round_robin") == SchedulingType.ROUND_ROBIN


class TestEventStatus:
    """Tests for the EventStatus enum."""

    def test_enum_values(self):
        """Status values are correct."""
        assert EventStatus.ACTIVE.value == "active"
        assert EventStatus.INACTIVE.value == "inactive"


class TestAvailabilitySchedule:
    """Tests for AvailabilitySchedule."""

    def test_default_schedule(self):
        """Default schedule is Mon-Fri 9-5, weekends off."""
        sched = AvailabilitySchedule()
        assert sched.is_available_on(0) is True   # Monday
        assert sched.is_available_on(4) is True    # Friday
        assert sched.is_available_on(5) is False   # Saturday
        assert sched.is_available_on(6) is False   # Sunday

    def test_get_hours_for_day(self):
        """get_hours_for_day returns the correct ranges."""
        sched = AvailabilitySchedule()
        hours = sched.get_hours_for_day(0)
        assert len(hours) == 1
        assert hours[0]["start"] == "09:00"
        assert hours[0]["end"] == "17:00"

    def test_get_hours_out_of_range(self):
        """Out-of-range weekday returns empty list."""
        sched = AvailabilitySchedule()
        assert sched.get_hours_for_day(7) == []
        assert sched.get_hours_for_day(-1) == []

    def test_to_dict_roundtrip(self):
        """to_dict / from_dict roundtrips correctly."""
        sched = AvailabilitySchedule(timezone="America/Chicago")
        d = sched.to_dict()
        assert d["timezone"] == "America/Chicago"
        assert len(d["days"]) == 7
        restored = AvailabilitySchedule.from_dict(d)
        assert restored.timezone == "America/Chicago"
        assert restored.is_available_on(0) is True

    def test_from_dict_invalid_days_falls_back(self):
        """from_dict with missing/invalid days falls back to default."""
        restored = AvailabilitySchedule.from_dict({"timezone": "UTC"})
        assert len(restored.days) == 7
        assert restored.is_available_on(0) is True


class TestEventType:
    """Tests for EventType dataclass."""

    def test_default_values(self):
        """Default event type has expected values."""
        et = EventType()
        assert et.title == "30 Minute Meeting"
        assert et.slug == "30-min"
        assert et.duration_minutes == 30
        assert et.scheduling_type == SchedulingType.COLLECTIVE
        assert et.status == EventStatus.ACTIVE

    def test_to_dict_roundtrip(self):
        """to_dict / from_dict roundtrips correctly."""
        et = EventType(
            id="test-1",
            title="Coffee Chat",
            slug="coffee",
            duration_minutes=15,
            scheduling_type=SchedulingType.ROUND_ROBIN,
            status=EventStatus.INACTIVE,
            color="#FF0000",
            metadata={"location": "Zoom"},
        )
        d = et.to_dict()
        assert d["id"] == "test-1"
        assert d["title"] == "Coffee Chat"
        assert d["scheduling_type"] == "round_robin"
        assert d["status"] == "inactive"
        assert d["metadata"]["location"] == "Zoom"

        restored = EventType.from_dict(d)
        assert restored.id == "test-1"
        assert restored.title == "Coffee Chat"
        assert restored.scheduling_type == SchedulingType.ROUND_ROBIN
        assert restored.status == EventStatus.INACTIVE

    def test_from_dict_invalid_scheduling_type(self):
        """Invalid scheduling_type falls back to COLLECTIVE."""
        et = EventType.from_dict({"scheduling_type": "nonsense"})
        assert et.scheduling_type == SchedulingType.COLLECTIVE

    def test_from_dict_invalid_status(self):
        """Invalid status falls back to ACTIVE."""
        et = EventType.from_dict({"status": "nonsense"})
        assert et.status == EventStatus.ACTIVE


class TestGetAggregatedAvailability:
    """Tests for get_aggregated_availability."""

    def test_empty_participants_returns_default(self):
        """No participants returns the default schedule."""
        result = get_aggregated_availability([], SchedulingType.COLLECTIVE)
        assert result == DEFAULT_SCHEDULE

    def test_managed_uses_first_participant(self):
        """Managed scheduling uses the first participant's schedule."""
        sched1 = AvailabilitySchedule()
        sched2 = AvailabilitySchedule()
        # Modify sched2 to have different hours
        sched2.days[0] = [{"start": "10:00", "end": "18:00"}]
        result = get_aggregated_availability([sched1, sched2], SchedulingType.MANAGED)
        assert result[0] == sched1.days[0]
        assert result[0][0]["start"] == "09:00"

    def test_collective_intersection(self):
        """Collective takes the latest start and earliest end."""
        sched1 = AvailabilitySchedule()
        sched2 = AvailabilitySchedule()
        # sched2 starts later, ends earlier
        sched2.days[0] = [{"start": "10:00", "end": "16:00"}]
        result = get_aggregated_availability([sched1, sched2], SchedulingType.COLLECTIVE)
        # Intersection: latest start (10:00), earliest end (16:00)
        assert result[0][0]["start"] == "10:00"
        assert result[0][0]["end"] == "16:00"

    def test_collective_one_unavailable_makes_day_off(self):
        """If any participant is unavailable, the day is off (collective)."""
        sched1 = AvailabilitySchedule()
        sched2 = AvailabilitySchedule()
        sched2.days[0] = []  # sched2 off on Monday
        result = get_aggregated_availability([sched1, sched2], SchedulingType.COLLECTIVE)
        assert result[0] == []

    def test_round_robin_union(self):
        """Round robin takes the union of all participants' hours."""
        sched1 = AvailabilitySchedule()
        sched2 = AvailabilitySchedule()
        sched2.days[0] = [{"start": "17:00", "end": "19:00"}]  # extends past sched1
        result = get_aggregated_availability([sched1, sched2], SchedulingType.ROUND_ROBIN)
        # Union: 09:00-19:00 (merged since 17:00 <= 17:00)
        assert len(result[0]) == 1
        assert result[0][0]["start"] == "09:00"
        assert result[0][0]["end"] == "19:00"

    def test_round_robin_non_overlapping(self):
        """Non-overlapping ranges stay separate in round robin union."""
        sched1 = AvailabilitySchedule()
        sched2 = AvailabilitySchedule()
        sched2.days[0] = [{"start": "18:00", "end": "20:00"}]  # gap after sched1 ends
        result = get_aggregated_availability([sched1, sched2], SchedulingType.ROUND_ROBIN)
        assert len(result[0]) == 2
        assert result[0][0]["start"] == "09:00"
        assert result[0][1]["start"] == "18:00"

    def test_all_days_processed(self):
        """All 7 days are processed in the result."""
        sched1 = AvailabilitySchedule()
        result = get_aggregated_availability([sched1], SchedulingType.COLLECTIVE)
        assert len(result) == 7
