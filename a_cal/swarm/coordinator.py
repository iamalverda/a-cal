"""Swarm coordinator — manages P2P negotiations between sub-account agents.

The coordinator is the engine that drives the negotiation protocol. It:
  1. Detects conflicts (overlapping events from different sub-accounts).
  2. Creates negotiations with the conflicting claims.
  3. Runs the negotiation rounds (probe → propose → accept/reject/concede).
  4. Returns resolutions (winner + alternative slot + audit trail).

In standalone mode, resolution is rule-based:
  - Compare priorities; higher priority wins.
  - If equal priority, check `can_move` flags.
  - If both can move, the one with more flexibility (more available alternatives) concedes.
  - If neither can move, escalate to the conductor/user.

With atom's LLM service, the propose/accept/reject steps can be delegated to
specialist agents for richer reasoning (e.g. "the work meeting has the CEO
attending, so it should win over the gym session").
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from a_cal.swarm.protocol import (
    ConflictClaim,
    NegotiationMessage,
    NegotiationMessageType,
    NegotiationState,
    NegotiationStatus,
    SlotProposal,
    SubAccountPriority,
    SwarmNegotiation,
)

logger = logging.getLogger(__name__)


class SwarmCoordinator:
    """Coordinates federated swarm negotiations between sub-account agents.

    Usage:
        coordinator = SwarmCoordinator()
        negotiation = coordinator.initiate(claim_a, claim_b)
        result = coordinator.run(negotiation)
        if result["escalated"]:
            # ask the user or the conductor to decide
            ...

    The coordinator can be given an `available_slots` callback that, for a
    given sub-account and time window, returns free slots. This lets the
    coordinator propose real alternatives instead of just "move it somewhere."
    """

    def __init__(
        self,
        available_slots_fn: Any | None = None,
        llm_service: Any = None,
        user_id: str = "local-dev-user",
    ) -> None:
        """Initialize the coordinator.

        Args:
            available_slots_fn: async callable(sub_account_id, date, duration_min)
                → List[Tuple[datetime, datetime]]. Provides free slots for
                proposing alternatives. If None, the coordinator uses simple
                time-shifting (propose the same slot +/- offset).
            llm_service: atom's LLM service for LLM-backed negotiation. If None,
                negotiations are rule-based (standalone mode).
            user_id: the user whose sub-accounts are negotiating.
        """
        self.available_slots_fn = available_slots_fn
        self.llm_service = llm_service
        self.user_id = user_id
        self._negotiations: dict[str, SwarmNegotiation] = {}

    def initiate(
        self,
        claim_a: ConflictClaim,
        claim_b: ConflictClaim,
        max_rounds: int = 5,
    ) -> SwarmNegotiation:
        """Create a new negotiation for a conflict between two claims.

        Both claims should be for overlapping time slots from different
        sub-accounts. The coordinator will determine which sub keeps the slot
        and which gets an alternative.
        """
        negotiation = SwarmNegotiation(
            claims=[claim_a, claim_b],
            max_rounds=max_rounds,
        )
        negotiation.transition(NegotiationState.PROBING)

        # Log the initial probe messages from both sub-agents.
        for claim in (claim_a, claim_b):
            other_id = claim_b.sub_account_id if claim is claim_a else claim_a.sub_account_id
            probe = NegotiationMessage(
                id=str(uuid.uuid4()),
                negotiation_id=negotiation.id,
                from_sub_account_id=claim.sub_account_id,
                to_sub_account_id=other_id,
                message_type=NegotiationMessageType.PROBE,
                priority=claim.priority,
                reasoning=claim.reasoning or f"Claiming slot for '{claim.event_title}'",
                metadata={"can_move": claim.can_move},
            )
            negotiation.add_message(probe)

        self._negotiations[negotiation.id] = negotiation
        logger.info(
            "initiated negotiation %s: %s vs %s (priorities: %s vs %s)",
            negotiation.id, claim_a.sub_account_id, claim_b.sub_account_id,
            claim_a.priority.value, claim_b.priority.value,
        )
        return negotiation

    def run(self, negotiation: SwarmNegotiation) -> dict[str, Any]:
        """Run the negotiation to completion (or escalation).

        This is the main loop. In standalone mode, it's synchronous and
        rule-based. With atom's LLM service, each round could be an async
        LLM call (the coordinator would be awaited).

        Returns a dict with:
          - resolved: bool
          - escalated: bool
          - winner_sub_account_id: str | None
          - loser_sub_account_id: str | None
          - alternative_slot: SlotProposal | None
          - resolution_reason: str
          - negotiation: the full SwarmNegotiation (for audit/export)
        """
        claim_a = negotiation.claim_a
        claim_b = negotiation.claim_b
        if not claim_a or not claim_b:
            return self._error_result(negotiation, "negotiation missing claims")

        while not negotiation.is_terminal and negotiation.current_round < negotiation.max_rounds:
            negotiation.current_round += 1
            self._run_round(negotiation)

        if not negotiation.is_terminal:
            negotiation.escalate(
                f"max rounds ({negotiation.max_rounds}) reached without resolution"
            )

        return self._build_result(negotiation)

    def _run_round(self, negotiation: SwarmNegotiation) -> None:
        """Execute one round of the negotiation.

        Round logic (rule-based, standalone mode):
          1. Compare priorities. If one is strictly higher, it wins.
          2. If equal priority, check can_move flags.
          3. If one can move and the other can't, the movable one concedes.
          4. If both can move, the one with lower priority concedes (or
             if equal, propose an alternative and escalate if rejected).
          5. If neither can move, escalate.
        """
        claim_a = negotiation.claim_a
        claim_b = negotiation.claim_b

        # Step 1: Priority comparison.
        if claim_a.priority > claim_b.priority:
            self._declare_winner(negotiation, claim_a, claim_b)
            return
        if claim_b.priority > claim_a.priority:
            self._declare_winner(negotiation, claim_b, claim_a)
            return

        # Step 2: Equal priority — check can_move.
        if claim_a.can_move and not claim_b.can_move:
            self._concede(negotiation, claim_a, claim_b)
            return
        if claim_b.can_move and not claim_a.can_move:
            self._concede(negotiation, claim_b, claim_a)
            return

        # Step 2b: Neither can move — escalate immediately.
        if not claim_a.can_move and not claim_b.can_move:
            negotiation.escalate(
                "neither sub-account can move and no alternatives available"
            )
            return

        # Step 3: Both can move — propose an alternative to one of them.
        # Prefer proposing to the one that joined second (claim_b).
        negotiation.transition(NegotiationState.PROPOSING)
        proposal = self._generate_alternative(claim_b, claim_a)
        if proposal:
            propose_msg = NegotiationMessage(
                id=str(uuid.uuid4()),
                negotiation_id=negotiation.id,
                from_sub_account_id=claim_a.sub_account_id,
                to_sub_account_id=claim_b.sub_account_id,
                message_type=NegotiationMessageType.PROPOSE,
                proposal=proposal,
                reasoning=f"Proposing alternative slot for '{claim_b.event_title}'",
            )
            negotiation.add_message(propose_msg)

            # In standalone mode, the responder auto-accepts reasonable proposals.
            # With LLM, this would be an agent decision.
            if self._is_reasonable_proposal(proposal, claim_b):
                accept_msg = NegotiationMessage(
                    id=str(uuid.uuid4()),
                    negotiation_id=negotiation.id,
                    from_sub_account_id=claim_b.sub_account_id,
                    to_sub_account_id=claim_a.sub_account_id,
                    message_type=NegotiationMessageType.ACCEPT,
                    proposal=proposal,
                    reasoning="Alternative slot is acceptable",
                )
                negotiation.add_message(accept_msg)
                negotiation.resolve(
                    winner_id=claim_a.sub_account_id,
                    reason=f"{claim_b.sub_account_id} accepts alternative slot at {proposal.proposed_start.isoformat()}",
                )
            else:
                reject_msg = NegotiationMessage(
                    id=str(uuid.uuid4()),
                    negotiation_id=negotiation.id,
                    from_sub_account_id=claim_b.sub_account_id,
                    to_sub_account_id=claim_a.sub_account_id,
                    message_type=NegotiationMessageType.REJECT,
                    proposal=proposal,
                    reasoning="Alternative slot is not acceptable",
                )
                negotiation.add_message(reject_msg)
                # After rejection, try the other direction.
                proposal_b = self._generate_alternative(claim_a, claim_b)
                if proposal_b:
                    propose_b = NegotiationMessage(
                        id=str(uuid.uuid4()),
                        negotiation_id=negotiation.id,
                        from_sub_account_id=claim_b.sub_account_id,
                        to_sub_account_id=claim_a.sub_account_id,
                        message_type=NegotiationMessageType.PROPOSE,
                        proposal=proposal_b,
                        reasoning=f"Counter-proposal: alternative for '{claim_a.event_title}'",
                    )
                    negotiation.add_message(propose_b)
                    if self._is_reasonable_proposal(proposal_b, claim_a):
                        negotiation.resolve(
                            winner_id=claim_b.sub_account_id,
                            reason=f"{claim_a.sub_account_id} accepts counter-proposal at {proposal_b.proposed_start.isoformat()}",
                        )
                        return
                # Both proposals rejected — escalate.
                negotiation.escalate("both sub-agents rejected all proposals")
        else:
            # No alternative available — if neither can move, escalate.
            if not claim_a.can_move and not claim_b.can_move:
                negotiation.escalate("neither sub-account can move and no alternatives available")
            else:
                # One can move but no alternative slot found — it concedes.
                mover = claim_b if claim_b.can_move else claim_a
                keeper = claim_a if mover is claim_b else claim_b
                self._concede(negotiation, mover, keeper)

    def _declare_winner(
        self,
        negotiation: SwarmNegotiation,
        winner: ConflictClaim,
        loser: ConflictClaim,
    ) -> None:
        """Declare a winner based on priority. The loser gets an alternative if possible."""
        negotiation.transition(NegotiationState.PROPOSING)
        proposal = self._generate_alternative(loser, winner)

        claim_msg = NegotiationMessage(
            id=str(uuid.uuid4()),
            negotiation_id=negotiation.id,
            from_sub_account_id=winner.sub_account_id,
            to_sub_account_id=loser.sub_account_id,
            message_type=NegotiationMessageType.CLAIM,
            priority=winner.priority,
            reasoning=f"{winner.priority.value} priority claims this slot over {loser.priority.value}",
        )
        negotiation.add_message(claim_msg)

        if proposal:
            propose_msg = NegotiationMessage(
                id=str(uuid.uuid4()),
                negotiation_id=negotiation.id,
                from_sub_account_id=winner.sub_account_id,
                to_sub_account_id=loser.sub_account_id,
                message_type=NegotiationMessageType.PROPOSE,
                proposal=proposal,
                reasoning=f"Proposing alternative for '{loser.event_title}'",
            )
            negotiation.add_message(propose_msg)

        if loser.can_move:
            self._concede(negotiation, loser, winner)
        else:
            # Loser can't move despite lower priority — escalate.
            negotiation.escalate(
                f"{loser.sub_account_id} has lower priority but cannot move"
            )

    def _concede(
        self,
        negotiation: SwarmNegotiation,
        conceder: ConflictClaim,
        keeper: ConflictClaim,
    ) -> None:
        """One sub-account concedes the slot to the other."""
        negotiation.transition(NegotiationState.CONCEDED)
        concede_msg = NegotiationMessage(
            id=str(uuid.uuid4()),
            negotiation_id=negotiation.id,
            from_sub_account_id=conceder.sub_account_id,
            to_sub_account_id=keeper.sub_account_id,
            message_type=NegotiationMessageType.CONCEDE,
            reasoning=f"Conceding slot for '{conceder.event_title}' to '{keeper.event_title}'",
        )
        negotiation.add_message(concede_msg)

        # Try to provide an alternative for the conceder.
        proposal = self._generate_alternative(conceder, keeper)
        resolve_reason = f"{conceder.sub_account_id} concedes to {keeper.sub_account_id}"
        if proposal:
            resolve_msg = NegotiationMessage(
                id=str(uuid.uuid4()),
                negotiation_id=negotiation.id,
                from_sub_account_id=keeper.sub_account_id,
                to_sub_account_id=conceder.sub_account_id,
                message_type=NegotiationMessageType.RESOLVE,
                proposal=proposal,
                reasoning=f"Resolved: {keeper.sub_account_id} keeps slot, {conceder.sub_account_id} moves to {proposal.proposed_start.isoformat()}",
            )
            negotiation.add_message(resolve_msg)
            resolve_reason += f"; alternative at {proposal.proposed_start.isoformat()}"

        negotiation.resolve(winner_id=keeper.sub_account_id, reason=resolve_reason)

    def _generate_alternative(
        self,
        mover: ConflictClaim,
        keeper: ConflictClaim,
    ) -> SlotProposal | None:
        """Generate an alternative time slot for the mover.

        If an `available_slots_fn` was provided, use it to find real free slots.
        Otherwise, propose a simple time-shift (same time, next available day
        or +/- a few hours).
        """
        duration = mover.slot_end - mover.slot_start

        if self.available_slots_fn:
            # In production, this calls the sync engine to find real free slots.
            # For now, we skip async — the coordinator would need to be async.
            pass

        # Fallback: propose a simple shift (next day, same time).
        next_day = mover.slot_start + timedelta(days=1)
        proposal = SlotProposal(
            sub_account_id=mover.sub_account_id,
            proposed_start=next_day,
            proposed_end=next_day + duration,
            reason=f"Proposed next-day slot (same time) for '{mover.event_title}'",
            metadata={"shift_type": "next_day", "original_start": mover.slot_start.isoformat()},
        )
        return proposal

    def _is_reasonable_proposal(self, proposal: SlotProposal, claim: ConflictClaim) -> bool:
        """Check if a proposed alternative is reasonable for the claim.

        In standalone mode, a proposal is reasonable if:
          - It's on the same day or the next day.
          - It's not more than 2 days away.
          - It's not before 6am or after 10pm.

        With LLM, this would be an agent judgment call.
        """
        proposed = proposal.proposed_start
        original = claim.slot_start

        # Not more than 2 days away.
        if abs((proposed.date() - original.date()).days) > 2:
            return False

        # Not before 6am or after 10pm.
        if proposed.hour < 6 or proposed.hour >= 22:
            return False

        return True

    def _build_result(self, negotiation: SwarmNegotiation) -> dict[str, Any]:
        """Build the result dict from a completed negotiation."""
        winner_id = negotiation.winner_sub_account_id
        loser_id = None
        if winner_id and len(negotiation.claims) == 2:
            loser_id = (
                negotiation.claims[1].sub_account_id
                if winner_id == negotiation.claims[0].sub_account_id
                else negotiation.claims[0].sub_account_id
            )

        # Find the last proposal (the alternative slot for the loser).
        last_proposal = None
        for msg in reversed(negotiation.messages):
            if msg.proposal:
                last_proposal = msg.proposal
                break

        return {
            "resolved": negotiation.status == NegotiationStatus.RESOLVED,
            "escalated": negotiation.status == NegotiationStatus.ESCALATED,
            "winner_sub_account_id": winner_id,
            "loser_sub_account_id": loser_id,
            "alternative_slot": last_proposal.to_dict() if last_proposal else None,
            "resolution_reason": negotiation.resolution_reason,
            "rounds": negotiation.current_round,
            "negotiation_id": negotiation.id,
            "audit_trail": [m.to_dict() for m in negotiation.messages],
        }

    def _error_result(self, negotiation: SwarmNegotiation, reason: str) -> dict[str, Any]:
        """Build an error result for a malformed negotiation."""
        return {
            "resolved": False,
            "escalated": True,
            "winner_sub_account_id": None,
            "loser_sub_account_id": None,
            "alternative_slot": None,
            "resolution_reason": reason,
            "rounds": 0,
            "negotiation_id": negotiation.id,
            "audit_trail": [m.to_dict() for m in negotiation.messages],
        }

    def get_negotiation(self, negotiation_id: str) -> SwarmNegotiation | None:
        """Retrieve a negotiation by ID (for the audit/transparency view)."""
        return self._negotiations.get(negotiation_id)

    def list_negotiations(self) -> list[dict[str, Any]]:
        """List all negotiations (for the UI's negotiation history view)."""
        return [n.to_dict() for n in self._negotiations.values()]

    def detect_conflicts(
        self,
        events: list[Any],
    ) -> list[tuple[Any, Any]]:
        """Detect overlapping events from different sub-accounts.

        Takes a list of CalendarEventDTO-like objects (anything with .start,
        .end, .source_sub_account_id) and returns pairs of conflicting events
        from different sub-accounts.

        This is what the conductor calls before deciding whether to trigger
        a swarm negotiation.
        """
        conflicts: list[tuple[Any, Any]] = []
        sorted_events = sorted(events, key=lambda e: e.start)
        for i, ev_a in enumerate(sorted_events):
            for ev_b in sorted_events[i + 1:]:
                if ev_b.start >= ev_a.end:
                    break  # sorted by start, so no further overlaps
                if ev_a.source_sub_account_id != ev_b.source_sub_account_id:
                    conflicts.append((ev_a, ev_b))
        return conflicts
