"""HTTP-level cross-user isolation tests (P1-3).

Registers two real users via the auth API and verifies over HTTP that
user B cannot read or mutate user A's data for every user-scoped resource.
This is the regression guard for the AuthMiddleware contextvar fix — if the
middleware is reverted to BaseHTTPMiddleware, these tests will fail because
the contextvar won't propagate to route handlers.
"""

from __future__ import annotations

import datetime
from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient

from a_cal.api.standalone import app
from a_cal.db.store import PersistentStore

# Two registered users with their own session cookies.
_USERS = [
    {"email": "alice@acal.example", "password": "alice_pass_123", "name": "Alice"},
    {"email": "bob@acal.example", "password": "bob_pass_45678", "name": "Bob"},
]


def _patch_stores(db: PersistentStore) -> dict:
    """Patch every route module's store to use ``db`` and return originals."""
    from a_cal.api import (
        standalone_data,
        booking_routes,
        analytics_routes,
        team_routes,
        graphql_routes,
        oauth_routes,
        agent_routes,
    )
    originals = {
        "standalone_data": standalone_data._store,
        "booking": booking_routes._db,
        "analytics": analytics_routes._db,
        "team": team_routes._db,
        "graphql": graphql_routes._db,
        "oauth": oauth_routes._store,
        "agent_store_db": agent_routes._store._db,
    }
    standalone_data._store = db
    booking_routes._db = db
    analytics_routes._db = db
    team_routes._db = db
    graphql_routes._db = db
    oauth_routes._store = db
    agent_routes._store._db = db
    return originals


def _restore_stores(originals: dict) -> None:
    """Restore original store references."""
    from a_cal.api import (
        standalone_data,
        booking_routes,
        analytics_routes,
        team_routes,
        graphql_routes,
        oauth_routes,
        agent_routes,
    )
    standalone_data._store = originals["standalone_data"]
    booking_routes._db = originals["booking"]
    analytics_routes._db = originals["analytics"]
    team_routes._db = originals["team"]
    graphql_routes._db = originals["graphql"]
    oauth_routes._store = originals["oauth"]
    agent_routes._store._db = originals["agent_store_db"]


@pytest.fixture
def two_clients():
    """Provide two logged-in TestClients (alice + bob) backed by one store."""
    db = PersistentStore(in_memory=True)
    originals = _patch_stores(db)
    # Two separate clients → independent cookie jars → independent sessions.
    ca = TestClient(app)
    cb = TestClient(app)
    try:
        for u in _USERS:
            r = ca.post("/api/a-cal/auth/register", json={
                "email": u["email"], "password": u["password"], "display_name": u["name"],
            })
            # 409 is fine (already registered from a previous test in same session)
            assert r.status_code in (200, 409), r.text
        # Log in each client as a different user.
        ca.post("/api/a-cal/auth/login", json={
            "email": _USERS[0]["email"], "password": _USERS[0]["password"],
        })
        cb.post("/api/a-cal/auth/login", json={
            "email": _USERS[1]["email"], "password": _USERS[1]["password"],
        })
        yield ca, cb
    finally:
        _restore_stores(originals)


def _alice_id(ca: TestClient) -> str:
    return ca.get("/api/a-cal/auth/me").json()["id"]


def _bob_id(cb: TestClient) -> str:
    return cb.get("/api/a-cal/auth/me").json()["id"]


# --- Sub-accounts ----------------------------------------------------------

class TestSubAccountHttpIsolation:
    """User B cannot read or mutate user A's sub-accounts over HTTP."""

    def test_b_cannot_list_a_subaccount(self, two_clients):
        ca, cb = two_clients
        ca.post("/api/a-cal/sub-accounts", json={"name": "Alice Cal", "kind": "calendar"})

        b_list = cb.get("/api/a-cal/sub-accounts").json()
        assert all(s["name"] != "Alice Cal" for s in b_list)

    def test_b_cannot_delete_a_subaccount(self, two_clients):
        ca, cb = two_clients
        r = ca.post("/api/a-cal/sub-accounts", json={"name": "Alice Private", "kind": "calendar"})
        sid = r.json()["id"]

        del_r = cb.delete(f"/api/a-cal/sub-accounts/{sid}")
        # Should return 404 or not-found since B can't see A's sub-account
        assert del_r.status_code in (404, 200)
        # A can still see it
        a_list = ca.get("/api/a-cal/sub-accounts").json()
        assert any(s["id"] == sid for s in a_list)

    def test_b_cannot_patch_a_subaccount(self, two_clients):
        ca, cb = two_clients
        r = ca.post("/api/a-cal/sub-accounts", json={"name": "Alice Main", "kind": "calendar"})
        sid = r.json()["id"]

        cb.patch(f"/api/a-cal/sub-accounts/{sid}", json={"name": "Hacked"})
        a_list = ca.get("/api/a-cal/sub-accounts").json()
        target = [s for s in a_list if s["id"] == sid][0]
        assert target["name"] == "Alice Main"


