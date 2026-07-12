"""Tests for the standalone LLM service and LLM-enabled conductor.

These tests verify:
  - Model routing resolves correctly (privacy-forced local tasks)
  - The LLM service handles unreachable providers gracefully
  - The llm-enabled toggle controls whether the conductor dispatches to a real LLM
  - API key and Ollama status endpoints work
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.agents.llm_service import StandaloneLLMService, LLMResponse
from a_cal.settings.model_routing import ModelRoutingConfig, ModelProvider


# --- LLM service unit tests ------------------------------------------------

class TestStandaloneLLMService:
    """StandaloneLLMService routing and error handling."""

    def test_routing_resolves_privacy_tasks_to_local(self):
        """Email, self_model, and negotiate tasks are always forced local."""
        svc = StandaloneLLMService(routing=ModelRoutingConfig(
            global_provider=ModelProvider.OPENAI.value,
            global_model="gpt-4o",
        ))
        resolved = svc.routing.resolve_model("email")
        assert resolved["provider"] == ModelProvider.OLLAMA.value
        assert resolved["forced_local"] == "true"

    def test_routing_resolves_chat_to_global(self):
        """Non-privacy tasks use the global provider."""
        svc = StandaloneLLMService(routing=ModelRoutingConfig(
            global_provider=ModelProvider.ANTHROPIC.value,
            global_model="claude-sonnet-4",
        ))
        resolved = svc.routing.resolve_model("chat")
        assert resolved["provider"] == ModelProvider.ANTHROPIC.value
        assert resolved["model"] == "claude-sonnet-4"

    def test_routing_resolves_per_task_override(self):
        """Per-task overrides take precedence over global for non-privacy tasks."""
        svc = StandaloneLLMService(routing=ModelRoutingConfig(
            global_provider=ModelProvider.OPENAI.value,
            global_model="gpt-4o",
            per_task_overrides={"sync": "groq:llama-3.1-8b-instant"},
        ))
        resolved = svc.routing.resolve_model("sync")
        assert resolved["provider"] == "groq"
        assert resolved["model"] == "llama-3.1-8b-instant"

    @pytest.mark.asyncio
    async def test_generate_response_returns_error_on_unreachable(self):
        """If the provider is unreachable, returns an error string (never raises)."""
        svc = StandaloneLLMService(
            routing=ModelRoutingConfig(
                global_provider=ModelProvider.OLLAMA.value,
                global_model="nonexistent-model",
            ),
            ollama_url="http://127.0.0.1:1",  # unreachable port
        )
        result = await svc.generate_response(
            prompt="test", system_prompt="test", task="chat",
        )
        assert "couldn't reach" in result

    @pytest.mark.asyncio
    async def test_generate_response_missing_api_key(self):
        """Cloud provider without API key returns an error message."""
        svc = StandaloneLLMService(routing=ModelRoutingConfig(
            global_provider=ModelProvider.OPENAI.value,
            global_model="gpt-4o",
        ))
        result = await svc.generate_response(
            prompt="test", system_prompt="test", task="chat",
        )
        assert "couldn't reach" in result or "API key" in result


# --- LLM response dataclass ------------------------------------------------

class TestLLMResponse:
    """LLMResponse dataclass serialization."""

    def test_to_dict(self):
        resp = LLMResponse(text="hello", provider="ollama", model="gemma3:4b")
        d = resp.to_dict()
        assert d["text"] == "hello"
        assert d["provider"] == "ollama"
        assert d["model"] == "gemma3:4b"
        assert d["forced_local"] is False
        assert d["error"] is None


# --- API endpoint tests ----------------------------------------------------

@pytest.fixture
def client():
    """Test client with agent routes mounted."""
    app = FastAPI()
    app.include_router(__import__("a_cal.api.agent_routes", fromlist=["router"]).router)
    return TestClient(app)


class TestLLMEndpoints:
    """LLM enable/disable and Ollama status endpoints."""

    def test_llm_disabled_by_default(self, client):
        """LLM is disabled by default (routing-only mode)."""
        resp = client.get("/api/a-cal/settings/llm-enabled")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_enable_llm(self, client):
        """Can enable LLM mode."""
        resp = client.post("/api/a-cal/settings/llm-enabled", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        # Verify it persists
        resp2 = client.get("/api/a-cal/settings/llm-enabled")
        assert resp2.json()["enabled"] is True

    def test_disable_llm(self, client):
        """Can disable LLM mode."""
        client.post("/api/a-cal/settings/llm-enabled", json={"enabled": True})
        resp = client.post("/api/a-cal/settings/llm-enabled", json={"enabled": False})
        assert resp.json()["enabled"] is False

    def test_ollama_status(self, client):
        """Ollama status endpoint returns available flag and model list."""
        resp = client.get("/api/a-cal/settings/ollama-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert "models" in data
        assert isinstance(data["models"], list)

    def test_api_keys_masked_on_get(self, client):
        """API key values are never returned — only which providers have keys."""
        client.post("/api/a-cal/settings/api-keys", json={
            "keys": {"openai": "sk-test-12345"},
        })
        resp = client.get("/api/a-cal/settings/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert "openai" in data
        assert data["openai"] == "***"
        assert "sk-test-12345" not in str(data)


class TestConductorWithLLM:
    """Conductor behavior with LLM enabled vs disabled."""

    def test_conductor_routing_only_when_disabled(self, client):
        """When LLM is disabled, conductor returns rule-based response (not None)."""
        client.post("/api/a-cal/settings/llm-enabled", json={"enabled": False})
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hello"})
        data = resp.json()
        assert data["standalone"] is True
        assert data["response"] is not None  # real rule-based response
        assert "routing" in data
        assert "actions" in data


# --- Ollama call parameters tests ------------------------------------------

class TestOllamaCallParameters:
    """Verify Ollama API call includes correct parameters for quality + speed."""

    def test_ollama_options_include_temperature(self):
        """Ollama call should include temperature:0.3 for deterministic responses."""
        import inspect
        from a_cal.agents.llm_service import StandaloneLLMService

        # Inspect the _call_ollama method source to verify temperature is set
        source = inspect.getsource(StandaloneLLMService._call_ollama)
        assert "temperature" in source, (
            "Ollama call should set temperature for deterministic responses"
        )
        assert "0.3" in source, "Temperature should be 0.3 for factual calendar responses"

    def test_ollama_options_include_num_ctx(self):
        """Ollama call should limit context window to 8192 for speed."""
        import inspect
        from a_cal.agents.llm_service import StandaloneLLMService

        source = inspect.getsource(StandaloneLLMService._call_ollama)
        assert "num_ctx" in source
        assert "8192" in source

    def test_ollama_options_include_keep_alive(self):
        """Ollama call should set keep_alive to keep model in memory."""
        import inspect
        from a_cal.agents.llm_service import StandaloneLLMService

        source = inspect.getsource(StandaloneLLMService._call_ollama)
        assert "keep_alive" in source


# --- Conductor anti-hallucination tests ------------------------------------

class TestConductorAntiHallucination:
    """Verify the conductor's hybrid mode includes anti-hallucination directives."""

    def test_conductor_prompt_includes_ground_rules(self):
        """Conductor's hybrid mode system prompt should include anti-hallucination directives."""
        import inspect
        from a_cal.agents.conductor import ACalConductor

        source = inspect.getsource(ACalConductor.handle)
        assert "GROUND RULES" in source or "ground truth" in source, (
            "Conductor hybrid mode should include anti-hallucination directives"
        )
        assert "invent" in source or "hallucinate" in source or "NOT invent" in source, (
            "Conductor should explicitly tell the LLM not to invent events"
        )
