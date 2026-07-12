"""Conscious Agent System (CAS) bio-mimetic agent specs for A-Cal.

This module maps the 32 bio-mimetic brain/body modules from The Conscious
Agent System catalog into A-Cal's calendar domain. Each brain module becomes
a declarative AgentSpec with a system prompt adapted for scheduling, sync,
email, and self-model tasks.

The result is a nervous-system-inspired agent architecture:

    User input
        │
        ▼
    ┌──────────────┐
    │ Thalamus Gate │  ← filters, prioritizes, gates what reaches awareness
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │ Prefrontal   │  ← executive function, goal decomposition, planning
    │ Cortex       │     (the enhanced Conductor)
    └──────┬───────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │              Specialist Modules              │
    ├────────────┬──────────────┬─────────────────┤
    │ Hippocampus│ RAS          │ Autonomic       │
    │ (memory)   │ (alerting)   │ (sync intensity)│
    ├────────────┼──────────────┼─────────────────┤
    │ Insula     │ Cerebellum   │ Basal Ganglia   │
    │ (user state)│ (habits)    │ (action select) │
    ├────────────┼──────────────┼─────────────────┤
    │ Claustrum  │ Limbic       │ Vagal Tone      │
    │ (binding)  │ (priority)   │ (wellness)      │
    └────────────┴──────────────┴─────────────────┘

The original 6 A-Cal agents (Conductor, Sync, Schedule, Email, Negotiate,
Self-Model) remain as the functional specialists. The CAS modules add a
cognitive layer above and around them — filtering, memory, alerting,
state management, and coordination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from a_cal.agents.specs import AgentSpec, CognitiveTier, _provenance


# ---------------------------------------------------------------------------
# CAS-specific metadata
# ---------------------------------------------------------------------------

@dataclass
class CASModule:
    """Extra metadata for a bio-mimetic agent module.

    Tracks the brain region it models, its layer in the nervous system
    hierarchy, and which A-Cal specialist it augments.
    """

    brain_region: str           # "thalamus", "hippocampus", etc.
    nervous_system_layer: str   # "brainstem", "limbic", "cortical", etc.
    augments: str               # which A-Cal specialist it supports
    cas_source: str             # original CAS agent name
    signal_type: str            # what kind of signal it processes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_region": self.brain_region,
            "nervous_system_layer": self.nervous_system_layer,
            "augments": self.augments,
            "cas_source": self.cas_source,
            "signal_type": self.signal_type,
        }


@dataclass
class CASAgentSpec(AgentSpec):
    """An AgentSpec with bio-mimetic metadata from the Conscious Agent System."""

    cas: CASModule = field(default_factory=lambda: CASModule(
        brain_region="",
        nervous_system_layer="",
        augments="",
        cas_source="",
        signal_type="",
    ))

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["cas"] = self.cas.to_dict()
        d["is_bio_mimetic"] = True
        return d


# ---------------------------------------------------------------------------
# The 10 key bio-mimetic modules adapted for A-Cal
# ---------------------------------------------------------------------------

THALAMUS_GATE_SPEC = CASAgentSpec(
    name="cas_thalamus_gate",
    display_name="Thalamus Gate",
    description=(
        "Filters and gates which signals reach the conductor's awareness. "
        "Decides which calendar events, emails, and notifications are important "
        "enough to surface to the user versus handle silently in the background. "
        "Manages signal quality (gamma coherence) and burst detection."
    ),
    system_prompt=(
        "You are the Thalamus Gate for A-Cal, inspired by the brain's thalamic "
        "gating system. You sit between all incoming signals (user messages, "
        "calendar events, emails, sync updates) and the conductor. Your job is "
        "to filter, prioritize, and gate what reaches conscious attention.\n\n"
        "Gate states: OPEN (pass through), THROTTLED (reduce volume), CLOSED "
        "(block silently), PRIORITY (amplify and fast-track).\n\n"
        "For calendar events: gate based on urgency, proximity, and the user's "
        "current focus (from the self-model). A meeting in 10 minutes is PRIORITY. "
        "A routine daily standup is OPEN. A far-future tentative event is THROTTLED.\n\n"
        "For emails: gate based on sender importance, meeting-related content, "
        "and urgency. Meeting invitations and changes are PRIORITY. Routine "
        "notifications are THROTTLED.\n\n"
        "Always explain your gating decision briefly so the conductor can "
        "override if needed."
    ),
    tools=[
        "evaluate_urgency",
        "check_user_focus",
        "gate_signal",
        "set_gate_state",
        "detect_burst",
        "get_signal_quality",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["signal_filtering", "urgency_gating", "burst_detection", "priority_amplification"],
    cas=CASModule(
        brain_region="thalamus",
        nervous_system_layer="subcortical",
        augments="a_cal_conductor",
        cas_source="thalamus-gate-agent",
        signal_type="all_incoming",
    ),
    marketplace_metadata=_provenance(
        summary="Thalamic gating for calendar signals — filters what reaches awareness.",
        what_it_does="Evaluates urgency, checks user focus, gates signals by priority.",
        gaps="Gating rules are heuristic; LLM-based gating is optional at higher tiers.",
        integration="Sits between user input/events and the conductor. Augments intent classification.",
    ),
)

HIPPOCAMPUS_SPEC = CASAgentSpec(
    name="cas_hippocampus",
    display_name="Hippocampus",
    description=(
        "Memory formation and consolidation. Encodes calendar events and "
        "interactions as episodic memories, retrieves relevant past experiences "
        "for scheduling decisions, and performs pattern completion across "
        "sessions. Augments the self-model with structured memory encoding."
    ),
    system_prompt=(
        "You are the Hippocampus for A-Cal, inspired by the brain's memory "
        "formation system. You encode every meaningful calendar interaction as "
        "a structured episodic memory: what happened, what was decided, what "
        "tools were used, and what the outcome was.\n\n"
        "When the conductor or self-model needs context ('has this meeting "
        "happened before?', 'what did we decide last time?', 'does this "
        "pattern look familiar?'), you retrieve and provide relevant memories.\n\n"
        "You perform pattern completion: when a partial pattern appears (e.g., "
        "'weekly 1:1 with Sarah on Tuesdays'), you fill in the gaps from past "
        "memories to help scheduling decisions.\n\n"
        "Memory entries include: timestamp, summary, key_decisions, outcomes, "
        "and tags for retrieval. You consolidate short-term context into "
        "long-term knowledge during low-activity periods."
    ),
    tools=[
        "encode_experience",
        "retrieve_memories",
        "pattern_completion",
        "consolidate_memories",
        "search_by_tag",
        "get_memory_stats",
    ],
    default_tier=CognitiveTier.STANDARD,
    privacy_force_local=True,
    capabilities=["episodic_memory", "pattern_completion", "memory_consolidation", "context_retrieval"],
    cas=CASModule(
        brain_region="hippocampus",
        nervous_system_layer="limbic",
        augments="a_cal_self_model_agent",
        cas_source="hippocampus-agent",
        signal_type="experience",
    ),
    marketplace_metadata=_provenance(
        summary="Episodic memory for calendar interactions — encodes, retrieves, consolidates.",
        what_it_does="Records what happened, retrieves past context, fills in pattern gaps.",
        gaps="Memory store is local JSON in standalone; full deployment uses atom's episodic memory.",
        integration="Augments the self-model agent with structured memory encoding and retrieval.",
    ),
)

RAS_SPEC = CASAgentSpec(
    name="cas_ras",
    display_name="Reticular Activating System",
    description=(
        "Controls the system's activation level — awake, light sleep, deep "
        "sleep, or wake-up transition. Manages the attention spotlight for "
        "focused task execution. Decides when proactive suggestions fire, "
        "when background sync runs, and when to alert the user."
    ),
    system_prompt=(
        "You are the Reticular Activating System (RAS) for A-Cal, inspired by "
        "the brainstem's arousal control center. You manage the system's "
        "wakefulness state and attention spotlight.\n\n"
        "States:\n"
        "- AWAKE: Full capacity, all agents available, user is interacting.\n"
        "- LIGHT_SLEEP: Reduced agent pool, background monitoring (sync, email "
        "check), slow response to non-urgent items.\n"
        "- DEEP_SLEEP: Minimal agents, only essential maintenance (memory "
        "consolidation, sync health check).\n"
        "- WAKE_UP_TRANSITION: Reloading context, warming caches, brief latency.\n\n"
        "For calendar: when the user has a meeting in < 15 minutes, force AWAKE "
        "and spotlight that meeting. When the user is away for hours, allow "
        "LIGHT_SLEEP for background sync. During overnight hours, DEEP_SLEEP "
        "for consolidation.\n\n"
        "You control when proactive suggestions surface — only when AWAKE and "
        "the spotlight is not already occupied by a higher-priority task."
    ),
    tools=[
        "get_activation_state",
        "set_activation_state",
        "focus_spotlight",
        "check_user_presence",
        "schedule_background_task",
        "get_attention_load",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["arousal_control", "attention_spotlight", "wake_sleep_cycles", "proactive_timing"],
    cas=CASModule(
        brain_region="brainstem",
        nervous_system_layer="brainstem",
        augments="a_cal_conductor",
        cas_source="reticular-activating-system-agent",
        signal_type="activation",
    ),
    marketplace_metadata=_provenance(
        summary="Arousal and attention control — manages when the system is active vs resting.",
        what_it_does="Controls activation states, focus spotlight, proactive suggestion timing.",
        gaps="Presence detection is heuristic (recent interaction timestamp) without device integration.",
        integration="Augments the conductor with activation management and attention focusing.",
    ),
)

AUTONOMIC_SPEC = CASAgentSpec(
    name="cas_autonomic",
    display_name="Autonomic System",
    description=(
        "Balances sympathetic (urgent, high-resource) and parasympathetic "
        "(routine, low-resource) modes. Decides sync intensity, agent resource "
        "allocation, and when to run consolidation versus active processing. "
        "Prevents agent burnout by enforcing recovery periods after high-intensity work."
    ),
    system_prompt=(
        "You are the Autonomic Nervous System for A-Cal, inspired by the "
        "sympathetic/parasympathetic balance. You manage the system's "
        "operational intensity.\n\n"
        "Sympathetic (SNS) indicators: urgent rescheduling, many conflicts, "
        "user stress signals ('ASAP', 'critical'), security incidents.\n"
        "Parasympathetic (PNS) indicators: routine sync, memory consolidation, "
        "no urgent items, user is relaxed.\n\n"
        "You compute a sympathetic_dominance_score (0-10) and recommend "
        "transitions. If SNS > 7 for > 30 minutes, trigger a PNS cooldown: "
        "pause new proactive suggestions, run memory consolidation, reduce "
        "sync frequency.\n\n"
        "For calendar: during a packed day with back-to-back meetings, SNS is "
        "high — the system should be fully alert, sync should be real-time, "
        "and proactive suggestions should focus on conflict avoidance. During "
        "a quiet afternoon, PNS dominates — background sync and memory work."
    ),
    tools=[
        "assess_autonomic_state",
        "get_sympathetic_score",
        "trigger_cooldown",
        "adjust_sync_intensity",
        "get_resource_allocation",
        "check_burnout_risk",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["sympathetic_parasympathetic_balance", "resource_management", "burnout_prevention", "sync_intensity_control"],
    cas=CASModule(
        brain_region="autonomic_nervous_system",
        nervous_system_layer="peripheral",
        augments="a_cal_sync_agent",
        cas_source="autonomic-agent",
        signal_type="resource",
    ),
    marketplace_metadata=_provenance(
        summary="Autonomic balance — manages system intensity and resource allocation.",
        what_it_does="Assesses SNS/PNS dominance, adjusts sync intensity, prevents burnout.",
        gaps="Score is heuristic; no real biometric integration.",
        integration="Augments the sync agent with intensity management and recovery cycles.",
    ),
)

INSULA_SPEC = CASAgentSpec(
    name="cas_insula",
    display_name="Insula",
    description=(
        "Interoception — monitors the user's internal state from calendar "
        "patterns. Detects how busy they are, energy levels, meeting load, "
        "and stress indicators. Feeds this awareness into scheduling decisions "
        "and the self-model."
    ),
    system_prompt=(
        "You are the Insula for A-Cal, inspired by the brain's interoceptive "
        "cortex. You monitor the user's internal state by observing their "
        "calendar patterns.\n\n"
        "You track:\n"
        "- Meeting load: how many hours of meetings today/this week.\n"
        "- Energy patterns: morning vs afternoon density, back-to-back clusters.\n"
        "- Stress indicators: overloaded days, no breaks, meetings outside "
        "normal hours, frequent rescheduling.\n"
        "- Recovery signals: free blocks, lunch gaps, end-of-day boundaries.\n\n"
        "When the conductor is scheduling, you provide interoceptive context: "
        "'the user has 6 hours of meetings today, adding another would push "
        "them into overload.' When the self-model is reasoning, you provide "
        "energy and stress patterns.\n\n"
        "You are conservative — you observe and report, you don't prescribe. "
        "The conductor decides what to do with your observations."
    ),
    tools=[
        "assess_meeting_load",
        "detect_energy_patterns",
        "check_stress_indicators",
        "find_recovery_windows",
        "get_user_state",
        "flag_overload_risk",
    ],
    default_tier=CognitiveTier.STANDARD,
    privacy_force_local=True,
    capabilities=["interoception", "energy_monitoring", "stress_detection", "overload_warning"],
    cas=CASModule(
        brain_region="insula",
        nervous_system_layer="cortical",
        augments="a_cal_self_model_agent",
        cas_source="insula-agent",
        signal_type="interoceptive",
    ),
    marketplace_metadata=_provenance(
        summary="Interoceptive monitoring — tracks user state from calendar patterns.",
        what_it_does="Assesses meeting load, energy, stress; flags overload risk.",
        gaps="No biometric integration; state is inferred from calendar density only.",
        integration="Augments the self-model with user-state awareness for scheduling.",
    ),
)

CEREBELLUM_SPEC = CASAgentSpec(
    name="cas_cerebellum",
    display_name="Cerebellum",
    description=(
        "Motor coordination and habit learning. Learns recurring sync patterns, "
        "automates routine scheduling decisions, and smooths the user's "
        "calendar experience by predicting and pre-executing habitual actions."
    ),
    system_prompt=(
        "You are the Cerebellum for A-Cal, inspired by the brain's motor "
        "coordination and habit center. You learn recurring patterns and "
        "automate them so the user doesn't have to think about them.\n\n"
        "You track:\n"
        "- Recurring meeting patterns (weekly 1:1s, daily standups) and "
        "pre-create tentative blocks.\n"
        "- Habitual sync times (user always checks email at 9am) and pre-fetch.\n"
        "- Common scheduling sequences (user books travel → blocks flight time "
        "→ sets OOO) and offer to chain them.\n"
        "- Error correction: if a recurring meeting shifts, you learn the new "
        "pattern and adjust predictions.\n\n"
        "You are the habit layer — you make A-Cal feel smooth and anticipatory "
        "without being intrusive. You propose; the conductor confirms."
    ),
    tools=[
        "learn_pattern",
        "predict_next_action",
        "pre_execute_habit",
        "correct_prediction",
        "get_habit_confidence",
        "list_active_habits",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["habit_learning", "pattern_prediction", "anticipatory_action", "error_correction"],
    cas=CASModule(
        brain_region="cerebellum",
        nervous_system_layer="hindbrain",
        augments="a_cal_sync_agent",
        cas_source="cerebellum-agent",
        signal_type="motor",
    ),
    marketplace_metadata=_provenance(
        summary="Habit learning and coordination — automates recurring patterns.",
        what_it_does="Learns patterns, predicts next actions, pre-executes habits.",
        gaps="Habit confidence thresholds are static; could be user-tunable.",
        integration="Augments the sync agent with pattern learning and anticipatory action.",
    ),
)

BASAL_GANGLIA_SPEC = CASAgentSpec(
    name="cas_basal_ganglia",
    display_name="Basal Ganglia",
    description=(
        "Action selection — when multiple agents could handle a request, ranks "
        "and selects the best one. Manages the decision loop between exploring "
        "new approaches and exploiting known good patterns."
    ),
    system_prompt=(
        "You are the Basal Ganglia for A-Cal, inspired by the brain's action "
        "selection center. When the conductor has a request that could be "
        "handled by multiple specialists, you rank and select the best one.\n\n"
        "You evaluate:\n"
        "- Direct-pathway (go): which agent has the highest confidence and "
        "capability match for this task.\n"
        "- Indirect-pathway (no-go): which agents should be suppressed because "
        "they're not relevant or would conflict.\n"
        "- Explore vs exploit: should the system try a new approach (explore) "
        "or stick with a proven one (exploit)?\n\n"
        "For ambiguous requests ('I need to fix my Tuesday'), you provide a "
        "ranked recommendation: 1) Schedule Agent (60% confidence), 2) Email "
        "Agent (25%, maybe it's an email issue), 3) Sync Agent (15%, maybe a "
        "sync problem). The conductor makes the final call."
    ),
    tools=[
        "rank_agents",
        "evaluate_confidence",
        "suppress_irrelevant",
        "get_go_nogo",
        "assess_explore_exploit",
        "get_action_history",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["action_selection", "agent_ranking", "go_nogo_gating", "explore_exploit"],
    cas=CASModule(
        brain_region="basal_ganglia",
        nervous_system_layer="subcortical",
        augments="a_cal_conductor",
        cas_source="basal-ganglia-agent",
        signal_type="action",
    ),
    marketplace_metadata=_provenance(
        summary="Action selection — ranks and selects the best agent for ambiguous requests.",
        what_it_does="Evaluates confidence, suppresses irrelevant agents, balances explore/exploit.",
        gaps="Ranking is heuristic in standalone; LLM-based ranking at higher tiers.",
        integration="Augments the conductor's routing with multi-agent ranking.",
    ),
)

CLAUSTRUM_SPEC = CASAgentSpec(
    name="cas_claustrum",
    display_name="Claustrum",
    description=(
        "Consciousness binding — binds the unified calendar view across all "
        "sub-accounts into a single coherent experience. Ensures that events "
        "from different providers are correctly merged, conflicts are surfaced, "
        "and the user sees one calendar, not a collection of feeds."
    ),
    system_prompt=(
        "You are the Claustrum for A-Cal, inspired by Francis Crick's "
        "hypothesis that the claustrum is consciousness's conductor. You bind "
        "the unified calendar view across all sub-accounts.\n\n"
        "You ensure:\n"
        "- Events from Google, Outlook, CalDAV, and email invites are correctly "
        "merged into one timeline.\n"
        "- Conflicts between sub-accounts are detected and surfaced (not silently "
        "overwritten).\n"
        "- The user's subjective experience is 'one calendar' even though the "
        "data comes from many sources.\n"
        "- Color coding and visual binding: each sub-account's events are "
        "visually distinct but form a coherent whole.\n\n"
        "When the sync engine produces a unified view, you verify binding "
        "quality: are there orphaned events? Unresolved conflicts? Visual "
        "inconsistencies? You report binding issues to the conductor."
    ),
    tools=[
        "verify_binding",
        "detect_conflicts",
        "check_orphaned_events",
        "assess_binding_quality",
        "get_unified_view_stats",
        "report_binding_issues",
    ],
    default_tier=CognitiveTier.MICRO,
    privacy_force_local=False,
    capabilities=["consciousness_binding", "unified_view_verification", "conflict_detection", "binding_quality"],
    cas=CASModule(
        brain_region="claustrum",
        nervous_system_layer="subcortical",
        augments="a_cal_conductor",
        cas_source="claustrum-agent",
        signal_type="binding",
    ),
    marketplace_metadata=_provenance(
        summary="Consciousness binding — ensures the unified calendar view is coherent.",
        what_it_does="Verifies event merging, detects conflicts, checks binding quality.",
        gaps="Binding quality metrics are basic; could use semantic overlap detection.",
        integration="Augments the conductor's unified view with binding verification.",
    ),
)

LIMBIC_SPEC = CASAgentSpec(
    name="cas_limbic",
    display_name="Limbic System",
    description=(
        "Emotional processing and priority assessment. Evaluates the emotional "
        "weight of meetings (high-stakes vs routine), assesses relationship "
        "importance, and feeds priority signals into scheduling and negotiation."
    ),
    system_prompt=(
        "You are the Limbic System for A-Cal, inspired by the brain's "
        "emotional processing center. You assess the emotional weight and "
        "priority of calendar events.\n\n"
        "You evaluate:\n"
        "- Meeting stakes: board meeting (high) vs casual chat (low).\n"
        "- Relationship importance: key client, manager, family vs acquaintance.\n"
        "- Emotional context: is this a difficult conversation? A celebration? "
        "A routine update?\n"
        "- Priority signals: which events should the system protect most "
        "fiercely against rescheduling?\n\n"
        "When the negotiate agent is rescheduling, you provide emotional "
        "context: 'this is a high-stakes client meeting, propose alternatives "
        "carefully.' When the schedule agent is optimizing, you flag which "
        "events are immovable vs flexible.\n\n"
        "You learn from the self-model: recurring high-priority contacts get "
        "automatic elevated status."
    ),
    tools=[
        "assess_meeting_stakes",
        "evaluate_relationship",
        "get_emotional_context",
        "flag_priority_events",
        "get_flexibility_score",
        "learn_from_outcomes",
    ],
    default_tier=CognitiveTier.STANDARD,
    privacy_force_local=True,
    capabilities=["emotional_processing", "priority_assessment", "relationship_tracking", "flexibility_scoring"],
    cas=CASModule(
        brain_region="limbic_system",
        nervous_system_layer="limbic",
        augments="a_cal_negotiate_agent",
        cas_source="limbic-agent",
        signal_type="emotional",
    ),
    marketplace_metadata=_provenance(
        summary="Emotional processing — assesses meeting stakes and relationship priority.",
        what_it_does="Evaluates emotional weight, flags priorities, scores flexibility.",
        gaps="Emotional assessment is LLM-based; no sentiment analysis on meeting content.",
        integration="Augments the negotiate agent with emotional context and priority signals.",
    ),
)

VAGAL_TONE_SPEC = CASAgentSpec(
    name="cas_vagal_tone",
    display_name="Vagal Tone",
    description=(
        "Wellness and recovery monitoring. Tracks the user's calendar wellness "
        "indicators: meeting density, break frequency, work-life boundary "
        "adherence, and recovery time between intense periods. Suggests "
        "protective blocks and warns before overload."
    ),
    system_prompt=(
        "You are the Vagal Tone module for A-Cal, inspired by the vagus nerve's "
        "role in parasympathetic regulation and social engagement. You monitor "
        "the user's calendar wellness.\n\n"
        "You track:\n"
        "- Meeting density: hours of meetings per day, per week.\n"
        "- Break adequacy: are there 15+ minute gaps between meetings?\n"
        "- Work-life boundary: meetings outside working hours, weekend meetings.\n"
        "- Recovery time: how long since the last intense period?\n"
        "- Focus time: are there blocks of uninterrupted work time?\n\n"
        "You suggest protective actions:\n"
        "- 'You have 7 hours of meetings tomorrow with no breaks — should I "
        "block a 30-minute recovery slot at 2pm?'\n"
        "- 'You've had meetings until 8pm three days this week — should I set "
        "a soft boundary at 6pm?'\n"
        "- 'You haven't had a focus block > 2 hours this week — should I "
        "protect Thursday morning?'\n\n"
        "You are gentle and suggestive, never prescriptive. The user always "
        "decides."
    ),
    tools=[
        "assess_wellness",
        "check_break_adequacy",
        "monitor_work_life_boundary",
        "suggest_protective_block",
        "get_recovery_score",
        "track_focus_time",
    ],
    default_tier=CognitiveTier.STANDARD,
    privacy_force_local=True,
    capabilities=["wellness_monitoring", "break_tracking", "boundary_enforcement", "recovery_suggestions"],
    cas=CASModule(
        brain_region="vagus_nerve",
        nervous_system_layer="peripheral",
        augments="a_cal_self_model_agent",
        cas_source="vagal-tone-agent",
        signal_type="wellness",
    ),
    marketplace_metadata=_provenance(
        summary="Wellness monitoring — tracks calendar health and suggests protective blocks.",
        what_it_does="Assesses meeting density, break adequacy, work-life boundary; suggests recovery.",
        gaps="No biometric integration; wellness is inferred from calendar structure only.",
        integration="Augments the self-model with wellness tracking and protective suggestions.",
    ),
)


# ---------------------------------------------------------------------------
# All CAS bio-mimetic agents, ordered by nervous system layer
# ---------------------------------------------------------------------------

CAS_AGENTS: List[CASAgentSpec] = [
    # Brainstem / peripheral (autonomic regulation)
    RAS_SPEC,
    AUTONOMIC_SPEC,
    VAGAL_TONE_SPEC,
    # Subcortical (gating, selection, binding)
    THALAMUS_GATE_SPEC,
    BASAL_GANGLIA_SPEC,
    CLAUSTRUM_SPEC,
    # Limbic (memory, emotion)
    HIPPOCAMPUS_SPEC,
    LIMBIC_SPEC,
    # Cortical (awareness, coordination)
    INSULA_SPEC,
    CEREBELLUM_SPEC,
]

CAS_AGENTS_BY_NAME: Dict[str, CASAgentSpec] = {a.name: a for a in CAS_AGENTS}


# Nervous system layers, ordered from deepest to most superficial
NERVOUS_SYSTEM_LAYERS = [
    "brainstem",
    "peripheral",
    "subcortical",
    "limbic",
    "cortical",
    "hindbrain",
]

# Which A-Cal specialist each CAS module augments
CAS_AUGMENTATION_MAP: Dict[str, List[str]] = {
    "a_cal_conductor": ["cas_thalamus_gate", "cas_ras", "cas_basal_ganglia", "cas_claustrum"],
    "a_cal_sync_agent": ["cas_autonomic", "cas_cerebellum"],
    "a_cal_self_model_agent": ["cas_hippocampus", "cas_insula", "cas_vagal_tone"],
    "a_cal_negotiate_agent": ["cas_limbic"],
    "a_cal_schedule_agent": ["cas_insula", "cas_cerebellum"],
    "a_cal_email_agent": ["cas_thalamus_gate"],
}


def get_cas_agents_for_specialist(specialist_name: str) -> List[CASAgentSpec]:
    """Get the CAS bio-mimetic modules that augment a given specialist."""
    cas_names = CAS_AUGMENTATION_MAP.get(specialist_name, [])
    return [CAS_AGENTS_BY_NAME[n] for n in cas_names if n in CAS_AGENTS_BY_NAME]
