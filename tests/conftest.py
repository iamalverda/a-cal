"""Pytest config -- make the a_cal package importable without atom installed.

Sets A_CAL_DB_PATH=:memory: so tests use an in-memory SQLite database
instead of the persistent file-based database.

Also opts the test suite into the insecure dev session secret
(A_CAL_ALLOW_INSECURE_DEV_SECRET=1) and enables the demo-login route
(A_CAL_ENABLE_DEMO=1) so tests can exercise the auth wall + OAuth flow
without configuring a strong secret. These are set BEFORE any test module
imports ``a_cal.api.standalone`` (pytest loads conftest first).
"""
import os
import sys

# In-memory database for tests.
os.environ["A_CAL_DB_PATH"] = ":memory:"

# Tests use the public dev secret; the startup enforcement must allow it.
os.environ.setdefault("A_CAL_ALLOW_INSECURE_DEV_SECRET", "1")

# The demo-login route is gated behind this flag; enable it for the suite so
# test_demo_auth.py and fixtures can mint an authenticated session.
os.environ.setdefault("A_CAL_ENABLE_DEMO", "1")

# Tests register many users from a single TestClient IP; raise the signup
# cap so the per-IP rate limiter doesn't 429 the suite mid-run.
os.environ.setdefault("A_CAL_REGISTER_MAX_PER_IP", "100000")

_pkg_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import pytest  # noqa: E402


@pytest.fixture
def authed_client():
    """A TestClient with an authenticated session cookie set.

    Registers a unique user via the public register endpoint and returns the
    client with its cookie jar carrying the session. Use this for any test
    that hits a protected route (i.e. anything outside the public allowlist).
    """
    import uuid

    from fastapi.testclient import TestClient

    from a_cal.api.standalone import app

    client = TestClient(app)
    email = f"authed-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/a-cal/auth/register",
        json={"email": email, "password": "securepass123", "display_name": "Authed User"},
    )
    assert resp.status_code == 200, resp.text
    return client
