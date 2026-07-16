"""Tests for the hardened auth wall, session-secret enforcement, and
DB-backed brute-force lockout added for the public multi-user launch.

Covers:
  * AuthMiddleware 401s protected routes without a session.
  * The public allowlist still serves unauthenticated traffic.
  * Login lockout escalates after repeated failures.
  * The per-IP registration cap returns 429 past the limit.
  * The insecure dev session secret is refused at startup unless opted in.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from a_cal.api.standalone import app
from a_cal.auth.session import (
    assert_secure_session_secret,
    is_insecure_dev_secret,
    _lockout_seconds,
)


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a unique user and return its email."""
    email = email or f"wall-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/a-cal/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    assert resp.status_code == 200, resp.text
    return email


class TestAuthWall:
    """The auth wall blocks protected routes and allows the public allowlist."""

    def test_protected_route_401_without_session(self):
        """A protected route returns 401 when no session cookie is set."""
        client = TestClient(app)
        # /api/a-cal/teams is a protected route (not in the allowlist).
        resp = client.get("/api/a-cal/teams")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Not authenticated"}

    def test_health_is_public(self):
        """/health is on the allowlist and served without a session."""
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_marketplace_browse_is_public(self):
        """Public marketplace browsing works without a session."""
        client = TestClient(app)
        resp = client.get("/api/a-cal/marketplace/items")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_protected_route_passes_after_login(self):
        """A protected route returns 200 once a session is established."""
        client = TestClient(app)
        _register(client)
        resp = client.get("/api/a-cal/auth/me")
        assert resp.status_code == 200
        assert resp.json() is not None

    def test_openapi_is_public(self):
        """OpenAPI schema is served without a session."""
        client = TestClient(app)
        assert client.get("/openapi.json").status_code == 200


class TestLoginLockout:
    """Brute-force lockout escalates with repeated failures."""

    def test_lockout_tiers_escalate(self):
        """_lockout_seconds returns 0 below the threshold, then escalates."""
        assert _lockout_seconds(0) == 0
        assert _lockout_seconds(4) == 0
        assert _lockout_seconds(5) == 15
        assert _lockout_seconds(10) == 30
        assert _lockout_seconds(50) == 3600  # capped at 1h

    def test_login_locks_after_repeated_failures(self):
        """Repeated bad passwords produce a 429 after the threshold."""
        client = TestClient(app)
        email = _register(client)
        # Log the authed client out so we can hammer login anonymously.
        client.post("/api/a-cal/auth/logout")
        anon = TestClient(app)
        locked = False
        for _ in range(6):
            resp = anon.post(
                "/api/a-cal/auth/login",
                json={"email": email, "password": "wrong-password-1"},
            )
            if resp.status_code == 429:
                locked = True
                assert "Retry-After" in resp.headers
                break
        assert locked, "expected the account to lock after repeated failures"

    def test_successful_login_resets_counter(self):
        """A correct login clears the failure counter so no false lockout."""
        client = TestClient(app)
        email = _register(client)
        client.post("/api/a-cal/auth/logout")
        anon = TestClient(app)
        # One failure must NOT lock the account.
        bad = anon.post(
            "/api/a-cal/auth/login",
            json={"email": email, "password": "wrong"},
        )
        assert bad.status_code == 401
        good = anon.post(
            "/api/a-cal/auth/login",
            json={"email": email, "password": "securepass123"},
        )
        assert good.status_code == 200


class TestRegisterCap:
    """The per-IP registration cap returns 429 past the limit."""

    def test_register_cap_enforced(self, monkeypatch):
        """Registrations past A_CAL_REGISTER_MAX_PER_IP are rejected."""
        # The cap is read lazily from env, so a low value takes effect live.
        monkeypatch.setenv("A_CAL_REGISTER_MAX_PER_IP", "3")
        monkeypatch.setenv("A_CAL_REGISTER_WINDOW_HOURS", "24")
        client = TestClient(app)
        limited = False
        for i in range(5):
            resp = client.post(
                "/api/a-cal/auth/register",
                json={"email": f"cap-{uuid.uuid4().hex[:8]}-{i}@example.com",
                      "password": "securepass123"},
            )
            if resp.status_code == 429:
                limited = True
                break
        assert limited, "expected the per-IP registration cap to trigger"


class TestSessionSecretEnforcement:
    """The insecure dev session secret is refused at startup."""

    def test_dev_secret_refused(self, monkeypatch):
        """assert_secure_session_secret raises on the dev default."""
        monkeypatch.delenv("A_CAL_SESSION_SECRET", raising=False)
        monkeypatch.delenv("A_CAL_ALLOW_INSECURE_DEV_SECRET", raising=False)
        with pytest.raises(RuntimeError):
            assert_secure_session_secret()

    def test_real_secret_accepted(self, monkeypatch):
        """A real (non-dev) secret passes enforcement."""
        monkeypatch.setenv("A_CAL_SESSION_SECRET", "a-real-random-secret-value")
        monkeypatch.delenv("A_CAL_ALLOW_INSECURE_DEV_SECRET", raising=False)
        assert_secure_session_secret()  # must not raise

    def test_allow_flag_overrides(self, monkeypatch):
        """The dev default is allowed when the opt-in flag is set."""
        monkeypatch.delenv("A_CAL_SESSION_SECRET", raising=False)
        monkeypatch.setenv("A_CAL_ALLOW_INSECURE_DEV_SECRET", "1")
        assert is_insecure_dev_secret()
        assert_secure_session_secret()  # must not raise
