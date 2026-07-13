"""Tests for the atom integration bridge.

Covers:
  - is_atom_available() auto-detection and env-var override
  - get_atom_adapters() returns adapters when atom is available, None when not
  - get_atom_status() returns a status dict for the frontend
  - mount_a_cal() mounts all routers into a FastAPI app
  - AtomTokenStorage / AtomLLMAdapter / AtomIntentClassifier construction
  - Conductor gracefully handles no atom (keyword classification works)
  - OAuth callback falls back to SQLite when atom not available
  - _map_atom_intent maps atom categories to A-Cal IntentType
  - Backend mode setting (standalone vs atom)
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.integrations.atom_bridge import (
    AtomIntentClassifier,
    AtomLLMAdapter,
    AtomTokenStorage,
    get_atom_adapters,
    get_atom_status,
    get_atom_token_storage,
    is_atom_available,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def atom_disabled(monkeypatch):
    """Force atom detection off for tests that need standalone mode."""
    monkeypatch.setenv("A_CAL_DISABLE_ATOM", "1")
    yield
    monkeypatch.delenv("A_CAL_DISABLE_ATOM", raising=False)


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------

def test_is_atom_available_returns_bool():
    """is_atom_available should return a boolean."""
    result = is_atom_available()
    assert isinstance(result, bool)


def test_atom_disabled_via_env_var(atom_disabled):
    """When A_CAL_DISABLE_ATOM is set, atom should not be available."""
    assert is_atom_available() is False


def test_atom_auto_detected_if_installed():
    """If atom's backend is on disk, is_atom_available should find it.

    This test passes when atom is installed alongside A-Cal (the normal
    development setup). If atom is not installed, it skips.
    """
    # Don't disable atom — check if it's actually there
    if os.environ.get("A_CAL_DISABLE_ATOM"):
        pytest.skip("atom disabled by env var")
    result = is_atom_available()
    # In the dev environment, atom IS installed
    if result:
        # Verify we can get adapters
        token, llm, intent = get_atom_adapters()
        # At least one adapter should be non-None
        assert token is not None or llm is not None or intent is not None
    else:
        pytest.skip("atom not installed — auto-detection test skipped")


def test_get_atom_adapters_returns_none_without_atom(atom_disabled):
    """get_atom_adapters should return (None, None, None) without atom."""
    token, llm, intent = get_atom_adapters()
    assert token is None
    assert llm is None
    assert intent is None


def test_get_atom_status_returns_dict():
    """get_atom_status should return a dict with expected keys."""
    status = get_atom_status()
    assert "available" in status
    assert "backend_path" in status
    assert "adapters" in status
    assert isinstance(status["available"], bool)
    assert isinstance(status["adapters"], dict)


def test_get_atom_status_when_disabled(atom_disabled):
    """When atom is disabled, status should show unavailable."""
    status = get_atom_status()
    assert status["available"] is False
    assert status["backend_path"] is None


# ---------------------------------------------------------------------------
# Adapter construction tests (should fail gracefully without atom)
# ---------------------------------------------------------------------------

def test_atom_token_storage_raises_without_atom(atom_disabled):
    """AtomTokenStorage should raise ImportError when atom isn't available."""
    with pytest.raises(ImportError):
        AtomTokenStorage()


def test_atom_llm_adapter_raises_without_atom(atom_disabled):
    """AtomLLMAdapter should raise ImportError when atom isn't available."""
    with pytest.raises(ImportError):
        AtomLLMAdapter()


def test_atom_intent_classifier_raises_without_atom(atom_disabled):
    """AtomIntentClassifier should raise ImportError when atom isn't available."""
    with pytest.raises(ImportError):
        AtomIntentClassifier()


# ---------------------------------------------------------------------------
# Token storage tests (when atom is available)
# ---------------------------------------------------------------------------

def test_atom_token_storage_round_trip():
    """Test that atom token storage can save and retrieve tokens.

    Only runs when atom is installed and available.
    """
    if not is_atom_available():
        pytest.skip("atom not available")

    ts = get_atom_token_storage()
    if ts is None:
        pytest.skip("atom token storage unavailable")

    # Save tokens
    conn_id = ts.save_oauth_tokens(
        user_id="test-a-cal-user",
        provider_type="google_calendar",
        tokens={"access_token": "test-acc", "refresh_token": "test-ref"},
    )
    assert conn_id is not None

    # Retrieve tokens (async call — use asyncio.run)
    import asyncio
    tokens = asyncio.run(
        ts.get_oauth_tokens("test-a-cal-user", "google_calendar")
    )
    assert tokens is not None
    assert tokens["access_token"] == "test-acc"

    # Clean up
    deleted = ts.delete_oauth_tokens("test-a-cal-user", "google_calendar")
    assert deleted is True


# ---------------------------------------------------------------------------
# Mount tests
# ---------------------------------------------------------------------------

def test_mount_a_cal_adds_routes():
    """mount_a_cal should add all A-Cal routers to a FastAPI app."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    mount_a_cal(app)

    client = TestClient(app)
    resp = client.get("/api/a-cal/sub-accounts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_mount_a_cal_route_count():
    """mount_a_cal should mount at least 6 routers."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    initial_count = len(app.routes)
    mount_a_cal(app)
    added = len(app.routes) - initial_count
    assert added >= 6, f"Expected 6+ routers added, got {added}"


