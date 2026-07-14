"""Team, routing form, webhook, and payment API routes (Phase 5).

Provides endpoints for:
- Team CRUD and team member management
- Routing form CRUD
- Webhook CRUD and event delivery
- Payment configuration and payment intent creation
- Payment config stored as a setting (Stripe key managed via env)
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from a_cal.api.store import _store
from a_cal.integrations.payments import PaymentService
from a_cal.integrations.webhooks import dispatch_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-team"])

_payments = PaymentService()


def _uid() -> str:
    """Return the current user ID from the auth context."""
    from a_cal.auth.session import get_current_user_id
    return get_current_user_id()


# --- Request models --------------------------------------------------------

class TeamCreate(BaseModel):
    """Payload for creating a team."""
    name: str
    slug: str = ""
    description: str = ""
    logo_url: str | None = None
    branding: dict[str, Any] = Field(default_factory=dict)


class TeamUpdate(BaseModel):
    """Payload for updating a team."""
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    logo_url: str | None = None
    branding: dict[str, Any] | None = None


class TeamMemberCreate(BaseModel):
    """Payload for adding a team member."""
    email: str
    display_name: str = ""
    role: str = "member"
    provider_connection_id: str | None = None
    is_active: bool = True


class TeamMemberUpdate(BaseModel):
    """Payload for updating a team member."""
    display_name: str | None = None
    role: str | None = None
    provider_connection_id: str | None = None
    is_active: bool | None = None


class RoutingQuestion(BaseModel):
    """A question on a routing form."""
    id: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class RoutingRule(BaseModel):
    """A routing rule that maps answers to an event type or member."""
    condition: str
    event_type_id: str | None = None
    member_id: str | None = None


class RoutingFormCreate(BaseModel):
    """Payload for creating a routing form."""
    name: str
    description: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    routing_rules: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class RoutingFormUpdate(BaseModel):
    """Payload for updating a routing form."""
    name: str | None = None
    description: str | None = None
    questions: list[dict[str, Any]] | None = None
    routing_rules: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class WebhookCreate(BaseModel):
    """Payload for creating a webhook endpoint."""
    url: str
    events: list[str] = Field(default_factory=lambda: ["*"])
    secret: str | None = None
    is_active: bool = True


class WebhookUpdate(BaseModel):
    """Payload for updating a webhook endpoint."""
    url: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    is_active: bool | None = None


class PaymentIntentRequest(BaseModel):
    """Payload for creating a payment intent for a booking."""
    event_type_id: str
    booking_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class PaymentConfigOut(BaseModel):
    """Payment configuration status."""
    is_configured: bool
    is_mock: bool
    publishable_key: str | None = None


# --- Team endpoints --------------------------------------------------------

@router.get("/teams")
def list_teams() -> list[dict[str, Any]]:
    """List all teams for the current user."""
    return _store.list_teams()


@router.post("/teams")
def create_team(body: TeamCreate) -> dict[str, Any]:
    """Create a new scheduling team."""
    data = body.model_dump()
    if not data.get("slug"):
        data["slug"] = data["name"].lower().replace(" ", "-")
    return _store.create_team(data)


@router.get("/teams/{team_id}")
def get_team(team_id: str) -> dict[str, Any]:
    """Get a single team by ID."""
    team = _store.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    members = _store.list_team_members(team_id)
    return {**team, "members": members}


@router.patch("/teams/{team_id}")
def update_team(team_id: str, body: TeamUpdate) -> dict[str, Any]:
    """Update a team's fields."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _store.update_team(team_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return result


@router.delete("/teams/{team_id}")
def delete_team(team_id: str) -> dict[str, str]:
    """Delete a team and all its members."""
    if not _store.delete_team(team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    return {"status": "deleted"}


# --- Team member endpoints -------------------------------------------------

@router.get("/teams/{team_id}/members")
def list_team_members(team_id: str) -> list[dict[str, Any]]:
    """List all members of a team."""
    return _store.list_team_members(team_id)


@router.post("/teams/{team_id}/members")
def add_team_member(team_id: str, body: TeamMemberCreate) -> dict[str, Any]:
    """Add a member to a team."""
    if _store.get_team(team_id) is None:
        raise HTTPException(status_code=404, detail="Team not found")
    data = body.model_dump()
    data["team_id"] = team_id
    return _store.add_team_member(data)


@router.patch("/teams/{team_id}/members/{member_id}")
def update_team_member(team_id: str, member_id: str, body: TeamMemberUpdate) -> dict[str, Any]:
    """Update a team member's fields."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _store.update_team_member(member_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return result


@router.delete("/teams/{team_id}/members/{member_id}")
def remove_team_member(team_id: str, member_id: str) -> dict[str, str]:
    """Remove a member from a team."""
    if not _store.remove_team_member(member_id):
        raise HTTPException(status_code=404, detail="Member not found")
    return {"status": "removed"}


# --- Routing form endpoints ------------------------------------------------

@router.get("/routing-forms")
def list_routing_forms() -> list[dict[str, Any]]:
    """List all routing forms for the current user."""
    return _store.list_routing_forms()


@router.post("/routing-forms")
def create_routing_form(body: RoutingFormCreate) -> dict[str, Any]:
    """Create a new routing form."""
    return _store.create_routing_form(body.model_dump())


@router.get("/routing-forms/{form_id}")
def get_routing_form(form_id: str) -> dict[str, Any]:
    """Get a routing form by ID."""
    form = _store.get_routing_form(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Routing form not found")
    return form


@router.patch("/routing-forms/{form_id}")
def update_routing_form(form_id: str, body: RoutingFormUpdate) -> dict[str, Any]:
    """Update a routing form."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _store.update_routing_form(form_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Routing form not found")
    return result


