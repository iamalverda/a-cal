"""Federated swarm protocol — P2P negotiation between sub-account agents.

When two sub-accounts conflict over the same time slot (e.g. work has a
meeting and personal has a gym session at 3pm), their agents negotiate
peer-to-peer to resolve it — without a central authority making the call.

The conductor triggers negotiations when it detects conflicts; the swarm
protocol handles the back-and-forth. In standalone mode, negotiations are
rule-based (priority + preferences). With atom, they're LLM-backed.
"""

from a_cal.swarm.protocol import (
    NegotiationMessage,
    NegotiationMessageType,
    NegotiationState,
    NegotiationStatus,
    SlotProposal,
    SwarmNegotiation,
    SubAccountPriority,
)
from a_cal.swarm.coordinator import SwarmCoordinator

__all__ = [
    "NegotiationMessage",
    "NegotiationMessageType",
    "NegotiationState",
    "NegotiationStatus",
    "SlotProposal",
    "SwarmNegotiation",
    "SubAccountPriority",
    "SwarmCoordinator",
]
