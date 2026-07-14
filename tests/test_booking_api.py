"""Tests for the booking API — public booking pages, slots, and booking CRUD.

Covers Phase 2 scheduling features: booking page by slug, available slot
computation, booking creation with video link generation, booking management,
and event type extended fields.
"""

from __future__ import annotations

import datetime
from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient

from a_cal.api.standalone import app
from a_cal.db.store import PersistentStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_event_types():
    """Clear event types and bookings before each test for isolation."""
    db = PersistentStore(in_memory=True)
    # We need to use the same store the app uses — patch it.
    from a_cal.api import booking_routes, analytics_routes
    original_db = booking_routes._db
    original_analytics_db = analytics_routes._db
    booking_routes._db = db
    analytics_routes._db = db
    yield db
    booking_routes._db = original_db
    analytics_routes._db = original_analytics_db


@pytest.fixture(autouse=True)
def _auth():
    """Log in as demo user for authenticated endpoints."""
    client.post("/api/a-cal/auth/demo-login")
    yield


class TestEventTypesExtended:
    """Tests for event type creation with extended scheduling fields."""

    def test_create_event_type_with_scheduling_fields(self, _clean_event_types):
        """Event types accept buffer, min notice, custom questions, video."""
        r = client.post("/api/a-cal/event-types", json={
            "title": "Deep Dive",
            "slug": "deep-dive",
            "duration_minutes": 60,
            "buffer_before_minutes": 10,
            "buffer_after_minutes": 10,
            "min_notice_hours": 4,
            "max_booking_days": 14,
            "custom_questions": [
                {"id": "q1", "label": "Topic?", "type": "text", "required": True}
            ],
            "video_provider": "zoom",
            "reminder_minutes_before": 15,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["buffer_before_minutes"] == 10
        assert data["buffer_after_minutes"] == 10
        assert data["min_notice_hours"] == 4
        assert data["max_booking_days"] == 14
        assert data["video_provider"] == "zoom"
        assert data["reminder_minutes_before"] == 15
        assert len(data["custom_questions"]) == 1

    def test_update_event_type(self, _clean_event_types):
        """PUT /event-types/{id} updates scheduling fields."""
        r = client.post("/api/a-cal/event-types", json={
            "title": "Quick Chat",
            "slug": "quick-chat",
        })
        et_id = r.json()["id"]

        r2 = client.put(f"/api/a-cal/event-types/{et_id}", json={
            "title": "Quick Chat",
            "slug": "quick-chat",
            "duration_minutes": 15,
            "buffer_before_minutes": 5,
            "video_provider": "meet",
        })
        assert r2.status_code == 200
        assert r2.json()["buffer_before_minutes"] == 5
        assert r2.json()["video_provider"] == "meet"


class TestPublicBooking:
    """Tests for the public booking page flow (no auth required)."""

    def test_get_public_event_type(self, _clean_event_types):
        """GET /booking/{slug} returns event type info without auth."""
        client.post("/api/a-cal/event-types", json={
            "title": "Consultation",
            "slug": "consultation",
            "duration_minutes": 30,
            "description": "30-min consultation call",
        })
        # Logout to simulate public access
        client.post("/api/a-cal/auth/logout")

        r = client.get("/api/a-cal/booking/consultation")
        assert r.status_code == 200
        assert r.json()["title"] == "Consultation"
        assert r.json()["slug"] == "consultation"
        assert r.json()["duration_minutes"] == 30

    def test_get_public_event_type_not_found(self):
        """GET /booking/{nonexistent} returns 404."""
        r = client.get("/api/a-cal/booking/nonexistent-slug")
        assert r.status_code == 404

    def test_get_booking_slots(self, _clean_event_types):
        """GET /booking/{slug}/slots returns available time slots."""
        client.post("/api/a-cal/event-types", json={
            "title": "Meeting",
            "slug": "team-meeting",
            "duration_minutes": 30,
            "min_notice_hours": 0,  # allow immediate booking for test
        })

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        r = client.get(f"/api/a-cal/booking/team-meeting/slots?date={tomorrow}")
        assert r.status_code == 200
        data = r.json()
        assert data["duration_minutes"] == 30
        assert len(data["slots"]) > 0
        # Each slot has start and end
        for slot in data["slots"]:
            assert "start" in slot
            assert "end" in slot

    def test_get_slots_past_date(self, _clean_event_types):
        """Slots for a past date return empty."""
        client.post("/api/a-cal/event-types", json={
            "title": "Meeting",
            "slug": "past-test",
        })
        yesterday = (datetime.datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        r = client.get(f"/api/a-cal/booking/past-test/slots?date={yesterday}")
        assert r.status_code == 200
        assert r.json()["slots"] == []

    def test_create_public_booking(self, _clean_event_types):
        """POST /booking/{slug} creates a booking with video link."""
        client.post("/api/a-cal/event-types", json={
            "title": "Demo Meeting",
            "slug": "demo-meeting",
            "duration_minutes": 30,
            "min_notice_hours": 0,
            "video_provider": "meet",
        })

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slots_r = client.get(f"/api/a-cal/booking/demo-meeting/slots?date={tomorrow}")
        slots = slots_r.json()["slots"]
        assert len(slots) > 0

        r = client.post("/api/a-cal/booking/demo-meeting", json={
            "attendee_name": "Alice Smith",
            "attendee_email": "alice@example.com",
            "start_time": slots[0]["start"],
            "answers": {},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "confirmed"
        assert data["booking_id"]
        assert data["video_link"] is not None
        assert "meet.google.com" in data["video_link"]

    def test_create_booking_no_video_provider(self, _clean_event_types):
        """Bookings without a video provider have no video link."""
        client.post("/api/a-cal/event-types", json={
            "title": "In Person",
            "slug": "in-person",
            "duration_minutes": 30,
            "min_notice_hours": 0,
            "video_provider": "",
        })

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slots_r = client.get(f"/api/a-cal/booking/in-person/slots?date={tomorrow}")
        slots = slots_r.json()["slots"]

        r = client.post("/api/a-cal/booking/in-person", json={
            "attendee_name": "Bob Jones",
            "attendee_email": "bob@example.com",
            "start_time": slots[0]["start"],
            "answers": {},
        })
        assert r.status_code == 200
        assert r.json()["video_link"] is None

    def test_double_booking_conflict(self, _clean_event_types):
        """Booking an already-taken slot returns 409."""
        client.post("/api/a-cal/event-types", json={
            "title": "Conflict Test",
            "slug": "conflict-test",
            "duration_minutes": 30,
            "min_notice_hours": 0,
            "video_provider": "meet",
        })

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slots_r = client.get(f"/api/a-cal/booking/conflict-test/slots?date={tomorrow}")
        slots = slots_r.json()["slots"]
        slot = slots[0]

        # First booking
        r1 = client.post("/api/a-cal/booking/conflict-test", json={
            "attendee_name": "First Person",
            "attendee_email": "first@example.com",
            "start_time": slot["start"],
        })
        assert r1.status_code == 200

        # Second booking for same slot → conflict
        r2 = client.post("/api/a-cal/booking/conflict-test", json={
            "attendee_name": "Second Person",
            "attendee_email": "second@example.com",
            "start_time": slot["start"],
        })
        assert r2.status_code == 409


class TestBookingManagement:
    """Tests for authenticated booking management endpoints."""

    def test_list_bookings(self, _clean_event_types):
        """GET /bookings returns bookings for the current user."""
        # Create event type + booking
        et_r = client.post("/api/a-cal/event-types", json={
            "title": "List Test",
            "slug": "list-test",
            "duration_minutes": 30,
            "min_notice_hours": 0,
            "video_provider": "zoom",
        })
        et_id = et_r.json()["id"]

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slots_r = client.get(f"/api/a-cal/booking/list-test/slots?date={tomorrow}")
        slot = slots_r.json()["slots"][0]

        client.post("/api/a-cal/booking/list-test", json={
            "attendee_name": "Carol",
            "attendee_email": "carol@example.com",
            "start_time": slot["start"],
        })

        r = client.get("/api/a-cal/bookings")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        assert r.json()[0]["attendee_name"] == "Carol"

    def test_list_bookings_by_event_type(self, _clean_event_types):
        """GET /bookings?event_type_id=X filters by event type."""
        et1 = client.post("/api/a-cal/event-types", json={
            "title": "Type A", "slug": "type-a", "min_notice_hours": 0,
        }).json()
        et2 = client.post("/api/a-cal/event-types", json={
            "title": "Type B", "slug": "type-b", "min_notice_hours": 0,
        }).json()

        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        for slug in ["type-a", "type-b"]:
            slots = client.get(f"/api/a-cal/booking/{slug}/slots?date={tomorrow}").json()["slots"]
            client.post(f"/api/a-cal/booking/{slug}", json={
                "attendee_name": f"User for {slug}",
                "attendee_email": f"{slug}@example.com",
                "start_time": slots[0]["start"],
            })

        r = client.get(f"/api/a-cal/bookings?event_type_id={et1['id']}")
        assert r.status_code == 200
        bookings = r.json()
        assert all(b["event_type_id"] == et1["id"] for b in bookings)

    def test_cancel_booking(self, _clean_event_types):
        """PATCH /bookings/{id} cancels a booking."""
        client.post("/api/a-cal/event-types", json={
            "title": "Cancel Test", "slug": "cancel-test",
            "min_notice_hours": 0, "video_provider": "teams",
        })
        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slot = client.get(f"/api/a-cal/booking/cancel-test/slots?date={tomorrow}").json()["slots"][0]
        book_r = client.post("/api/a-cal/booking/cancel-test", json={
            "attendee_name": "Dan",
            "attendee_email": "dan@example.com",
            "start_time": slot["start"],
        })
        booking_id = book_r.json()["booking_id"]

        r = client.patch(f"/api/a-cal/bookings/{booking_id}", json={"status": "cancelled"})
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_delete_booking(self, _clean_event_types):
        """DELETE /bookings/{id} removes a booking."""
        client.post("/api/a-cal/event-types", json={
            "title": "Delete Test", "slug": "delete-test",
            "min_notice_hours": 0,
        })
        tomorrow = (datetime.datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        slot = client.get(f"/api/a-cal/booking/delete-test/slots?date={tomorrow}").json()["slots"][0]
        book_r = client.post("/api/a-cal/booking/delete-test", json={
            "attendee_name": "Eve",
            "attendee_email": "eve@example.com",
            "start_time": slot["start"],
        })
        booking_id = book_r.json()["booking_id"]

        r = client.delete(f"/api/a-cal/bookings/{booking_id}")
        assert r.status_code == 200

        # Verify it's gone
        r2 = client.get(f"/api/a-cal/bookings/{booking_id}")
        assert r2.status_code == 404


class TestVideoLinkGeneration:
    """Tests for video conference link auto-generation."""

    @pytest.mark.parametrize("provider,expected_url", [
        ("zoom", "zoom.us"),
        ("meet", "meet.google.com"),
        ("teams", "teams.microsoft.com"),
    ])
    def test_video_link_generation(self, _clean_event_types, provider, expected_url):
        """Each video provider generates a valid meeting URL."""
        from a_cal.api.booking_routes import _generate_video_link
        link = _generate_video_link(provider)
        assert link is not None
        assert expected_url in link

    def test_no_video_provider(self):
        """Empty video provider returns None."""
        from a_cal.api.booking_routes import _generate_video_link
        assert _generate_video_link("") is None


# --- P0-3: public-booking workflow runs under owner context ----------------

class TestTriggerWorkflowsOwnerContext:
    """Regression tests for P0-3 — _trigger_workflows must run under the
    event-type owner's user context, not the public request user's."""

    def test_trigger_workflows_scopes_to_owner(self):
        """_trigger_workflows sets the contextvar to owner_user_id during lookup."""
        from unittest.mock import patch, MagicMock
        from a_cal.api import booking_routes
        from a_cal.auth.session import set_current_user_id, reset_current_user_id, get_current_user_id

        # Start from a known non-owner user (simulating a public request).
        baseline_token = set_current_user_id("public-anon")
        captured: dict[str, str] = {}
        try:
            # Patch WorkflowStore so we can capture the active user_id.
            class _CapturingStore:
                def __init__(self, db):
                    pass

                def list_workflows(self):
                    captured["uid_during_lookup"] = get_current_user_id()
                    return []  # no matching workflows → early return

            with patch("a_cal.workflows.store.WorkflowStore", _CapturingStore):
                booking_routes._trigger_workflows(
                    "booking_created",
                    {"booking_id": "bk-1"},
                    owner_user_id="owner-xyz",
                )

            assert captured.get("uid_during_lookup") == "owner-xyz"
            # Contextvar is restored after the call.
            assert get_current_user_id() == "public-anon"
        finally:
            reset_current_user_id(baseline_token)

    def test_trigger_workflows_without_owner_uses_session_user(self):
        """When owner_user_id is None, the session user is preserved (no override)."""
        from unittest.mock import patch
        from a_cal.api import booking_routes
        from a_cal.auth.session import set_current_user_id, reset_current_user_id, get_current_user_id

        baseline_token = set_current_user_id("session-user")
        captured: dict[str, str] = {}
        try:
            class _CapturingStore:
                def __init__(self, db):
                    pass

                def list_workflows(self):
                    captured["uid_during_lookup"] = get_current_user_id()
                    return []

            with patch("a_cal.workflows.store.WorkflowStore", _CapturingStore):
                booking_routes._trigger_workflows(
                    "booking_created",
                    {"booking_id": "bk-2"},
                    owner_user_id=None,
                )

            assert captured.get("uid_during_lookup") == "session-user"
        finally:
            reset_current_user_id(baseline_token)
