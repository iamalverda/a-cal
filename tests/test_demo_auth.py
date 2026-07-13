"""Tests for the demo auto-login flow in standalone mode."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Standalone server test client with a fresh in-memory DB."""
    from a_cal.api.standalone import app
    return TestClient(app)


class TestDemoAuth:
    """Demo auto-login for standalone/dev mode."""

    def test_me_returns_null_without_session(self, client):
        """GET /auth/me returns null when no session is active."""
        resp = client.get("/api/a-cal/auth/me")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_demo_login_creates_user_and_session(self, client):
        """POST /auth/demo-login creates a demo user and sets the session."""
        resp = client.post("/api/a-cal/auth/demo-login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "demo@acal.local"
        assert data["display_name"] == "Demo User"
        assert data["is_active"] is True
        assert "id" in data

    def test_me_returns_demo_user_after_demo_login(self, client):
        """GET /auth/me returns the demo user after demo-login sets the session."""
        client.post("/api/a-cal/auth/demo-login")
        resp = client.get("/api/a-cal/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["email"] == "demo@acal.local"

    def test_demo_login_is_idempotent(self, client):
        """Calling demo-login multiple times returns the same user."""
        r1 = client.post("/api/a-cal/auth/demo-login").json()
        r2 = client.post("/api/a-cal/auth/demo-login").json()
        assert r1["id"] == r2["id"]
        assert r1["email"] == r2["email"]

    def test_logout_clears_demo_session(self, client):
        """POST /auth/logout clears the session even after demo login."""
        client.post("/api/a-cal/auth/demo-login")
        assert client.get("/api/a-cal/auth/me").json() is not None
        client.post("/api/a-cal/auth/logout")
        assert client.get("/api/a-cal/auth/me").json() is None

    def test_demo_login_then_real_register(self, client):
        """A real user can register even after the demo user exists."""
        resp = client.post("/api/a-cal/auth/register", json={
            "email": "realuser@test.com",
            "password": "testpassword123",
            "display_name": "Real User",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "realuser@test.com"
        assert data["display_name"] == "Real User"
        # The session should now be the real user, not the demo user
        me = client.get("/api/a-cal/auth/me").json()
        assert me["email"] == "realuser@test.com"