# --- Calendar events ------------------------------------------------------

class TestEventHttpIsolation:
    """User B cannot read or delete user A's calendar events over HTTP."""

    def test_b_cannot_list_a_events(self, two_clients):
        ca, cb = two_clients
        now = datetime.datetime.now(UTC)
        ca.post("/api/a-cal/calendar/events", json={
            "title": "Alice Secret Meeting",
            "start": (now + timedelta(days=1)).isoformat(),
            "end": (now + timedelta(days=1, hours=1)).isoformat(),
        })

        b_events = cb.get("/api/a-cal/calendar/events").json()
        assert all(e.get("title") != "Alice Secret Meeting" for e in b_events)

    def test_b_cannot_delete_a_event(self, two_clients):
        ca, cb = two_clients
        now = datetime.datetime.now(UTC)
        r = ca.post("/api/a-cal/calendar/events", json={
            "title": "Alice Lunch",
            "start": (now + timedelta(days=2)).isoformat(),
            "end": (now + timedelta(days=2, hours=1)).isoformat(),
        })
        eid = r.json()["provider_event_id"]

        cb.delete(f"/api/a-cal/calendar/events/{eid}")
        a_events = ca.get("/api/a-cal/calendar/events").json()
        assert any(e["provider_event_id"] == eid for e in a_events)


# --- Event types + bookings -----------------------------------------------

class TestEventTypeHttpIsolation:
    """User B cannot read or mutate user A's event types or bookings."""

    def test_b_cannot_list_a_event_types(self, two_clients):
        ca, cb = two_clients
        # Event types are created via the booking route module
        r = ca.post("/api/a-cal/event-types", json={
            "title": "Alice Consult", "slug": "alice-consult",
            "duration_minutes": 30, "min_notice_hours": 0,
        })
        assert r.status_code == 200, r.text
        a_et_id = r.json()["id"]

        b_ets = cb.get("/api/a-cal/event-types").json()
        assert all(et["id"] != a_et_id for et in b_ets)

    def test_b_cannot_patch_a_event_type(self, two_clients):
        ca, cb = two_clients
        r = ca.post("/api/a-cal/event-types", json={
            "title": "Alice Call", "slug": "alice-call",
            "duration_minutes": 15, "min_notice_hours": 0,
        })
        et_id = r.json()["id"]

        cb.put(f"/api/a-cal/event-types/{et_id}", json={
            "title": "Hacked", "slug": "alice-call",
            "duration_minutes": 15, "min_notice_hours": 0,
        })
        a_ets = ca.get("/api/a-cal/event-types").json()
        target = [et for et in a_ets if et["id"] == et_id][0]
        assert target["title"] == "Alice Call"

    def test_b_cannot_list_a_bookings(self, two_clients):
        """User B's booking list does not include user A's bookings."""
        ca, cb = two_clients
        # Create an event type and a booking as Alice
        et_r = ca.post("/api/a-cal/event-types", json={
            "title": "Alice Intro", "slug": "alice-intro",
            "duration_minutes": 30, "min_notice_hours": 0,
        })
        et_id = et_r.json()["id"]
        now = datetime.datetime.now(UTC)
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        # Public booking (no auth) — but we'll do it as Alice
        ca.post("/api/a-cal/booking/alice-intro", json={
            "attendee_name": "Attendee",
            "attendee_email": "att@example.com",
            "attendee_timezone": "UTC",
            "start_time": f"{tomorrow}T10:00:00Z",
            "answers": [],
        })

        b_bookings = cb.get("/api/a-cal/bookings").json()
        assert all(b.get("event_type_id") != et_id for b in b_bookings)


# --- Self-model facts -----------------------------------------------------

