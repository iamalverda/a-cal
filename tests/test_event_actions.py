"""Tests for event CRUD endpoints and agentic event actions.

Covers:
  - Event CRUD via the standalone data API (POST/PATCH/DELETE/GET)
  - Conductor creating/rescheduling/deleting events via natural language
  - Standalone response generator event action detection
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.agents.conductor import ACalConductor
from a_cal.agents.standalone_responses import (
    generate_standalone_response,
    _detect_event_action,
)
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


@pytest.fixture
def fresh_store():
    """A fresh PersistentStore for agentic event tests."""
    return PersistentStore()


def _iso(dt: datetime) -> str:
    """Convert a datetime to an ISO string suitable for the API."""
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Event CRUD API
# ---------------------------------------------------------------------------

class TestEventCrudApi:
    """Event create / read / update / delete endpoints."""

    def test_create_event(self, client):
        """POST /calendar/events should create and return the event."""
        start = datetime.now(timezone.utc) + timedelta(days=2, hours=10)
        end = start + timedelta(minutes=45)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Strategy Sync",
            "start": _iso(start),
            "end": _iso(end),
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Strategy Sync"
        assert body["provider_event_id"]
        assert body["provider_type"] == "local"

    def test_list_events(self, client):
        """GET /calendar/events should return all events in the window."""
        resp = client.get("/api/a-cal/calendar/events", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_create_then_list_shows_new_event(self, client):
        """A created event should appear in the list."""
        start = datetime.now(timezone.utc) + timedelta(days=5, hours=14)
        end = start + timedelta(minutes=60)
        create_resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Quarterly Review",
            "start": _iso(start),
            "end": _iso(end),
        })
        eid = create_resp.json()["provider_event_id"]

        list_resp = client.get("/api/a-cal/calendar/events", params={"days": 30})
        titles = [e["title"] for e in list_resp.json()]
        assert "Quarterly Review" in titles

    def test_update_event(self, client):
        """PATCH should update event fields."""
        start = datetime.now(timezone.utc) + timedelta(days=3, hours=9)
        end = start + timedelta(minutes=30)
        create_resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Original Title",
            "start": _iso(start),
            "end": _iso(end),
        })
        eid = create_resp.json()["provider_event_id"]

        patch_resp = client.patch(f"/api/a-cal/calendar/events/{eid}", json={
            "title": "Renamed Meeting",
        })
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Renamed Meeting"

    def test_update_nonexistent_event_404s(self, client):
        """Patching a non-existent event should 404."""
        resp = client.patch("/api/a-cal/calendar/events/nonexistent-id", json={
            "title": "Nope",
        })
        assert resp.status_code == 404

    def test_delete_event(self, client):
        """DELETE should remove the event."""
        start = datetime.now(timezone.utc) + timedelta(days=4, hours=11)
        end = start + timedelta(minutes=30)
        create_resp = client.post("/api/a-cal/calendar/events", json={
            "title": "To Be Deleted",
            "start": _iso(start),
            "end": _iso(end),
        })
        eid = create_resp.json()["provider_event_id"]

        del_resp = client.delete(f"/api/a-cal/calendar/events/{eid}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

    def test_delete_nonexistent_event_404s(self, client):
        """Deleting a non-existent event should 404."""
        resp = client.delete("/api/a-cal/calendar/events/does-not-exist")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Agentic event actions via conductor
# ---------------------------------------------------------------------------

class TestConductorEventActions:
    """The conductor should create, reschedule, and delete events via natural language."""

    @pytest.mark.asyncio
    async def test_conductor_creates_event_from_natural_language(self, fresh_store):
        """Saying 'schedule a meeting called Test Planning at 2pm tomorrow' should create an event."""
        conductor = ACalConductor(event_store=fresh_store)
        result = await conductor.handle("schedule a meeting called Test Planning at 2pm tomorrow")
        assert result["standalone"] is True
        assert result["routing"]["specialist"] == "a_cal_schedule_agent"
        actions = result.get("actions", [])
        create_actions = [a for a in actions if a.get("type") == "create_event"]
        assert len(create_actions) == 1
        assert create_actions[0]["status"] == "created"
        assert "Test Planning" in result["response"]

    @pytest.mark.asyncio
    async def test_conductor_finds_slots_without_create(self, fresh_store):
        """Saying 'find a free slot tomorrow afternoon' should find slots, not create."""
        conductor = ACalConductor(event_store=fresh_store)
        result = await conductor.handle("find a free slot tomorrow afternoon")
        actions = result.get("actions", [])
        create_actions = [a for a in actions if a.get("type") == "create_event"]
        assert len(create_actions) == 0
        find_actions = [a for a in actions if a.get("type") == "find_slots"]
        assert len(find_actions) == 1

    @pytest.mark.asyncio
    async def test_conductor_deletes_event_by_name(self, fresh_store):
        """Saying 'cancel Team Standup' should delete the matching event."""
        # Seed an event to delete
        start = datetime.now(timezone.utc) + timedelta(days=1, hours=9)
        fresh_store.create_event({
            "title": "Team Standup",
            "start": _iso(start),
            "end": _iso(start + timedelta(minutes=30)),
        })

        conductor = ACalConductor(event_store=fresh_store)
        result = await conductor.handle("cancel Team Standup")
        actions = result.get("actions", [])
        delete_actions = [a for a in actions if a.get("type") == "delete_event"]
        assert len(delete_actions) == 1
        assert delete_actions[0]["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_conductor_reschedules_event_by_name(self, fresh_store):
        """Saying 'move Project Review to 3pm tomorrow' should reschedule the event."""
        start = datetime.now(timezone.utc) + timedelta(days=2, hours=10)
        fresh_store.create_event({
            "title": "Project Review",
            "start": _iso(start),
            "end": _iso(start + timedelta(minutes=60)),
        })

        conductor = ACalConductor(event_store=fresh_store)
        result = await conductor.handle("reschedule Project Review to 3pm tomorrow")
        actions = result.get("actions", [])
        resched_actions = [a for a in actions if a.get("type") == "reschedule_event"]
        assert len(resched_actions) == 1
        assert resched_actions[0]["status"] == "moved"

    @pytest.mark.asyncio
    async def test_conductor_create_conflict_detected(self, fresh_store):
        """Creating an event that overlaps an existing one should report a conflict."""
        tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        start = tomorrow.replace(hour=14)
        fresh_store.create_event({
            "title": "Busy Block",
            "start": _iso(start),
            "end": _iso(start + timedelta(minutes=60)),
        })

        conductor = ACalConductor(event_store=fresh_store)
        result = await conductor.handle("schedule a meeting called Overlap Test at 2pm tomorrow")
        actions = result.get("actions", [])
        create_actions = [a for a in actions if a.get("type") == "create_event"]
        assert len(create_actions) == 1
        assert create_actions[0]["status"] == "conflict"


# ---------------------------------------------------------------------------
# Standalone response generator action detection
# ---------------------------------------------------------------------------

class TestActionDetection:
    """_detect_event_action should classify intent correctly."""

    def test_detect_create(self):
        assert _detect_event_action("schedule a meeting called Demo") == "create"
        assert _detect_event_action("book a call at 3pm") == "create"
        assert _detect_event_action("create an event tomorrow") == "create"
        assert _detect_event_action("add a meeting") == "create"

    def test_detect_delete(self):
        assert _detect_event_action("cancel the standup") == "delete"
        assert _detect_event_action("delete my dentist appointment") == "delete"
        assert _detect_event_action("remove the team meeting") == "delete"

    def test_detect_reschedule(self):
        assert _detect_event_action("move the standup to 3pm") == "reschedule"
        assert _detect_event_action("reschedule my dentist appointment") == "reschedule"
        assert _detect_event_action("push back the review") == "reschedule"

    def test_detect_find(self):
        assert _detect_event_action("find a free slot tomorrow") == "find"
        assert _detect_event_action("what times are open on friday") == "find"
        assert _detect_event_action("show me my schedule") == "find"

    def test_create_with_find_keyword_is_find(self):
        """'find a free slot to schedule' should be find, not create."""
        assert _detect_event_action("find a free slot to schedule a meeting") == "find"

    def test_detect_list(self):
        """Viewing/listing events should be classified as 'list'."""
        assert _detect_event_action("what events do I have today?") == "list"
        assert _detect_event_action("what do I have tomorrow?") == "list"
        assert _detect_event_action("show me my events") == "list"
        assert _detect_event_action("what's on my calendar this week?") == "list"
        assert _detect_event_action("do I have anything on Friday?") == "list"
        assert _detect_event_action("my agenda for today") == "list"
        assert _detect_event_action("am I free today?") == "list"
        assert _detect_event_action("upcoming meetings") == "list"

    def test_list_does_not_override_create(self):
        """'create an event today' should be create, not list."""
        assert _detect_event_action("create an event today") == "create"
        assert _detect_event_action("schedule a meeting tomorrow") == "create"
        assert _detect_event_action("book a slot this week") == "create"

    def test_list_does_not_override_find(self):
        """'find a free slot tomorrow' should be find, not list."""
        assert _detect_event_action("find a free slot tomorrow") == "find"
        assert _detect_event_action("show me my schedule") == "find"


class TestListEventsResponse:
    """The standalone response generator should list events for viewing queries."""

    def test_list_events_today(self):
        """'what do I have today?' should return events for today."""
        now = datetime.now(timezone.utc)
        events = [
            {
                "title": "Standup",
                "start": (now.replace(hour=9, minute=0, second=0, microsecond=0)).isoformat(),
                "end": (now.replace(hour=9, minute=30, second=0, microsecond=0)).isoformat(),
                "location": "Zoom",
                "source_sub_account_id": "sa-work",
            },
            {
                "title": "Lunch with Sarah",
                "start": (now.replace(hour=12, minute=0, second=0, microsecond=0)).isoformat(),
                "end": (now.replace(hour=13, minute=0, second=0, microsecond=0)).isoformat(),
                "location": "",
                "source_sub_account_id": "sa-personal",
            },
        ]

        from a_cal.agents.standalone_responses import _handle_list_events
        result = _handle_list_events("what do I have today?", events, now)
        assert result["actions"][0]["type"] == "list_events"
        assert result["actions"][0]["count"] == 2
        assert "Standup" in result["response"]
        assert "Lunch with Sarah" in result["response"]

    def test_list_events_empty_day(self):
        """An empty day should return a clear 'no events' message."""
        now = datetime.now(timezone.utc)
        # Events on a different day
        tomorrow = now + timedelta(days=1)
        events = [
            {
                "title": "Tomorrow Meeting",
                "start": (tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)).isoformat(),
                "end": (tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)).isoformat(),
            },
        ]

        from a_cal.agents.standalone_responses import _handle_list_events
        result = _handle_list_events("what do I have today?", events, now)
        assert result["actions"][0]["count"] == 0
        assert "no events" in result["response"].lower()

    def test_list_events_this_week(self):
        """'this week' should show events across the full week."""
        now = datetime.now(timezone.utc)
        monday = now - timedelta(days=now.weekday())
        events = [
            {
                "title": "Monday Meeting",
                "start": (monday.replace(hour=10, minute=0, second=0, microsecond=0)).isoformat(),
                "end": (monday.replace(hour=11, minute=0, second=0, microsecond=0)).isoformat(),
            },
            {
                "title": "Wednesday Call",
                "start": (monday + timedelta(days=2, hours=14)).isoformat(),
                "end": (monday + timedelta(days=2, hours=15)).isoformat(),
            },
        ]

        from a_cal.agents.standalone_responses import _handle_list_events
        result = _handle_list_events("what do I have this week?", events, now)
        assert result["actions"][0]["count"] == 2
        assert "Monday Meeting" in result["response"]
        assert "Wednesday Call" in result["response"]

    @pytest.mark.asyncio
    async def test_conductor_lists_events_via_chat(self):
        """The conductor should route 'what events do I have today?' to schedule
        and return a list of events, not a generic chat response."""
        store = PersistentStore(in_memory=True)

        # Create an event in the future (get_unified_calendar returns from now onward)
        now = datetime.now(timezone.utc)
        future_start = now + timedelta(hours=2)
        future_end = future_start + timedelta(minutes=30)
        store.create_event({
            "title": "Test Planning Session",
            "start": future_start.isoformat(),
            "end": future_end.isoformat(),
            "provider_type": "local",
            "provider_event_id": "test-list-1",
        })

        conductor = ACalConductor(
            event_store=store,
            provider_store=store,
        )
        result = await conductor.handle("what events do I have today?")
        assert result["routing"]["intent"] == "schedule"
        assert "Test Planning Session" in result["response"]
        assert result["actions"][0]["type"] == "list_events"


# ---------------------------------------------------------------------------
# Standalone response generator with event_store
# ---------------------------------------------------------------------------

class TestStandaloneEventActions:
    """generate_standalone_response should handle event actions with a store."""

    def test_create_event_with_store(self, fresh_store):
        """A create request should produce a created action when a store is present."""
        from a_cal.agents.conductor import IntentType, RoutingDecision
        from a_cal.agents.specs import CognitiveTier
        decision = RoutingDecision(
            intent=IntentType.SCHEDULE,
            specialist=None,
            tier=CognitiveTier.VERSATILE,
            force_local=False,
            self_model_context=None,
        )
        now = datetime.now(timezone.utc)
        result = generate_standalone_response(
            message="schedule a meeting called Test Meeting at 2pm tomorrow",
            decision=decision,
            now=now,
            events=[],
            event_store=fresh_store,
        )
        actions = result["actions"]
        assert any(a["type"] == "create_event" and a["status"] == "created" for a in actions)

    def test_create_event_without_store_is_dry_run(self):
        """Without a store, create should be a dry run."""
        from a_cal.agents.conductor import IntentType, RoutingDecision
        from a_cal.agents.specs import CognitiveTier
        decision = RoutingDecision(
            intent=IntentType.SCHEDULE,
            specialist=None,
            tier=CognitiveTier.VERSATILE,
            force_local=False,
            self_model_context=None,
        )
        now = datetime.now(timezone.utc)
        result = generate_standalone_response(
            message="schedule a meeting called No Store Planning at 2pm tomorrow",
            decision=decision,
            now=now,
            events=[],
            event_store=None,
        )
        actions = result["actions"]
        assert any(a["type"] == "create_event" and a["status"] == "dry_run" for a in actions)


# ---------------------------------------------------------------------------
# Provider connection management
# ---------------------------------------------------------------------------

class TestProviderConnections:
    """Provider connection CRUD and sync trigger endpoints."""

    def test_list_all_providers(self, client):
        """GET /providers/all should return all provider connections."""
        resp = client.get("/api/a-cal/providers/all")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    def test_create_and_delete_provider(self, client):
        """Creating then deleting a provider should work."""
        create_resp = client.post("/api/a-cal/providers", json={
            "sub_account_id": "sa-personal",
            "provider_type": "caldav",
            "provider_account_id": "test@cal.com",
            "display_name": "Test CalDAV",
            "config": {"server_url": "https://cal.example.com"},
        })
        assert create_resp.status_code == 200
        pid = create_resp.json()["id"]
        assert create_resp.json()["status"] == "pending"

        del_resp = client.delete(f"/api/a-cal/providers/{pid}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

    def test_delete_nonexistent_provider_404s(self, client):
        """Deleting a non-existent provider should 404."""
        resp = client.delete("/api/a-cal/providers/nonexistent-pc")
        assert resp.status_code == 404

    def test_trigger_sync(self, client):
        """POST /sync/trigger should sync providers and return a summary.

        In standalone mode, providers that require external services (Google,
        Outlook) will error gracefully — the status may be 'partial' rather
        than 'synced'. Either is valid as long as the endpoint returns a
        structured response.
        """
        resp = client.post("/api/a-cal/sync/trigger", json={
            "sub_account_id": "sa-work-google",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("synced", "partial")
        assert "providers_synced" in data
        assert "events_in_store" in data
        assert "events_pulled" in data
        assert isinstance(data.get("errors"), list)

    def test_update_provider_status(self, client):
        """PATCH /providers/{id} should update the status."""
        create_resp = client.post("/api/a-cal/providers", json={
            "sub_account_id": "sa-personal",
            "provider_type": "imap_smtp",
            "provider_account_id": "test@example.com",
            "display_name": "Test IMAP",
        })
        pid = create_resp.json()["id"]

        patch_resp = client.patch(f"/api/a-cal/providers/{pid}", json={
            "status": "connected",
        })
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "connected"
