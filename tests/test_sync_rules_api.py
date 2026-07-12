"""Tests for sync rule CRUD endpoints."""

from __future__ import annotations

import os

# Disable atom for standalone testing.
os.environ.setdefault("A_CAL_DISABLE_ATOM", "1")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as data_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(data_router)
    return TestClient(app)


def _make_sub(client: TestClient) -> str:
    resp = client.post("/api/a-cal/sub-accounts", json={"name": "Test Sub", "kind": "calendar"})
    return resp.json()["id"]


class TestSyncRuleCreate:
    """Tests for POST /sync-rules."""

    def test_create_exclude_rule(self):
        client = _client()
        sub_id = _make_sub(client)

        resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id,
            "rule_type": "exclude",
            "field": "title",
            "pattern": "*private*",
            "priority": 0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["sub_account_id"] == sub_id

    def test_create_include_rule(self):
        client = _client()
        sub_id = _make_sub(client)

        resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id,
            "rule_type": "include",
            "field": "keyword",
            "pattern": "meeting",
            "priority": 1,
        })
        assert resp.status_code == 200

    def test_create_transform_rule_with_action(self):
        client = _client()
        sub_id = _make_sub(client)

        resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id,
            "rule_type": "transform",
            "field": "title",
            "pattern": "dentist",
            "action": {"rename": "Busy: {title}"},
            "priority": 2,
        })
        assert resp.status_code == 200

    def test_create_agent_rule(self):
        client = _client()
        sub_id = _make_sub(client)

        resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id,
            "rule_type": "agent",
            "field": "title",
            "pattern": "*review*",
            "priority": 3,
        })
        assert resp.status_code == 200


class TestSyncRuleList:
    """Tests for GET /sync-rules."""

    def test_list_empty(self):
        client = _client()
        sub_id = _make_sub(client)

        resp = client.get("/api/a-cal/sync-rules", params={"sub_account_id": sub_id})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_rules(self):
        client = _client()
        sub_id = _make_sub(client)

        client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id, "rule_type": "exclude",
            "field": "title", "pattern": "*private*", "priority": 0,
        })
        client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id, "rule_type": "include",
            "field": "keyword", "pattern": "meeting", "priority": 1,
        })

        resp = client.get("/api/a-cal/sync-rules", params={"sub_account_id": sub_id})
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 2
        assert all(r["sub_account_id"] == sub_id for r in rules)
        assert all(r["is_active"] for r in rules)


class TestSyncRuleDelete:
    """Tests for DELETE /sync-rules/{rule_id}."""

    def test_delete_existing_rule(self):
        client = _client()
        sub_id = _make_sub(client)

        create_resp = client.post("/api/a-cal/sync-rules", json={
            "sub_account_id": sub_id, "rule_type": "exclude",
            "field": "title", "pattern": "*test*", "priority": 0,
        })
        rule_id = create_resp.json()["id"]

        resp = client.delete(f"/api/a-cal/sync-rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        list_resp = client.get("/api/a-cal/sync-rules", params={"sub_account_id": sub_id})
        assert len(list_resp.json()) == 0

    def test_delete_nonexistent_rule_returns_404(self):
        client = _client()
        resp = client.delete("/api/a-cal/sync-rules/nonexistent-id")
        assert resp.status_code == 404


class TestSyncRulesWithSyncEngine:
    """Test that created rules are actually used by the sync engine."""

    def test_exclude_rule_hides_events(self):
        """An exclude rule should prevent matching events from appearing."""
        from a_cal.providers.base import CalendarEventDTO
        from a_cal.sync.engine import SubAccountSyncEngine
        from datetime import datetime

        # Create rules directly (not through API, to test the engine)
        sub_account = {
            "id": "test-sub-engine",
            "name": "Test",
            "sync_mode": "mirror_filter",
            "sync_rules": [
                {"rule_type": "exclude", "field": "title", "pattern": "private", "priority": 0, "is_active": True},
            ],
        }
        engine = SubAccountSyncEngine(sub_account, [])

        events = [
            CalendarEventDTO(
                provider_event_id="1", provider_type="local",
                title="Team Meeting", start=datetime(2026, 7, 15, 10, 0),
                end=datetime(2026, 7, 15, 11, 0),
            ),
            CalendarEventDTO(
                provider_event_id="2", provider_type="local",
                title="private appointment", start=datetime(2026, 7, 15, 14, 0),
                end=datetime(2026, 7, 15, 15, 0),
            ),
        ]

        result = engine._apply_model(events)
        titles = [e.title for e in result]
        assert "Team Meeting" in titles
        assert "private appointment" not in titles

    def test_transform_rule_renames_events(self):
        """A transform rule should rename matching events."""
        from a_cal.providers.base import CalendarEventDTO
        from a_cal.sync.engine import SubAccountSyncEngine
        from datetime import datetime

        sub_account = {
            "id": "test-sub-transform",
            "name": "Test",
            "sync_mode": "mirror_filter",
            "sync_rules": [
                {
                    "rule_type": "transform", "field": "title", "pattern": "dentist",
                    "action": {"rename": "Busy: {title}"}, "priority": 0, "is_active": True,
                },
            ],
        }
        engine = SubAccountSyncEngine(sub_account, [])

        events = [
            CalendarEventDTO(
                provider_event_id="1", provider_type="local",
                title="dentist appointment", start=datetime(2026, 7, 15, 10, 0),
                end=datetime(2026, 7, 15, 11, 0),
            ),
        ]

        result = engine._apply_model(events)
        assert len(result) == 1
        assert result[0].title == "Busy: dentist appointment"
