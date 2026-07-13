"""Tests for self-model integration with the standalone schedule response.

Verifies that self-model facts about energy patterns, meeting preferences,
and busy times are used to:
  - Rank free slots by alignment with user preferences
  - Pick optimal times when creating events without a specified time
  - Add contextual notes to responses explaining why slots were chosen
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from a_cal.agents.standalone_responses import (
    _extract_self_model_prefs,
    _rank_slots_by_prefs,
    generate_schedule_response,
    _handle_create_event,
)
from a_cal.self_model.types import FactCategory, PrivacyTier, SelfModelFact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fact(
    category: FactCategory,
    content: str,
    confidence: float = 0.8,
) -> SelfModelFact:
    """Create a self-model fact for testing."""
    return SelfModelFact(
        id=f"fact-{category.value}-{hash(content) % 10000}",
        category=category.value,
        content=content,
        depth="attention_intent",
        privacy_tier=PrivacyTier.TIER_LOCAL.value,
        confidence=confidence,
        provenance="test",
        source_event_ids=[],
    )


def _make_mock_self_model(facts: list[SelfModelFact]) -> Any:
    """Create a mock self-model with the given facts."""
    sm = MagicMock()
    sm.store.all_active.return_value = facts
    sm.store.list_all.return_value = facts
    return sm


def _make_event(
    title: str,
    start: datetime,
    duration_min: int = 60,
) -> dict[str, Any]:
    """Create an event dict matching the store format."""
    return {
        "title": title,
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=duration_min)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Tests — _extract_self_model_prefs
# ---------------------------------------------------------------------------

class TestExtractSelfModelPrefs:
    """Test the self-model preference extraction helper."""

    def test_no_self_model(self):
        """Returns empty dict when no self-model is provided."""
        prefs = _extract_self_model_prefs(None)
        assert prefs == {}

    def test_no_facts(self):
        """Returns empty dict when self-model has no facts."""
        sm = _make_mock_self_model([])
        prefs = _extract_self_model_prefs(sm)
        assert prefs == {}

    def test_morning_person(self):
        """Detects morning person energy pattern."""
        sm = _make_mock_self_model([
            _make_fact(FactCategory.ENERGY_PATTERNS, "User is a morning person, most productive 8-11am"),
        ])
        prefs = _extract_self_model_prefs(sm)
        assert prefs["pref_start"] == 8
        assert prefs["pref_end"] == 12
        assert "morning person" in prefs["energy_note"]

    def test_afternoon_peak(self):
        """Detects afternoon energy peak."""
        sm = _make_mock_self_model([
            _make_fact(FactCategory.ENERGY_PATTERNS, "Energy peaks in the afternoon"),
        ])
        prefs = _extract_self_model_prefs(sm)
        assert prefs["pref_start"] == 13
        assert prefs["pref_end"] == 17
        assert "afternoon" in prefs["energy_note"]

    def test_meeting_prefs_avoid_morning(self):
        """Detects meeting preference to avoid mornings."""
        sm = _make_mock_self_model([
            _make_fact(FactCategory.MEETING_PREFS, "Prefers no morning meetings"),
        ])
        prefs = _extract_self_model_prefs(sm)
        assert prefs["pref_start"] == 13
        assert "meeting_note" in prefs

    def test_multiple_facts(self):
        """Combines multiple fact types."""
        sm = _make_mock_self_model([
            _make_fact(FactCategory.ENERGY_PATTERNS, "Morning person, peaks at 9am"),
            _make_fact(FactCategory.MEETING_PREFS, "Prefers short meetings under 30 min"),
        ])
        prefs = _extract_self_model_prefs(sm)
        assert prefs["pref_start"] == 8
        assert "energy_note" in prefs
        assert "meeting_note" in prefs

    def test_store_error_graceful(self):
        """Handles store errors gracefully."""
        sm = MagicMock()
        sm.store.all_active.side_effect = RuntimeError("store unavailable")
        prefs = _extract_self_model_prefs(sm)
        assert prefs == {}


# ---------------------------------------------------------------------------
# Tests — _rank_slots_by_prefs
# ---------------------------------------------------------------------------

class TestRankSlotsByPrefs:
    """Test slot ranking by self-model preferences."""

    def test_no_prefs_returns_original(self):
        """Returns original order when no preferences."""
        slots = [
            {"start": "2025-07-15T14:00:00", "end": "2025-07-15T15:00:00"},
            {"start": "2025-07-15T09:00:00", "end": "2025-07-15T10:00:00"},
        ]
        ranked = _rank_slots_by_prefs(slots, {})
        assert ranked == slots

    def test_morning_pref_ranks_morning_first(self):
        """Morning preference puts morning slots first."""
        slots = [
            {"start": "2025-07-15T14:00:00", "end": "2025-07-15T15:00:00"},
            {"start": "2025-07-15T09:00:00", "end": "2025-07-15T10:00:00"},
            {"start": "2025-07-15T11:00:00", "end": "2025-07-15T12:00:00"},
        ]
        prefs = {"pref_start": 8, "pref_end": 12}
        ranked = _rank_slots_by_prefs(slots, prefs)
        # 9am (closest to 10am center) should be first
        assert ranked[0]["start"] == "2025-07-15T09:00:00"
        assert ranked[1]["start"] == "2025-07-15T11:00:00"
        assert ranked[2]["start"] == "2025-07-15T14:00:00"


# ---------------------------------------------------------------------------
# Tests — generate_schedule_response with self-model
# ---------------------------------------------------------------------------

class TestScheduleWithSelfModel:
    """Test that schedule responses use self-model context."""

    def test_find_slots_uses_self_model_prefs(self):
        """Slot finding uses self-model preferred hours when no time specified."""
        now = datetime(2025, 7, 10, 10, 0, tzinfo=UTC)
        # Create events that fill the afternoon but leave morning open
        events = [
            _make_event("Afternoon meeting", datetime(2025, 7, 11, 13, 0), 120),
            _make_event("Late call", datetime(2025, 7, 11, 16, 0), 60),
        ]
        sm = _make_mock_self_model([
            _make_fact(FactCategory.ENERGY_PATTERNS, "User is a morning person"),
        ])

        result = generate_schedule_response(
            "find me a 30 minute slot tomorrow",
            events,
            now,
            self_model=sm,
        )

        assert result["actions"][0]["type"] == "find_slots"
        assert result["actions"][0].get("self_model_ranked") is True
        # The response should mention the self-model context
        assert "morning person" in result["response"]

    def test_find_slots_without_self_model(self):
        """Slot finding works normally without self-model."""
        now = datetime(2025, 7, 10, 10, 0, tzinfo=UTC)
        events = []

        result = generate_schedule_response(
            "find me a 30 minute slot tomorrow",
            events,
            now,
        )

        assert result["actions"][0]["type"] == "find_slots"
        assert result["actions"][0].get("self_model_ranked") is False

    def test_create_event_uses_self_model_time(self):
        """Event creation uses self-model preferred time when no time specified."""
        now = datetime(2025, 7, 10, 10, 0, tzinfo=UTC)
        events: list[dict[str, Any]] = []
        sm = _make_mock_self_model([
            _make_fact(FactCategory.ENERGY_PATTERNS, "Morning person, peaks at 8am"),
        ])

        result = _handle_create_event(
            "schedule a meeting tomorrow",
            events,
            now,
            event_store=None,
            self_model_prefs=_extract_self_model_prefs(sm),
        )

        # Should use 8 AM (self-model pref) instead of default 9 AM
        assert result["actions"][0]["type"] == "create_event"
        assert "08:00 AM" in result["response"]
        # Should mention why this time was chosen
        assert "morning person" in result["response"]

    def test_create_event_with_specific_time_overrides_self_model(self):
        """Explicit time in message overrides self-model preferences."""
        now = datetime(2025, 7, 10, 10, 0, tzinfo=UTC)
        events: list[dict[str, Any]] = []
        sm_prefs = {"pref_start": 8, "energy_note": "you\'re a morning person"}

        result = _handle_create_event(
            "schedule a meeting tomorrow at 2pm",
            events,
            now,
            event_store=None,
            self_model_prefs=sm_prefs,
        )

        # Should use 2 PM (explicit) not 8 AM (self-model)
        assert "02:00 PM" in result["response"]
        # Should NOT add self-model note since user specified time
        assert "morning person" not in result["response"]
