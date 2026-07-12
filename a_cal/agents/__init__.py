"""A-Cal specialist agents — the conductor + federated swarm (Q1).

The conductor agent orchestrates five specialists:
  - SyncAgent      — manages sub-account sync, provider health, rule evaluation
  - ScheduleAgent  — conflict resolution, scheduling optimization, time finding
  - EmailAgent     — inbox triage, invite parsing, draft replies
  - NegotiateAgent — negotiates meeting changes with other attendees' agents
  - SelfModelAgent — reads/writes the self-model, injects context into others

Specialists can also negotiate peer-to-peer (federated swarm) when useful —
e.g. two sub-account agents resolving a conflict over the same slot.

Agent specs are defined as data (not code) so they can be registered with
atom's AtomMetaAgent / IntentClassifier system, customized by users, and
shared via the community marketplace.
"""

from a_cal.agents.specs import (
    AgentSpec,
    CognitiveTier,
    A_CAL_AGENTS,
    CONDUCTOR_SPEC,
    SYNC_AGENT_SPEC,
    SCHEDULE_AGENT_SPEC,
    EMAIL_AGENT_SPEC,
    NEGOTIATE_AGENT_SPEC,
    SELF_MODEL_AGENT_SPEC,
)
from a_cal.agents.conductor import ACalConductor
from a_cal.agents.registry import AgentRegistry

__all__ = [
    "AgentSpec",
    "CognitiveTier",
    "A_CAL_AGENTS",
    "CONDUCTOR_SPEC",
    "SYNC_AGENT_SPEC",
    "SCHEDULE_AGENT_SPEC",
    "EMAIL_AGENT_SPEC",
    "NEGOTIATE_AGENT_SPEC",
    "SELF_MODEL_AGENT_SPEC",
    "ACalConductor",
    "AgentRegistry",
]
