"""Unit tests for calendar analytics functions.

Tests analyze_busy_times, get_calendar_analytics, find_free_time_slots_range,
and suggest_rescheduling with mock event data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from a_cal.analytics.calendar_analytics import (
    analyze_busy_times,
    find_free_time_slots_range,
    get_calendar_analytics,
    suggest_rescheduling,
)


def _evt(start: str, end: str, **extra) -> dict:
    """Build a minimal event dict for testing."""
    base = {"start": start, "end": end, "title": "Test", "provider_event_id": "evt-1"}
    base.update(extra)
    return base


class TestAnalyzeBusyTimes:
    """Tests for analyze_busy_times."""

    def test_empty_events(self):
        """No events produces zero counts and Monday as default busiest day."""
        result = analyze_busy_times([], datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 0
        assert result["busy_by_day_of_week"] == [0.0] * 7
        assert result["busy_by_hour"] == [0] * 24
        assert result["busiest_day"] == "Monday"

    def test_single_event(self):
        """A single 1-hour event on Monday 10am is counted correctly."""
        events = [_evt("2025-01-06T10:00:00", "2025-01-06T11:00:00")]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 1
        assert result["busy_by_day_of_week"][0] == 1.0  # Monday
        assert result["events_by_day_of_week"][0] == 1
        assert result["busy_by_hour"][10] == 1
        assert result["busiest_day"] == "Monday"
        assert result["busiest_day_hours"] == 1.0
        assert result["busiest_hour"] == 10

    def test_all_day_event_skipped(self):
        """All-day events (>= 24h) are skipped."""
        events = [_evt("2025-01-06T00:00:00", "2025-01-07T00:00:00", all_day=True)]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 0

    def test_event_outside_range_skipped(self):
        """Events outside the date range are skipped."""
        events = [_evt("2025-06-06T10:00:00", "2025-06-06T11:00:00")]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 0

    def test_timezone_aware_events(self):
        """Timezone-aware ISO strings are handled correctly."""
        events = [_evt("2025-01-06T10:00:00-05:00", "2025-01-06T11:00:00-05:00")]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 1

    def test_invalid_datetimes_skipped(self):
        """Events with unparseable datetimes are skipped gracefully."""
        events = [_evt("not-a-date", "also-not-a-date")]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["total_events"] == 0

    def test_multi_hour_event_spans_hours(self):
        """A 3-hour event increments busy_by_hour for each hour spanned."""
        events = [_evt("2025-01-06T10:00:00", "2025-01-06T13:00:00")]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["busy_by_hour"][10] == 1
        assert result["busy_by_hour"][11] == 1
        assert result["busy_by_hour"][12] == 1

    def test_busiest_day_correct(self):
        """Busiest day is the one with the most hours."""
        events = [
            _evt("2025-01-06T09:00:00", "2025-01-06T12:00:00"),  # Monday 3h
            _evt("2025-01-08T09:00:00", "2025-01-08T10:00:00"),  # Wednesday 1h
        ]
        result = analyze_busy_times(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["busiest_day"] == "Monday"
        assert result["busiest_day_hours"] == 3.0


class TestGetCalendarAnalytics:
    """Tests for get_calendar_analytics."""

    def test_empty_events(self):
        """No events yields zero stats."""
        result = get_calendar_analytics([], datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["meeting_count"] == 0
        assert result["total_meeting_minutes"] == 0
        assert result["total_meeting_hours"] == 0
        assert result["average_meeting_length"] == 0

    def test_single_meeting_stats(self):
        """A single 60-minute meeting produces correct stats."""
        events = [_evt("2025-01-06T10:00:00", "2025-01-06T11:00:00")]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["meeting_count"] == 1
        assert result["total_meeting_minutes"] == 60
        assert result["total_meeting_hours"] == 1.0
        assert result["average_meeting_length"] == 60

    def test_multiple_meetings_avg(self):
        """Average meeting length is correctly computed."""
        events = [
            _evt("2025-01-06T10:00:00", "2025-01-06T11:00:00"),  # 60 min
            _evt("2025-01-07T10:00:00", "2025-01-07T10:30:00"),  # 30 min
        ]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["meeting_count"] == 2
        assert result["total_meeting_minutes"] == 90
        assert result["average_meeting_length"] == 45

    def test_category_breakdown(self):
        """Categories from metadata are counted correctly."""
        events = [
            _evt("2025-01-06T10:00:00", "2025-01-06T11:00:00",
                 metadata={"categories": ["work", "internal"]}),
            _evt("2025-01-07T10:00:00", "2025-01-07T10:30:00",
                 metadata={"categories": ["personal"]}),
        ]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["category_counts"]["work"] == 1
        assert result["category_counts"]["internal"] == 1
        assert result["category_counts"]["personal"] == 1

    def test_uncategorized_default(self):
        """Events without categories are counted as Uncategorized."""
        events = [_evt("2025-01-06T10:00:00", "2025-01-06T11:00:00")]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["category_counts"]["Uncategorized"] == 1

    def test_busiest_day_by_minutes(self):
        """Busiest day is the date with the most meeting minutes."""
        events = [
            _evt("2025-01-06T09:00:00", "2025-01-06T12:00:00"),  # 180 min
            _evt("2025-01-07T09:00:00", "2025-01-07T10:00:00"),  # 60 min
        ]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["busiest_day"] == "2025-01-06"
        assert result["busiest_day_minutes"] == 180

    def test_all_day_event_excluded(self):
        """All-day events are excluded from meeting stats."""
        events = [_evt("2025-01-06T00:00:00", "2025-01-07T00:00:00", all_day=True)]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["meeting_count"] == 0

    def test_daily_meeting_minutes(self):
        """Daily meeting minutes are tracked per date."""
        events = [
            _evt("2025-01-06T10:00:00", "2025-01-06T11:00:00"),  # 60 min
            _evt("2025-01-06T14:00:00", "2025-01-06T15:00:00"),  # 60 min
        ]
        result = get_calendar_analytics(events, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result["daily_meeting_minutes"]["2025-01-06"] == 120


class TestFindFreeTimeSlotsRange:
    """Tests for find_free_time_slots_range."""

    def test_empty_calendar_full_day_free(self):
        """With no events, the entire workday is a free slot."""
        start = datetime(2025, 1, 6, 0, 0)  # Monday
        end = datetime(2025, 1, 6, 23, 59)
        slots = find_free_time_slots_range([], start, end, work_start_hour=9, work_end_hour=17)
        assert len(slots) == 1
        assert slots[0]["duration"] == 480  # 8 hours = 480 minutes

    def test_event_splits_day(self):
        """A midday event splits the workday into two free slots."""
        start = datetime(2025, 1, 6, 0, 0)
        end = datetime(2025, 1, 6, 23, 59)
        events = [_evt("2025-01-06T11:00:00", "2025-01-06T13:00:00")]
        slots = find_free_time_slots_range(events, start, end, work_start_hour=9, work_end_hour=17)
        # 9-11 and 13-17 = two slots
        assert len(slots) == 2
        assert slots[0]["duration"] == 120  # 9-11 = 120 min
        assert slots[1]["duration"] == 240  # 13-17 = 240 min

    def test_min_duration_filters_short_slots(self):
        """Slots shorter than min_duration are excluded."""
        start = datetime(2025, 1, 6, 0, 0)
        end = datetime(2025, 1, 6, 23, 59)
        events = [_evt("2025-01-06T09:00:00", "2025-01-06T16:30:00")]
        slots = find_free_time_slots_range(
            events, start, end, min_duration_minutes=60, work_start_hour=9, work_end_hour=17,
        )
        # Only 16:30-17:00 = 30 min, below min_duration of 60
        assert len(slots) == 0

    def test_multi_day_range(self):
        """Free slots are found across multiple days."""
        start = datetime(2025, 1, 6, 0, 0)  # Monday
        end = datetime(2025, 1, 7, 23, 59)  # Tuesday
        slots = find_free_time_slots_range([], start, end, work_start_hour=9, work_end_hour=17)
        assert len(slots) == 2  # one per day

    def test_weekend_excluded_by_default_schedule(self):
        """Weekend days with no work hours produce no slots."""
        start = datetime(2025, 1, 4, 0, 0)  # Saturday
        end = datetime(2025, 1, 4, 23, 59)
        slots = find_free_time_slots_range([], start, end, work_start_hour=9, work_end_hour=17)
        # Saturday with 9-17 work hours still produces a slot since we pass work hours
        assert len(slots) == 1

    def test_full_day_busy_no_slots(self):
        """A fully booked workday yields no free slots."""
        start = datetime(2025, 1, 6, 0, 0)
        end = datetime(2025, 1, 6, 23, 59)
        events = [_evt("2025-01-06T09:00:00", "2025-01-06T17:00:00")]
        slots = find_free_time_slots_range(events, start, end, work_start_hour=9, work_end_hour=17)
        assert len(slots) == 0


class TestSuggestRescheduling:
    """Tests for suggest_rescheduling."""

    def test_event_not_found(self):
        """Returns failure when event_id doesn't match any event."""
        result = suggest_rescheduling([], "nonexistent")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_invalid_times(self):
        """Returns failure when event has unparseable times."""
        events = [_evt("bad-date", "also-bad", provider_event_id="evt-1")]
        result = suggest_rescheduling(events, "evt-1")
        assert result["success"] is False

    def test_successful_suggestion(self):
        """Returns alternative slots for a valid event."""
        now = datetime.utcnow()
        # Event tomorrow at 10am
        evt_start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        evt_end = evt_start + timedelta(hours=1)
        events = [
            {
                "provider_event_id": "evt-1",
                "title": "Standup",
                "start": evt_start.isoformat(),
                "end": evt_end.isoformat(),
            }
        ]
        result = suggest_rescheduling(events, "evt-1", look_ahead_days=14)
        assert result["success"] is True
        assert result["event"]["title"] == "Standup"
        assert result["event"]["duration"] == 60
        assert isinstance(result["alternative_slots"], list)
        # Alternatives should not be on the same day as the original event
        for slot in result["alternative_slots"]:
            slot_date = datetime.fromisoformat(slot["start"]).date()
            assert slot_date != evt_start.date()

    def test_max_three_alternatives(self):
        """At most 3 alternative slots are returned."""
        now = datetime.utcnow()
        evt_start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        evt_end = evt_start + timedelta(hours=1)
        events = [
            {
                "provider_event_id": "evt-1",
                "title": "Meeting",
                "start": evt_start.isoformat(),
                "end": evt_end.isoformat(),
            }
        ]
        result = suggest_rescheduling(events, "evt-1", look_ahead_days=14)
        assert len(result["alternative_slots"]) <= 3

    def test_finds_event_by_id_field(self):
        """Events matched by 'id' field (not just 'provider_event_id')."""
        now = datetime.utcnow()
        evt_start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        evt_end = evt_start + timedelta(hours=1)
        events = [
            {
                "id": "evt-99",
                "title": "Review",
                "start": evt_start.isoformat(),
                "end": evt_end.isoformat(),
            }
        ]
        result = suggest_rescheduling(events, "evt-99", look_ahead_days=14)
        assert result["success"] is True
        assert result["event"]["title"] == "Review"
