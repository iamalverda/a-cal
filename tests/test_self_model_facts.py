"""Tests for self-model facts API endpoints (transparency view)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api import agent_routes
from a_cal.api.agent_routes import router as agent_router
from a_cal.self_model.store import SelfModelStore
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
