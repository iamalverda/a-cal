"""Tests for the hybrid LLM+standalone conductor mode.

Verifies that when an LLM service is connected, the conductor:
  - Still performs real calendar operations (via the standalone response generator)
  - Returns the LLM's natural language response
  - Includes structured actions from the standalone generator
  - Falls back to the standalone response when the LLM fails
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.agents.conductor import ACalConductor
from a_cal.db.store import PersistentStore


@pytest.fixture
def event_store():
    """Fresh in-memory store for each test."""
    return PersistentStore(in_memory=True)


@pytest.fixture
def mock_llm():
    """Mock LLM service that returns a canned response."""
    llm = AsyncMock()
    llm.generate_response = AsyncMock(return_value="I've handled that for you with AI-powered reasoning.")
    return llm


def _make_conductor(llm_service=None, event_store=None):
    """Create a conductor with optional LLM service."""
    return ACalConductor(
        user_id="test-user",
        llm_service=llm_service,
        event_store=event_store,
    )


class TestHybridMode:
    """Test that hybrid mode combines LLM responses with real actions."""

    @pytest.mark.asyncio
    async def test_hybrid_performs_calendar_operations(self, event_store, mock_llm):
        """When LLM is connected, calendar operations still happen."""
        conductor = _make_conductor(llm_service=mock_llm, event_store=event_store)
        result = await conductor.handle("create a meeting called Team Review at 2pm tomorrow")

        # The LLM response should be returned
        assert result["standalone"] is False
        assert "AI-powered reasoning" in result["response"]
        # But actions should still be present (from the standalone generator)
        assert len(result["actions"]) > 0
        assert result["actions"][0]["type"] == "create_event"
        # And the event should actually be created in the store
        events = event_store.get_all_events()
        assert any(e["title"] == "Team Review" for e in events)

    @pytest.mark.asyncio
    async def test_hybrid_falls_back_on_llm_error(self, event_store):
        """When the LLM fails, the standalone response is used as fallback."""
        failing_llm = AsyncMock()
        failing_llm.generate_response = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        conductor = _make_conductor(llm_service=failing_llm, event_store=event_store)
        result = await conductor.handle("find me a free 30 minute slot tomorrow")

        # Should fall back to standalone response
        assert result["standalone"] is False
        assert "free" in result["response"].lower() or "slot" in result["response"].lower()
        assert len(result["actions"]) > 0

    @pytest.mark.asyncio
    async def test_hybrid_includes_actions_source(self, event_store, mock_llm):
        """Hybrid mode response includes actions_source field."""
        conductor = _make_conductor(llm_service=mock_llm, event_store=event_store)
        result = await conductor.handle("what's my schedule look like")

        assert result.get("actions_source") == "hybrid"

    @pytest.mark.asyncio
    async def test_hybrid_self_model_context_in_prompt(self, event_store, mock_llm):
        """Self-model context is included in the LLM prompt when available."""
        conductor = _make_conductor(llm_service=mock_llm, event_store=event_store)
        # Set up a mock self-model
        sm = MagicMock()
        sm.has_local_only_facts.return_value = False
        sm.settings.feed_into_agents = True
        sm.inject_into_prompt.return_value = "[Self-model: user prefers morning meetings]"
        conductor.self_model = sm

        await conductor.handle("find me a slot tomorrow")

        # Verify the LLM was called with self-model context in the prompt
        mock_llm.generate_response.assert_called_once()
        call_kwargs = mock_llm.generate_response.call_args
        prompt = call_kwargs.kwargs.get("prompt") or call_kwargs.args[0]
        assert "Self-model" in prompt or "morning" in prompt

    @pytest.mark.asyncio
    async def test_pure_standalone_no_llm(self, event_store):
        """Without an LLM, the conductor returns standalone responses."""
        conductor = _make_conductor(llm_service=None, event_store=event_store)
        result = await conductor.handle("find me a free slot tomorrow")

        assert result["standalone"] is True
        assert "actions_source" not in result
        assert len(result["actions"]) > 0

    @pytest.mark.asyncio
    async def test_hybrid_reschedule_actually_updates(self, event_store, mock_llm):
        """Hybrid mode actually reschedules events in the store."""
        # First create an event
        event_store.create_event({
            "title": "Standup",
            "start": datetime(2025, 7, 11, 9, 0).isoformat(),
            "end": datetime(2025, 7, 11, 9, 30).isoformat(),
            "provider_type": "local",
        })

        conductor = _make_conductor(llm_service=mock_llm, event_store=event_store)
        result = await conductor.handle("reschedule Standup to tomorrow at 3pm")

        # LLM response should be returned
        assert "AI-powered reasoning" in result["response"]
        # And the event should be updated — "3pm tomorrow" is interpreted in
        # the user's local timezone and stored as UTC, so convert back to
        # local time to verify the hour is 3 PM (15).
        events = event_store.get_all_events()
        standup = next(e for e in events if e["title"] == "Standup")
        start = datetime.fromisoformat(standup["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        local_start = start.astimezone()
        assert local_start.hour == 15  # 3 PM local
