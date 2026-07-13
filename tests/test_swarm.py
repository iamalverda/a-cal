"""Tests for the federated swarm protocol and coordinator.

Covers negotiation initiation, the full run loop (all resolution paths),
conflict detection, audit trails, and edge cases. These run in standalone
mode (rule-based, no LLM) so they're deterministic and fast.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from types import SimpleNamespace

import pytest

from a_cal.swarm.protocol import (
    ConflictClaim,
    NegotiationMessage,
    NegotiationMessageType,
    NegotiationState,
    NegotiationStatus,
    SlotProposal,
    SubAccountPriority,
    SwarmNegotiation,
)
from a_cal.swarm.coordinator import SwarmCoordinator


# --- helpers -----------------------------------------------------------------

BASE = datetime(2026, 7, 16, 14, 0, tzinfo=UTC)


def _claim(
    sub: str,
    title: str,
    start: datetime = BASE,
    duration_hours: float = 1.0,
    priority: SubAccountPriority = SubAccountPriority.NORMAL,
    can_move: bool = True,
    reasoning: str = "",
) -> ConflictClaim:
    return ConflictClaim(
        sub_account_id=sub,
        event_id=f"{sub}-evt-1",
        event_title=title,
        slot_start=start,
        slot_end=start + timedelta(hours=duration_hours),
        priority=priority,
        can_move=can_move,
        reasoning=reasoning,
    )


def _event(title: str, sub: str, start: datetime, end: datetime):
    """Minimal event-like object for detect_conflicts."""
    return SimpleNamespace(
        title=title,
        source_sub_account_id=sub,
        start=start,
        end=end,
    )


# --- initiation tests --------------------------------------------------------

class TestInitiate:
    def test_creates_negotiation_with_two_claims(self):
        coord = SwarmCoordinator()
        a = _claim("work", "CEO 1:1", priority=SubAccountPriority.HIGH)
        b = _claim("personal", "Gym", priority=SubAccountPriority.LOW)
        neg = coord.initiate(a, b)

        assert neg.state == NegotiationState.PROBING
        assert len(neg.claims) == 2
        assert neg.claim_a is a
        assert neg.claim_b is b
        assert neg.status is None  # not yet resolved

    def test_logs_probe_messages_from_both_sides(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(_claim("work", "Meeting"), _claim("personal", "Gym"))

        probes = [m for m in neg.messages if m.message_type == NegotiationMessageType.PROBE]
        assert len(probes) == 2
        from_ids = {m.from_sub_account_id for m in probes}
        assert from_ids == {"work", "personal"}

    def test_stores_negotiation_for_retrieval(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(_claim("work", "M"), _claim("personal", "G"))
        retrieved = coord.get_negotiation(neg.id)
        assert retrieved is neg


# --- run loop tests ----------------------------------------------------------

class TestRunNegotiation:
    def test_higher_priority_wins(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "CEO 1:1", priority=SubAccountPriority.HIGH, can_move=False),
            _claim("personal", "Gym", priority=SubAccountPriority.LOW, can_move=True),
        )
        result = coord.run(neg)

        assert result["resolved"] is True
        assert result["escalated"] is False
        assert result["winner_sub_account_id"] == "work"
        assert result["loser_sub_account_id"] == "personal"
        assert neg.state == NegotiationState.RESOLVED

    def test_lower_priority_concedes_with_alternative(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "CEO 1:1", priority=SubAccountPriority.HIGH, can_move=False),
            _claim("personal", "Gym", priority=SubAccountPriority.LOW, can_move=True),
        )
        result = coord.run(neg)

        # The loser should get an alternative slot proposal.
        assert result["alternative_slot"] is not None
        assert result["alternative_slot"]["sub_account_id"] == "personal"

    def test_equal_priority_one_can_move(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "Standup", priority=SubAccountPriority.NORMAL, can_move=False),
            _claim("personal", "Lunch", priority=SubAccountPriority.NORMAL, can_move=True),
        )
        result = coord.run(neg)

        assert result["resolved"] is True
        assert result["winner_sub_account_id"] == "work"
        assert result["loser_sub_account_id"] == "personal"

    def test_equal_priority_both_can_move_accepts_proposal(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "Standup", priority=SubAccountPriority.NORMAL, can_move=True),
            _claim("personal", "Lunch", priority=SubAccountPriority.NORMAL, can_move=True),
        )
        result = coord.run(neg)

        # Should resolve via proposal + accept.
        assert result["resolved"] is True
        # claim_a wins (proposer), claim_b gets the alternative.
        assert result["winner_sub_account_id"] == "work"

    def test_neither_can_move_escalates(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "Board meeting", priority=SubAccountPriority.HIGH, can_move=False),
            _claim("personal", "Surgery", priority=SubAccountPriority.HIGH, can_move=False),
        )
        result = coord.run(neg)

        assert result["escalated"] is True
        assert result["resolved"] is False
        assert result["winner_sub_account_id"] is None
        assert neg.state == NegotiationState.ESCALATED

    def test_critical_beats_everything(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("personal", "Flight", priority=SubAccountPriority.CRITICAL, can_move=False),
            _claim("work", "All-hands", priority=SubAccountPriority.HIGH, can_move=True),
        )
        result = coord.run(neg)

        assert result["resolved"] is True
        assert result["winner_sub_account_id"] == "personal"

    def test_max_rounds_escalates_if_unresolvable(self):
        """With max_rounds=0, the negotiation can't run any rounds → escalates."""
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "M", priority=SubAccountPriority.NORMAL, can_move=True),
            _claim("personal", "L", priority=SubAccountPriority.NORMAL, can_move=True),
            max_rounds=0,
        )
        result = coord.run(neg)

        assert result["escalated"] is True

    def test_missing_claims_returns_error(self):
        coord = SwarmCoordinator()
        neg = SwarmNegotiation(claims=[])  # no claims
        result = coord.run(neg)

        assert result["escalated"] is True
        assert "missing claims" in result["resolution_reason"]

    def test_single_claim_returns_error(self):
        coord = SwarmCoordinator()
        neg = SwarmNegotiation(claims=[_claim("work", "Solo")])
        result = coord.run(neg)

        assert result["escalated"] is True


