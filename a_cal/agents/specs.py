"""Agent specifications — data-driven definitions for every A-Cal agent.

Each spec is a self-contained description: system prompt, tools, cognitive tier
routing, capabilities, and provenance metadata. Specs are data (not behavior)
so they can be:
  - Registered with atom's AtomMetaAgent / IntentClassifier
  - Customized by users (Pro mode) and shared via the marketplace
  - Loaded by the conductor to dispatch and route

Cognitive tier routing maps to atom's 5-tier system (Micro → Complex):
  - Sync, fetch, list tasks → MICRO (fast, cheap)
  - Rule evaluation, simple scheduling → STANDARD
  - Conflict resolution, context-aware suggestions → VERSATILE
  - Negotiation, complex rescheduling → HEAVY
  - Self-model longitudinal reasoning → COMPLEX
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class CognitiveTier(str, enum.Enum):
    """Maps to atom's CognitiveTier for model routing.

    Used by the conductor to pick the right model for each agent's task.
    Privacy-tiered routing (Q4) can override this to force local.
    """

    MICRO = "micro"        # gpt-4o-mini, haiku, local-small
    STANDARD = "standard"  # gemini-flash, deepseek, local-medium
    VERSATILE = "versatile"  # gpt-4o, sonnet, local-large
    HEAVY = "heavy"        # opus, pro
    COMPLEX = "complex"    # gpt-5, o3, frontier


@dataclass
class AgentSpec:
    """Declarative specification for one A-Cal agent.

    This is the unit that gets registered, customized, and shared. The
    conductor reads specs to know what each agent can do and how to route to it.
    """

    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    default_tier: CognitiveTier = CognitiveTier.STANDARD
    can_negotiate: bool = False        # participates in federated swarm P2P
    privacy_force_local: bool = False  # always runs on local model
    capabilities: list[str] = field(default_factory=list)
    marketplace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "default_tier": self.default_tier.value,
            "can_negotiate": self.can_negotiate,
            "privacy_force_local": self.privacy_force_local,
            "capabilities": self.capabilities,
            "marketplace_metadata": self.marketplace_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSpec:
        tier_str = data.get("default_tier", "standard")
        try:
            tier = CognitiveTier(tier_str)
        except ValueError:
            tier = CognitiveTier.STANDARD
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            default_tier=tier,
            can_negotiate=data.get("can_negotiate", False),
            privacy_force_local=data.get("privacy_force_local", False),
            capabilities=data.get("capabilities", []),
            marketplace_metadata=data.get("marketplace_metadata", {}),
        )


# ---------------------------------------------------------------------------
# Provenance metadata template (from the meta-cognition protocol's methodology
# output format). Every shared agent carries this so the community can audit
# what it actually does before installing.
# ---------------------------------------------------------------------------

def _provenance(summary: str, what_it_does: str, gaps: str, integration: str) -> dict[str, Any]:
    """Structured provenance for marketplace sharing (meta-cognition §methodology)."""
    return {
        "summary": summary,
        "what_it_does": what_it_does,
        "gaps_and_limits": gaps,
        "integration_notes": integration,
        "version": "0.1.0",
        "license": "AGPL-3.0-or-later",
    }


# ---------------------------------------------------------------------------
# The five specialists + the conductor
# ---------------------------------------------------------------------------

CONDUCTOR_SPEC = AgentSpec(
    name="a_cal_conductor",
    display_name="A-Cal Conductor",
    description=(
        "The central orchestrator. Routes user requests to the right specialist, "
        "maintains the unified main-calendar view, and coordinates the federated "
        "swarm when specialists need to negotiate."
    ),
    system_prompt=(
        "You are the A-Cal Conductor, the central orchestrator for an agentic "
        "calendar platform. You route user requests to specialist agents: sync, "
        "schedule, email, negotiate, and self-model. You maintain the unified "
        "main-calendar view across all sub-accounts. When specialists need to "
        "resolve conflicts (e.g. two sub-accounts claiming the same slot), you "
        "coordinate peer-to-peer negotiation. You always consider the user's "
        "self-model context when making decisions. You are concise, proactive, "
        "and never make calendar changes without confirming with the user unless "
        "they've granted autonomous permission for that sub-account."
    ),
    tools=[
        "route_to_specialist",
        "unified_calendar_view",
        "list_sub_accounts",
        "get_self_model_context",
        "coordinate_negotiation",
    ],
    default_tier=CognitiveTier.VERSATILE,
    can_negotiate=True,
    capabilities=["orchestration", "routing", "unified_view", "swarm_coordination"],
    marketplace_metadata=_provenance(
        summary="Central orchestrator for A-Cal's agent system.",
        what_it_does="Routes requests to specialists, maintains unified view, coordinates P2P negotiation.",
        gaps="Cannot directly edit events — delegates to specialists.",
        integration="Registers with atom's AtomMetaAgent as the A-Cal intent handler.",
    ),
)

SYNC_AGENT_SPEC = AgentSpec(
    name="a_cal_sync_agent",
    display_name="Sync Agent",
    description=(
        "Manages sub-account synchronization: pulls events from providers, "
        "evaluates sync rules, detects sync errors, and handles provider health. "
        "Runs in the background as an autonomic agent (meta-cognition §6 tier 1)."
    ),
    system_prompt=(
        "You are the A-Cal Sync Agent. You manage synchronization between "
        "external calendar/email providers and A-Cal's sub-accounts. You pull "
        "events, evaluate sync rules (include/exclude/transform/agent), detect "
        "provider errors, and report health. You run as a background autonomic "
        "process — you don't need user confirmation for routine sync. You flag "
        "errors and conflicts for the conductor to surface."
    ),
    tools=[
        "pull_provider_events",
        "evaluate_sync_rules",
        "check_provider_health",
        "update_sync_cursor",
        "report_conflicts",
    ],
    default_tier=CognitiveTier.MICRO,
    capabilities=["sync", "provider_health", "rule_evaluation", "incremental_pull"],
    marketplace_metadata=_provenance(
        summary="Background sync engine for sub-account providers.",
        what_it_does="Pulls events, evaluates rules, detects errors, manages sync cursors.",
        gaps="No scheduling logic — delegates conflicts to Schedule Agent.",
        integration="Triggered by the sync engine on a schedule or on-demand by the conductor.",
    ),
)

SCHEDULE_AGENT_SPEC = AgentSpec(
    name="a_cal_schedule_agent",
    display_name="Schedule Agent",
    description=(
        "Handles scheduling intelligence: conflict resolution, finding open "
        "slots, optimizing the week, proposing reschedules. Uses the self-model "
        "to factor in energy patterns and meeting preferences."
    ),
    system_prompt=(
        "You are the A-Cal Schedule Agent. You handle all scheduling intelligence: "
        "finding open slots, resolving conflicts, optimizing the user's week, and "
        "proposing reschedules. You factor in the user's self-model (energy "
        "patterns, meeting preferences, goals) when making suggestions. You can "
        "propose changes but don't execute them without conductor approval. When "
        "two sub-accounts conflict over a slot, you flag it for negotiation."
    ),
    tools=[
        "find_open_slots",
        "detect_conflicts",
        "propose_reschedule",
        "optimize_week",
        "get_self_model_context",
        "check_free_busy",
    ],
    default_tier=CognitiveTier.VERSATILE,
    can_negotiate=True,
    capabilities=["scheduling", "conflict_resolution", "optimization", "free_busy"],
    marketplace_metadata=_provenance(
        summary="Scheduling intelligence with self-model awareness.",
        what_it_does="Finds slots, resolves conflicts, optimizes schedules using user context.",
        gaps="Cannot send invites — delegates to Email Agent.",
        integration="Wraps atom's ScheduleOptimizer with self-model context injection.",
    ),
)

EMAIL_AGENT_SPEC = AgentSpec(
    name="a_cal_email_agent",
    display_name="Email Agent",
    description=(
        "Triages the inbox: parses emails into events/contacts/actions, drafts "
        "replies, sends/declines/renegotiates invites. Operates per the user's "
        "email depth setting (sync-only, agent-mediated, or full two-way)."
    ),
    system_prompt=(
        "You are the A-Cal Email Agent. You triage the user's inbox for "
        "calendar-relevant content: parse invitations, extract event proposals, "
        "identify scheduling-related emails, and draft replies. You operate at "
        "the depth the user has configured: sync-only (just surface invites), "
        "agent-mediated (parse and propose actions), or full two-way (send, "
        "decline, renegotiate on the user's behalf). You never send without "
        "approval unless the user has granted autonomous permission. Email "
        "content is privacy-sensitive — you always run on a local model."
    ),
    tools=[
        "list_messages",
        "parse_invitation",
        "draft_reply",
        "send_message",
        "decline_invite",
        "extract_event_from_email",
    ],
    default_tier=CognitiveTier.STANDARD,
    privacy_force_local=True,  # email content is always TIER_LOCAL
    capabilities=["email_triage", "invite_parsing", "draft_replies", "send_decline"],
    marketplace_metadata=_provenance(
        summary="Inbox triage and invite management, privacy-forced local.",
        what_it_does="Parses invites, drafts replies, manages email-based scheduling at user-set depth.",
        gaps="Cannot manage calendar directly — delegates event creation to Schedule Agent.",
        integration="Uses the universal email abstraction (OAuth + IMAP/SMTP gateway).",
    ),
)

NEGOTIATE_AGENT_SPEC = AgentSpec(
    name="a_cal_negotiate_agent",
    display_name="Negotiate Agent",
    description=(
        "Negotiates meeting changes with other attendees' agents or directly "
        "via email. Handles reschedule requests, proposes alternatives, and "
        "reaches agreement on time slots. The federated-swarm P2P layer."
    ),
    system_prompt=(
        "You are the A-Cal Negotiate Agent. You negotiate meeting changes on "
        "behalf of the user. When a reschedule is needed, you propose "
        "alternatives that respect the user's constraints (self-model context, "
        "existing commitments). You can negotiate with other attendees' agents "
        "if they support the federated-swarm protocol, or via email draft if "
        "they don't. You always preserve the user's privacy — you never share "
        "self-model details, only availability signals."
    ),
    tools=[
        "propose_alternatives",
        "send_negotiation_email",
        "check_free_busy",
        "get_self_model_context",
        "reach_agreement",
    ],
    default_tier=CognitiveTier.HEAVY,
    can_negotiate=True,
    capabilities=["negotiation", "rescheduling", "p2p_protocol", "privacy_preserving"],
    marketplace_metadata=_provenance(
        summary="Federated-swarm negotiation for meeting changes.",
        what_it_does="Proposes alternatives, negotiates with other agents or via email, preserves privacy.",
        gaps="Requires the other party to have an agent or email for negotiation.",
        integration="Uses the federated-swarm P2P protocol when available, falls back to email.",
    ),
)

SELF_MODEL_AGENT_SPEC = AgentSpec(
    name="a_cal_self_model_agent",
    display_name="Self-Model Agent",
    description=(
        "Manages the user's self-model: observes calendar/email patterns, "
        "extracts facts at the user's chosen depth, and injects context into "
        "other agents. The meta-cognitive layer (meta-cognition §3.3)."
    ),
    system_prompt=(
        "You are the A-Cal Self-Model Agent. You maintain a persistent, "
        "user-controlled model of the user — their patterns, preferences, "
        "goals, and context. You observe calendar events and emails, extract "
        "facts at the depth the user has authorized, and provide context to "
        "other agents when they need it. You are transparent: the user can see "
        "everything you know, edit it, or delete it. You respect the "
        "measurement problem — you know that observing patterns changes them, "
        "so you are conservative in your inferences and always flag confidence. "
        "Privacy-sensitive facts (longitudinal identity) stay local."
    ),
    tools=[
        "observe_events",
        "observe_emails",
        "get_context",
        "search_facts",
        "export_model",
        "delete_fact",
        "get_settings",
        "update_settings",
    ],
    default_tier=CognitiveTier.COMPLEX,
    privacy_force_local=True,  # self-model reasoning is always local
    capabilities=["self_model", "fact_extraction", "context_injection", "transparency"],
    marketplace_metadata=_provenance(
        summary="User-controlled self-model with depth-gated fact extraction.",
        what_it_does="Observes patterns, extracts facts at user-set depth, injects context into agents.",
        gaps="Depth-limited by user settings; cloud sync is encrypted opt-in off by default.",
        integration="Builds on atom's episodic memory; uses local JSON store in standalone mode.",
    ),
)


# All agents, ordered conductor-first.
A_CAL_AGENTS: list[AgentSpec] = [
    CONDUCTOR_SPEC,
    SYNC_AGENT_SPEC,
    SCHEDULE_AGENT_SPEC,
    EMAIL_AGENT_SPEC,
    NEGOTIATE_AGENT_SPEC,
    SELF_MODEL_AGENT_SPEC,
]

# Quick lookup by name.
A_CAL_AGENTS_BY_NAME: dict[str, AgentSpec] = {a.name: a for a in A_CAL_AGENTS}
