"""Tests for OAuth start/callback endpoints and token storage.

Covers:
  - OAuth start for google_calendar (builds auth URL with client_id)
  - OAuth start for outlook_calendar
  - OAuth start for unsupported provider type (400)
  - OAuth start for missing provider (404)
  - OAuth start with no client_id configured (400)
  - OAuth callback success (mocked token exchange, tokens stored, status=connected)
  - OAuth callback with invalid state (redirects with error)
  - OAuth callback with user-denied authorization (redirects with denied)
  - OAuth callback for missing provider (redirects with error)
  - get_provider / update_provider_config store methods
  - _serialize_provider includes config and scopes
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.api.oauth_routes import router as oauth_router
from a_cal.db.store import PersistentStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """FastAPI app with standalone data + OAuth routes."""
    a = FastAPI()
    a.include_router(standalone_data_router)
    a.include_router(oauth_router)
    return a


@pytest.fixture
def client(app):
    """Test client with cleanup of test-created resources."""
    c = TestClient(app)
    existing_subs = {s["id"] for s in c.get("/api/a-cal/sub-accounts").json()}
    existing_provs = {p["id"] for p in c.get("/api/a-cal/providers/all").json()}
    yield c
    try:
        for p in c.get("/api/a-cal/providers/all").json():
            if p["id"] not in existing_provs:
                c.delete(f"/api/a-cal/providers/{p['id']}")
        for s in c.get("/api/a-cal/sub-accounts").json():
            if s["id"] not in existing_subs:
                c.delete(f"/api/a-cal/sub-accounts/{s['id']}")
    except Exception:
        pass


@pytest.fixture
def store():
    """Fresh PersistentStore for direct store-level tests."""
    return PersistentStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_sub(client, name="OAuth Test"):
    resp = client.post("/api/a-cal/sub-accounts", json={"name": name, "kind": "unified"})
    return resp.json()["id"]


def _create_google_provider(client, sub_id, config=None):
    if config is None:
        config = {"client_id": "test-client-id", "client_secret": "test-secret"}
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": "google_calendar",
        "provider_account_id": "user@gmail.com",
        "display_name": "Google Calendar",
        "config": config,
    })
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Store-level tests
# ---------------------------------------------------------------------------

def test_serialize_provider_includes_config_and_scopes(store):
    """_serialize_provider should include config and scopes fields."""
    sub = store.create_sub_account({"name": "CfgTest", "kind": "unified"})
    prov = store.create_provider({
        "sub_account_id": sub["id"],
        "provider_type": "google_calendar",
        "provider_account_id": "u@gmail.com",
        "config": {"client_id": "abc", "custom": "val"},
        "scopes": ["calendar", "email"],
    })
    fetched = store.get_provider(prov["id"])
    assert fetched is not None
    assert fetched["config"] == {"client_id": "abc", "custom": "val"}
    assert fetched["scopes"] == ["calendar", "email"]


def test_get_provider_returns_none_for_missing(store):
    assert store.get_provider("nonexistent-id") is None


def test_update_provider_config_merges_not_replaces(store):
    """update_provider_config should merge, not replace, existing config."""
    sub = store.create_sub_account({"name": "MergeTest", "kind": "unified"})
    prov = store.create_provider({
        "sub_account_id": sub["id"],
        "provider_type": "gmail",
        "provider_account_id": "u@gmail.com",
        "config": {"client_id": "abc", "keep_me": True},
    })
    result = store.update_provider_config(prov["id"], {"oauth_tokens": {"access_token": "tok123"}})
    assert result is not None
    assert result["config"]["keep_me"] is True
    assert result["config"]["oauth_tokens"]["access_token"] == "tok123"
    assert result["config"]["client_id"] == "abc"


def test_update_provider_config_missing_returns_none(store):
    assert store.update_provider_config("no-such-id", {"x": 1}) is None


# ---------------------------------------------------------------------------
# OAuth start endpoint tests
# ---------------------------------------------------------------------------

def test_oauth_start_google(client):
    """OAuth start for google_calendar returns a valid authorization URL."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts.google.com" in data["authorization_url"]
    assert data["provider_id"] == prov_id
    assert data["provider_type"] == "google_calendar"
    assert "client_id=test-client-id" in data["authorization_url"]
    assert "state=" in data["authorization_url"]


def test_oauth_start_outlook(client):
    """OAuth start for outlook_calendar returns a Microsoft auth URL."""
    sub_id = _create_sub(client)
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": "outlook_calendar",
        "provider_account_id": "user@outlook.com",
        "config": {"client_id": "ms-client-id", "client_secret": "ms-secret"},
    })
    prov_id = resp.json()["id"]

    resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    assert resp.status_code == 200
    data = resp.json()
    assert "login.microsoftonline.com" in data["authorization_url"]
    assert "client_id=ms-client-id" in data["authorization_url"]


def test_oauth_start_gmail(client):
    """OAuth start for gmail returns a Google auth URL with gmail scopes."""
    sub_id = _create_sub(client)
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": "gmail",
        "provider_account_id": "user@gmail.com",
        "config": {"client_id": "gmail-id", "client_secret": "gmail-secret"},
    })
    prov_id = resp.json()["id"]

    resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    assert resp.status_code == 200
    assert "gmail.readonly" in resp.json()["authorization_url"]


def test_oauth_start_unsupported_provider_type(client):
    """OAuth start for a non-OAuth provider type returns 400."""
    sub_id = _create_sub(client)
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": "caldav",
        "provider_account_id": "user@cal.example",
        "config": {},
    })
    prov_id = resp.json()["id"]

    resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    assert resp.status_code == 400
    assert "not supported" in resp.json()["detail"].lower()


