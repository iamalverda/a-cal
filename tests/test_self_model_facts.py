"""Tests for self-model facts API endpoints (transparency view)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api import agent_routes
from a_cal.api.agent_routes import router as agent_router
from a_cal.self_model.store import SelfModelStore
from a_cal.self_model.settings import SelfModelSettings
from a_cal.self_model.types import SelfModelFact, FactCategory, SelfModelDepth, PrivacyTier


@pytest.fixture(autouse=True)
def _set_sm_data_dir():
    """Point the API's self-model store at the test data dir."""
    agent_routes._sm_data_dir = "/tmp/a-cal-test-sm"
    yield
    agent_routes._sm_data_dir = None


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(agent_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def store_with_facts():
    """Create a self-model store with test facts."""
    store = SelfModelStore(user_id="local-dev-user", data_dir="/tmp/a-cal-test-sm")

    # Clean any existing facts
    store.clear_all()

    store.upsert(SelfModelFact(
        id="fact-1",
        category=FactCategory.ENERGY_PATTERNS,
        content="User is most productive in the morning (8-11 AM)",
        depth=SelfModelDepth.ATTENTION_INTENT,
        privacy_tier=PrivacyTier.TIER_PATTERN,
        confidence=0.85,
        provenance="inferred_from_events",
    ))
    store.upsert(SelfModelFact(
        id="fact-2",
        category=FactCategory.MEETING_PREFS,
        content="Prefers 30-minute meetings over longer ones",
        depth=SelfModelDepth.ATTENTION_INTENT,
        privacy_tier=PrivacyTier.TIER_PATTERN,
        confidence=0.72,
        provenance="inferred_from_events",
    ))
    store.upsert(SelfModelFact(
        id="fact-3",
        category=FactCategory.GOALS,
        content="Working toward a promotion this quarter",
        depth=SelfModelDepth.LONGITUDINAL_IDENTITY,
        privacy_tier=PrivacyTier.TIER_LOCAL,
        confidence=0.6,
        provenance="user_stated",
    ))
    yield store
    store.clear_all()


class TestSelfModelFactsAPI:
    """Test the self-model facts transparency endpoints."""

    def test_list_facts(self, client, store_with_facts):
        """GET /self-model/facts returns all active facts."""
        resp = client.get("/api/a-cal/self-model/facts")
        assert resp.status_code == 200
        facts = resp.json()
        assert len(facts) == 3
        # Sorted by confidence (highest first)
        assert facts[0]["confidence"] >= facts[1]["confidence"]
        assert facts[0]["id"] == "fact-1"

    def test_list_facts_by_category(self, client, store_with_facts):
        """GET /self-model/facts?category=energy_patterns filters by category."""
        resp = client.get("/api/a-cal/self-model/facts?category=energy_patterns")
        assert resp.status_code == 200
        facts = resp.json()
        assert len(facts) == 1
        assert facts[0]["category"] == "energy_patterns"

    def test_search_facts(self, client, store_with_facts):
        """GET /self-model/facts/search?q=morning finds matching facts."""
        resp = client.get("/api/a-cal/self-model/facts/search?q=morning&limit=5")
        assert resp.status_code == 200
        facts = resp.json()
        assert len(facts) >= 1
        assert any("morning" in f["content"].lower() for f in facts)

    def test_delete_fact(self, client, store_with_facts):
        """DELETE /self-model/facts/{id} soft-deletes a fact."""
        resp = client.delete("/api/a-cal/self-model/facts/fact-2")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone from the active list
        resp = client.get("/api/a-cal/self-model/facts")
        facts = resp.json()
        assert len(facts) == 2
        assert all(f["id"] != "fact-2" for f in facts)

    def test_delete_nonexistent_fact_404s(self, client, store_with_facts):
        """DELETE /self-model/facts/{bad_id} returns 404."""
        resp = client.delete("/api/a-cal/self-model/facts/nonexistent")
        assert resp.status_code == 404

    def test_clear_all_facts(self, client, store_with_facts):
        """DELETE /self-model/facts clears all facts."""
        resp = client.delete("/api/a-cal/self-model/facts")
        assert resp.status_code == 200
        assert resp.json()["facts_removed"] == 3

        # Verify all gone
        resp = client.get("/api/a-cal/self-model/facts")
        assert len(resp.json()) == 0

    def test_edit_fact(self, client, store_with_facts):
        """PATCH /self-model/facts/{id} edits fact content."""
        resp = client.patch(
            "/api/a-cal/self-model/facts/fact-1",
            json={"content": "User is most productive in the afternoon (1-4 PM)"},
        )
        assert resp.status_code == 200
        fact = resp.json()
        assert fact["content"] == "User is most productive in the afternoon (1-4 PM)"
        assert fact["confidence"] == 1.0
        assert "user-corrected" in fact["provenance"]

    def test_export_facts(self, client, store_with_facts):
        """GET /self-model/export returns all facts as a blob."""
        resp = client.get("/api/a-cal/self-model/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fact_count"] == 3
        assert len(data["facts"]) == 3
        assert data["user_id"] == "local-dev-user"


class TestProactiveSuggestionsAPI:
    """Test the GET /self-model/suggestions endpoint."""

    @pytest.fixture(autouse=True)
    def _reset_sm_settings(self):
        """Reset self-model settings to defaults after each test."""
        yield
        # Reset to defaults so other test files aren't affected
        from a_cal.api.agent_routes import _store, _current_user_id
        _store.set_self_model_settings(
            _current_user_id(),
            SelfModelSettings(),
        )

    def test_suggestions_empty_when_proactive_disabled(self, client, store_with_facts):
        """Returns empty list when proactive suggestions are disabled (default)."""
        resp = client.get("/api/a-cal/self-model/suggestions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_suggestions_returned_when_enabled(self, client, store_with_facts):
        """Returns ranked suggestions when proactive is enabled."""
        # Enable proactive suggestions + feed_into_proactive
        client.post("/api/a-cal/settings/self-model", json={
            "depth": "attention_intent",
            "enabled_categories": {},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": True,
            "feed_into_proactive": True,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })

        resp = client.get("/api/a-cal/self-model/suggestions")
        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) > 0
        assert all("fact_id" in s for s in suggestions)
        assert all("content" in s for s in suggestions)
        assert all("priority" in s for s in suggestions)
        assert all("confidence" in s for s in suggestions)

    def test_suggestions_ranked_by_priority(self, client, store_with_facts):
        """Longitudinal identity facts rank higher than attention/pattern facts."""
        client.post("/api/a-cal/settings/self-model", json={
            "depth": "longitudinal_identity",
            "enabled_categories": {},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": True,
            "feed_into_proactive": True,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })

        resp = client.get("/api/a-cal/self-model/suggestions")
        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) == 3

        # fact-3 is longitudinal_identity (priority 3), should be first
        assert suggestions[0]["fact_id"] == "fact-3"
        assert suggestions[0]["priority"] == 3

    def test_suggestions_limit_parameter(self, client, store_with_facts):
        """The limit parameter caps the number of suggestions."""
        client.post("/api/a-cal/settings/self-model", json={
            "depth": "longitudinal_identity",
            "enabled_categories": {},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": True,
            "feed_into_proactive": True,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })

        resp = client.get("/api/a-cal/self-model/suggestions?limit=2")
        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) == 2

    def test_suggestions_empty_when_no_facts(self, client):
        """Returns empty list when proactive is enabled but no facts exist."""
        # Clear any existing facts
        store = SelfModelStore(user_id="local-dev-user", data_dir="/tmp/a-cal-test-sm")
        store.clear_all()

        client.post("/api/a-cal/settings/self-model", json={
            "depth": "attention_intent",
            "enabled_categories": {},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": True,
            "feed_into_proactive": True,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })

        resp = client.get("/api/a-cal/self-model/suggestions")
        assert resp.status_code == 200
        assert resp.json() == []