# --- audit trail tests -------------------------------------------------------

class TestAuditTrail:
    def test_audit_trail_contains_all_messages(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "CEO 1:1", priority=SubAccountPriority.HIGH, can_move=False),
            _claim("personal", "Gym", priority=SubAccountPriority.LOW, can_move=True),
        )
        result = coord.run(neg)

        # Should have: 2 probes + at least 1 propose + resolve.
        trail = result["audit_trail"]
        assert len(trail) >= 3
        types = [m["message_type"] for m in trail]
        assert "probe" in types

    def test_audit_trail_messages_have_timestamps(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(_claim("a", "A"), _claim("b", "B"))
        result = coord.run(neg)

        for msg in result["audit_trail"]:
            assert msg["timestamp"]  # non-empty ISO string

    def test_full_negotiation_export(self):
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "M", priority=SubAccountPriority.HIGH),
            _claim("personal", "L", priority=SubAccountPriority.LOW),
        )
        coord.run(neg)
        exported = neg.to_dict()

        assert exported["state"] == "resolved"
        assert len(exported["claims"]) == 2
        assert len(exported["messages"]) >= 2
        assert exported["winner_sub_account_id"] == "work"


# --- conflict detection tests ------------------------------------------------

class TestDetectConflicts:
    def test_detects_overlap_different_subs(self):
        coord = SwarmCoordinator()
        events = [
            _event("Work meeting", "work", BASE, BASE + timedelta(hours=1)),
            _event("Gym", "personal", BASE, BASE + timedelta(hours=1)),
        ]
        conflicts = coord.detect_conflicts(events)
        assert len(conflicts) == 1
        assert conflicts[0][0].source_sub_account_id == "work"
        assert conflicts[0][1].source_sub_account_id == "personal"

    def test_no_conflict_same_sub(self):
        coord = SwarmCoordinator()
        events = [
            _event("Meeting A", "work", BASE, BASE + timedelta(hours=1)),
            _event("Meeting B", "work", BASE, BASE + timedelta(hours=1)),
        ]
        conflicts = coord.detect_conflicts(events)
        assert len(conflicts) == 0

    def test_no_conflict_different_times(self):
        coord = SwarmCoordinator()
        events = [
            _event("Morning", "work", BASE, BASE + timedelta(hours=1)),
            _event("Afternoon", "personal", BASE + timedelta(hours=2), BASE + timedelta(hours=3)),
        ]
        conflicts = coord.detect_conflicts(events)
        assert len(conflicts) == 0

    def test_partial_overlap_detected(self):
        coord = SwarmCoordinator()
        events = [
            _event("Long meeting", "work", BASE, BASE + timedelta(hours=2)),
            _event("Quick chat", "personal", BASE + timedelta(hours=1), BASE + timedelta(hours=1, minutes=30)),
        ]
        conflicts = coord.detect_conflicts(events)
        assert len(conflicts) == 1

    def test_multiple_conflicts(self):
        coord = SwarmCoordinator()
        events = [
            _event("A", "work", BASE, BASE + timedelta(hours=1)),
            _event("B", "personal", BASE, BASE + timedelta(hours=1)),
            _event("C", "side", BASE, BASE + timedelta(hours=1)),
        ]
        conflicts = coord.detect_conflicts(events)
        assert len(conflicts) == 3  # work-personal, work-side, personal-side


# --- listing / retrieval tests ----------------------------------------------

class TestNegotiationManagement:
    def test_list_negotiations(self):
        coord = SwarmCoordinator()
        coord.initiate(_claim("work", "M"), _claim("personal", "L"))
        coord.initiate(_claim("work", "M2"), _claim("side", "S"))

        listing = coord.list_negotiations()
        assert len(listing) == 2
        assert all("state" in n for n in listing)

    def test_get_negotiation_unknown_id(self):
        coord = SwarmCoordinator()
        assert coord.get_negotiation("nonexistent") is None


# --- priority system tests ---------------------------------------------------

class TestSubAccountPriority:
    def test_rank_ordering(self):
        assert SubAccountPriority.rank(SubAccountPriority.CRITICAL) > SubAccountPriority.rank(SubAccountPriority.HIGH)
        assert SubAccountPriority.rank(SubAccountPriority.HIGH) > SubAccountPriority.rank(SubAccountPriority.NORMAL)
        assert SubAccountPriority.rank(SubAccountPriority.NORMAL) > SubAccountPriority.rank(SubAccountPriority.LOW)
        assert SubAccountPriority.rank(SubAccountPriority.LOW) > SubAccountPriority.rank(SubAccountPriority.DEFERRED)

    def test_comparison_operators(self):
        assert SubAccountPriority.CRITICAL > SubAccountPriority.HIGH
        assert SubAccountPriority.LOW < SubAccountPriority.NORMAL

    def test_critical_wins_over_critical_if_one_can_move(self):
        """Two critical-priority claims: the one that can't move wins."""
        coord = SwarmCoordinator()
        neg = coord.initiate(
            _claim("work", "Hard deadline", priority=SubAccountPriority.CRITICAL, can_move=False),
            _claim("personal", "Medical", priority=SubAccountPriority.CRITICAL, can_move=True),
        )
        result = coord.run(neg)
        assert result["resolved"] is True
        assert result["winner_sub_account_id"] == "work"
