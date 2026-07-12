"""The Nervous System Coordinator — routes signals through bio-mimetic modules.

This is the layer that makes A-Cal's agent architecture feel like a nervous
system rather than a flat list of specialists. When a user message or calendar
event comes in, it flows through:

1. Thalamus Gate → filters and prioritizes
2. RAS → checks activation state (is the system awake?)
3. Basal Ganglia → ranks which specialists could handle this
4. Conductor (prefrontal cortex) → makes the routing decision
5. Specialist executes → with CAS module augmentation
6. Hippocampus → encodes the experience as a memory
7. Claustrum → verifies the unified view is still coherent

The coordinator is lightweight in standalone mode (rule-based) and delegates
to LLM-based reasoning in full deployment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from a_cal.agents.cas_specs import (
    CAS_AGENTS,
    CAS_AGENTS_BY_NAME,
    CAS_AUGMENTATION_MAP,
    CASAgentSpec,
    get_cas_agents_for_specialist,
)
from a_cal.agents.specs import (
    A_CAL_AGENTS_BY_NAME,
    AgentSpec,
    CognitiveTier,
)

logger = logging.getLogger(__name__)


class ActivationState(str, Enum):
    """System arousal states (from RAS agent)."""

    AWAKE = "awake"
    LIGHT_SLEEP = "light_sleep"
    DEEP_SLEEP = "deep_sleep"
    WAKE_UP_TRANSITION = "wake_up_transition"


class GateState(str, Enum):
    """Thalamic gate states for signal filtering."""

    OPEN = "open"
    THROTTLED = "throttled"
    CLOSED = "closed"
    PRIORITY = "priority"


class AutonomicMode(str, Enum):
    """Sympathetic/parasympathetic balance (from Autonomic agent)."""

    SYMPATHETIC = "sympathetic"        # high urgency, full resources
    BALANCED = "balanced"              # normal operation
    PARASYMPATHETIC = "parasympathetic"  # consolidation, recovery


@dataclass
class SystemState:
    """The current state of the nervous system.

    This is the live context that all CAS modules read from and write to.
    It's updated on every signal that flows through the system.
    """

    activation: ActivationState = ActivationState.AWAKE
    autonomic_mode: AutonomicMode = AutonomicMode.BALANCED
    sympathetic_score: int = 5  # 0-10, 5 = balanced
    spotlight_target: Optional[str] = None  # what the attention is on
    spotlight_priority: int = 0  # 0-10
    meeting_load_hours: float = 0.0
    break_adequacy: float = 1.0  # 0-1, 1 = good breaks
    focus_block_hours: float = 0.0
    last_user_interaction: Optional[str] = None
    binding_quality: float = 1.0  # 0-1, 1 = perfect binding
    overload_risk: bool = False
    burnout_risk: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activation": self.activation.value,
            "autonomic_mode": self.autonomic_mode.value,
            "sympathetic_score": self.sympathetic_score,
            "spotlight_target": self.spotlight_target,
            "spotlight_priority": self.spotlight_priority,
            "meeting_load_hours": self.meeting_load_hours,
            "break_adequacy": self.break_adequacy,
            "focus_block_hours": self.focus_block_hours,
            "last_user_interaction": self.last_user_interaction,
            "binding_quality": self.binding_quality,
            "overload_risk": self.overload_risk,
            "burnout_risk": self.burnout_risk,
        }


@dataclass
class SignalEvaluation:
    """The thalamus gate's evaluation of an incoming signal."""

    gate_state: GateState
    urgency: int  # 0-10
    relevance: int  # 0-10
    recommended_specialist: Optional[str]
    reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_state": self.gate_state.value,
            "urgency": self.urgency,
            "relevance": self.relevance,
            "recommended_specialist": self.recommended_specialist,
            "reasoning": self.reasoning,
        }


