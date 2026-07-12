"""Sub-account sync engine.

Composes events from every provider connection under a sub-account and rolls
them up into the main (conductor) view according to the sub-account's
``sync_mode`` and its ``SubCalendarSyncRule`` rows.

The four modes (Q3):
  * MIRROR_FILTER (default) — mirror every event up, then apply include/exclude
    rules. Simple and predictable.
  * INTELLIGENT_MERGE — merge across subs, deduplicate, resolve conflicts (using
    atom's ScheduleOptimizer), surface the most relevant per context.
  * LAYERED_FEDERATION — each sub stays fully autonomous; the main view is a
    read-only composite; writes flow back down per two-way rules.
  * PER_SUB_AGENT — each sub gets its own agent; the conductor merges agent
    outputs and sub-agents can negotiate conflicts.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from a_cal.providers.base import CalendarEventDTO, CalendarProvider
from a_cal.sync.rules import RuleOutcome, evaluate_rules

logger = logging.getLogger(__name__)


class SubAccountSyncEngine:
    """Pulls events from a sub-account's providers and applies its sync model."""

    def __init__(self, sub_account: Dict[str, Any], providers: List[CalendarProvider]) -> None:
        self.sub_account = sub_account
        self.providers = providers
        self.sync_mode = sub_account.get("sync_mode", "mirror_filter")
        self.sync_rules = sub_account.get("sync_rules", [])

    async def pull_window(self, start: datetime, end: datetime) -> List[CalendarEventDTO]:
        """Fetch + filter/transform events for [start, end) from all providers."""
        raw: List[CalendarEventDTO] = []
        for provider in self.providers:
            try:
                events = await provider.list_events(start, end)
                # Stamp provenance so the main view always knows the source sub.
                for ev in events:
                    ev.source_sub_account_id = self.sub_account.get("id")
                raw.extend(events)
            except Exception as exc:
                logger.warning("provider pull failed for sub %s: %s", self.sub_account.get("id"), exc)

        return self._apply_model(raw)

    def _apply_model(self, events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Apply the sub-account's sync mode + rules to the raw event list."""
        if self.sync_mode == "mirror_filter":
            return self._mirror_filter(events)
        if self.sync_mode == "intelligent_merge":
            return self._intelligent_merge(events)
        if self.sync_mode == "layered_federation":
            return self._layered_federation(events)
        if self.sync_mode == "per_sub_agent":
            return self._per_sub_agent(events)
        # Unknown mode — degrade to mirror+filter (the safe default).
        return self._mirror_filter(events)

    def _mirror_filter(self, events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Default: mirror everything up, then apply include/exclude/transform rules."""
        out: List[CalendarEventDTO] = []
        for ev in events:
            outcome = evaluate_rules(ev, self.sync_rules)
            if outcome.included:
                out.append(outcome.transformed_event or ev)
        return out

    def _intelligent_merge(self, events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Merge + deduplicate + conflict-resolve across the sub's providers."""
        filtered = self._mirror_filter(events)
        deduped = self._deduplicate(filtered)
        return self._resolve_conflicts(deduped)

    def _layered_federation(self, events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Federation: keep each provider's events distinct and tagged, read-only roll-up.

        Events are tagged with their provider + calendar origin but NOT merged.
        The main view is a composite; writes are routed back by the API layer.
        """
        out: List[CalendarEventDTO] = []
        for ev in events:
            outcome = evaluate_rules(ev, self.sync_rules)
            if not outcome.included:
                continue
            tagged = outcome.transformed_event or ev
            tagged.metadata["federated"] = True
            tagged.metadata["read_only"] = True
            out.append(tagged)
        return out

    def _per_sub_agent(self, events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Each event that hits an AGENT rule is flagged for agent review.

        The conductor merges the sub-agent's filtered output. Agent dispatch is
        delegated to atom's conductor (this layer marks intent; atom executes).
        """
        out: List[CalendarEventDTO] = []
        agent_queue: List[CalendarEventDTO] = []
        for ev in events:
            outcome = evaluate_rules(ev, self.sync_rules)
            if outcome.agent_review:
                agent_queue.append(ev)
                continue
            if outcome.included:
                out.append(outcome.transformed_event or ev)
        # Flag agent-queued events for atom's conductor to process.
        for ev in agent_queue:
            ev.metadata["agent_review"] = True
            ev.metadata["source_sub_account_id"] = self.sub_account.get("id")
            out.append(ev)
        return out

    @staticmethod
    def _deduplicate(events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Drop near-duplicate events (same title + overlapping time window)."""
        kept: List[CalendarEventDTO] = []
        for ev in events:
            dup = False
            for k in kept:
                if (
                    k.title == ev.title
                    and abs((k.start - ev.start).total_seconds()) < 300  # 5-min tolerance
                ):
                    dup = True
                    break
            if not dup:
                kept.append(ev)
        return kept

    @staticmethod
    def _resolve_conflicts(events: List[CalendarEventDTO]) -> List[CalendarEventDTO]:
        """Detect overlapping events and flag them for agent/optimizer resolution.

        Full rescheduling is delegated to atom's ScheduleOptimizer; here we only
        flag overlaps so the conductor can propose moves.
        """
        sorted_ev = sorted(events, key=lambda e: e.start)
        for i, ev in enumerate(sorted_ev):
            for other in sorted_ev[i + 1:]:
                if other.start >= ev.end:
                    break  # sorted, so no further overlaps
                ev.metadata["conflict"] = True
                other.metadata["conflict"] = True
        return sorted_ev
