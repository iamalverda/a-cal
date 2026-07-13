"""Tests for Phase 5 (Team & Payments) and Phase 6 (Developer & Platform).

Covers:
- Team CRUD and team member management
- Round-robin member assignment
- Routing form CRUD
- Webhook CRUD, delivery, and test dispatch
- Payment config and payment intent creation (mock mode)
- Paid event type booking flow
- Custom domain configuration
- Workflow trigger configuration
- GraphQL query API and schema introspection
- Webhook delivery history
"""

from __future__ import annotations

import datetime
from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient

from a_cal.api.standalone import app
from a_cal.db.store import PersistentStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    """Log in as demo user for authenticated endpoints."""
    client.post("/api/a-cal/auth/demo-login")
    yield


@pytest.fixture(autouse=True)
def _clean_db():
    """Patch all route modules to use a fresh in-memory store."""
    db = PersistentStore(in_memory=True)
    from a_cal.api import booking_routes, analytics_routes, team_routes, graphql_routes
    from a_cal.integrations import webhooks as webhook_mod
    from a_cal.integrations import payments as payments_mod
    originals = {
        "booking": booking_routes._db,
        "analytics": analytics_routes._db,
        "team": team_routes._db,
        "graphql": graphql_routes._db,
        "webhook_store": webhook_mod._store,
        "payments": team_routes._payments,
    }
    booking_routes._db = db
    analytics_routes._db = db
    team_routes._db = db
    graphql_routes._db = db
    webhook_mod._store = db
    yield db
    booking_routes._db = originals["booking"]
    analytics_routes._db = originals["analytics"]
    team_routes._db = originals["team"]
    graphql_routes._db = originals["graphql"]
    webhook_mod._store = originals["webhook_store"]
    team_routes._payments = originals["payments"]


# --- Team CRUD -------------------------------------------------------------

