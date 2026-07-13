"""Tests for email integration depth settings (charter §5)."""

from __future__ import annotations

from a_cal.settings.email import (
    EmailDepth,
    EmailIntegrationConfig,
    EMAIL_DEPTH_LABELS,
    EMAIL_DEPTH_DESCRIPTIONS,
)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.agent_routes import router as agent_router


@pytest.fixture
def client():
    """Test client with the agent/settings routes mounted."""
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


class TestEmailDepthEnum:
    def test_three_levels(self):
        assert EmailDepth.SYNC_NOTIFY.value == "sync_notify"
        assert EmailDepth.AGENT_MEDIATED.value == "agent_mediated"
        assert EmailDepth.FULL_TWO_WAY.value == "full_two_way"

    def test_default_is_sync_notify(self):
        assert EmailDepth.default() == EmailDepth.SYNC_NOTIFY

    def test_labels_and_descriptions_cover_all(self):
        for d in EmailDepth:
            assert d.value in EMAIL_DEPTH_LABELS
            assert d.value in EMAIL_DEPTH_DESCRIPTIONS


class TestEmailIntegrationConfig:
    def test_defaults(self):
        c = EmailIntegrationConfig()
        assert c.depth == "sync_notify"
        assert c.per_provider == {}
        assert c.auto_scan_enabled is False

    def test_effective_depth_global(self):
        c = EmailIntegrationConfig(depth="agent_mediated")
        assert c.effective_depth() == EmailDepth.AGENT_MEDIATED
        assert c.effective_depth("gmail") == EmailDepth.AGENT_MEDIATED

    def test_effective_depth_per_provider_override(self):
        c = EmailIntegrationConfig(
            depth="sync_notify",
            per_provider={"gmail": "full_two_way"},
        )
        assert c.effective_depth("gmail") == EmailDepth.FULL_TWO_WAY
        assert c.effective_depth("outlook") == EmailDepth.SYNC_NOTIFY
        assert c.effective_depth() == EmailDepth.SYNC_NOTIFY

    def test_effective_depth_invalid_falls_back(self):
        c = EmailIntegrationConfig(depth="bogus")
        assert c.effective_depth() == EmailDepth.SYNC_NOTIFY

    def test_effective_depth_invalid_per_provider_falls_back(self):
        c = EmailIntegrationConfig(
            depth="agent_mediated",
            per_provider={"gmail": "bogus"},
        )
        assert c.effective_depth("gmail") == EmailDepth.AGENT_MEDIATED

    def test_allows_agent_actions(self):
        assert not EmailIntegrationConfig(depth="sync_notify").allows_agent_actions()
        assert EmailIntegrationConfig(depth="agent_mediated").allows_agent_actions()
        assert EmailIntegrationConfig(depth="full_two_way").allows_agent_actions()

    def test_allows_autonomous_send(self):
        assert not EmailIntegrationConfig(depth="sync_notify").allows_autonomous_send()
        assert not EmailIntegrationConfig(depth="agent_mediated").allows_autonomous_send()
        assert EmailIntegrationConfig(depth="full_two_way").allows_autonomous_send()

    def test_allows_autonomous_send_per_provider(self):
        c = EmailIntegrationConfig(
            depth="sync_notify",
            per_provider={"gmail": "full_two_way"},
        )
        assert c.allows_autonomous_send("gmail")
        assert not c.allows_autonomous_send("outlook")

    def test_roundtrip(self):
        c = EmailIntegrationConfig(
            depth="full_two_way",
            per_provider={"gmail": "agent_mediated"},
            auto_scan_enabled=True,
        )
        d = EmailIntegrationConfig.from_dict(c.to_dict())
        assert d.depth == "full_two_way"
        assert d.per_provider == {"gmail": "agent_mediated"}
        assert d.auto_scan_enabled is True

    def test_from_dict_defaults(self):
        d = EmailIntegrationConfig.from_dict({})
        assert d.depth == "sync_notify"
        assert d.per_provider == {}
        assert d.auto_scan_enabled is False


class TestEmailDepthAPI:
    """Tests for the /settings/email API endpoints."""

    def test_get_default_email_settings(self, client):
        resp = client.get("/api/a-cal/settings/email")
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == "sync_notify"
        assert data["per_provider"] == {}
        assert data["auto_scan_enabled"] is False

    def test_set_email_depth(self, client):
        resp = client.post("/api/a-cal/settings/email", json={
            "depth": "agent_mediated",
            "auto_scan_enabled": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == "agent_mediated"
        assert data["auto_scan_enabled"] is True

        # Verify persistence
        resp2 = client.get("/api/a-cal/settings/email")
        assert resp2.json()["depth"] == "agent_mediated"
        assert resp2.json()["auto_scan_enabled"] is True

    def test_set_full_two_way_with_per_provider(self, client):
        resp = client.post("/api/a-cal/settings/email", json={
            "depth": "full_two_way",
            "per_provider": {"gmail": "full_two_way", "outlook": "sync_notify"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_provider"]["gmail"] == "full_two_way"
        assert data["per_provider"]["outlook"] == "sync_notify"

    def test_invalid_depth_rejected(self, client):
        resp = client.post("/api/a-cal/settings/email", json={"depth": "bogus"})
        assert resp.status_code == 400

    def test_invalid_per_provider_depth_rejected(self, client):
        resp = client.post("/api/a-cal/settings/email", json={
            "depth": "sync_notify",
            "per_provider": {"gmail": "bogus"},
        })
        assert resp.status_code == 400
