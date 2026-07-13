"""The SelfModel — the user's persistent, queryable self-model.

This ties together settings, store, and extractor into the object that agents
and the calendar UI interact with. It provides:
  - Context injection: format relevant facts into a prompt prefix for agents.
  - Calendar enrichment: tag events with energy/context signals.
  - Proactive suggestion ranking: filter facts by priority tier.
  - Transparency: export everything the model knows for the settings view.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from a_cal.providers.base import CalendarEventDTO, EmailMessageDTO
from a_cal.self_model.extractor import SelfModelExtractor
from a_cal.self_model.settings import SelfModelSettings
from a_cal.self_model.store import SelfModelStore
from a_cal.self_model.types import FactCategory, PrivacyTier, SelfModelFact

logger = logging.getLogger(__name__)


class SelfModel:
    """The user's self-model — the object agents and the UI talk to.

    Lifecycle:
      1. Created per user with their settings + local store.
      2. Fed calendar events and emails by the sync engine (extraction).
      3. Queried by agents for context (inject_into_prompt).
      4. Queried by the UI for enrichment (enrich_events) and transparency (export).
    """

    def __init__(
        self,
        user_id: str,
        settings: SelfModelSettings | None = None,
        store: SelfModelStore | None = None,
        extractor: SelfModelExtractor | None = None,
        data_dir: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.settings = settings or SelfModelSettings()
        self.store = store or SelfModelStore(user_id, data_dir=data_dir)
        self.extractor = extractor or SelfModelExtractor(self.settings, self.store)

    def update_settings(self, settings: SelfModelSettings) -> None:
        """Update the user's self-model settings (from the settings UI)."""
        self.settings = settings
        self.extractor.settings = settings

    async def observe_events(
        self, events: list[CalendarEventDTO], provenance: str = "calendar"
    ) -> list[SelfModelFact]:
        """Feed calendar events into the extractor (fire-and-forget safe)."""
        return await self.extractor.extract_from_events(events, provenance)

    async def observe_emails(
        self, messages: list[EmailMessageDTO], provenance: str = "email"
    ) -> list[SelfModelFact]:
        """Feed email messages into the extractor."""
        return await self.extractor.extract_from_emails(messages, provenance)

    def inject_into_prompt(
        self, max_facts: int = 10, categories: list[FactCategory] | None = None
    ) -> str:
        """Format active facts as a context prefix for agent prompts.

        Only facts the user has enabled are included. Privacy-tier-local facts
        are included (they're always local), but only when feeding a local model
        — the caller is responsible for not sending this to a cloud model when
        TIER_LOCAL facts are present.
        """
        if not self.settings.feed_into_agents:
            return ""

        facts = self.store.all_active()
        if categories:
            cat_values = {c.value for c in categories}
            facts = [f for f in facts if f.category in cat_values]

        # Sort by confidence, take top N
        facts = facts[:max_facts]
        if not facts:
            return ""

        lines: list[str] = ["[Self-model context — what I know about you]"]
        for fact in facts:
            lines.append(f"- {fact.content} (confidence: {fact.confidence:.0%})")
        return "\n".join(lines)

    def enrich_events(self, events: list[CalendarEventDTO]) -> list[CalendarEventDTO]:
        """Tag events with self-model context (energy, relationship, pattern).

        This is what powers the calendar view's color-coding and context badges.
        Mutates event metadata in place — returns the same list.
        """
        if not self.settings.feed_into_calendar_view:
            return events

        import copy

        # Build lookup tables from facts
        busy_times = {
            f.content.split(" on ")[1].split(" (")[0]: f
            for f in self.store.by_category(FactCategory.BUSY_TIMES.value)
            if " on " in f.content
        }
        relationships = {
            addr: f for f in self.store.by_category(FactCategory.RELATIONSHIPS.value)
            for addr in [w for w in f.content.split() if "@" in w]
        }
        prefs = self.store.by_category(FactCategory.MEETING_PREFS.value)

        enriched: list[CalendarEventDTO] = []
        for ev in events:
            ev_copy = copy.copy(ev)
            ev_copy.metadata = dict(ev.metadata)

            # Tag with busy-time pattern
            slot = f"{ev.start.strftime('%A')} {ev.start.hour:02d}:00"
            if slot in busy_times:
                ev_copy.metadata["self_model_pattern"] = "recurring_busy_slot"

            # Tag with relationship context
            for attendee in ev.attendees:
                email = attendee.get("email", "")
                if email in relationships:
                    ev_copy.metadata.setdefault("self_model_contacts", []).append(email)

            # Tag with meeting preference alignment
            if prefs:
                ev_copy.metadata["self_model_prefs"] = [p.content for p in prefs]

            enriched.append(ev_copy)
        return enriched

    def get_proactive_suggestions(self, limit: int = 5) -> list[dict[str, Any]]:
        """Rank facts by priority for proactive suggestions.

        Uses the tiered priority concept from the meta-cognition protocol:
        facts that touch the user's attention/intent are higher priority than
        pure pattern facts. Only returned if the user opted into proactive.
        """
        if not self.settings.feed_into_proactive or not self.settings.proactive_suggestions_enabled:
            return []

        facts = self.store.all_active()
        suggestions: list[dict[str, Any]] = []

        for fact in facts:
            # Priority: longitudinal > attention > pattern
            depth = fact.depth
            priority = 1
            if depth == "attention_intent":
                priority = 2
            elif depth == "longitudinal_identity":
                priority = 3

            suggestions.append({
                "fact_id": fact.id,
                "content": fact.content,
                "category": fact.category,
                "priority": priority,
                "confidence": fact.confidence,
            })

        suggestions.sort(key=lambda s: (s["priority"], s["confidence"]), reverse=True)
        return suggestions[:limit]

    def export(self) -> dict[str, Any]:
        """Full transparency export — everything the model knows, for the UI."""
        store_export = self.store.export()
        return {
            "user_id": self.user_id,
            "settings": self.settings.to_dict(),
            "store": store_export,
            "available_categories": [c.value for c in self.settings.available_categories()],
            "enabled_categories": [c.value for c in self.settings.enabled_category_list()],
        }

    def delete_fact(self, fact_id: str) -> bool:
        """User-initiated fact deletion (from the transparency settings view)."""
        return self.store.delete(fact_id)

    def clear_all(self) -> int:
        """Wipe the self-model entirely (nuclear option in settings)."""
        return self.store.clear_all()

    def has_local_only_facts(self) -> bool:
        """Whether the model holds any TIER_LOCAL facts.

        Agents use this to decide whether context can go to a cloud model or
        must stay local (privacy-tiered routing, Q4).
        """
        return any(
            f.privacy_tier == PrivacyTier.TIER_LOCAL.value
            for f in self.store.all_active()
        )
