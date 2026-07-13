"""Swarm negotiation API routes.

Exposes the federated swarm coordinator via HTTP so the frontend can trigger
negotiations, browse the negotiation history, and inspect audit trails.

In standalone mode, the coordinator is rule-based (no LLM). With atom, the
coordinator can be LLM-backed for richer negotiation reasoning.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from a_cal.swarm.coordinator import SwarmCoordinator
from a_cal.swarm.protocol import (
    ConflictClaim,
    SubAccountPriority,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal/swarm", tags=["a-cal-swarm"])


# --- per-user coordinator store (standalone mode) --------------------------

_coordinators: dict[str, SwarmCoordinator] = {}


def _get_coordinator(user_id: str) -> SwarmCoordinator:
    """Get or create a SwarmCoordinator for a user."""
    if user_id not in _coordinators:
        _coordinators[user_id] = SwarmCoordinator(user_id=user_id)
    return _coordinators[user_id]


def _current_user_id() -> str:
    """Placeholder — wired to atom's auth in production."""
    return "local-dev-user"


# --- request/response models -----------------------------------------------

class ClaimInput(BaseModel):
    """One sub-account's claim on a contested time slot."""

    sub_account_id: str
    event_id: str
    event_title: str
    slot_start: str  # ISO 8601
    slot_end: str  # ISO 8601
    priority: str = "normal"  # critical | high | normal | low | deferred
    can_move: bool = True
    reasoning: str = ""


class NegotiateRequest(BaseModel):
    """Trigger a negotiation between two conflicting claims."""

    claim_a: ClaimInput
    claim_b: ClaimInput
    max_rounds: int = 5


class EventInput(BaseModel):
    """Minimal event for conflict detection."""

    title: str
    source_sub_account_id: str
    start: str  # ISO 8601
    end: str  # ISO 8601


class DetectConflictsRequest(BaseModel):
    """Detect overlapping events from different sub-accounts."""

    events: list[EventInput]


# --- helpers ----------------------------------------------------------------

def _claim_from_input(data: ClaimInput) -> ConflictClaim:
    """Convert API input to a ConflictClaim."""
    priority: SubAccountPriority
    try:
        priority = SubAccountPriority(data.priority)
    except ValueError:
        priority = SubAccountPriority.NORMAL

    return ConflictClaim(
        sub_account_id=data.sub_account_id,
        event_id=data.event_id,
        event_title=data.event_title,
        slot_start=datetime.fromisoformat(data.slot_start),
        slot_end=datetime.fromisoformat(data.slot_end),
        priority=priority,
        can_move=data.can_move,
        reasoning=data.reasoning,
    )


# --- endpoints --------------------------------------------------------------

@router.post("/negotiate")
def negotiate(body: NegotiateRequest):
    """Trigger a swarm negotiation between two conflicting claims.

    Creates a negotiation, runs it to completion (or escalation), and returns
    the result including the full audit trail.
    """
    user_id = _current_user_id()
    coord = _get_coordinator(user_id)

    claim_a = _claim_from_input(body.claim_a)
    claim_b = _claim_from_input(body.claim_b)

    negotiation = coord.initiate(claim_a, claim_b, max_rounds=body.max_rounds)
    result = coord.run(negotiation)

    logger.info(
        "negotiation %s: resolved=%s escalated=%s winner=%s",
        negotiation.id, result["resolved"], result["escalated"],
        result["winner_sub_account_id"],
    )
    return result


@router.get("/negotiations")
def list_negotiations():
    """List all past and current negotiations for the user."""
    user_id = _current_user_id()
    coord = _get_coordinator(user_id)
    return coord.list_negotiations()


@router.get("/negotiations/{negotiation_id}")
def get_negotiation(negotiation_id: str):
    """Get a specific negotiation with its full audit trail."""
    user_id = _current_user_id()
    coord = _get_coordinator(user_id)
    neg = coord.get_negotiation(negotiation_id)

    if neg is None:
        raise HTTPException(status_code=404, detail="negotiation not found")

    return neg.to_dict()


@router.post("/detect-conflicts")
def detect_conflicts(body: DetectConflictsRequest):
    """Detect overlapping events from different sub-accounts.

    Returns pairs of conflicting events. The conductor calls this before
    deciding whether to trigger a swarm negotiation.
    """
    user_id = _current_user_id()
    coord = _get_coordinator(user_id)

    events = []
    for ev in body.events:
        events.append(
            type("Event", (), {
                "title": ev.title,
                "source_sub_account_id": ev.source_sub_account_id,
                "start": datetime.fromisoformat(ev.start),
                "end": datetime.fromisoformat(ev.end),
            })()
        )

    conflicts = coord.detect_conflicts(events)

    return {
        "conflict_count": len(conflicts),
        "conflicts": [
            {
                "event_a": {
                    "title": a.title,
                    "sub_account_id": a.source_sub_account_id,
                    "start": a.start.isoformat(),
                    "end": a.end.isoformat(),
                },
                "event_b": {
                    "title": b.title,
                    "sub_account_id": b.source_sub_account_id,
                    "start": b.start.isoformat(),
                    "end": b.end.isoformat(),
                },
            }
            for a, b in conflicts
        ],
    }
