"""Nervous system routes for A-Cal.

Split from ``agent_routes.py``. These endpoints expose the CAS bio-mimetic
agent architecture — the nervous system coordinator that models signal
routing through brain-inspired modules (thalamus, RAS, basal ganglia,
conductor, hippocampus, insula, claustrum).

The ``_get_nervous_system`` singleton is also imported back by
``agent_routes.py`` for conductor construction.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from a_cal.agents.nervous_system import NervousSystemCoordinator
from a_cal.agents.cas_specs import CAS_AGENTS

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-agents"])

# Singleton nervous system coordinator (per-server instance)
_nervous_system: NervousSystemCoordinator | None = None


def _get_nervous_system() -> NervousSystemCoordinator:
    """Get or create the singleton nervous system coordinator.

    The coordinator is lazily instantiated on first access and reused for
    all subsequent calls within the same server process.
    """
    global _nervous_system
    if _nervous_system is None:
        _nervous_system = NervousSystemCoordinator()
    return _nervous_system


# --- request models --------------------------------------------------------

class NSRouteRequest(BaseModel):
    """Request to route a signal through the nervous system."""
    signal: str


class NSUserStateRequest(BaseModel):
    """Request to assess user state from events."""
    events: list[dict[str, Any]] = Field(default_factory=list)


class NSBindingRequest(BaseModel):
    """Request to verify calendar binding."""
    events: list[dict[str, Any]] = Field(default_factory=list)
    sub_accounts: list[dict[str, Any]] = Field(default_factory=list)


# --- nervous system endpoints ----------------------------------------------

@router.get("/nervous-system/overview")
def ns_overview():
    """Get a complete overview of the nervous system state and CAS agents."""
    ns = _get_nervous_system()
    return ns.get_system_overview()


@router.get("/nervous-system/agents")
def ns_agents():
    """Get all agents — original 6 specialists + 10 CAS bio-mimetic modules."""
    ns = _get_nervous_system()
    return ns.get_all_agents_combined()


@router.get("/nervous-system/state")
def ns_state():
    """Get the current nervous system state (activation, autonomic, spotlight)."""
    ns = _get_nervous_system()
    return ns.state.to_dict()


@router.post("/nervous-system/route")
def ns_route(body: NSRouteRequest):
    """Route a signal through the complete nervous system and return a trace.

    The trace shows how the signal flowed through:
    thalamus gate -> RAS -> basal ganglia -> conductor -> CAS modules -> hippocampus.
    """
    ns = _get_nervous_system()
    trace = ns.route_through_nervous_system(body.signal)
    return trace.to_dict()


@router.get("/nervous-system/memories")
def ns_memories(limit: int = 10):
    """Get recent episodic memories from the hippocampus module."""
    ns = _get_nervous_system()
    return ns._memory_store[-limit:]


@router.post("/nervous-system/assess-user-state")
def ns_assess_user_state(body: NSUserStateRequest):
    """Assess the user's state from calendar events (insula module)."""
    ns = _get_nervous_system()
    return ns.assess_user_state(body.events)


@router.post("/nervous-system/verify-binding")
def ns_verify_binding(body: NSBindingRequest):
    """Verify the unified calendar view is coherent (claustrum module)."""
    ns = _get_nervous_system()
    return ns.verify_binding(body.events, body.sub_accounts)


@router.get("/nervous-system/cas-agents")
def ns_cas_agents():
    """Get only the CAS bio-mimetic agents with their brain-module metadata."""
    return [a.to_dict() for a in CAS_AGENTS]
