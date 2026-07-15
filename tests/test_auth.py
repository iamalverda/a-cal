"""Tests for user authentication (register, login, logout, session).

Verifies the full auth flow: registration creates a user, login sets a
session cookie, subsequent requests carry the user ID via the contextvar,
and logout clears the session.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone import app


@pytest.fixture
def client():
    """Create a test client with the standalone app.

    Uses the in-memory SQLite database configured by conftest.py.
    Each test uses unique emails to avoid conflicts.
    """
    return TestClient(app)


@pytest.fixture
def unique_email():
    """Generate a unique email for each test to avoid duplicate conflicts."""
    import uuid
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


class TestPasswordHashing:
    """Test the password hashing utilities."""

    def test_hash_and_verify(self):
        """hash_password produces a verifiable hash."""
        from a_cal.auth.session import hash_password, verify_password

        h = hash_password("mysecret123")
        assert h.startswith("pbkdf2_sha256$")
        assert verify_password("mysecret123", h)
        assert not verify_password("wrong", h)

    def test_different_hashes_for_same_password(self):
        """Each hash is unique (random salt)."""
        from a_cal.auth.session import hash_password

        h1 = hash_password("samepass")
        h2 = hash_password("samepass")
        assert h1 != h2

    def test_verify_rejects_malformed_hash(self):
        """Malformed hash strings are rejected gracefully."""
        from a_cal.auth.session import verify_password

        assert not verify_password("pass", "not-a-valid-hash")
        assert not verify_password("pass", "wrong_algo$100$salt$hash")


class TestRegistration:
    """Test user registration."""

    def test_register_creates_user(self, client, unique_email):
        """Registration creates a user and sets a session."""
        resp = client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
            "display_name": "Test User",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == unique_email
        assert data["display_name"] == "Test User"
        assert data["is_active"] is True
        assert "id" in data

    def test_register_duplicate_email_409(self, client, unique_email):
        """Duplicate email registration returns 409."""
        payload = {
            "email": unique_email,
            "password": "securepass123",
        }
        client.post("/api/a-cal/auth/register", json=payload)
        resp = client.post("/api/a-cal/auth/register", json=payload)
        assert resp.status_code == 409

    def test_register_short_password_422(self, client, unique_email):
        """Password shorter than 8 chars is rejected (422 validation)."""
        resp = client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "short",
        })
        assert resp.status_code == 422


class TestLogin:
    """Test user login."""

    def test_login_success(self, client, unique_email):
        """Valid credentials log in successfully."""
        client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
        })
        resp = client.post("/api/a-cal/auth/login", json={
            "email": unique_email,
            "password": "securepass123",
        })
        assert resp.status_code == 200
        assert resp.json()["email"] == unique_email

    def test_login_wrong_password_401(self, client, unique_email):
        """Wrong password returns 401."""
        client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
        })
        resp = client.post("/api/a-cal/auth/login", json={
            "email": unique_email,
            "password": "incorrect",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user_401(self, client, unique_email):
        """Login for nonexistent user returns 401."""
        resp = client.post("/api/a-cal/auth/login", json={
            "email": unique_email,
            "password": "securepass123",
        })
        assert resp.status_code == 401


class TestSession:
    """Test session management."""

    def test_me_returns_user_when_logged_in(self, client, unique_email):
        """GET /me returns the logged-in user."""
        client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
            "display_name": "Me User",
        })
        resp = client.get("/api/a-cal/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == unique_email

    def test_me_returns_null_when_not_logged_in(self, client):
        """GET /me returns null when not authenticated."""
        resp = client.get("/api/a-cal/auth/me")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_logout_clears_session(self, client, unique_email):
        """Logout clears the session."""
        client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
        })
        # Verify logged in
        assert client.get("/api/a-cal/auth/me").json() is not None
        # Logout
        resp = client.post("/api/a-cal/auth/logout")
        assert resp.status_code == 200
        # Verify logged out
        assert client.get("/api/a-cal/auth/me").json() is None

    def test_session_carries_user_id_to_routes(self, client, unique_email):
        """User ID from session is available in route handlers via contextvar."""
        client.post("/api/a-cal/auth/register", json={
            "email": unique_email,
            "password": "securepass123",
        })
        # The /me endpoint reads from the DB using the session user_id.
        # If the contextvar weren't set, /me would return null.
        resp = client.get("/api/a-cal/auth/me")
        assert resp.json()["email"] == unique_email


class TestAuthContextvar:
    """Test that the contextvar-based user ID propagates to existing routes."""

    def test_contextvar_defaults_to_local_dev_user(self):
        """Without middleware, get_current_user_id returns the dev fallback."""
        from a_cal.auth.session import get_current_user_id
        # No active session in a bare test context -> the dev fallback.
        assert get_current_user_id() == "local-dev-user"

    def test_contextvar_set_and_reset(self):
        """set_current_user_id and reset_current_user_id work correctly."""
        from a_cal.auth.session import get_current_user_id, set_current_user_id, reset_current_user_id

        token = set_current_user_id("test-user-123")
        assert get_current_user_id() == "test-user-123"
        reset_current_user_id(token)
        assert get_current_user_id() == "local-dev-user"