def test_oauth_start_missing_provider(client):
    """OAuth start for a nonexistent provider returns 404."""
    resp = client.get("/api/a-cal/providers/nonexistent/oauth/start")
    assert resp.status_code == 404


def test_oauth_start_no_client_id(client):
    """OAuth start with no client_id configured returns 400."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id, config={})

    resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    assert resp.status_code == 400
    assert "client_id" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# OAuth callback endpoint tests
# ---------------------------------------------------------------------------

def test_oauth_callback_success(client):
    """OAuth callback with valid state + mocked token exchange stores tokens."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    # Start the flow to register a state token
    start_resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    auth_url = start_resp.json()["authorization_url"]
    # Extract state from the auth URL
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(auth_url).query)["state"][0]

    # Mock the token exchange
    mock_tokens = {
        "access_token": "mock-access-token",
        "refresh_token": "mock-refresh-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    with patch(
        "a_cal.api.oauth_routes.exchange_code_for_tokens",
        new_callable=AsyncMock,
        return_value=mock_tokens,
    ):
        resp = client.get(
            f"/api/a-cal/providers/{prov_id}/oauth/callback",
            params={"code": "test-auth-code", "state": state},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert "success" in resp.headers["location"]

    # Verify tokens were stored and provider is connected
    store = PersistentStore()
    provider = store.get_provider(prov_id)
    assert provider["status"] == "connected"
    assert provider["config"]["oauth_tokens"]["access_token"] == "mock-access-token"
    assert provider["config"]["oauth_tokens"]["refresh_token"] == "mock-refresh-token"


def test_oauth_callback_invalid_state(client):
    """OAuth callback with an invalid state token redirects with error."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    resp = client.get(
        f"/api/a-cal/providers/{prov_id}/oauth/callback",
        params={"code": "some-code", "state": "bogus-state"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=invalid_state" in resp.headers["location"]


def test_oauth_callback_user_denied(client):
    """OAuth callback when the user denies redirects with 'denied'."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    resp = client.get(
        f"/api/a-cal/providers/{prov_id}/oauth/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "denied" in resp.headers["location"]


def test_oauth_callback_missing_code_or_state(client):
    """OAuth callback without code/state redirects with error."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    resp = client.get(
        f"/api/a-cal/providers/{prov_id}/oauth/callback",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=missing_code_or_state" in resp.headers["location"]


def test_oauth_callback_provider_not_found(client):
    """OAuth callback for a missing provider redirects with error."""
    # Register a valid state but for a nonexistent provider
    from a_cal.providers.oauth import _state_store
    _state_store["valid-state-123"] = "nonexistent-prov"

    resp = client.get(
        "/api/a-cal/providers/nonexistent-prov/oauth/callback",
        params={"code": "x", "state": "valid-state-123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "provider_not_found" in resp.headers["location"]


def test_oauth_callback_token_exchange_failure(client):
    """OAuth callback when token exchange fails marks provider as error."""
    sub_id = _create_sub(client)
    prov_id = _create_google_provider(client, sub_id)

    start_resp = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(start_resp.json()["authorization_url"]).query)["state"][0]

    with patch(
        "a_cal.api.oauth_routes.exchange_code_for_tokens",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider returned 400"),
    ):
        resp = client.get(
            f"/api/a-cal/providers/{prov_id}/oauth/callback",
            params={"code": "bad-code", "state": state},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert "token_exchange_failed" in resp.headers["location"]

    store = PersistentStore()
    provider = store.get_provider(prov_id)
    assert provider["status"] == "error"


# ---------------------------------------------------------------------------
# OAuth helper module tests
# ---------------------------------------------------------------------------

def test_oauth_scopes_defined():
    """OAUTH_SCOPES should have scopes for all supported provider types."""
    from a_cal.providers.oauth import OAUTH_SCOPES
    assert "google_calendar" in OAUTH_SCOPES
    assert "outlook_calendar" in OAUTH_SCOPES
    assert "gmail" in OAUTH_SCOPES
    assert "https://www.googleapis.com/auth/calendar" in OAUTH_SCOPES["google_calendar"]
    assert "https://graph.microsoft.com/Calendars.ReadWrite" in OAUTH_SCOPES["outlook_calendar"]


def test_oauth_get_config_from_env():
    """get_oauth_config should fall back to environment variables."""
    from a_cal.providers.oauth import get_oauth_config
    import os

    os.environ["A_CAL_GOOGLE_CLIENT_ID"] = "env-client-id"
    os.environ["A_CAL_GOOGLE_CLIENT_SECRET"] = "env-secret"
    try:
        cfg = get_oauth_config("google_calendar", {})
        assert cfg["client_id"] == "env-client-id"
        assert cfg["client_secret"] == "env-secret"
    finally:
        del os.environ["A_CAL_GOOGLE_CLIENT_ID"]
        del os.environ["A_CAL_GOOGLE_CLIENT_SECRET"]


def test_oauth_get_config_from_connection_config():
    """get_oauth_config should prefer connection config over env vars."""
    from a_cal.providers.oauth import get_oauth_config
    cfg = get_oauth_config("google_calendar", {"client_id": "conn-id", "client_secret": "conn-secret"})
    assert cfg["client_id"] == "conn-id"
    assert cfg["client_secret"] == "conn-secret"


def test_validate_state_returns_none_for_invalid():
    """validate_state should return None for an unrecognized state token."""
    from a_cal.providers.oauth import validate_state
    assert validate_state("never-issued-state") is None