@router.delete("/routing-forms/{form_id}")
def delete_routing_form(form_id: str) -> dict[str, str]:
    """Delete a routing form."""
    if not _store.delete_routing_form(form_id):
        raise HTTPException(status_code=404, detail="Routing form not found")
    return {"status": "deleted"}


# --- Webhook endpoints -----------------------------------------------------

@router.get("/webhooks")
def list_webhooks() -> list[dict[str, Any]]:
    """List all webhook configs for the current user."""
    return _store.list_webhooks()


@router.post("/webhooks")
def create_webhook(body: WebhookCreate) -> dict[str, Any]:
    """Create a new webhook endpoint."""
    data = body.model_dump()
    if not data.get("secret"):
        data["secret"] = secrets.token_hex(16)
    return _store.create_webhook(data)


@router.patch("/webhooks/{webhook_id}")
def update_webhook(webhook_id: str, body: WebhookUpdate) -> dict[str, Any]:
    """Update a webhook endpoint."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _store.update_webhook(webhook_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return result


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str) -> dict[str, str]:
    """Delete a webhook endpoint."""
    if not _store.delete_webhook(webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deleted"}


@router.post("/webhooks/test")
def test_webhook_delivery(body: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a test event to the current user's active webhooks."""
    event_type = body.get("event", "test.event")
    results = dispatch_event(event_type, body.get("payload", {"test": True}), _uid())
    return {"dispatched": len(results), "deliveries": results}


# --- Payment endpoints -----------------------------------------------------

@router.get("/payments/config")
def get_payment_config() -> dict[str, Any]:
    """Get payment service configuration status."""
    import os
    publishable = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    return {
        "is_configured": not _payments.is_mock,
        "is_mock": _payments.is_mock,
        "publishable_key": publishable or None,
    }


@router.post("/payments/intent")
def create_payment_intent(body: PaymentIntentRequest) -> dict[str, Any]:
    """Create a payment intent for a paid event type booking.

    Looks up the event type to get the price, then creates a Stripe
    PaymentIntent (or mock intent if Stripe is not configured).
    """
    et = _store.get_event_type(body.event_type_id)
    if et is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    if not et.get("is_paid"):
        raise HTTPException(status_code=400, detail="Event type is not paid")

    metadata = dict(body.metadata)
    if body.booking_id:
        metadata["booking_id"] = body.booking_id
    metadata["event_type_id"] = body.event_type_id

    intent = _payments.create_payment_intent(
        amount_cents=et.get("price_cents", 0),
        currency=et.get("currency", "usd"),
        metadata=metadata,
    )
    return intent


@router.post("/payments/confirm/{payment_intent_id}")
def confirm_payment(payment_intent_id: str) -> dict[str, Any]:
    """Confirm/check the status of a payment intent."""
    return _payments.confirm_payment(payment_intent_id)


# --- Custom domain (Phase 6) -----------------------------------------------

class CustomDomainConfig(BaseModel):
    """Configuration for a custom booking page domain."""
    domain: str = ""
    is_active: bool = True
    ssl_verified: bool = False


@router.get("/platform/domain")
def get_custom_domain() -> dict[str, Any]:
    """Get the custom domain configuration for booking pages."""
    config = _store.get_setting("custom_domain", {})
    return {
        "domain": config.get("domain", ""),
        "is_active": config.get("is_active", False),
        "ssl_verified": config.get("ssl_verified", False),
    }


@router.put("/platform/domain")
def set_custom_domain(body: CustomDomainConfig) -> dict[str, Any]:
    """Set or update the custom domain for booking pages."""
    config = {
        "domain": body.domain.strip().lower(),
        "is_active": body.is_active,
        "ssl_verified": body.ssl_verified,
    }
    _store.set_setting("custom_domain", config)
    return config


# --- Webhook delivery history ----------------------------------------------

@router.get("/webhooks/{webhook_id}/deliveries")
def list_webhook_deliveries(webhook_id: str) -> list[dict[str, Any]]:
    """List delivery history for a specific webhook."""
    return _store.list_webhook_deliveries(webhook_id)


# --- Workflow triggers (Phase 5) -------------------------------------------

class WorkflowTriggerConfig(BaseModel):
    """Configuration mapping booking events to workflow triggers."""
    booking_created: bool = True
    booking_cancelled: bool = True
    booking_rescheduled: bool = True


@router.get("/workflow-triggers")
def get_workflow_triggers() -> dict[str, Any]:
    """Get which booking events trigger workflow automation."""
    return _store.get_setting("workflow_triggers", {
        "booking_created": True,
        "booking_cancelled": True,
        "booking_rescheduled": True,
    })


@router.put("/workflow-triggers")
def set_workflow_triggers(body: WorkflowTriggerConfig) -> dict[str, Any]:
    """Configure which booking events trigger workflow automation."""
    config = body.model_dump()
    _store.set_setting("workflow_triggers", config)
    return config
