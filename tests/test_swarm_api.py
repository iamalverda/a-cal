"""Tests for the swarm negotiation API endpoints.

Uses FastAPI's TestClient to verify the HTTP layer: negotiate, list,
get-by-id, and detect-conflicts. These run in standalone mode (rule-based,
no LLM, no database).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.swarm_routes import router as swarm_router

# Fresh app per test module — the coordinator store is module-level, so
# we import the router directly and mount it on a clean app.
app = FastAPI()
app.include_router(swarm_router)

client = TestClient(app)

BASE = "2026-07-16T14:00:00+00:00"
END = "2026-07-16T15:00:00+00:00"


def _claim_a():
    return {
        "sub_account_id": "work",
        "event_id": "work-evt-1",
        "event_title": "CEO 1:1",
        "slot_start": BASE,
        "slot_end": END,
        "priority": "high",
        "can_move": False,
        "reasoning": "CEO is only available this slot",
    }


def _claim_b():
    return {
        "sub_account_id": "personal",
        "event_id": "personal-evt-1",
        "event_title": "Gym session",
        "slot_start": BASE,
        "slot_end": END,
        "priority": "low",
        "can_move": True,
        "reasoning": "Flexible, can move to another day",
    }


class TestNegotiate:
    def test_negotiate_resolves_with_winner(self):
        resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": _claim_a(),
            "claim_b": _claim_b(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["winner_sub_account_id"] == "work"
        assert data["loser_sub_account_id"] == "personal"
        assert len(data["audit_trail"]) >= 3

    def test_negotiate_returns_alternative_slot(self):
        resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": _claim_a(),
            "claim_b": _claim_b(),
        })
        data = resp.json()
        assert data["alternative_slot"] is not None
        assert data["alternative_slot"]["sub_account_id"] == "personal"

    def test_negotiate_escalates_when_neither_can_move(self):
        resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": {
                **_claim_a(),
                "priority": "high",
                "can_move": False,
            },
            "claim_b": {
                **_claim_b(),
                "sub_account_id": "surgery",
                "event_title": "Medical appointment",
                "priority": "high",
                "can_move": False,
            },
        })
        data = resp.json()
        assert data["escalated"] is True
        assert data["resolved"] is False

    def test_negotiate_includes_negotiation_id(self):
        resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": _claim_a(),
            "claim_b": _claim_b(),
        })
        data = resp.json()
        assert data["negotiation_id"]  # non-empty UUID string

    def test_invalid_priority_defaults_to_normal(self):
        resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": {**_claim_a(), "priority": "not-a-real-priority"},
            "claim_b": _claim_b(),
        })
        assert resp.status_code == 200
        # Should still resolve — invalid priority falls back to NORMAL.
        data = resp.json()
        assert data["resolved"] is True


class TestListNegotiations:
    def test_list_after_negotiation(self):
        client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": _claim_a(),
            "claim_b": _claim_b(),
        })
        resp = client.get("/api/a-cal/swarm/negotiations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "state" in data[0]
        assert "claims" in data[0]


class TestGetNegotiation:
    def test_get_existing_negotiation(self):
        neg_resp = client.post("/api/a-cal/swarm/negotiate", json={
            "claim_a": _claim_a(),
            "claim_b": _claim_b(),
        })
        neg_id = neg_resp.json()["negotiation_id"]

        resp = client.get(f"/api/a-cal/swarm/negotiations/{neg_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == neg_id
        assert len(data["claims"]) == 2
        assert len(data["messages"]) >= 2

    def test_get_nonexistent_returns_404(self):
        resp = client.get("/api/a-cal/swarm/negotiations/nonexistent-id")
        assert resp.status_code == 404


class TestDetectConflicts:
    def test_detects_conflicting_events(self):
        resp = client.post("/api/a-cal/swarm/detect-conflicts", json={
            "events": [
                {
                    "title": "Work meeting",
                    "source_sub_account_id": "work",
                    "start": BASE,
                    "end": END,
                },
                {
                    "title": "Gym",
                    "source_sub_account_id": "personal",
                    "start": BASE,
                    "end": END,
                },
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_count"] == 1
        assert data["conflicts"][0]["event_a"]["sub_account_id"] == "work"
        assert data["conflicts"][0]["event_b"]["sub_account_id"] == "personal"

    def test_no_conflicts_different_times(self):
        resp = client.post("/api/a-cal/swarm/detect-conflicts", json={
            "events": [
                {
                    "title": "Morning",
                    "source_sub_account_id": "work",
                    "start": BASE,
                    "end": END,
                },
                {
                    "title": "Afternoon",
                    "source_sub_account_id": "personal",
                    "start": "2026-07-16T16:00:00+00:00",
                    "end": "2026-07-16T17:00:00+00:00",
                },
            ],
        })
        data = resp.json()
        assert data["conflict_count"] == 0

    def test_no_conflicts_same_sub(self):
        resp = client.post("/api/a-cal/swarm/detect-conflicts", json={
            "events": [
                {
                    "title": "A",
                    "source_sub_account_id": "work",
                    "start": BASE,
                    "end": END,
                },
                {
                    "title": "B",
                    "source_sub_account_id": "work",
                    "start": BASE,
                    "end": END,
                },
            ],
        })
        data = resp.json()
        assert data["conflict_count"] == 0

    def test_empty_events_list(self):
        resp = client.post("/api/a-cal/swarm/detect-conflicts", json={
            "events": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflict_count"] == 0
