"""Shared test helper: an authenticated TestClient for the standalone app.

The auth wall (AuthMiddleware) 401s protected routes without a session, so
tests that exercise protected endpoints need a logged-in client. This
registers a unique user and returns a client carrying the session cookie.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def make_authed_client() -> TestClient:
    """Return a TestClient authenticated against the standalone app."""
    from a_cal.api.standalone import app

    client = TestClient(app)
    email = f"auth-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/a-cal/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    assert resp.status_code == 200, resp.text
    return client
