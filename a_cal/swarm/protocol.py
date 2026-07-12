"""Federated swarm negotiation protocol.

Defines the message types, negotiation states, and resolution rules for
peer-to-peer conflict resolution between sub-account agents.

The protocol is designed to be:
  * **Serializable** — every negotiation can be exported as JSON (for the
    marketplace: shared negotiation strategies are remixable configs).
  * **Standalone-capable** — rule-based resolution works without an LLM.
  * **LLM-backable** — when atom's LLM service is available, the propose/
    accept/reject steps can be delegated to specialist agents for richer
    reasoning (e.g. "the work meeting has the CEO, so it wins over gym").
  * **Auditable** — every message in a negotiation is logged with a
    timestamp and reasoning, so the user can see how a conflict was resolved.

Protocol flow (simplified):

    Conductor detects conflict
        │
        ▼
    INITIATED ──► PROBING (each sub-agent states its claim + priority)
        │
        ▼
    PROPOSING (higher-priority sub proposes alternatives to lower-priority)
        │
        ├──► ACCEPTED   (lower-priority sub accepts the alternative)
        ├──► REJECTED   (lower-priority sub rejects; escalation)
        │       │
        │       ▼
        │   ESCALATED (conductor steps in, or user is asked)
        │
        └──► CONCEDED  (lower-priority sub concedes the slot)
                │
                ▼
            RESOLVED
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class NegotiationMessageType(str, enum.Enum):
    """Message types exchanged between sub-account agents during negotiation."""

    PROBE = "probe"           # "I want this slot, here's my priority"
    CLAIM = "claim"           # "I'm claiming this slot, I have higher priority"
    PROPOSE = "propose"       # "Here's an alternative slot for you"
    ACCEPT = "accept"         # "I accept your proposed alternative"
    REJECT = "reject"         # "I reject your proposed alternative"
    CONCEDE = "concede"       # "I give up the slot, take it"
    ESCALATE = "escalate"     # "We can't resolve this, escalate to conductor/user"
    RESOLVE = "resolve"       # "Negotiation is resolved, here's the outcome"


class NegotiationStatus(str, enum.Enum):
    """Terminal status of a negotiation."""

    RESOLVED = "resolved"     # an agreement was reached
    ESCALATED = "escalated"   # couldn't resolve; needs conductor or user
    TIMEOUT = "timeout"       # negotiation took too long (configurable)
    CANCELLED = "cancelled"   # user cancelled the negotiation


class NegotiationState(str, enum.Enum):
    """States a negotiation transitions through.

    State machine:
        INITIATED → PROBING → PROPOSING → (ACCEPTED | REJECTED | CONCEDED)
                                      → (RESOLVED | ESCALATED)
    """

    INITIATED = "initiated"
    PROBING = "probing"
    PROPOSING = "proposing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONCEDED = "conceded"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class SubAccountPriority(str, enum.Enum):
    """Priority levels for a sub-account's claim on a time slot.

    Higher priority wins in a conflict. When two subs have the same priority,
    the negotiation escalates to the conductor (or the user).

    These map to the user's per-sub-account configuration — the user decides
    which sub-accounts are higher priority, not the system.
    """

    CRITICAL = "critical"     # can't be moved (hard deadline, flight, surgery)
    HIGH = "high"             # important but movable (client meeting, CEO 1:1)
    NORMAL = "normal"         # standard commitment (team standup, recurring)
    LOW = "low"               # flexible (gym, personal errand, lunch)
    DEFERRED = "deferred"     # can be moved freely (focus block, buffer time)

    @classmethod
    def rank(cls, priority: "SubAccountPriority") -> int:
        """Numeric rank for comparison (higher = more important)."""
        order = {
            cls.CRITICAL: 5,
            cls.HIGH: 4,
            cls.NORMAL: 3,
            cls.LOW: 2,
            cls.DEFERRED: 1,
        }
        return order.get(priority, 3)

    def __gt__(self, other: "SubAccountPriority") -> bool:
        return self.rank(self) > self.rank(other)

    def __lt__(self, other: "SubAccountPriority") -> bool:
        return self.rank(self) < self.rank(other)


@dataclass
class SlotProposal:
    """A proposed alternative time slot during negotiation.

    The higher-priority sub proposes alternatives to the lower-priority sub.
    Each proposal includes the proposed time and a reason (for auditability).
    """

    sub_account_id: str
    proposed_start: datetime
    proposed_end: datetime
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_account_id": self.sub_account_id,
            "proposed_start": self.proposed_start.isoformat(),
            "proposed_end": self.proposed_end.isoformat(),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class NegotiationMessage:
    """A single message in a negotiation exchange.

    Every message is logged with a timestamp and reasoning so the user can
    audit how a conflict was resolved. Messages are serializable for the
    marketplace (shared negotiation logs carry provenance).
    """

    id: str
    negotiation_id: str
    from_sub_account_id: str
    to_sub_account_id: str
    message_type: NegotiationMessageType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: Optional[SubAccountPriority] = None
    proposal: Optional[SlotProposal] = None
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "negotiation_id": self.negotiation_id,
            "from_sub_account_id": self.from_sub_account_id,
            "to_sub_account_id": self.to_sub_account_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value if self.priority else None,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "reasoning": self.reasoning,
            "metadata": dict(self.metadata),
        }


@dataclass
class ConflictClaim:
    """One sub-account's claim on a contested time slot.

    Contains the event that's conflicting and the sub-account's priority
    for that slot (as configured by the user).
    """

    sub_account_id: str
    event_id: str
    event_title: str
    slot_start: datetime
    slot_end: datetime
    priority: SubAccountPriority = SubAccountPriority.NORMAL
    can_move: bool = True
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_account_id": self.sub_account_id,
            "event_id": self.event_id,
            "event_title": self.event_title,
            "slot_start": self.slot_start.isoformat(),
            "slot_end": self.slot_end.isoformat(),
            "priority": self.priority.value,
            "can_move": self.can_move,
            "reasoning": self.reasoning,
        }


@dataclass
class SwarmNegotiation:
    """A complete P2P negotiation between two sub-account agents.

    Lifecycle:
      1. Created by the SwarmCoordinator when a conflict is detected.
      2. Transitions through states as messages are exchanged.
      3. Terminates in RESOLVED (agreement) or ESCALATED (needs user).

    The negotiation is fully serializable — it can be exported as JSON for
    the transparency view (the user can see exactly how a conflict was
    resolved) and for the marketplace (shared negotiation strategies).
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conflict_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: NegotiationState = NegotiationState.INITIATED
    status: Optional[NegotiationStatus] = None
    claims: List[ConflictClaim] = field(default_factory=list)
    messages: List[NegotiationMessage] = field(default_factory=list)
    winner_sub_account_id: Optional[str] = None
    resolution_reason: str = ""
    resolved_at: Optional[datetime] = None
    max_rounds: int = 5
    current_round: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """Whether the negotiation has reached a terminal state."""
        return self.state in (
            NegotiationState.RESOLVED,
            NegotiationState.ESCALATED,
        )

    @property
    def claim_a(self) -> Optional[ConflictClaim]:
        """The first claim (by convention, the initiator)."""
        return self.claims[0] if self.claims else None

    @property
    def claim_b(self) -> Optional[ConflictClaim]:
        """The second claim (the responder)."""
        return self.claims[1] if len(self.claims) > 1 else None

    def add_message(self, msg: NegotiationMessage) -> None:
        """Log a message in the negotiation's history."""
        self.messages.append(msg)

    def transition(self, new_state: NegotiationState) -> None:
        """Transition to a new state (validated by the coordinator)."""
        self.state = new_state

    def resolve(self, winner_id: str, reason: str) -> None:
        """Mark the negotiation as resolved with a winner."""
        self.state = NegotiationState.RESOLVED
        self.status = NegotiationStatus.RESOLVED
        self.winner_sub_account_id = winner_id
        self.resolution_reason = reason
        self.resolved_at = datetime.now(timezone.utc)

    def escalate(self, reason: str) -> None:
        """Mark the negotiation as escalated (needs conductor or user)."""
        self.state = NegotiationState.ESCALATED
        self.status = NegotiationStatus.ESCALATED
        self.resolution_reason = reason
        self.resolved_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conflict_start": self.conflict_start.isoformat(),
            "state": self.state.value,
            "status": self.status.value if self.status else None,
            "claims": [c.to_dict() for c in self.claims],
            "messages": [m.to_dict() for m in self.messages],
            "winner_sub_account_id": self.winner_sub_account_id,
            "resolution_reason": self.resolution_reason,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "metadata": dict(self.metadata),
        }
