"""Tests for Phase 3 (calendar improvements) and Phase 4 (advanced email).

Phase 3 — Calendar Improvements:
  - Event CRUD with all-day, recurring, attendees, color fields
  - Schema upgrade adds new columns

Phase 4 — Advanced Email:
  - Email labels CRUD
  - Email filters CRUD
  - Email snooze / unsnooze
  - Scheduled emails
  - Vacation responder config
  - Email templates CRUD
  - AI summarization (extractive fallback)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.db.store import PersistentStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """FastAPI app with standalone data routes."""
    a = FastAPI()
    a.include_router(standalone_data_router)
    return a


@pytest.fixture
def client(app):
    """Test client with standalone data routes."""
    return TestClient(app)


def _iso(dt: datetime) -> str:
    """Convert a datetime to an ISO string suitable for the API."""
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Phase 3: Calendar Event CRUD with new fields
# ---------------------------------------------------------------------------

class TestCalendarImprovements:
    """Event create/update with all-day, recurring, attendees, color."""

    def test_create_event_with_all_day(self, client):
        """All-day flag is stored and returned."""
        start = datetime(2026, 7, 20, tzinfo=UTC)
        end = datetime(2026, 7, 20, 23, 59, tzinfo=UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Conference",
            "start": _iso(start),
            "end": _iso(end),
            "is_all_day": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_all_day"] is True
        assert data["title"] == "Conference"

    def test_create_event_with_color(self, client):
        """Color field is stored and returned."""
        start = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Team Sync",
            "start": _iso(start),
            "end": _iso(end),
            "color": "#ff5733",
        })
        assert resp.status_code == 200
        assert resp.json()["color"] == "#ff5733"

    def test_create_event_with_recurrence(self, client):
        """Recurrence rule is stored and returned."""
        start = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Daily Standup",
            "start": _iso(start),
            "end": _iso(end),
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
        })
        assert resp.status_code == 200
        assert resp.json()["recurrence_rule"] == "FREQ=DAILY;INTERVAL=1"

    def test_create_event_with_attendees(self, client):
        """Attendees list is stored and returned."""
        start = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
        attendees = [
            {"email": "alice@example.com", "name": "Alice", "status": "accepted"},
            {"email": "bob@example.com", "name": "Bob", "status": "tentative"},
        ]
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Project Review",
            "start": _iso(start),
            "end": _iso(end),
            "attendees": attendees,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["attendees"]) == 2
        assert data["attendees"][0]["email"] == "alice@example.com"

    def test_update_event_color(self, client):
        """Update color on an existing event."""
        start = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
        create = client.post("/api/a-cal/calendar/events", json={
            "title": "Lunch",
            "start": _iso(start),
            "end": _iso(end),
        })
        eid = create.json()["provider_event_id"]
        resp = client.patch(f"/api/a-cal/calendar/events/{eid}", json={"color": "#00ff00"})
        assert resp.status_code == 200
        assert resp.json()["color"] == "#00ff00"

    def test_update_event_all_day(self, client):
        """Update all-day flag on an existing event."""
        start = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
        create = client.post("/api/a-cal/calendar/events", json={
            "title": "Workshop",
            "start": _iso(start),
            "end": _iso(end),
        })
        eid = create.json()["provider_event_id"]
        resp = client.patch(f"/api/a-cal/calendar/events/{eid}", json={
            "is_all_day": True,
            "attendees": [{"email": "carol@example.com", "name": "Carol"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_all_day"] is True
        assert len(data["attendees"]) == 1

    def test_event_defaults_no_all_day(self, client):
        """Events default to is_all_day=False when not specified."""
        start = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
        end = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Quick Chat",
            "start": _iso(start),
            "end": _iso(end),
        })
        assert resp.json()["is_all_day"] is False
        assert resp.json()["recurrence_rule"] is None
        assert resp.json()["attendees"] is None
        assert resp.json()["color"] is None


# ---------------------------------------------------------------------------
# Phase 4: Email Labels
# ---------------------------------------------------------------------------

class TestEmailLabels:
    """Custom email label CRUD."""

    def test_create_label(self, client):
        """Create a custom email label."""
        resp = client.post("/api/a-cal/email/labels", json={"name": "Important", "color": "#ef4444"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Important"
        assert data["color"] == "#ef4444"
        assert "id" in data

    def test_list_labels(self, client):
        """List all custom labels."""
        client.post("/api/a-cal/email/labels", json={"name": "Work", "color": "#3b82f6"})
        client.post("/api/a-cal/email/labels", json={"name": "Personal", "color": "#10b981"})
        resp = client.get("/api/a-cal/email/labels")
        assert resp.status_code == 200
        labels = resp.json()
        assert len(labels) >= 2
        names = [l["name"] for l in labels]
        assert "Work" in names
        assert "Personal" in names

    def test_delete_label(self, client):
        """Delete a custom label."""
        create = client.post("/api/a-cal/email/labels", json={"name": "ToDelete", "color": "#999"})
        label_id = create.json()["id"]
        resp = client.delete(f"/api/a-cal/email/labels/{label_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_label_not_found(self, client):
        """Deleting a non-existent label returns 404."""
        resp = client.delete("/api/a-cal/email/labels/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 4: Email Filters
# ---------------------------------------------------------------------------

class TestEmailFilters:
    """Email filter rule CRUD."""

    def test_create_filter(self, client):
        """Create an email filter rule."""
        resp = client.post("/api/a-cal/email/filters", json={
            "name": "Label newsletters",
            "field": "from",
            "pattern": "newsletter@",
            "action": "label",
            "action_value": "Newsletter",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Label newsletters"
        assert data["field"] == "from"
        assert data["pattern"] == "newsletter@"

    def test_list_filters(self, client):
        """List all filter rules."""
        client.post("/api/a-cal/email/filters", json={
            "name": "Filter 1",
            "field": "subject",
            "pattern": "urgent",
            "action": "mark_read",
        })
        resp = client.get("/api/a-cal/email/filters")
        assert resp.status_code == 200
        filters = resp.json()
        assert any(f["name"] == "Filter 1" for f in filters)

    def test_delete_filter(self, client):
        """Delete a filter rule."""
        create = client.post("/api/a-cal/email/filters", json={
            "name": "Temp Filter",
            "field": "from",
            "pattern": "spam@",
        })
        fid = create.json()["id"]
        resp = client.delete(f"/api/a-cal/email/filters/{fid}")
        assert resp.status_code == 200

    def test_delete_filter_not_found(self, client):
        """Deleting a non-existent filter returns 404."""
        resp = client.delete("/api/a-cal/email/filters/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 4: Email Snooze
# ---------------------------------------------------------------------------

class TestEmailSnooze:
    """Snooze and unsnooze emails."""

    def test_snooze_email(self, client):
        """Snooze an email until a future time."""
        snooze_until = datetime.now(UTC) + timedelta(hours=3)
        resp = client.post("/api/a-cal/email/snooze", json={
            "provider_connection_id": "conn-1",
            "provider_message_id": "msg-123",
            "snooze_until": _iso(snooze_until),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider_message_id"] == "msg-123"
        assert "snooze_until" in data

    def test_list_snoozed(self, client):
        """List snoozed emails."""
        snooze_until = datetime.now(UTC) + timedelta(hours=2)
        client.post("/api/a-cal/email/snooze", json={
            "provider_connection_id": "conn-2",
            "provider_message_id": "msg-456",
            "snooze_until": _iso(snooze_until),
        })
        resp = client.get("/api/a-cal/email/snoozed")
        assert resp.status_code == 200
        snoozed = resp.json()
        assert any(s["provider_message_id"] == "msg-456" for s in snoozed)

    def test_unsnooze_email(self, client):
        """Remove a snooze record."""
        snooze_until = datetime.now(UTC) + timedelta(hours=1)
        create = client.post("/api/a-cal/email/snooze", json={
            "provider_connection_id": "conn-3",
            "provider_message_id": "msg-789",
            "snooze_until": _iso(snooze_until),
        })
        sid = create.json()["id"]
        resp = client.delete(f"/api/a-cal/email/snoozed/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unsnoozed"

    def test_unsnooze_not_found(self, client):
        """Unsnoozing a non-existent record returns 404."""
        resp = client.delete("/api/a-cal/email/snoozed/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 4: Scheduled Emails
# ---------------------------------------------------------------------------

class TestScheduledEmails:
    """Schedule and cancel emails to send later."""

    def test_schedule_email(self, client):
        """Schedule an email for future delivery."""
        scheduled = datetime.now(UTC) + timedelta(days=1)
        resp = client.post("/api/a-cal/email/schedule", json={
            "provider_connection_id": "conn-1",
            "to_addresses": ["alice@example.com"],
            "subject": "Tomorrow's Meeting",
            "body_text": "Don't forget about our meeting tomorrow.",
            "scheduled_for": _iso(scheduled),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["subject"] == "Tomorrow's Meeting"

    def test_list_scheduled(self, client):
        """List pending scheduled emails."""
        scheduled = datetime.now(UTC) + timedelta(hours=6)
        client.post("/api/a-cal/email/schedule", json={
            "provider_connection_id": "conn-2",
            "to_addresses": ["bob@example.com"],
            "subject": "Follow up",
            "body_text": "Following up on our discussion.",
            "scheduled_for": _iso(scheduled),
        })
        resp = client.get("/api/a-cal/email/scheduled")
        assert resp.status_code == 200
        emails = resp.json()
        assert any(e["subject"] == "Follow up" for e in emails)

    def test_cancel_scheduled(self, client):
        """Cancel a scheduled email."""
        scheduled = datetime.now(UTC) + timedelta(hours=12)
        create = client.post("/api/a-cal/email/schedule", json={
            "provider_connection_id": "conn-3",
            "to_addresses": ["carol@example.com"],
            "subject": "To Cancel",
            "body_text": "This should be cancelled.",
            "scheduled_for": _iso(scheduled),
        })
        sid = create.json()["id"]
        resp = client.delete(f"/api/a-cal/email/scheduled/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_not_found(self, client):
        """Cancelling a non-existent scheduled email returns 404."""
        resp = client.delete("/api/a-cal/email/scheduled/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 4: Vacation Responder
# ---------------------------------------------------------------------------

class TestVacationResponder:
    """Vacation auto-responder configuration."""

    def test_get_default_vacation(self, client):
        """Default vacation config is disabled."""
        resp = client.get("/api/a-cal/email/vacation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    def test_update_vacation(self, client):
        """Update vacation responder config."""
        resp = client.put("/api/a-cal/email/vacation", json={
            "enabled": True,
            "subject": "On Leave",
            "body_text": "I'm on leave until July 30.",
            "start_date": "2026-07-20",
            "end_date": "2026-07-30",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["subject"] == "On Leave"

    def test_get_updated_vacation(self, client):
        """Vacation config persists after update."""
        client.put("/api/a-cal/email/vacation", json={
            "enabled": True,
            "subject": "Away",
            "body_text": "Out of office.",
        })
        resp = client.get("/api/a-cal/email/vacation")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        assert resp.json()["subject"] == "Away"


# ---------------------------------------------------------------------------
# Phase 4: Email Templates
# ---------------------------------------------------------------------------

class TestEmailTemplates:
    """Email template CRUD."""

    def test_create_template(self, client):
        """Create an email template."""
        resp = client.post("/api/a-cal/email/templates", json={
            "name": "Welcome Email",
            "subject": "Welcome to A-Cal!",
            "body_text": "Hello! Thanks for joining.",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Welcome Email"
        assert data["subject"] == "Welcome to A-Cal!"

    def test_list_templates(self, client):
        """List all email templates."""
        client.post("/api/a-cal/email/templates", json={
            "name": "Follow Up",
            "subject": "Following up",
            "body_text": "Just checking in.",
        })
        resp = client.get("/api/a-cal/email/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert any(t["name"] == "Follow Up" for t in templates)

    def test_update_template(self, client):
        """Update an email template."""
        create = client.post("/api/a-cal/email/templates", json={
            "name": "Original",
            "body_text": "Original body.",
        })
        tid = create.json()["id"]
        resp = client.put(f"/api/a-cal/email/templates/{tid}", json={
            "name": "Updated",
            "body_text": "Updated body.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["body_text"] == "Updated body."

    def test_delete_template(self, client):
        """Delete an email template."""
        create = client.post("/api/a-cal/email/templates", json={
            "name": "To Delete",
            "body_text": "Bye.",
        })
        tid = create.json()["id"]
        resp = client.delete(f"/api/a-cal/email/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_update_template_not_found(self, client):
        """Updating a non-existent template returns 404."""
        resp = client.put("/api/a-cal/email/templates/nonexistent", json={"name": "X"})
        assert resp.status_code == 404

    def test_delete_template_not_found(self, client):
        """Deleting a non-existent template returns 404."""
        resp = client.delete("/api/a-cal/email/templates/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 4: AI Email Summarization
# ---------------------------------------------------------------------------

class TestEmailSummarization:
    """AI email summarization endpoint."""

    def test_summarize_short_email(self, client):
        """Very short emails return a skip message."""
        resp = client.post("/api/a-cal/email/summarize", json={
            "body_text": "Hi",
            "subject": "Test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert data["method"] == "skip"

    def test_summarize_long_email_fallback(self, client):
        """Long email falls back to extractive summary when no LLM available."""
        long_body = (
            "Dear team, I wanted to update you on the project status. "
            "We have completed the first phase of development. "
            "The second phase will begin next week. "
            "Please review the attached timeline and let me know if you have concerns. "
            "Best regards, Project Manager."
        )
        resp = client.post("/api/a-cal/email/summarize", json={
            "body_text": long_body,
            "subject": "Project Update",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert len(data["summary"]) > 10
        # Method is either "llm" or "extractive" (fallback)
        assert data["method"] in ("llm", "extractive")

    def test_summarize_empty_email(self, client):
        """Empty body returns a skip message."""
        resp = client.post("/api/a-cal/email/summarize", json={
            "body_text": "",
            "subject": "Empty",
        })
        assert resp.status_code == 200
        assert resp.json()["method"] == "skip"
