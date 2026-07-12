"""Tests for the in-memory data/sync routes used in standalone mode.

These routes provide sub-account CRUD, provider connections, sync rules,
and the unified calendar view without requiring atom's database.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as standalone_data_router


@pytest.fixture
def client():
    """Test client with the standalone data routes mounted."""
    app = FastAPI()
    app.include_router(standalone_data_router)
    return TestClient(app)


# --- sub-accounts ----------------------------------------------------------

class TestSubAccounts:
    """Sub-account CRUD endpoints."""

    def test_list_returns_seeded_accounts(self, client):
        """The in-memory store should be seeded with demo sub-accounts."""
        resp = client.get("/api/a-cal/sub-accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 4
        names = [s["name"] for s in data]
        assert "Main Calendar" in names
        assert "Work Google" in names

    def test_list_includes_main_account(self, client):
        """One sub-account should have is_main=True."""
        resp = client.get("/api/a-cal/sub-accounts")
        mains = [s for s in resp.json() if s["is_main"]]
        assert len(mains) == 1
        assert mains[0]["name"] == "Main Calendar"

    def test_create_sub_account(self, client):
        """Creating a sub-account should return the new account with an ID."""
        resp = client.post("/api/a-cal/sub-accounts", json={
            "name": "Test Calendar",
            "kind": "calendar",
            "sync_mode": "mirror_filter",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Calendar"
        assert data["id"].startswith("sa-")

    def test_update_sub_account(self, client):
        """Updating a sub-account should change the specified fields."""
        create = client.post("/api/a-cal/sub-accounts", json={
            "name": "Update Me",
            "kind": "calendar",
        })
        sub_id = create.json()["id"]
        resp = client.patch(f"/api/a-cal/sub-accounts/{sub_id}", json={
            "sync_mode": "intelligent_merge",
            "agent_enabled": True,
        })
        assert resp.status_code == 200
        assert resp.json()["sync_mode"] == "intelligent_merge"
        assert resp.json()["agent_enabled"] is True

    def test_update_nonexistent_sub_account_404s(self, client):
        """Updating a non-existent sub-account should 404."""
        resp = client.patch("/api/a-cal/sub-accounts/nonexistent", json={"name": "Nope"})
        assert resp.status_code == 404

    def test_delete_sub_account(self, client):
        """Deleting a sub-account should remove it and its providers."""
        create = client.post("/api/a-cal/sub-accounts", json={
            "name": "Delete Me",
            "kind": "calendar",
        })
        sub_id = create.json()["id"]
        client.post("/api/a-cal/providers", json={
            "sub_account_id": sub_id,
            "provider_type": "google_calendar",
            "provider_account_id": "test@test.com",
        })
        resp = client.delete(f"/api/a-cal/sub-accounts/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        subs = client.get("/api/a-cal/sub-accounts").json()
        assert sub_id not in [s["id"] for s in subs]


# --- provider connections --------------------------------------------------

class TestProviders:
    """Provider connection endpoints."""

    def test_list_providers_by_sub_account(self, client):
        """Listing providers should filter by sub_account_id."""
        resp = client.get("/api/a-cal/providers", params={"sub_account_id": "sa-work-google"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider_type"] == "google_calendar"

    def test_list_all_providers(self, client):
        """The /providers/all endpoint should return all connections."""
        resp = client.get("/api/a-cal/providers/all")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 4

    def test_create_provider(self, client):
        """Creating a provider connection should return it with pending status."""
        resp = client.post("/api/a-cal/providers", json={
            "sub_account_id": "sa-personal",
            "provider_type": "outlook_calendar",
            "provider_account_id": "test@outlook.com",
            "display_name": "Outlook",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_type"] == "outlook_calendar"
        assert data["status"] == "pending"
        assert data["id"].startswith("pc-")


# --- unified calendar ------------------------------------------------------

class TestUnifiedCalendar:
    """Unified calendar timeline endpoint."""

    def test_unified_returns_events(self, client):
        """The unified calendar should return seeded events within the window."""
        resp = client.get("/api/a-cal/calendar/unified", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        titles = [e["title"] for e in data]
        assert "Team Standup" in titles

    def test_unified_respects_days_param(self, client):
        """A 1-day window should return fewer events than a 7-day window."""
        week = client.get("/api/a-cal/calendar/unified", params={"days": 7}).json()
        day = client.get("/api/a-cal/calendar/unified", params={"days": 1}).json()
        assert len(day) <= len(week)

    def test_unified_event_has_required_fields(self, client):
        """Each event should have the required UnifiedEvent fields."""
        resp = client.get("/api/a-cal/calendar/unified", params={"days": 7})
        for evt in resp.json():
            assert "provider_event_id" in evt
            assert "provider_type" in evt
            assert "title" in evt
            assert "start" in evt
            assert "end" in evt
            assert "source_sub_account_id" in evt


# --- sync rules ------------------------------------------------------------

class TestSyncRules:
    """Sync rule endpoints."""

    def test_create_sync_rule(self, client):
        """Creating a sync rule should return an ID."""
        resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": "sa-work-google",
            "rule_type": "exclude",
            "field": "title",
            "pattern": "standup",
        })
        assert resp.status_code == 200
        assert "id" in resp.json()

    def test_list_sync_rules_by_sub_account(self, client):
        """Listing sync rules should filter by sub_account_id."""
        client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": "sa-personal",
            "rule_type": "include",
            "field": "title",
            "pattern": "*",
        })
        resp = client.get("/api/a-cal/sync-rules", params={"sub_account_id": "sa-personal"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["sub_account_id"] == "sa-personal" for r in data)

    def test_seeded_sync_rule_exists(self, client):
        """The seeded sync rule for the work sub-account should be present."""
        resp = client.get("/api/a-cal/sync-rules", params={"sub_account_id": "sa-work-google"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