class TestSelfModelHttpIsolation:
    """User B cannot read or delete user A's self-model facts."""

    def test_b_cannot_read_a_facts(self, two_clients, tmp_path):
        """Facts are stored per-user; B's fact list excludes A's facts."""
        import tempfile
        from a_cal.self_model.store import SelfModelStore
        from a_cal.self_model.types import SelfModelFact
        from a_cal.api import agent_routes

        ca, cb = two_clients
        alice_id = _alice_id(ca)

        # Patch _sm_data_dir to a temp directory for file-based facts.
        old_dir = agent_routes._sm_data_dir
        agent_routes._sm_data_dir = str(tmp_path / "sm")
        try:
            fact = SelfModelFact(
                id="alice-fact-1",
                content="Alice prefers mornings",
                category="preference",
                confidence=0.9,
                provenance="test",
            )
            SelfModelStore(user_id=alice_id, data_dir=agent_routes._sm_data_dir).upsert(fact)

            # Alice sees her fact
            a_facts = ca.get("/api/a-cal/self-model/facts").json()
            assert any(f.get("id") == "alice-fact-1" for f in a_facts)

            # Bob does not see Alice's fact
            b_facts = cb.get("/api/a-cal/self-model/facts").json()
            assert all(f.get("id") != "alice-fact-1" for f in b_facts)
        finally:
            agent_routes._sm_data_dir = old_dir

    def test_b_cannot_delete_a_fact(self, two_clients, tmp_path):
        """B's DELETE on A's fact returns 404; A's fact is preserved."""
        from a_cal.self_model.store import SelfModelStore
        from a_cal.self_model.types import SelfModelFact
        from a_cal.api import agent_routes

        ca, cb = two_clients
        alice_id = _alice_id(ca)

        old_dir = agent_routes._sm_data_dir
        agent_routes._sm_data_dir = str(tmp_path / "sm")
        try:
            fact = SelfModelFact(
                id="alice-fact-2",
                content="Alice likes Python",
                category="preference",
                confidence=0.9,
                provenance="test",
            )
            SelfModelStore(user_id=alice_id, data_dir=agent_routes._sm_data_dir).upsert(fact)

            # Bob tries to delete Alice's fact — gets 404 (not found for B)
            r = cb.delete("/api/a-cal/self-model/facts/alice-fact-2")
            assert r.status_code == 404

            # Alice can still see the fact
            a_facts = ca.get("/api/a-cal/self-model/facts").json()
            assert any(f.get("id") == "alice-fact-2" for f in a_facts)
        finally:
            agent_routes._sm_data_dir = old_dir


# --- Email labels ---------------------------------------------------------

class TestEmailLabelHttpIsolation:
    """User B cannot read or delete user A's email labels."""

    def test_b_cannot_see_a_labels(self, two_clients):
        ca, cb = two_clients
        ca.post("/api/a-cal/email/labels", json={"name": "Alice Label", "color": "#f00"})

        b_labels = cb.get("/api/a-cal/email/labels").json()
        assert all(lbl.get("name") != "Alice Label" for lbl in b_labels)

    def test_b_cannot_delete_a_label(self, two_clients):
        ca, cb = two_clients
        r = ca.post("/api/a-cal/email/labels", json={"name": "Alice VIP", "color": "#0f0"})
        label_id = r.json().get("id", "")

        cb.delete(f"/api/a-cal/email/labels/{label_id}")
        a_labels = ca.get("/api/a-cal/email/labels").json()
        assert any(lbl.get("name") == "Alice VIP" for lbl in a_labels)


# --- Analytics ------------------------------------------------------------

class TestAnalyticsHttpIsolation:
    """User B's analytics do not include user A's data."""

    def test_b_analytics_empty_for_a(self, two_clients):
        ca, cb = two_clients
        # Create an event as Alice
        now = datetime.datetime.now(UTC)
        ca.post("/api/a-cal/calendar/events", json={
            "title": "Alice Analytics Event",
            "start": (now + timedelta(days=1)).isoformat(),
            "end": (now + timedelta(days=1, hours=1)).isoformat(),
        })

        # Bob's analytics should not reference Alice's events
        r = cb.get("/api/a-cal/analytics/summary")
        if r.status_code == 200:
            data = r.json()
            # The summary should not contain Alice's event data
            assert "Alice Analytics Event" not in str(data)
