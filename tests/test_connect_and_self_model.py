"""Tests for natural-language account connection and self-model extraction.

Covers:
  - _parse_connect_request parsing various NL patterns
  - generate_sync_response creating sub-accounts + providers via event_store
  - Sync trigger endpoint feeding events to the self-model extractor
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.agents.standalone_responses import (
    _parse_connect_request,
    generate_sync_response,
    generate_standalone_response,
)
from a_cal.agents.conductor import ACalConductor, IntentType
from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.db.store import PersistentStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(standalone_data_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def fresh_store():
    return PersistentStore()


# ---------------------------------------------------------------------------
# NL connect request parsing
# ---------------------------------------------------------------------------

class TestParseConnectRequest:
    """Test _parse_connect_request with various natural language patterns."""

    def test_single_provider(self):
        result = _parse_connect_request("connect my work Google")
        assert len(result) == 1
        assert result[0]["sub_account_name"] == "Work"
        assert result[0]["provider_type"] == "google_calendar"

    def test_multiple_providers_with_and(self):
        result = _parse_connect_request("connect my work google and personal outlook")
        assert len(result) == 2
        assert result[0]["sub_account_name"] == "Work"
        assert result[0]["provider_type"] == "google_calendar"
        assert result[1]["sub_account_name"] == "Personal"
        assert result[1]["provider_type"] == "outlook_calendar"

    def test_three_providers(self):
        result = _parse_connect_request(
            "connect my work google and personal gmail and home outlook"
        )
        assert len(result) == 3
        assert result[2]["sub_account_name"] == "Home"
        assert result[2]["provider_type"] == "outlook_calendar"

    def test_link_verb(self):
        result = _parse_connect_request("link my personal Gmail")
        assert len(result) == 1
        assert result[0]["sub_account_name"] == "Personal"
        assert result[0]["provider_type"] == "gmail"

    def test_add_verb(self):
        result = _parse_connect_request("add my work Google Calendar")
        assert len(result) == 1
        assert result[0]["sub_account_name"] == "Work"
        assert result[0]["provider_type"] == "google_calendar"

    def test_caldav(self):
        result = _parse_connect_request("connect my home caldav")
        assert len(result) == 1
        assert result[0]["sub_account_name"] == "Home"
        assert result[0]["provider_type"] == "caldav"

    def test_imap_smtp(self):
        result = _parse_connect_request("connect my work imap")
        assert len(result) == 1
        assert result[0]["provider_type"] == "imap_smtp"

    def test_no_provider_mentioned(self):
        result = _parse_connect_request("connect my calendar")
        assert len(result) == 0

    def test_no_connect_keyword(self):
        result = _parse_connect_request("what events do I have today?")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# generate_sync_response with event_store
# ---------------------------------------------------------------------------

class TestSyncResponseWithStore:
    """Test that generate_sync_response creates sub-accounts and providers."""

    def test_creates_sub_account_and_provider(self, fresh_store):
        """'connect my work Google' creates a sub-account + provider connection."""
        existing_subs = fresh_store.list_sub_accounts()
        result = generate_sync_response(
            "connect my work Google",
            providers=[],
            sub_accounts=existing_subs,
            event_store=fresh_store,
        )

        assert "created" in result["response"].lower() or "set things up" in result["response"].lower()
        actions = result["actions"]
        assert actions[0]["type"] == "connect_provider"
        assert actions[0]["status"] == "created"

        # Verify sub-account was created
        updated_subs = fresh_store.list_sub_accounts()
        new_subs = [s for s in updated_subs if s not in existing_subs]
        assert len(new_subs) >= 1
        work_sub = next(s for s in new_subs if s["name"] == "Work")
        assert work_sub["sync_mode"] == "mirror_filter"

        # Verify provider was created
        providers = fresh_store.list_providers(work_sub["id"])
        assert len(providers) >= 1
        assert providers[0]["provider_type"] == "google_calendar"
        assert providers[0]["status"] == "pending"

    def test_creates_multiple_providers(self, fresh_store):
        """'connect my work google and personal outlook' creates two sub-accounts."""
        result = generate_sync_response(
            "connect my work google and personal outlook",
            providers=[],
            sub_accounts=fresh_store.list_sub_accounts(),
            event_store=fresh_store,
        )

        assert result["actions"][0]["status"] == "created"

        # Verify both sub-accounts exist (may have been created by a prior test)
        all_subs = fresh_store.list_sub_accounts()
        names = {s["name"] for s in all_subs}
        assert "Work" in names
        assert "Personal" in names

        # Verify each has a provider connection
        work_sub = next(s for s in all_subs if s["name"] == "Work")
        personal_sub = next(s for s in all_subs if s["name"] == "Personal")
        work_providers = fresh_store.list_providers(work_sub["id"])
        personal_providers = fresh_store.list_providers(personal_sub["id"])
        assert any(p["provider_type"] == "google_calendar" for p in work_providers)
        assert any(p["provider_type"] == "outlook_calendar" for p in personal_providers)

    def test_reuses_existing_sub_account(self, fresh_store):
        """If a sub-account with the same name exists, reuse it."""
        # Create a sub-account first
        fresh_store.create_sub_account({
            "name": "Work",
            "kind": "calendar",
            "sync_mode": "mirror_filter",
        })
        existing = fresh_store.list_sub_accounts()
        existing_count = len(existing)

        result = generate_sync_response(
            "connect my work Google",
            providers=[],
            sub_accounts=existing,
            event_store=fresh_store,
        )

        # Should not create a new sub-account
        updated = fresh_store.list_sub_accounts()
        assert len(updated) == existing_count  # no new sub-account

        # But should create a provider
        work_sub = next(s for s in updated if s["name"] == "Work")
        providers = fresh_store.list_providers(work_sub["id"])
        assert len(providers) >= 1

    def test_oauth_guidance_in_response(self, fresh_store):
        """Response includes OAuth guidance for Google/Outlook/Gmail."""
        existing = fresh_store.list_sub_accounts()
        result = generate_sync_response(
            "connect my work Google",
            providers=[],
            sub_accounts=existing,
            event_store=fresh_store,
        )
        assert "authorize" in result["response"].lower() or "oauth" in result["response"].lower()

    def test_no_store_returns_parsed_info(self):
        """Without event_store, still parses and returns guidance."""
        result = generate_sync_response(
            "connect my work Google",
            providers=[],
            sub_accounts=[],
            event_store=None,
        )
        assert "Work" in result["response"]
        assert "Google" in result["response"]
        assert result["actions"][0]["status"] == "parsed_no_store"


# ---------------------------------------------------------------------------
# Conductor end-to-end: NL → account creation
# ---------------------------------------------------------------------------

class TestConductorConnectFlow:
    """Test that the conductor creates accounts from natural language."""

    async def test_conductor_creates_accounts(self, fresh_store):
        """Conductor dispatches 'connect my work Google' and creates accounts."""
        conductor = ACalConductor(
            user_id="local-dev-user",
            llm_service=None,
            event_store=fresh_store,
            provider_store=fresh_store,
        )

        result = await conductor.handle("connect my work Google")

        assert result["standalone"] is True
        assert "created" in result["response"].lower() or "set things up" in result["response"].lower()
        assert result["actions"][0]["type"] == "connect_provider"

        # Verify in the store
        subs = fresh_store.list_sub_accounts()
        work_sub = next((s for s in subs if s["name"] == "Work"), None)
        assert work_sub is not None

        providers = fresh_store.list_providers(work_sub["id"])
        assert len(providers) >= 1
        assert providers[0]["provider_type"] == "google_calendar"


# ---------------------------------------------------------------------------
# Sync trigger with self-model extraction
# ---------------------------------------------------------------------------

class TestSyncTriggerSelfModel:
    """Test that sync trigger feeds events to the self-model extractor."""

    def test_sync_returns_facts_learned_field(self, client):
        """POST /sync/trigger includes facts_learned in the response."""
        # Get a sub-account to sync
        resp = client.get("/api/a-cal/sub-accounts")
        subs = resp.json()
        if not subs:
            pytest.skip("No sub-accounts in test store")

        # Trigger sync
        resp = client.post("/api/a-cal/sync/trigger", json={
            "sub_account_id": subs[0]["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "facts_learned" in data
        assert isinstance(data["facts_learned"], int)
