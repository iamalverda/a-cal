"""Tests for the atom integration bridge.

Covers:
  - is_atom_available() returns False when atom is not importable
  - get_atom_adapters() returns (None, None, None) without atom
  - mount_a_cal() mounts all routers into a FastAPI app
  - AtomTokenStorage raises ImportError when atom not available
  - AtomLLMAdapter raises ImportError when atom not available
  - AtomIntentClassifier raises ImportError when atom not available
  - Conductor gracefully handles no atom (keyword classification works)
  - OAuth callback falls back to SQLite when atom not available
  - _map_atom_intent maps atom categories to A-Cal IntentType
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.integrations.atom_bridge import (
    AtomIntentClassifier,
    AtomLLMAdapter,
    AtomTokenStorage,
    get_atom_adapters,
    is_atom_available,
)


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------

def test_is_atom_available_returns_bool():
    """is_atom_available should return a boolean (False in test env)."""
    result = is_atom_available()
    assert isinstance(result, bool)


def test_atom_not_available_in_test_env():
    """In the test environment, atom should not be importable."""
    assert is_atom_available() is False


def test_get_atom_adapters_returns_none_without_atom():
    """get_atom_adapters should return (None, None, None) without atom."""
    token, llm, intent = get_atom_adapters()
    assert token is None
    assert llm is None
    assert intent is None


# ---------------------------------------------------------------------------
# Adapter construction tests (should fail gracefully without atom)
# ---------------------------------------------------------------------------

def test_atom_token_storage_raises_without_atom():
    """AtomTokenStorage should raise ImportError when atom isn't available."""
    if is_atom_available():
        pytest.skip("atom is available — skip negative test")
    with pytest.raises(ImportError):
        AtomTokenStorage()


def test_atom_llm_adapter_raises_without_atom():
    """AtomLLMAdapter should raise ImportError when atom isn't available."""
    if is_atom_available():
        pytest.skip("atom is available — skip negative test")
    with pytest.raises(ImportError):
        AtomLLMAdapter()


def test_atom_intent_classifier_raises_without_atom():
    """AtomIntentClassifier should raise ImportError when atom isn't available."""
    if is_atom_available():
        pytest.skip("atom is available — skip negative test")
    with pytest.raises(ImportError):
        AtomIntentClassifier()


# ---------------------------------------------------------------------------
# Mount tests
# ---------------------------------------------------------------------------

def test_mount_a_cal_adds_routes():
    """mount_a_cal should add all A-Cal routers to a FastAPI app."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    mount_a_cal(app)

    client = TestClient(app)
    # Health is not part of A-Cal routes, but sub-accounts should be
    resp = client.get("/api/a-cal/sub-accounts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_mount_a_cal_route_count():
    """mount_a_cal should mount at least 6 routers (data, agents, swarm,
    marketplace, developer, oauth)."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    initial_count = len(app.routes)
    mount_a_cal(app)
    added = len(app.routes) - initial_count
    # 6 routers should be mounted (data, agents, swarm, marketplace, developer, oauth)
    assert added >= 6, f"Expected 6+ routers added, got {added}"


def test_mount_a_cal_oauth_endpoint_accessible():
    """After mounting, OAuth start endpoint should be accessible."""
    from a_cal.integrations.mount import mount_a_cal

    app = FastAPI()
    mount_a_cal(app)
    client = TestClient(app)

    # Nonexistent provider should return 404
    resp = client.get("/api/a-cal/providers/nonexistent/oauth/start")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Conductor fallback tests (keyword classification works without atom)
# ---------------------------------------------------------------------------

def test_conductor_keyword_classification_without_atom():
    """Conductor should classify intents using keywords when atom is absent."""
    from a_cal.agents.conductor import ACalConductor, IntentType

    conductor = ACalConductor()
    assert conductor.classify_intent("find a 30 min slot tomorrow") == IntentType.SCHEDULE
    assert conductor.classify_intent("sync my providers") == IntentType.SYNC
    assert conductor.classify_intent("check my inbox for invites") == IntentType.EMAIL
    assert conductor.classify_intent("hello there") == IntentType.CHAT


def test_conductor_atom_intent_is_none_without_atom():
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

def test_oauth_callback_stores_in_sqlite_without_atom():
    """OAuth callback should store tokens in SQLite config when atom is absent."""
    from a_cal.api.standalone_data import router as standalone_data_router
    from a_cal.api.oauth_routes import router as oauth_router, _atom_token_storage
    from unittest.mock import AsyncMock, patch

    # Verify atom token storage is None in test env
    assert _atom_token_storage is None

    app = FastAPI()
    app.include_router(standalone_data_router)
    app.include_router(oauth_router)
    client = TestClient(app)

    existing_subs = {s["id"] for s in client.get("/api/a-cal/sub-accounts").json()}
    existing_provs = {p["id"] for p in client.get("/api/a-cal/providers/all").json()}

    # Create a provider with OAuth credentials
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": "sa-main",
        "provider_type": "google_calendar",
        "provider_account_id": "test@gmail.com",
        "config": {"client_id": "test-id", "client_secret": "test-secret"},
    })
    prov_id = resp.json()["id"]

    # Start OAuth to get a state token
    start = client.get(f"/api/a-cal/providers/{prov_id}/oauth/start")
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    # Mock token exchange and verify tokens go to SQLite config
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

    # Verify tokens stored in SQLite (not atom)
    from a_cal.db.store import PersistentStore
    store = PersistentStore()
    provider = store.get_provider(prov_id)
    assert provider["config"]["oauth_tokens"]["access_token"] == "tok"
    assert "token_storage" not in provider["config"]  # no atom reference

    # Cleanup
    client.delete(f"/api/a-cal/providers/{prov_id}")
    for s in client.get("/api/a-cal/sub-accounts").json():
        if s["id"] not in existing_subs:
            client.delete(f"/api/a-cal/sub-accounts/{s['id']}")