@dataclass
class RoutingTrace:
    """Full trace of how a signal flowed through the nervous system.

    This is returned to the frontend so the user can see (in Developer mode)
    exactly how their request was processed through the bio-mimetic architecture.
    """

    signal: str
    timestamp: str
    thalamus_gate: SignalEvaluation
    activation_state: ActivationState
    autonomic_mode: AutonomicMode
    basal_ganglia_ranking: List[Dict[str, Any]]
    conductor_decision: Dict[str, Any]
    cas_modules_engaged: List[str]
    hippocampus_encoding: Optional[Dict[str, Any]]
    binding_check: Optional[Dict[str, Any]]
    total_latency_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal,
            "timestamp": self.timestamp,
            "thalamus_gate": self.thalamus_gate.to_dict(),
            "activation_state": self.activation_state.value,
            "autonomic_mode": self.autonomic_mode.value,
            "basal_ganglia_ranking": self.basal_ganglia_ranking,
            "conductor_decision": self.conductor_decision,
            "cas_modules_engaged": self.cas_modules_engaged,
            "hippocampus_encoding": self.hippocampus_encoding,
            "binding_check": self.binding_check,
            "total_latency_ms": self.total_latency_ms,
        }


class NervousSystemCoordinator:
    """Coordinates signal flow through the bio-mimetic agent architecture.

    In standalone mode, this uses rule-based heuristics for each module.
    In full deployment (with atom's LLM service), each module can delegate
    to an LLM for richer reasoning.
    """

    def __init__(
        self,
        system_state: Optional[SystemState] = None,
        llm_service: Any = None,
    ) -> None:
        self.state = system_state or SystemState()
        self.llm_service = llm_service
        self._memory_store: List[Dict[str, Any]] = []
        self._habit_store: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Thalamus Gate — filter and prioritize incoming signals
    # ------------------------------------------------------------------

    def evaluate_signal(self, signal: str) -> SignalEvaluation:
        """The thalamus gate evaluates an incoming signal.

        Returns a gate state (OPEN/THROTTLED/CLOSED/PRIORITY) and a
        recommended specialist for routing.
        """
        lower = signal.lower()

        # Urgency keywords
        urgent_keywords = ["asap", "urgent", "critical", "now", "emergency", "cancel"]
        is_urgent = any(kw in lower for kw in urgent_keywords)
        urgency = 9 if is_urgent else 5

        # Time-proximity signals (meeting in X minutes)
        time_keywords = ["in 10", "in 15", "in 5", "starting soon", "about to start"]
        is_time_critical = any(kw in lower for kw in time_keywords)
        if is_time_critical:
            urgency = 10

        # Determine specialist from content
        specialist: Optional[str] = None
        if any(kw in lower for kw in ["sync", "pull", "refresh", "connect", "provider"]):
            specialist = "a_cal_sync_agent"
        elif any(kw in lower for kw in ["schedule", "slot", "free", "busy", "conflict", "reschedule", "move", "find time"]):
            specialist = "a_cal_schedule_agent"
        elif any(kw in lower for kw in ["email", "inbox", "invite", "message", "reply", "draft"]):
            specialist = "a_cal_email_agent"
        elif any(kw in lower for kw in ["negotiate", "ask them", "coordinate", "propose to"]):
            specialist = "a_cal_negotiate_agent"
        elif any(kw in lower for kw in ["what do you know", "self model", "my patterns", "settings", "privacy"]):
            specialist = "a_cal_self_model_agent"

        # Gate decision
        if urgency >= 9:
            gate = GateState.PRIORITY
            reasoning = f"High urgency ({urgency}/10) — fast-tracking through gate"
        elif urgency >= 7:
            gate = GateState.OPEN
            reasoning = f"Moderate urgency ({urgency}/10) — passing through normally"
        elif urgency >= 4:
            gate = GateState.OPEN
            reasoning = f"Normal priority ({urgency}/10) — standard routing"
        else:
            gate = GateState.THROTTLED
            reasoning = f"Low priority ({urgency}/10) — throttling, batch if possible"

        # If system is in deep sleep, escalate to wake-up
        if self.state.activation == ActivationState.DEEP_SLEEP and urgency >= 7:
            self.state.activation = ActivationState.WAKE_UP_TRANSITION
            reasoning += "; triggered wake-up from deep sleep"

        return SignalEvaluation(
            gate_state=gate,
            urgency=urgency,
            relevance=8 if specialist else 5,
            recommended_specialist=specialist,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # RAS — activation state management
    # ------------------------------------------------------------------

    def update_activation(self, user_present: bool, current_hour: int) -> None:
        """Update the system's activation state based on presence and time."""
        if user_present:
            self.state.activation = ActivationState.AWAKE
            self.state.last_user_interaction = datetime.now(timezone.utc).isoformat()
            return

        # User not present — check time of day
        if 22 <= current_hour or current_hour < 7:
            self.state.activation = ActivationState.DEEP_SLEEP
        elif 7 <= current_hour < 9 or 17 <= current_hour < 22:
            self.state.activation = ActivationState.LIGHT_SLEEP
        else:
            self.state.activation = ActivationState.LIGHT_SLEEP

    def set_spotlight(self, target: str, priority: int) -> None:
        """Focus the attention spotlight on a specific target."""
        self.state.spotlight_target = target
        self.state.spotlight_priority = max(0, min(10, priority))

    # ------------------------------------------------------------------
    # Autonomic — sympathetic/parasympathetic balance
    # ------------------------------------------------------------------

    def assess_autonomic(self, meeting_count: int, conflict_count: int,
                         urgent_count: int) -> None:
        """Assess and update the autonomic balance."""
        score = 5  # baseline balanced
        if urgent_count > 2:
            score += 2
        if conflict_count > 1:
            score += 2
        if meeting_count > 6:
            score += 1
        if urgent_count == 0 and conflict_count == 0 and meeting_count < 4:
            score -= 2

        score = max(0, min(10, score))
        self.state.sympathetic_score = score

        if score >= 7:
            self.state.autonomic_mode = AutonomicMode.SYMPATHETIC
        elif score <= 3:
            self.state.autonomic_mode = AutonomicMode.PARASYMPATHETIC
        else:
            self.state.autonomic_mode = AutonomicMode.BALANCED

        # Burnout risk: high SNS for extended periods
        if score >= 8:
            self.state.burnout_risk = True
        elif score <= 5:
            self.state.burnout_risk = False

    # ------------------------------------------------------------------
    # Basal Ganglia — action selection
    # ------------------------------------------------------------------

    def rank_specialists(self, signal: str, gate_eval: SignalEvaluation) -> List[Dict[str, Any]]:
        """Rank which specialists could handle this signal.

        Returns a list of {name, confidence, reason} sorted by confidence.
        """
        rankings: List[Dict[str, Any]] = []
        lower = signal.lower()

        # Score each specialist
        specialist_scores: Dict[str, tuple[int, str]] = {}

        sync_kws = ["sync", "pull", "refresh", "connect", "provider", "health"]
        sched_kws = ["schedule", "slot", "free", "busy", "conflict", "reschedule", "move", "find time", "when"]
        email_kws = ["email", "inbox", "invite", "message", "reply", "draft"]
        neg_kws = ["negotiate", "ask them", "coordinate", "propose to", "reschedule with"]
        sm_kws = ["what do you know", "self model", "my patterns", "preferences", "goals", "settings", "privacy"]

        def score_keywords(kws: List[str]) -> tuple[int, str]:
            matches = sum(1 for kw in kws if kw in lower)
            if matches == 0:
                return 0, "no keyword match"
            return min(100, matches * 25), f"{matches} keyword match(es)"

        specialist_scores["a_cal_schedule_agent"] = score_keywords(sched_kws)
        specialist_scores["a_cal_sync_agent"] = score_keywords(sync_kws)
        specialist_scores["a_cal_email_agent"] = score_keywords(email_kws)
        specialist_scores["a_cal_negotiate_agent"] = score_keywords(neg_kws)
        specialist_scores["a_cal_self_model_agent"] = score_keywords(sm_kws)
        specialist_scores["a_cal_conductor"] = (10, "fallback — conductor handles directly")

        # Build ranking
        for name, (score, reason) in sorted(specialist_scores.items(),
                                             key=lambda x: x[1][0], reverse=True):
            spec = A_CAL_AGENTS_BY_NAME.get(name)
            if spec:
                rankings.append({
                    "name": name,
                    "display_name": spec.display_name,
                    "confidence": score,
                    "reason": reason,
                })

        return rankings

    # ------------------------------------------------------------------
    # Hippocampus — memory encoding
    # ------------------------------------------------------------------

    def encode_experience(self, signal: str, specialist: str,
                          outcome: str, decisions: List[str]) -> Dict[str, Any]:
        """Encode a calendar interaction as an episodic memory."""
        memory = {
            "id": f"mem-{len(self._memory_store) + 1}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "specialist": specialist,
            "outcome": outcome,
            "decisions": decisions,
            "activation_state": self.state.activation.value,
            "autonomic_mode": self.state.autonomic_mode.value,
            "tags": self._extract_tags(signal),
        }
        self._memory_store.append(memory)
        # Keep memory store bounded
        if len(self._memory_store) > 500:
            self._memory_store = self._memory_store[-500:]
        return memory

    def retrieve_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve memories relevant to a query (simple keyword match)."""
        lower = query.lower()
        scored: List[tuple[float, Dict[str, Any]]] = []
        for mem in self._memory_store:
            mem_text = (mem["signal"] + " " + " ".join(mem.get("tags", []))).lower()
            overlap = sum(1 for word in lower.split() if word in mem_text)
            if overlap > 0:
                scored.append((overlap, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def _extract_tags(self, signal: str) -> List[str]:
        """Extract simple tags from a signal for memory indexing."""
        lower = signal.lower()
        tags: List[str] = []
        if "meeting" in lower or "schedule" in lower:
            tags.append("scheduling")
        if "email" in lower or "invite" in lower:
            tags.append("email")
        if "sync" in lower or "connect" in lower:
            tags.append("sync")
        if "conflict" in lower or "reschedule" in lower:
            tags.append("conflict")
        if "urgent" in lower or "asap" in lower:
            tags.append("urgent")
        return tags if tags else ["general"]

    # ------------------------------------------------------------------
    # Insula — user state assessment
    # ------------------------------------------------------------------

    def assess_user_state(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess the user's state from their calendar events."""
        if not events:
            return {
                "meeting_load_hours": 0,
                "break_adequacy": 1.0,
                "focus_block_hours": 8,
                "overload_risk": False,
                "energy_pattern": "unknown",
            }

        # Count today's meetings
        today = datetime.now(timezone.utc).date()
        today_events = [e for e in events if today.isoformat() in e.get("start", "")]

        total_minutes = 0
        for e in today_events:
            start = e.get("start", "")
            end = e.get("end", "")
            if start and end:
                try:
                    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    en = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    total_minutes += (en - s).total_seconds() / 60
                except (ValueError, TypeError):
                    pass

        meeting_hours = total_minutes / 60
        self.state.meeting_load_hours = meeting_hours

        # Break adequacy: do meetings have gaps?
        break_adequacy = 1.0
        if len(today_events) > 1:
            sorted_events = sorted(today_events, key=lambda e: e.get("start", ""))
            gaps = 0
            for i in range(1, len(sorted_events)):
                try:
                    prev_end = datetime.fromisoformat(sorted_events[i-1]["end"].replace("Z", "+00:00"))
                    curr_start = datetime.fromisoformat(sorted_events[i]["start"].replace("Z", "+00:00"))
                    gap_min = (curr_start - prev_end).total_seconds() / 60
                    if gap_min >= 15:
                        gaps += 1
                except (ValueError, TypeError, KeyError):
                    pass
            break_adequacy = gaps / max(1, len(sorted_events) - 1)

        self.state.break_adequacy = break_adequacy
        self.state.overload_risk = meeting_hours > 6 or break_adequacy < 0.3

        # Energy pattern: morning vs afternoon density
        morning_count = sum(1 for e in today_events if "T0" in e.get("start", "") or "T1" in e.get("start", ""))
        afternoon_count = len(today_events) - morning_count
        if morning_count > afternoon_count * 1.5:
            energy_pattern = "morning_person"
        elif afternoon_count > morning_count * 1.5:
            energy_pattern = "afternoon_person"
        else:
            energy_pattern = "balanced"

        return {
            "meeting_load_hours": round(meeting_hours, 1),
            "break_adequacy": round(break_adequacy, 2),
            "focus_block_hours": max(0, 8 - meeting_hours),
            "overload_risk": self.state.overload_risk,
            "energy_pattern": energy_pattern,
        }

    # ------------------------------------------------------------------
    # Claustrum — binding verification
    # ------------------------------------------------------------------

    def verify_binding(self, events: List[Dict[str, Any]],
                       sub_accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify the unified calendar view is coherent across sub-accounts."""
        sub_ids = {sa["id"] for sa in sub_accounts}
        orphaned = [e for e in events if e.get("source_sub_account_id") and
                    e["source_sub_account_id"] not in sub_ids]

        # Detect conflicts (overlapping events from different sub-accounts)
        conflicts: List[Dict[str, Any]] = []
        sorted_events = sorted(events, key=lambda e: e.get("start", ""))
        for i in range(len(sorted_events)):
            for j in range(i + 1, min(i + 5, len(sorted_events))):
                e1, e2 = sorted_events[i], sorted_events[j]
                if (e1.get("source_sub_account_id") != e2.get("source_sub_account_id") and
                    e1.get("start", "") < e2.get("end", "") and
                    e2.get("start", "") < e1.get("end", "")):
                    conflicts.append({
                        "event1": e1.get("title", "?"),
                        "event2": e2.get("title", "?"),
                        "time": e1.get("start", ""),
                    })

        binding_quality = 1.0
        if orphaned:
            binding_quality -= 0.2 * min(1, len(orphaned) / 5)
        if conflicts:
            binding_quality -= 0.15 * min(1, len(conflicts) / 5)
        binding_quality = max(0, binding_quality)
        self.state.binding_quality = binding_quality

        return {
            "binding_quality": round(binding_quality, 2),
            "orphaned_events": len(orphaned),
            "conflicts": conflicts[:5],
            "total_events": len(events),
            "sub_accounts_represented": len({e.get("source_sub_account_id") for e in events if e.get("source_sub_account_id")}),
        }

    # ------------------------------------------------------------------
    # Cerebellum — habit learning
    # ------------------------------------------------------------------

    def learn_habit(self, pattern_name: str, pattern_data: Dict[str, Any]) -> None:
        """Learn a recurring pattern for anticipatory action."""
        if pattern_name not in self._habit_store:
            self._habit_store[pattern_name] = {
                "data": pattern_data,
                "confidence": 0.3,
                "occurrences": 1,
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
        else:
            habit = self._habit_store[pattern_name]
            habit["occurrences"] += 1
            habit["confidence"] = min(1.0, habit["confidence"] + 0.15)
            habit["last_seen"] = datetime.now(timezone.utc).isoformat()

    def get_habits(self) -> List[Dict[str, Any]]:
        """Get all learned habits above a confidence threshold."""
        return [
            {"name": name, **data}
            for name, data in self._habit_store.items()
            if data["confidence"] >= 0.5
        ]

    # ------------------------------------------------------------------
    # Full signal routing — the complete nervous system flow
    # ------------------------------------------------------------------

    def route_through_nervous_system(self, signal: str) -> RoutingTrace:
        """Route a signal through the complete bio-mimetic architecture.

        This is the main entry point. It:
        1. Evaluates the signal through the thalamus gate
        2. Checks activation state (RAS)
        3. Ranks specialists (basal ganglia)
        4. Makes a conductor decision
        5. Identifies which CAS modules to engage
        6. Returns a full trace for developer-mode visualization
        """
        start = datetime.now(timezone.utc)

        # 1. Thalamus gate
        gate_eval = self.evaluate_signal(signal)

        # 2. RAS — if system is asleep and signal is low priority, note it
        if self.state.activation in (ActivationState.DEEP_SLEEP, ActivationState.LIGHT_SLEEP):
            if gate_eval.gate_state != GateState.PRIORITY:
                self.state.activation = ActivationState.WAKE_UP_TRANSITION

        # 3. Basal ganglia — rank specialists
        rankings = self.rank_specialists(signal, gate_eval)

        # 4. Conductor decision — pick top specialist
        top = rankings[0] if rankings else None
        conductor_decision = {
            "chosen_specialist": top["name"] if top else "a_cal_conductor",
            "chosen_display_name": top["display_name"] if top else "A-Cal Conductor",
            "confidence": top["confidence"] if top else 30,
            "gate_state": gate_eval.gate_state.value,
            "activation": self.state.activation.value,
        }

        # 5. Identify CAS modules to engage
        chosen = conductor_decision["chosen_specialist"]
        cas_modules = [a.name for a in get_cas_agents_for_specialist(chosen)]
        # Always engage thalamus gate and hippocampus
        if "cas_thalamus_gate" not in cas_modules:
            cas_modules.insert(0, "cas_thalamus_gate")
        if "cas_hippocampus" not in cas_modules:
            cas_modules.append("cas_hippocampus")

        # 6. Hippocampus — encode the experience
        memory = self.encode_experience(
            signal=signal,
            specialist=chosen,
            outcome="routed",
            decisions=[f"Routed to {chosen} via {gate_eval.gate_state.value} gate"],
        )

        # 7. Claustrum — note binding quality
        binding_check = {
            "binding_quality": self.state.binding_quality,
            "verified": self.state.binding_quality >= 0.8,
        }

        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        return RoutingTrace(
            signal=signal,
            timestamp=start.isoformat(),
            thalamus_gate=gate_eval,
            activation_state=self.state.activation,
            autonomic_mode=self.state.autonomic_mode,
            basal_ganglia_ranking=rankings[:4],
            conductor_decision=conductor_decision,
            cas_modules_engaged=cas_modules,
            hippocampus_encoding=memory,
            binding_check=binding_check,
            total_latency_ms=int(elapsed),
        )

    # ------------------------------------------------------------------
    # System overview for the frontend
    # ------------------------------------------------------------------

    def get_system_overview(self) -> Dict[str, Any]:
        """Get a complete overview of the nervous system state for the frontend."""
        return {
            "state": self.state.to_dict(),
            "cas_agents": [a.to_dict() for a in CAS_AGENTS],
            "augmentation_map": CAS_AUGMENTATION_MAP,
            "memory_count": len(self._memory_store),
            "habit_count": len(self._habit_store),
            "recent_memories": self._memory_store[-5:] if self._memory_store else [],
            "active_habits": self.get_habits(),
        }

    def get_all_agents_combined(self) -> List[Dict[str, Any]]:
        """Get all agents (original + CAS) as a combined list for the frontend."""
        from a_cal.agents.specs import A_CAL_AGENTS
        all_agents: List[Dict[str, Any]] = []
        for spec in A_CAL_AGENTS:
            d = spec.to_dict()
            d["is_bio_mimetic"] = False
            d["cas"] = None
            all_agents.append(d)
        for spec in CAS_AGENTS:
            all_agents.append(spec.to_dict())
        return all_agents
