"""Tests for the sync rule evaluator and the sub-account sync engine.

These run WITHOUT atom's database — they use an in-memory mock provider so the
core sync logic is verified independently of any provider integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from typing import List, Optional

import pytest

from a_cal.providers.base import CalendarEventDTO, CalendarProvider, SyncPage
from a_cal.sync.engine import SubAccountSyncEngine
from a_cal.sync.rules import evaluate_rules


def _ev(title: str, start: datetime, sub: str = "sub-1", cal: str = "primary") -> CalendarEventDTO:
    return CalendarEventDTO(
        provider_event_id=f"{title}-1",
        provider_type="mock",
        title=title,
        start=start,
        end=start + timedelta(hours=1),
        calendar_id=cal,
        source_sub_account_id=sub,
    )


class MockProvider(CalendarProvider):
    def __init__(self, events: list[CalendarEventDTO]) -> None:
        self._events = events

    async def list_events(self, start, end, calendar_id=None):
        return [e for e in self._events if start <= e.start < end]

    async def list_changes(self, since_cursor, start, end):
        return SyncPage(events=await self.list_events(start, end), next_cursor=None, has_more=False)

    async def create_event(self, event):
        return event

    async def update_event(self, event):
        return event

    async def cancel_event(self, provider_event_id, calendar_id=None):
        pass


NOW = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


# --- rule evaluation -------------------------------------------------------

def test_exclude_rule_drops_event():
    ev = _ev("Confidential 1:1", NOW)
    rules = [{"rule_type": "exclude", "field": "keyword", "pattern": "Confidential", "priority": 0, "is_active": True}]
    outcome = evaluate_rules(ev, rules)
    assert outcome.included is False


def test_include_rule_keeps_event():
    ev = _ev("Team Standup", NOW)
    rules = [{"rule_type": "include", "field": "keyword", "pattern": "Team", "priority": 0, "is_active": True}]
    outcome = evaluate_rules(ev, rules)
    assert outcome.included is True


def test_transform_tag_rule_adds_tag():
    ev = _ev("Sprint Review", NOW)
    rules = [{"rule_type": "transform", "field": "keyword", "pattern": "Sprint", "action": {"tag": "work"}, "priority": 0, "is_active": True}]
    outcome = evaluate_rules(ev, rules)
    assert outcome.transformed_event is not None
    assert "work" in outcome.transformed_event.metadata["tags"]


def test_agent_rule_flags_review():
    ev = _ev("Maybe Reschedule Me", NOW)
    rules = [{"rule_type": "agent", "field": "keyword", "pattern": "Maybe", "priority": 0, "is_active": True}]
    outcome = evaluate_rules(ev, rules)
    assert outcome.agent_review is True


# --- engine modes ----------------------------------------------------------

@pytest.mark.asyncio
async def test_mirror_filter_default():
    events = [_ev("Standup", NOW), _ev("Confidential", NOW + timedelta(hours=2))]
    rules = [{"rule_type": "exclude", "field": "keyword", "pattern": "Confidential", "priority": 0, "is_active": True}]
    engine = SubAccountSyncEngine({"id": "sub-1", "sync_mode": "mirror_filter", "sync_rules": rules}, [MockProvider(events)])
    out = await engine.pull_window(NOW, NOW + timedelta(days=1))
    titles = [e.title for e in out]
    assert "Standup" in titles
    assert "Confidential" not in titles


@pytest.mark.asyncio
async def test_intelligent_merge_deduplicates():
    ev1 = _ev("Standup", NOW)
    ev2 = _ev("Standup", NOW + timedelta(minutes=1))  # near-duplicate
    engine = SubAccountSyncEngine({"id": "sub-1", "sync_mode": "intelligent_merge", "sync_rules": []}, [MockProvider([ev1, ev2])])
    out = await engine.pull_window(NOW, NOW + timedelta(days=1))
    standups = [e for e in out if e.title == "Standup"]
    assert len(standups) == 1  # deduplicated


@pytest.mark.asyncio
async def test_layered_federation_tags_readonly():
    events = [_ev("Work Event", NOW)]
    engine = SubAccountSyncEngine({"id": "sub-1", "sync_mode": "layered_federation", "sync_rules": []}, [MockProvider(events)])
    out = await engine.pull_window(NOW, NOW + timedelta(days=1))
    assert out
    assert out[0].metadata["federated"] is True
    assert out[0].metadata["read_only"] is True


@pytest.mark.asyncio
async def test_per_sub_agent_flags_agent_review():
    events = [_ev("Maybe Move This", NOW)]
    rules = [{"rule_type": "agent", "field": "keyword", "pattern": "Maybe", "priority": 0, "is_active": True}]
    engine = SubAccountSyncEngine({"id": "sub-1", "sync_mode": "per_sub_agent", "sync_rules": rules}, [MockProvider(events)])
    out = await engine.pull_window(NOW, NOW + timedelta(days=1))
    flagged = [e for e in out if e.metadata.get("agent_review")]
    assert len(flagged) == 1


def test_include_rule_excludes_non_matching():
    """When include rules exist, events that don't match any are excluded (whitelist)."""
    ev = _ev("Personal Lunch", NOW)
    rules = [{"rule_type": "include", "field": "keyword", "pattern": "Team", "priority": 0, "is_active": True}]
    outcome = evaluate_rules(ev, rules)
    assert outcome.included is False


def test_include_rule_whitelist_with_multiple_rules():
    """Multiple include rules: event must match at least one to be included."""
    ev_match = _ev("Team Standup", NOW)
    ev_no_match = _ev("Personal Lunch", NOW)
    rules = [
        {"rule_type": "include", "field": "keyword", "pattern": "Team", "priority": 0, "is_active": True},
        {"rule_type": "include", "field": "keyword", "pattern": "Sprint", "priority": 1, "is_active": True},
    ]
    assert evaluate_rules(ev_match, rules).included is True
    assert evaluate_rules(ev_no_match, rules).included is False


def test_exclude_overrides_include():
    """An exclude match always wins over an include match."""
    ev = _ev("Confidential Team Meeting", NOW)
    rules = [
        {"rule_type": "include", "field": "keyword", "pattern": "Team", "priority": 0, "is_active": True},
        {"rule_type": "exclude", "field": "keyword", "pattern": "Confidential", "priority": 1, "is_active": True},
    ]
    outcome = evaluate_rules(ev, rules)
    assert outcome.included is False


def test_no_rules_includes_everything():
    """With no rules, all events are included (default behavior)."""
    ev = _ev("Anything", NOW)
    outcome = evaluate_rules(ev, [])
    assert outcome.included is True


@pytest.mark.asyncio
async def test_mirror_filter_with_include_whitelist():
    """Mirror+filter with include rules acts as a whitelist on the main calendar."""
    events = [_ev("Team Standup", NOW), _ev("Personal Lunch", NOW + timedelta(hours=1))]
    rules = [{"rule_type": "include", "field": "keyword", "pattern": "Team", "priority": 0, "is_active": True}]
    engine = SubAccountSyncEngine({"id": "sub-1", "sync_mode": "mirror_filter", "sync_rules": rules}, [MockProvider(events)])
    out = await engine.pull_window(NOW, NOW + timedelta(days=1))
    titles = [e.title for e in out]
    assert "Team Standup" in titles
    assert "Personal Lunch" not in titles
