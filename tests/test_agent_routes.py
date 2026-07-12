"""Tests for the agent and settings API endpoints.

These tests use FastAPI's TestClient against a standalone app that mounts
the A-Cal agent/settings router. No atom backend required — the endpoints
work in standalone mode.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.agent_routes import router as agent_router


@pytest.fixture
def client():
    """Test client with only the agent/settings routes mounted."""
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


# --- conductor chat --------------------------------------------------------

class TestConductorChat:
    """Conductor chat endpoint — intent classification and routing."""

    def test_chat_returns_routing_decision(self, client):
        """A simple chat message returns a routing decision with intent=chat."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] if "intent" in data else data["routing"]["intent"] == "chat"
        assert data["standalone"] is True
        assert data["response"] is not None  # real rule-based response in standalone

    def test_sync_keyword_routes_to_sync_agent(self, client):
        """Message with 'sync' keyword routes to sync specialist."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "sync all my providers"})
        data = resp.json()
        assert data["routing"]["intent"] == "sync"
        assert data["routing"]["specialist"] == "a_cal_sync_agent"

    def test_schedule_keyword_routes_to_schedule_agent(self, client):
        """Message with 'slot' keyword routes to schedule specialist."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "find a free slot tomorrow"})
        data = resp.json()
        assert data["routing"]["intent"] == "schedule"
        assert data["routing"]["specialist"] == "a_cal_schedule_agent"

    def test_email_keyword_routes_to_email_agent(self, client):
        """Email-related message routes to email specialist with force_local."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "check my inbox for invites"})
        data = resp.json()
        assert data["routing"]["intent"] == "email"
        assert data["routing"]["specialist"] == "a_cal_email_agent"
        assert data["routing"]["force_local"] is True

    def test_negotiate_keyword_routes_to_negotiate_agent(self, client):
        """Negotiation message routes to negotiate specialist."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "reschedule with the team"})
        data = resp.json()
        assert data["routing"]["intent"] == "schedule"  # 'reschedule' matches schedule first

    def test_response_has_timestamp(self, client):
        """Response includes an ISO timestamp."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hi"})
        data = resp.json()
        assert "timestamp" in data
        assert "T" in data["timestamp"]  # ISO format


# --- agents ----------------------------------------------------------------

class TestAgentsEndpoint:
    """Agent listing endpoint."""

    def test_list_agents_returns_six_agents(self, client):
        """Six built-in agents are returned (conductor + 5 specialists)."""
        resp = client.get("/api/a-cal/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 6

    def test_conductor_is_first(self, client):
        """Conductor agent appears first in the list."""
        resp = client.get("/api/a-cal/agents")
        agents = resp.json()
        assert agents[0]["name"] == "a_cal_conductor"

    def test_agent_has_required_fields(self, client):
        """Each agent spec has the fields the frontend expects."""
        resp = client.get("/api/a-cal/agents")
        agents = resp.json()
        for agent in agents:
            assert "name" in agent
            assert "display_name" in agent
            assert "description" in agent
            assert "tools" in agent
            assert "default_tier" in agent
            assert "can_negotiate" in agent
            assert "privacy_force_local" in agent
            assert "capabilities" in agent

    def test_email_agent_is_force_local(self, client):
        """Email agent has privacy_force_local=True."""
        resp = client.get("/api/a-cal/agents")
        agents = resp.json()
        email_agent = next(a for a in agents if a["name"] == "a_cal_email_agent")
        assert email_agent["privacy_force_local"] is True


# --- settings: mode --------------------------------------------------------

class TestModeSettings:
    """Skill mode get/set endpoints."""

    def test_default_mode_is_pro(self, client):
        """Default mode is Pro (power user, not overwhelming for beginners though)."""
        resp = client.get("/api/a-cal/settings/mode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "pro"
        assert data["display_name"] == "Pro"

    def test_set_mode_to_simple(self, client):
        """Switching to Simple mode returns Simple config."""
        resp = client.post("/api/a-cal/settings/mode", json={"mode": "simple"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "simple"
        assert data["display_name"] == "Simple"
        assert data["per_task_model_routing"] is False

    def test_set_mode_to_developer(self, client):
        """Switching to Developer mode enables developer features."""
        resp = client.post("/api/a-cal/settings/mode", json={"mode": "developer"})
        data = resp.json()
        assert data["mode"] == "developer"
        assert data["developer_studio"] is True
        assert data["api_sdk"] is True

    def test_mode_persistence(self, client):
        """Setting a mode persists for subsequent GET calls."""
        client.post("/api/a-cal/settings/mode", json={"mode": "simple"})
        resp = client.get("/api/a-cal/settings/mode")
        assert resp.json()["mode"] == "simple"

    def test_mode_config_has_visible_panels(self, client):
        """Mode config includes visible_panels list."""
        resp = client.get("/api/a-cal/settings/mode")
        data = resp.json()
        assert "visible_panels" in data
        assert "calendar" in data["visible_panels"]


# --- settings: model routing -----------------------------------------------

class TestModelRouting:
    """Model routing get/set endpoints."""

    def test_default_routing_is_local(self, client):
        """Default model routing uses Ollama (local)."""
        resp = client.get("/api/a-cal/settings/model-routing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["global_provider"] == "ollama"
        assert data["privacy_force_local"] is True

    def test_set_routing_to_openai(self, client):
        """Can switch global provider to OpenAI."""
        resp = client.post("/api/a-cal/settings/model-routing", json={
            "global_provider": "openai",
            "global_model": "gpt-4o",
            "per_task_overrides": {},
            "privacy_force_local": True,
        })
        data = resp.json()
        assert data["global_provider"] == "openai"
        assert data["global_model"] == "gpt-4o"

    def test_routing_persistence(self, client):
        """Setting routing persists for subsequent GET calls."""
        client.post("/api/a-cal/settings/model-routing", json={
            "global_provider": "anthropic",
            "global_model": "claude-sonnet-4",
            "per_task_overrides": {"sync": "ollama:llama3.2"},
            "privacy_force_local": True,
        })
        resp = client.get("/api/a-cal/settings/model-routing")
        data = resp.json()
        assert data["global_provider"] == "anthropic"
        assert data["per_task_overrides"]["sync"] == "ollama:llama3.2"


# --- settings: self-model --------------------------------------------------

class TestSelfModelSettings:
    """Self-model settings get/set endpoints."""

    def test_default_self_model_is_pattern_memory(self, client):
        """Default self-model depth is pattern_memory (conservative)."""
        resp = client.get("/api/a-cal/settings/self-model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == "pattern_memory"
        assert data["cloud_sync_enabled"] is False

    def test_set_depth_to_attention_intent(self, client):
        """Can escalate self-model depth to attention_intent."""
        resp = client.post("/api/a-cal/settings/self-model", json={
            "depth": "attention_intent",
            "enabled_categories": {"busy_times": True, "work_focus": True},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": True,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })
        data = resp.json()
        assert data["depth"] == "attention_intent"
        assert data["proactive_suggestions_enabled"] is True

    def test_self_model_persistence(self, client):
        """Setting self-model config persists for subsequent GET calls."""
        client.post("/api/a-cal/settings/self-model", json={
            "depth": "longitudinal_identity",
            "enabled_categories": {},
            "cloud_sync_enabled": False,
            "proactive_suggestions_enabled": False,
            "feed_into_calendar_view": True,
            "feed_into_agents": True,
        })
        resp = client.get("/api/a-cal/settings/self-model")
        assert resp.json()["depth"] == "longitudinal_identity"

    def test_cloud_sync_off_by_default(self, client):
        """Cloud sync is off by default (privacy-first)."""
        resp = client.get("/api/a-cal/settings/self-model")
        assert resp.json()["cloud_sync_enabled"] is False