def test_mount_a_cal_oauth_endpoint_accessible():
    """After mounting, OAuth start endpoint should be accessible."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    mount_a_cal(app)
    client = TestClient(app)

    resp = client.get("/api/a-cal/providers/nonexistent/oauth/start")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Conductor fallback tests (keyword classification works without atom)
# ---------------------------------------------------------------------------

def test_conductor_keyword_classification(atom_disabled):
    """Conductor should classify intents using keywords when atom is absent."""
    from a_cal.agents.conductor import ACalConductor, IntentType

    conductor = ACalConductor()
    assert conductor.classify_intent("find a 30 min slot tomorrow") == IntentType.SCHEDULE
    assert conductor.classify_intent("sync my providers") == IntentType.SYNC
    assert conductor.classify_intent("check my inbox for invites") == IntentType.EMAIL
    assert conductor.classify_intent("hello there") == IntentType.CHAT


def test_conductor_atom_intent_is_none_without_atom(atom_disabled):
    """Conductor's _atom_intent should be None when atom isn't available."""
    from a_cal.agents.conductor import ACalConductor

    conductor = ACalConductor()
    assert conductor._atom_intent is None


def test_map_atom_intent():
    """_map_atom_intent should correctly map atom categories."""
    from a_cal.agents.conductor import ACalConductor, IntentType

    assert ACalConductor._map_atom_intent("chat") == IntentType.CHAT
    assert ACalConductor._map_atom_intent("workflow") == IntentType.SCHEDULE
    assert ACalConductor._map_atom_intent("task") == IntentType.SCHEDULE
    assert ACalConductor._map_atom_intent("unknown") == IntentType.CHAT


# ---------------------------------------------------------------------------
# OAuth callback fallback test (uses SQLite when atom not available)
# ---------------------------------------------------------------------------

def test_oauth_callback_stores_in_sqlite_without_atom(atom_disabled):
    """OAuth callback should store tokens in SQLite config when atom is absent."""
    from a_cal.api.standalone_data import router as standalone_data_router
    from a_cal.api.oauth_routes import router as oauth_router, _get_token_storage
    from unittest.mock import AsyncMock, patch

    # Verify atom token storage is None when disabled
    assert _get_token_storage() is None

    app = FastAPI()
    app.include_router(standalone_data_router)
    app.include_router(oauth_router)
    client = TestClient(app)

    existing_subs = {s["id"] for s in client.get("/api/a-cal/sub-accounts").json()}
    existing_provs = {p["id"] for p in client.get("/api/a-cal/providers/all").json()}

    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": "sa-main",
        "provider_type": "google_calendar",
        "provider_account_id": "test@gmail.com",
        "config": {"client_id": "test-id", "client_secret": "test-secret"},
    })
    prov_id = resp.json()["id"]

    start = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    mock_tokens = {"access_token": "tok", "refresh_token": "ref", "token_type": "Bearer"}
    with patch(
        "a_cal.api.oauth_routes.exchange_code_for_tokens",
        new_callable=AsyncMock,
        return_value=mock_tokens,
    ):
        callback = client.get(
            f"/api/a-cal/providers/{prov_id}/oauth/callback",
            params={"code": "x", "state": state},
            follow_redirects=False,
        )

    assert callback.status_code == 302
    assert "success" in callback.headers["location"]

    from a_cal.db.store import PersistentStore
    store = PersistentStore()
    provider = store.get_provider(prov_id)
    assert provider["config"]["oauth_tokens"]["access_token"] == "tok"
    assert "token_storage" not in provider["config"]

    client.delete(f"/api/a-cal/providers/{prov_id}")
    for s in client.get("/api/a-cal/sub-accounts").json():
        if s["id"] not in existing_subs:
            client.delete(f"/api/a-cal/sub-accounts/{s['id']}")


# ---------------------------------------------------------------------------
# Backend mode setting tests
# ---------------------------------------------------------------------------

def test_backend_mode_default_is_standalone():
    """Backend mode should default to 'standalone'."""
    from a_cal.api.agent_routes import _store

    # The default should be standalone
    mode = _store.get_backend_mode("test-user")
    assert mode == "standalone"


def test_backend_mode_can_be_set_to_atom():
    """Backend mode can be switched to 'atom'."""
    from a_cal.api.agent_routes import _store

    original = _store.get_backend_mode("test-user")
    try:
        _store.set_backend_mode("test-user", "atom")
        assert _store.get_backend_mode("test-user") == "atom"
    finally:
        _store.set_backend_mode("test-user", original)


def test_backend_mode_api_endpoints():
    """The backend mode API endpoints should work."""
    from a_cal.api.agent_routes import router as agent_router
    from a_cal.api.standalone_data import router as data_router

    app = FastAPI()
    app.include_router(data_router)
    app.include_router(agent_router)
    client = TestClient(app)

    # Get current mode
    resp = client.get("/api/a-cal/settings/backend-mode")
    assert resp.status_code == 200
    assert "mode" in resp.json()

    # Set to atom
    resp = client.post("/api/a-cal/settings/backend-mode", json={"mode": "atom"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "atom"

    # Set back to standalone
    resp = client.post("/api/a-cal/settings/backend-mode", json={"mode": "standalone"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "standalone"

    # Invalid mode should 400
    resp = client.post("/api/a-cal/settings/backend-mode", json={"mode": "invalid"})
    assert resp.status_code == 400


def test_atom_status_api_endpoint():
    """The atom status endpoint should return a valid status dict."""
    from a_cal.api.agent_routes import router as agent_router

    app = FastAPI()
    app.include_router(agent_router)
    client = TestClient(app)

    resp = client.get("/api/a-cal/settings/atom-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert "adapters" in data
    assert isinstance(data["available"], bool)
