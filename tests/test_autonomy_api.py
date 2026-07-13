"""Tests for the agent autonomy API endpoints.

GET/POST /api/a-cal/settings/autonomy — global default + per-sub-account overrides.
Conductor chat responses include autonomy_level and confirmation_required fields.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.agent_routes import router as agent_router
from a_cal.settings.autonomy import AutonomyLevel


@pytest.fixture
def client():
    """Test client with only the agent/settings routes mounted."""
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


class TestAutonomyAPI:
    """Autonomy settings CRUD via the API."""

    def test_get_autonomy_returns_default(self, client):
        """GET returns the default autonomy config (confirm)."""
        resp = client.get("/api/a-cal/settings/autonomy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_level"] == "confirm"
        assert data["per_sub_account"] == {}

    def test_set_autonomy_updates_global_level(self, client):
        """POST updates the global default level."""
        resp = client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "full_auto",
            "per_sub_account": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_level"] == "full_auto"

        # Verify it persisted
        resp2 = client.get("/api/a-cal/settings/autonomy")
        assert resp2.json()["default_level"] == "full_auto"

    def test_set_autonomy_with_per_sub_account(self, client):
        """POST with per_sub_account overrides persists them."""
        resp = client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "confirm",
            "per_sub_account": {"sub1": "suggest_only", "sub2": "full_auto"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_sub_account"]["sub1"] == "suggest_only"
        assert data["per_sub_account"]["sub2"] == "full_auto"

    def test_set_autonomy_rejects_invalid_level(self, client):
        """POST with invalid default_level returns 400."""
        resp = client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "bogus",
            "per_sub_account": {},
        })
        assert resp.status_code == 400

    def test_set_autonomy_rejects_invalid_per_sub_level(self, client):
        """POST with invalid per-sub-account level returns 400."""
        resp = client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "confirm",
            "per_sub_account": {"sub1": "bogus"},
        })
        assert resp.status_code == 400


class TestConductorAutonomyIntegration:
    """Conductor chat responses include autonomy metadata."""

    def test_standalone_response_includes_autonomy_level(self, client):
        """Conductor response includes autonomy_level and confirmation_required."""
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "autonomy_level" in data
        assert data["autonomy_level"] == "confirm"
        assert data["confirmation_required"] is True

    def test_suggest_only_produces_dry_run_actions(self, client):
        """When autonomy is suggest_only, actions have dry_run status."""
        client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "suggest_only",
            "per_sub_account": {},
        })
        resp = client.post("/api/a-cal/conductor/chat", json={
            "message": "create a meeting tomorrow at 2pm",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["autonomy_level"] == "suggest_only"
        assert data["confirmation_required"] is False
        # In suggest_only mode, actions should be proposed not executed
        actions = data.get("actions", [])
        for action in actions:
            if action.get("type") == "create_event":
                assert action.get("status") in ("dry_run", "conflict")

    def test_full_auto_no_confirmation_required(self, client):
        """When autonomy is full_auto, confirmation_required is False."""
        client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "full_auto",
            "per_sub_account": {},
        })
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["autonomy_level"] == "full_auto"
        assert data["confirmation_required"] is False

    def test_confirm_level_requires_confirmation(self, client):
        """When autonomy is confirm, confirmation_required is True."""
        client.post("/api/a-cal/settings/autonomy", json={
            "default_level": "confirm",
            "per_sub_account": {},
        })
        resp = client.post("/api/a-cal/conductor/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["autonomy_level"] == "confirm"
        assert data["confirmation_required"] is True
