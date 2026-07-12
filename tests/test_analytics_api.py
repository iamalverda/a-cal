"""Tests for analytics and event-type API endpoints.

Uses FastAPI TestClient to test all analytics_routes endpoints:
- GET /analytics/summary, /analytics/busy-times, /analytics/meeting-stats
- GET /analytics/free-slots
- POST /analytics/suggest-reschedule
- GET/POST/DELETE /event-types, GET /event-types/{id}
- GET /availability/schedule
- POST /availability/aggregated
- GET /calendar-tools
- GET /schedule-prompt
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import tempfile
import os

from a_cal.api.analytics_routes import router as analytics_router


@pytest.fixture
def client():
    """Test client with only the analytics routes mounted."""
    # Clear event types from the DB between tests so each test starts clean
    from a_cal.api.analytics_routes import _db
    _db.clear_event_types()
    app = FastAPI()
    app.include_router(analytics_router)
    return TestClient(app)


class TestAnalyticsSummary:
    """Tests for the combined analytics summary endpoint."""

    def test_summary_default_days(self, client):
        """GET /analytics/summary returns 200 with default 30-day period."""
        resp = client.get("/api/a-cal/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30
        assert "busy_times" in data
        assert "meeting_stats" in data

    def test_summary_custom_days(self, client):
        """GET /analytics/summary with days param returns correct period."""
        resp = client.get("/api/a-cal/analytics/summary?days=7")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7

    def test_summary_days_validation(self, client):
        """days param outside 1-365 returns 422."""
        resp = client.get("/api/a-cal/analytics/summary?days=0")
        assert resp.status_code == 422
        resp = client.get("/api/a-cal/analytics/summary?days=999")
        assert resp.status_code == 422


class TestBusyTimes:
    """Tests for the busy-times endpoint."""

    def test_busy_times_returns_200(self, client):
        """GET /analytics/busy-times returns 200."""
        resp = client.get("/api/a-cal/analytics/busy-times")
        assert resp.status_code == 200
        data = resp.json()
        assert "busy_by_day_of_week" in data
        assert "busy_by_hour" in data
        assert len(data["busy_by_day_of_week"]) == 7
        assert len(data["busy_by_hour"]) == 24


class TestMeetingStats:
    """Tests for the meeting-stats endpoint."""

    def test_meeting_stats_returns_200(self, client):
        """GET /analytics/meeting-stats returns 200."""
        resp = client.get("/api/a-cal/analytics/meeting-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "meeting_count" in data
        assert "total_meeting_minutes" in data
        assert "category_counts" in data


class TestFreeSlots:
    """Tests for the free-slots endpoint."""

    def test_free_slots_valid_dates(self, client):
        """GET /analytics/free-slots with valid dates returns 200."""
        resp = client.get("/api/a-cal/analytics/free-slots", params={
            "start_date": "2025-01-06T00:00:00",
            "end_date": "2025-01-06T23:59:00",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "free_slots" in data
        assert "total" in data

    def test_free_slots_invalid_dates(self, client):
        """Invalid date format returns 400."""
        resp = client.get("/api/a-cal/analytics/free-slots", params={
            "start_date": "not-a-date",
            "end_date": "also-bad",
        })
        assert resp.status_code == 400

    def test_free_slots_missing_dates(self, client):
        """Missing date params return 422."""
        resp = client.get("/api/a-cal/analytics/free-slots")
        assert resp.status_code == 422


class TestSuggestReschedule:
    """Tests for the suggest-reschedule endpoint."""

    def test_reschedule_event_not_found(self, client):
        """POST /analytics/suggest-reschedule with unknown ID returns failure."""
        resp = client.post("/api/a-cal/analytics/suggest-reschedule", json={
            "event_id": "nonexistent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_reschedule_custom_lookahead(self, client):
        """look_ahead_days parameter is accepted."""
        resp = client.post("/api/a-cal/analytics/suggest-reschedule", json={
            "event_id": "nonexistent",
            "look_ahead_days": 30,
        })
        assert resp.status_code == 200


class TestEventTypes:
    """Tests for event type CRUD endpoints."""

    def test_list_empty(self, client):
        """GET /event-types returns empty list initially."""
        resp = client.get("/api/a-cal/event-types")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_event_type(self, client):
        """POST /event-types creates an event type."""
        resp = client.post("/api/a-cal/event-types", json={
            "title": "Team Sync",
            "slug": "team-sync",
            "duration_minutes": 45,
            "scheduling_type": "collective",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Team Sync"
        assert data["slug"] == "team-sync"
        assert data["duration_minutes"] == 45
        assert data["scheduling_type"] == "collective"
        assert "id" in data

    def test_get_event_type(self, client):
        """GET /event-types/{id} returns a single event type."""
        create = client.post("/api/a-cal/event-types", json={
            "title": "1on1", "slug": "1on1", "duration_minutes": 30,
        })
        et_id = create.json()["id"]
        resp = client.get(f"/api/a-cal/event-types/{et_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "1on1"

    def test_get_event_type_not_found(self, client):
        """GET /event-types/{id} with unknown ID returns 404."""
        resp = client.get("/api/a-cal/event-types/does-not-exist")
        assert resp.status_code == 404

    def test_delete_event_type(self, client):
        """DELETE /event-types/{id} removes the event type."""
        create = client.post("/api/a-cal/event-types", json={
            "title": "Delete Me", "slug": "delete-me",
        })
        et_id = create.json()["id"]
        resp = client.delete(f"/api/a-cal/event-types/{et_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == et_id
        # Verify it's gone
        resp2 = client.get(f"/api/a-cal/event-types/{et_id}")
        assert resp2.status_code == 404

    def test_create_with_round_robin(self, client):
        """Creating with round_robin scheduling type works."""
        resp = client.post("/api/a-cal/event-types", json={
            "title": "Rotation", "slug": "rotation",
            "scheduling_type": "round_robin",
        })
        assert resp.status_code == 200
        assert resp.json()["scheduling_type"] == "round_robin"


class TestAvailability:
    """Tests for availability endpoints."""

    def test_get_default_schedule(self, client):
        """GET /availability/schedule returns default schedule."""
        resp = client.get("/api/a-cal/availability/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert "days" in data
        assert "timezone" in data
        assert len(data["days"]) == 7

    def test_aggregated_collective(self, client):
        """POST /availability/aggregated with collective type works."""
        resp = client.post("/api/a-cal/availability/aggregated", json={
            "schedules": [
                {"days": [[{"start": "09:00", "end": "17:00"}]] + [[]] * 6},
                {"days": [[{"start": "10:00", "end": "16:00"}]] + [[]] * 6},
            ],
            "scheduling_type": "collective",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Intersection: 10:00-16:00
        assert data["days"][0][0]["start"] == "10:00"
        assert data["days"][0][0]["end"] == "16:00"

    def test_aggregated_empty_schedules(self, client):
        """POST /availability/aggregated with no schedules returns default."""
        resp = client.post("/api/a-cal/availability/aggregated", json={
            "schedules": [],
            "scheduling_type": "collective",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 7


class TestCalendarTools:
    """Tests for the calendar tools catalog endpoint."""

    def test_list_calendar_tools(self, client):
        """GET /calendar-tools returns the tool catalog."""
        resp = client.get("/api/a-cal/calendar-tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert data["count"] == 12
        assert len(data["tools"]) == 12


class TestSchedulePrompt:
    """Tests for the schedule prompt endpoint."""

    def test_get_schedule_prompt(self, client):
        """GET /schedule-prompt returns a prompt string."""
        resp = client.get("/api/a-cal/schedule-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert isinstance(data["prompt"], str)
        assert len(data["prompt"]) > 50

    def test_get_schedule_prompt_custom_tz(self, client):
        """GET /schedule-prompt with timezone param includes it."""
        resp = client.get("/api/a-cal/schedule-prompt?timezone=America/New_York")
        assert resp.status_code == 200
        assert "America/New_York" in resp.json()["prompt"]


class TestEventTypePersistence:
    """Tests verifying event types survive a store re-creation (DB persistence)."""

    def test_create_then_new_store_preserves(self, tmp_path):
        """Event types created via one store are visible in a fresh store."""
        from a_cal.db.store import PersistentStore

        db_file = str(tmp_path / "test_event_types.db")
        store1 = PersistentStore.__new__(PersistentStore)
        from a_cal.db.models import create_engine_and_session
        store1._engine, store1._SessionLocal = create_engine_and_session(db_file)
        store1._seed_if_empty()

        created = store1.create_event_type({
            "title": "Persistent Meeting",
            "slug": "persistent",
            "duration_minutes": 60,
        })
        et_id = created["id"]

        # Simulate a server restart by creating a new store pointing at the same file.
        store2 = PersistentStore.__new__(PersistentStore)
        store2._engine, store2._SessionLocal = create_engine_and_session(db_file)
        store2._seed_if_empty()

        retrieved = store2.get_event_type(et_id)
        assert retrieved is not None
        assert retrieved["title"] == "Persistent Meeting"
        assert retrieved["duration_minutes"] == 60

        all_types = store2.list_event_types()
        assert len(all_types) == 1
        assert all_types[0]["slug"] == "persistent"

    def test_delete_across_stores(self, tmp_path):
        """Event type deleted in one store is gone in a fresh store."""
        from a_cal.db.store import PersistentStore
        from a_cal.db.models import create_engine_and_session

        db_file = str(tmp_path / "test_delete.db")
        store1 = PersistentStore.__new__(PersistentStore)
        store1._engine, store1._SessionLocal = create_engine_and_session(db_file)
        store1._seed_if_empty()

        created = store1.create_event_type({"title": "To Delete", "slug": "to-delete"})
        et_id = created["id"]
        assert store1.delete_event_type(et_id) is True

        store2 = PersistentStore.__new__(PersistentStore)
        store2._engine, store2._SessionLocal = create_engine_and_session(db_file)
        store2._seed_if_empty()
        assert store2.get_event_type(et_id) is None
        assert store2.list_event_types() == []

    def test_get_nonexistent_returns_none(self):
        """get_event_type with unknown ID returns None (not an exception)."""
        from a_cal.db.store import PersistentStore

        store = PersistentStore(in_memory=True)
        assert store.get_event_type("does-not-exist") is None

    def test_delete_nonexistent_returns_false(self):
        """delete_event_type with unknown ID returns False."""
        from a_cal.db.store import PersistentStore

        store = PersistentStore(in_memory=True)
        assert store.delete_event_type("nope") is False

    def test_availability_metadata_persisted(self, tmp_path):
        """Complex availability and metadata survive a store re-creation."""
        from a_cal.db.store import PersistentStore
        from a_cal.db.models import create_engine_and_session

        db_file = str(tmp_path / "test_complex.db")
        store1 = PersistentStore.__new__(PersistentStore)
        store1._engine, store1._SessionLocal = create_engine_and_session(db_file)
        store1._seed_if_empty()

        created = store1.create_event_type({
            "title": "Complex",
            "slug": "complex",
            "availability": {
                "days": [[{"start": "10:00", "end": "12:00"}]] + [[]] * 6,
                "timezone": "America/Chicago",
            },
            "metadata": {"location": "Zoom", "price": 50},
            "scheduling_type": "round_robin",
        })
        et_id = created["id"]

        store2 = PersistentStore.__new__(PersistentStore)
        store2._engine, store2._SessionLocal = create_engine_and_session(db_file)
        store2._seed_if_empty()

        retrieved = store2.get_event_type(et_id)
        assert retrieved is not None
        assert retrieved["availability"]["timezone"] == "America/Chicago"
        assert retrieved["availability"]["days"][0][0]["start"] == "10:00"
        assert retrieved["metadata"]["location"] == "Zoom"
        assert retrieved["metadata"]["price"] == 50
        assert retrieved["scheduling_type"] == "round_robin"