class TestTeams:
    """Team creation, retrieval, update, and deletion."""

    def test_create_team(self):
        """POST /teams creates a team with auto-generated slug."""
        r = client.post("/api/a-cal/teams", json={"name": "Engineering", "description": "Eng team"})
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Engineering"
        assert data["slug"] == "engineering"
        assert data["id"]

    def test_list_teams(self):
        """GET /teams returns all teams."""
        client.post("/api/a-cal/teams", json={"name": "Sales"})
        client.post("/api/a-cal/teams", json={"name": "Support"})
        r = client.get("/api/a-cal/teams")
        assert r.status_code == 200
        teams = r.json()
        assert len(teams) >= 2
        names = [t["name"] for t in teams]
        assert "Sales" in names
        assert "Support" in names

    def test_get_team_with_members(self):
        """GET /teams/{id} returns team with members list."""
        r = client.post("/api/a-cal/teams", json={"name": "Design"})
        team_id = r.json()["id"]
        client.post(f"/api/a-cal/teams/{team_id}/members", json={"email": "designer@example.com", "display_name": "Alice"})
        r = client.get(f"/api/a-cal/teams/{team_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Design"
        assert len(data["members"]) == 1
        assert data["members"][0]["email"] == "designer@example.com"

    def test_update_team(self):
        """PATCH /teams/{id} updates team fields."""
        r = client.post("/api/a-cal/teams", json={"name": "Old Name"})
        team_id = r.json()["id"]
        r = client.patch(f"/api/a-cal/teams/{team_id}", json={"name": "New Name", "slug": "new-slug"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"
        assert r.json()["slug"] == "new-slug"

    def test_delete_team(self):
        """DELETE /teams/{id} removes the team."""
        r = client.post("/api/a-cal/teams", json={"name": "Temp"})
        team_id = r.json()["id"]
        r = client.delete(f"/api/a-cal/teams/{team_id}")
        assert r.status_code == 200
        r = client.get(f"/api/a-cal/teams/{team_id}")
        assert r.status_code == 404

    def test_get_team_not_found(self):
        """GET /teams/{id} returns 404 for unknown team."""
        r = client.get("/api/a-cal/teams/nonexistent-id")
        assert r.status_code == 404


# --- Team Members ----------------------------------------------------------

class TestTeamMembers:
    """Team member management and round-robin assignment."""

    def test_add_member(self):
        """POST /teams/{id}/members adds a member."""
        r = client.post("/api/a-cal/teams", json={"name": "Team A"})
        team_id = r.json()["id"]
        r = client.post(f"/api/a-cal/teams/{team_id}/members", json={
            "email": "member@example.com",
            "display_name": "Bob",
            "role": "admin",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "member@example.com"
        assert data["role"] == "admin"
        assert data["is_active"] is True

    def test_update_member(self):
        """PATCH /teams/members/{id} updates member fields."""
        r = client.post("/api/a-cal/teams", json={"name": "Team B"})
        team_id = r.json()["id"]
        r = client.post(f"/api/a-cal/teams/{team_id}/members", json={"email": "c@example.com"})
        member_id = r.json()["id"]
        r = client.patch(f"/api/a-cal/teams/{team_id}/members/{member_id}", json={"role": "admin", "is_active": False})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
        assert r.json()["is_active"] is False

    def test_remove_member(self):
        """DELETE /teams/{id}/members/{mid} removes a member."""
        r = client.post("/api/a-cal/teams", json={"name": "Team C"})
        team_id = r.json()["id"]
        r = client.post(f"/api/a-cal/teams/{team_id}/members", json={"email": "d@example.com"})
        member_id = r.json()["id"]
        r = client.delete(f"/api/a-cal/teams/{team_id}/members/{member_id}")
        assert r.status_code == 200

    def test_round_robin_assignment(self):
        """get_next_round_robin_member picks the member with fewest bookings."""
        db = PersistentStore(in_memory=True)
        team = db.create_team({"name": "RR Team", "slug": "rr"})
        team_id = team["id"]
        m1 = db.add_team_member({"team_id": team_id, "email": "m1@x.com"})
        m2 = db.add_team_member({"team_id": team_id, "email": "m2@x.com"})
        m3 = db.add_team_member({"team_id": team_id, "email": "m3@x.com"})

        # First call should pick the oldest member (m1, all have 0 bookings)
        chosen = db.get_next_round_robin_member(team_id)
        assert chosen is not None
        assert chosen["email"] == "m1@x.com"

        # Create a real event type for the booking
        et = db.create_event_type({"title": "RR Event", "slug": "rr-event", "duration_minutes": 30})

        # Simulate m1 having a booking
        now = datetime.datetime.now(UTC)
        db.create_booking({
            "event_type_id": et["id"],
            "attendee_name": "Test",
            "attendee_email": "t@x.com",
            "attendee_timezone": "UTC",
            "start_time": now,
            "end_time": now + timedelta(minutes=30),
            "status": "confirmed",
            "assigned_member_id": m1["id"],
        })

        # Now m2 should be picked (0 bookings, oldest among remaining)
        chosen = db.get_next_round_robin_member(team_id)
        assert chosen["email"] == "m2@x.com"


# --- Routing Forms ---------------------------------------------------------

class TestRoutingForms:
    """Routing form CRUD operations."""

    def test_create_routing_form(self):
        """POST /routing-forms creates a form with questions and rules."""
        r = client.post("/api/a-cal/routing-forms", json={
            "name": "Sales Routing",
            "description": "Route to the right rep",
            "questions": [
                {"id": "q1", "label": "Product interest?", "type": "select", "required": True, "options": ["A", "B"]}
            ],
            "routing_rules": [
                {"condition": "A", "event_type_id": "et-1", "member_id": None}
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Sales Routing"
        assert len(data["questions"]) == 1
        assert len(data["routing_rules"]) == 1
        assert data["is_active"] is True

    def test_list_routing_forms(self):
        """GET /routing-forms returns all forms."""
        client.post("/api/a-cal/routing-forms", json={"name": "Form 1"})
        client.post("/api/a-cal/routing-forms", json={"name": "Form 2"})
        r = client.get("/api/a-cal/routing-forms")
        assert r.status_code == 200
        forms = r.json()
        assert len(forms) >= 2

    def test_update_routing_form(self):
        """PATCH /routing-forms/{id} updates form fields."""
        r = client.post("/api/a-cal/routing-forms", json={"name": "Old"})
        form_id = r.json()["id"]
        r = client.patch(f"/api/a-cal/routing-forms/{form_id}", json={"name": "New", "is_active": False})
        assert r.status_code == 200
        assert r.json()["name"] == "New"
        assert r.json()["is_active"] is False

    def test_delete_routing_form(self):
        """DELETE /routing-forms/{id} removes the form."""
        r = client.post("/api/a-cal/routing-forms", json={"name": "Temp"})
        form_id = r.json()["id"]
        r = client.delete(f"/api/a-cal/routing-forms/{form_id}")
        assert r.status_code == 200
        r = client.get(f"/api/a-cal/routing-forms/{form_id}")
        assert r.status_code == 404


# --- Webhooks --------------------------------------------------------------

class TestWebhooks:
    """Webhook CRUD, delivery, and test dispatch."""

    def test_create_webhook(self):
        """POST /webhooks creates a webhook with auto-generated secret."""
        r = client.post("/api/a-cal/webhooks", json={
            "url": "https://example.com/hook",
            "events": ["booking.created", "booking.cancelled"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["url"] == "https://example.com/hook"
        assert "booking.created" in data["events"]
        assert data["secret"]  # auto-generated
        assert data["is_active"] is True

    def test_list_webhooks(self):
        """GET /webhooks returns all webhooks."""
        client.post("/api/a-cal/webhooks", json={"url": "https://a.com/hook", "events": ["*"]})
        client.post("/api/a-cal/webhooks", json={"url": "https://b.com/hook", "events": ["booking.created"]})
        r = client.get("/api/a-cal/webhooks")
        assert r.status_code == 200
        hooks = r.json()
        assert len(hooks) >= 2

    def test_update_webhook(self):
        """PATCH /webhooks/{id} updates webhook fields."""
        r = client.post("/api/a-cal/webhooks", json={"url": "https://old.com/hook", "events": ["*"]})
        hook_id = r.json()["id"]
        r = client.patch(f"/api/a-cal/webhooks/{hook_id}", json={"is_active": False, "url": "https://new.com/hook"})
        assert r.status_code == 200
        assert r.json()["is_active"] is False
        assert r.json()["url"] == "https://new.com/hook"

    def test_delete_webhook(self):
        """DELETE /webhooks/{id} removes the webhook."""
        r = client.post("/api/a-cal/webhooks", json={"url": "https://temp.com/hook", "events": ["*"]})
        hook_id = r.json()["id"]
        r = client.delete(f"/api/a-cal/webhooks/{hook_id}")
        assert r.status_code == 200

    def test_test_webhook_dispatch(self):
        """POST /webhooks/test dispatches a test event to active webhooks."""
        client.post("/api/a-cal/webhooks", json={"url": "https://example.com/hook", "events": ["*"]})
        r = client.post("/api/a-cal/webhooks/test", json={"event": "test.event", "payload": {"test": True}})
        assert r.status_code == 200
        data = r.json()
        assert "dispatched" in data
        assert "deliveries" in data

    def test_webhook_deliveries_history(self):
        """GET /webhooks/{id}/deliveries returns delivery history."""
        r = client.post("/api/a-cal/webhooks", json={"url": "https://x.com/hook", "events": ["*"]})
        hook_id = r.json()["id"]
        r = client.get(f"/api/a-cal/webhooks/{hook_id}/deliveries")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# --- Payments --------------------------------------------------------------

class TestPayments:
    """Payment configuration and payment intent creation."""

    def test_payment_config_mock_mode(self):
        """GET /payments/config returns mock mode without Stripe keys."""
        r = client.get("/api/a-cal/payments/config")
        assert r.status_code == 200
        data = r.json()
        assert data["is_mock"] is True
        assert data["is_configured"] is False

    def test_create_payment_intent_for_paid_event(self):
        """POST /payments/intent creates a mock intent for a paid event type."""
        # Create a paid event type
        et = client.post("/api/a-cal/event-types", json={
            "title": "Paid Consultation",
            "slug": "paid-consult",
            "duration_minutes": 60,
            "is_paid": True,
            "price_cents": 5000,
            "currency": "USD",
        })
        assert et.status_code == 200
        et_id = et.json()["id"]

        r = client.post("/api/a-cal/payments/intent", json={
            "event_type_id": et_id,
            "metadata": {"customer": "test@example.com"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["amount"] == 5000
        assert data["status"] == "requires_confirmation"
        assert "client_secret" in data

    def test_payment_intent_free_event_rejected(self):
        """POST /payments/intent returns 400 for a free event type."""
        et = client.post("/api/a-cal/event-types", json={
            "title": "Free Chat",
            "slug": "free-chat",
            "is_paid": False,
        })
        et_id = et.json()["id"]
        r = client.post("/api/a-cal/payments/intent", json={"event_type_id": et_id})
        assert r.status_code == 400

    def test_confirm_payment_mock(self):
        """POST /payments/confirm/{id} returns succeeded in mock mode."""
        r = client.post("/api/a-cal/payments/confirm/pi_mock_123")
        assert r.status_code == 200
        assert r.json()["status"] == "succeeded"

    def test_paid_event_type_fields(self):
        """Event types store Phase 5 payment fields."""
        r = client.post("/api/a-cal/event-types", json={
            "title": "Premium",
            "slug": "premium",
            "is_paid": True,
            "price_cents": 10000,
            "currency": "EUR",
            "assignment_strategy": "round_robin",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_paid"] is True
        assert data["price_cents"] == 10000
        assert data["currency"] == "EUR"
        assert data["assignment_strategy"] == "round_robin"


# --- Paid Booking Flow -----------------------------------------------------

class TestPaidBookingFlow:
    """Booking flow for paid event types includes payment status."""

    def test_paid_booking_returns_pending_payment(self):
        """Public booking on a paid event type returns pending_payment status."""
        client.post("/api/a-cal/event-types", json={
            "title": "Paid Session",
            "slug": "paid-session",
            "duration_minutes": 30,
            "is_paid": True,
            "price_cents": 2500,
        })
        r = client.post("/api/a-cal/booking/paid-session", json={
            "attendee_name": "Client",
            "attendee_email": "client@example.com",
            "attendee_timezone": "America/Chicago",
            "start_time": "2026-07-14T14:00:00",
            "end_time": "2026-07-14T14:30:00",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending_payment"
        assert data["payment_status"] == "pending_payment"
        assert data["price_cents"] == 2500

    def test_free_booking_returns_confirmed(self):
        """Public booking on a free event type returns confirmed status."""
        client.post("/api/a-cal/event-types", json={
            "title": "Free Session",
            "slug": "free-session",
            "duration_minutes": 30,
            "is_paid": False,
        })
        r = client.post("/api/a-cal/booking/free-session", json={
            "attendee_name": "Client",
            "attendee_email": "client@example.com",
            "attendee_timezone": "America/Chicago",
            "start_time": "2026-07-14T14:00:00",
            "end_time": "2026-07-14T14:30:00",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "confirmed"
        assert data["payment_status"] == "paid"


# --- Custom Domain ---------------------------------------------------------

class TestCustomDomain:
    """Custom domain configuration for booking pages."""

    def test_get_default_domain(self):
        """GET /platform/domain returns empty default."""
        r = client.get("/api/a-cal/platform/domain")
        assert r.status_code == 200
        data = r.json()
        assert data["domain"] == ""

    def test_set_custom_domain(self):
        """PUT /platform/domain sets the custom domain."""
        r = client.put("/api/a-cal/platform/domain", json={
            "domain": "book.mycompany.com",
            "is_active": True,
            "ssl_verified": False,
        })
        assert r.status_code == 200
        assert r.json()["domain"] == "book.mycompany.com"
        assert r.json()["is_active"] is True

        r = client.get("/api/a-cal/platform/domain")
        assert r.json()["domain"] == "book.mycompany.com"


# --- Workflow Triggers -----------------------------------------------------

class TestWorkflowTriggers:
    """Workflow trigger configuration."""

    def test_get_default_triggers(self):
        """GET /workflow-triggers returns default config."""
        r = client.get("/api/a-cal/workflow-triggers")
        assert r.status_code == 200
        data = r.json()
        assert data["booking_created"] is True
        assert data["booking_cancelled"] is True
        assert data["booking_rescheduled"] is True

    def test_set_workflow_triggers(self):
        """PUT /workflow-triggers updates trigger config."""
        r = client.put("/api/a-cal/workflow-triggers", json={
            "booking_created": True,
            "booking_cancelled": False,
            "booking_rescheduled": True,
        })
        assert r.status_code == 200
        assert r.json()["booking_cancelled"] is False

        r = client.get("/api/a-cal/workflow-triggers")
        assert r.json()["booking_cancelled"] is False


# --- GraphQL API -----------------------------------------------------------

class TestGraphQL:
    """GraphQL query API and schema introspection."""

    def test_query_event_types(self):
        """GraphQL query for eventTypes returns projected fields."""
        client.post("/api/a-cal/event-types", json={"title": "GraphQL Test", "slug": "gql-test"})
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ eventTypes { id title slug } }",
        })
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert "eventTypes" in data["data"]
        assert len(data["data"]["eventTypes"]) >= 1
        et = data["data"]["eventTypes"][0]
        assert "id" in et
        assert "title" in et
        assert "slug" in et

    def test_query_teams(self):
        """GraphQL query for teams returns projected fields."""
        client.post("/api/a-cal/teams", json={"name": "GraphQL Team"})
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ teams { id name slug } }",
        })
        assert r.status_code == 200
        data = r.json()
        assert "teams" in data["data"]
        assert len(data["data"]["teams"]) >= 1

    def test_query_with_arguments(self):
        """GraphQL query with arguments (limit) works."""
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ events(limit: 7) { id title } }",
        })
        assert r.status_code == 200
        data = r.json()
        assert "events" in data["data"]

    def test_query_single_event_type(self):
        """GraphQL query for a single eventType by id."""
        et = client.post("/api/a-cal/event-types", json={"title": "Single", "slug": "single"})
        et_id = et.json()["id"]
        r = client.post("/api/a-cal/graphql", json={
            "query": f'{{ eventType(id: "{et_id}") {{ id title }} }}',
        })
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["eventType"] is not None
        assert data["data"]["eventType"]["title"] == "Single"

    def test_graphql_unknown_field_returns_error(self):
        """GraphQL query for unknown field returns an error."""
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ unknownField { id } }",
        })
        assert r.status_code == 200
        data = r.json()
        assert "errors" in data

    def test_graphql_schema_endpoint(self):
        """GET /graphql/schema returns schema introspection."""
        r = client.get("/api/a-cal/graphql/schema")
        assert r.status_code == 200
        data = r.json()
        assert "types" in data
        assert "Query" in data["types"]
        assert "Event" in data["types"]
        assert "Booking" in data["types"]
        assert "Team" in data["types"]

    def test_graphql_field_projection(self):
        """GraphQL only returns requested fields, not all fields."""
        client.post("/api/a-cal/event-types", json={"title": "Projection Test", "slug": "proj-test"})
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ eventTypes { title } }",
        })
        data = r.json()
        et = data["data"]["eventTypes"][0]
        assert "title" in et
        assert "slug" not in et
        assert "id" not in et

    def test_graphql_alias(self):
        """GraphQL field aliases work."""
        client.post("/api/a-cal/event-types", json={"title": "Alias Test", "slug": "alias-test"})
        r = client.post("/api/a-cal/graphql", json={
            "query": "{ eventTypes { myTitle: title } }",
        })
        data = r.json()
        et = data["data"]["eventTypes"][0]
        assert "myTitle" in et
        assert "title" not in et
