"""Tests for the timezone setting and conductor timezone-aware date grouping."""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.db.store import PersistentStore
from a_cal.agents.conductor import ACalConductor
from a_cal.api.agent_routes import router as agent_router


@pytest.fixture
def client():
    """Test client with the agent/settings routes mounted."""
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


class TestTimezoneAPI:
    """Timezone API endpoints."""

    def test_get_timezone(self, client):
        resp = client.get("/api/a-cal/settings/timezone")
        assert resp.status_code == 200
        data = resp.json()
        assert "timezone" in data
        assert isinstance(data["timezone"], str)
        assert len(data["timezone"]) > 0

    def test_set_valid_timezone(self, client):
        resp = client.post("/api/a-cal/settings/timezone", json={"timezone": "America/Chicago"})
        assert resp.status_code == 200
        assert resp.json()["timezone"] == "America/Chicago"

    def test_set_invalid_timezone_400(self, client):
        resp = client.post("/api/a-cal/settings/timezone", json={"timezone": "Mars/Olympus"})
        assert resp.status_code == 400

    def test_set_then_get_timezone(self, client):
        client.post("/api/a-cal/settings/timezone", json={"timezone": "Europe/London"})
        resp = client.get("/api/a-cal/settings/timezone")
        assert resp.json()["timezone"] == "Europe/London"
        # Reset to avoid affecting other tests
        client.post("/api/a-cal/settings/timezone", json={"timezone": "UTC"})


class TestConductorTimezone:
    """The conductor uses the user's timezone for date grouping."""

    def test_user_now_is_timezone_aware(self):
        """_get_user_now returns a timezone-aware datetime."""
        store = PersistentStore(in_memory=True)
        conductor = ACalConductor(event_store=store, provider_store=store)
        now = conductor._get_user_now()
        assert now.tzinfo is not None
        assert now.year >= 2026

    def test_explicit_timezone_setting(self):
        """When timezone is set in the store, the conductor uses it."""
        store = PersistentStore(in_memory=True)
        store.set_setting("timezone", "Asia/Tokyo")
        conductor = ACalConductor(event_store=store, provider_store=store)
        tz = conductor._get_user_timezone()
        assert tz == ZoneInfo("Asia/Tokyo")

    def test_falls_back_to_system_when_no_provider_store(self):
        """Without a provider_store, falls back to system local timezone."""
        conductor = ACalConductor(event_store=None, provider_store=None)
        tz = conductor._get_user_timezone()
        assert tz is not None

    def test_falls_back_to_system_for_unknown_timezone(self):
        """An invalid timezone setting falls back to system local."""
        store = PersistentStore(in_memory=True)
        store.set_setting("timezone", "Invalid/Zone")
        conductor = ACalConductor(event_store=store, provider_store=store)
        tz = conductor._get_user_timezone()
        assert str(tz) != "Invalid/Zone"

    @pytest.mark.asyncio
    async def test_event_near_utc_midnight_shows_as_today_in_local_tz(self):
        """An event 30 min from now should appear in 'today' results when the
        user's local timezone keeps it on the same calendar day — the bug that
        motivated timezone support."""
        store = PersistentStore(in_memory=True)
        now_utc = datetime.now(timezone.utc)
        event_start = now_utc + timedelta(minutes=30)
        store.create_event({
            "title": "Late Evening Meeting",
            "start": event_start.isoformat(),
            "end": (event_start + timedelta(minutes=30)).isoformat(),
            "provider_type": "local",
            "provider_event_id": "tz-test-1",
        })
        conductor = ACalConductor(event_store=store, provider_store=store)
        result = await conductor.handle("what events do I have today?")
        assert "Late Evening Meeting" in result["response"]
