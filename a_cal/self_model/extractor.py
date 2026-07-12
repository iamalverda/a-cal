"""Depth-gated fact extraction for the self-model.

The extractor observes calendar events and email messages and derives facts
about the user — but only within the categories the user has enabled at their
chosen depth. This is the bridge between raw provider data and the self-model.

Two modes:
  1. RULE_BASED (default, no LLM needed) — pattern detection from event
     metadata: recurring slots, meeting frequency, response times, timezones.
  2. LLM_ASSISTED (opt-in) — uses atom's LLM service to infer deeper facts
     (goals, energy patterns, relationships). Always respects privacy tiers:
     TIER_LOCAL facts are only extracted by local models.

The extractor never blocks the sync pipeline — it runs as a fire-and-forget
background task, mirroring atom's turn_fact_extractor design.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from a_cal.providers.base import CalendarEventDTO, EmailMessageDTO
from a_cal.self_model.settings import SelfModelSettings
from a_cal.self_model.store import SelfModelStore
from a_cal.self_model.types import FactCategory, PrivacyTier, SelfModelDepth, SelfModelFact

logger = logging.getLogger(__name__)


class SelfModelExtractor:
    """Derives self-model facts from calendar events and email messages.

    Gated by the user's settings: only enabled categories at the chosen depth
    are extracted. Rule-based extraction runs always (no deps); LLM-assisted
    extraction is opt-in and privacy-tier-aware.
    """

    def __init__(
        self,
        settings: SelfModelSettings,
        store: SelfModelStore,
        llm_service: Any = None,  # atom's get_llm_service() — None in standalone
    ) -> None:
        self.settings = settings
        self.store = store
        self.llm_service = llm_service

    async def extract_from_events(
        self, events: List[CalendarEventDTO], provenance_prefix: str = "calendar"
    ) -> List[SelfModelFact]:
        """Extract facts from a batch of calendar events.

        Returns the facts that were upserted (new or confidence-bumped).
        Never raises — extraction failures are logged and swallowed.
        """
        try:
            facts: List[SelfModelFact] = []
            facts.extend(self._extract_busy_times(events, provenance_prefix))
            facts.extend(self._extract_meeting_patterns(events, provenance_prefix))
            if self.settings.effective_depth().includes(SelfModelDepth.ATTENTION_INTENT):
                facts.extend(self._extract_meeting_prefs(events, provenance_prefix))
            if self.settings.effective_depth().includes(SelfModelDepth.LONGITUDINAL_IDENTITY):
                facts.extend(self._extract_relationships(events, provenance_prefix))
            # Persist
            for fact in facts:
                self.store.upsert(fact)
            return facts
        except Exception as exc:
            logger.warning("self-model extraction failed: %s", exc)
            return []

    async def extract_from_emails(
        self, messages: List[EmailMessageDTO], provenance_prefix: str = "email"
    ) -> List[SelfModelFact]:
        """Extract facts from email messages (response cadence, contacts)."""
        try:
            facts: List[SelfModelFact] = []
            facts.extend(self._extract_response_cadence(messages, provenance_prefix))
            if self.settings.effective_depth().includes(SelfModelDepth.LONGITUDINAL_IDENTITY):
                facts.extend(self._extract_email_relationships(messages, provenance_prefix))
            for fact in facts:
                self.store.upsert(fact)
            return facts
        except Exception as exc:
            logger.warning("self-model email extraction failed: %s", exc)
            return []

    # --- rule-based extractors (no LLM needed) -------------------------------

    def _extract_busy_times(
        self, events: List[CalendarEventDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Detect recurring busy time slots (e.g. "busy every Mon 9-10")."""
        if not self.settings.is_category_enabled(FactCategory.BUSY_TIMES):
            return []

        slot_counter: Counter[str] = Counter()
        event_ids_by_slot: Dict[str, List[str]] = {}

        for ev in events:
            day = ev.start.strftime("%A")
            hour = ev.start.hour
            slot = f"{day} {hour:02d}:00"
            slot_counter[slot] += 1
            event_ids_by_slot.setdefault(slot, []).append(ev.provider_event_id)

        facts: List[SelfModelFact] = []
        for slot, count in slot_counter.items():
            if count >= 3:  # recurring pattern threshold
                privacy = self.settings.privacy_tier_for(FactCategory.BUSY_TIMES)
                facts.append(SelfModelFact(
                    category=FactCategory.BUSY_TIMES.value,
                    content=f"Consistently busy on {slot} ({count} occurrences)",
                    depth=SelfModelDepth.PATTERN_MEMORY.value,
                    privacy_tier=privacy.value,
                    confidence=min(0.5 + count * 0.1, 0.95),
                    provenance=f"{provenance}:busy_times",
                    source_event_ids=event_ids_by_slot[slot],
                ))
        return facts

    def _extract_meeting_patterns(
        self, events: List[CalendarEventDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Detect frequent meeting types and typical durations."""
        if not self.settings.is_category_enabled(FactCategory.MEETING_PATTERNS):
            return []

        title_counter: Counter[str] = Counter()
        durations: List[float] = []

        for ev in events:
            # Normalize title: lowercase, strip numbers/special chars
            normalized = " ".join(w.lower() for w in ev.title.split() if w.isalpha())
            if normalized:
                title_counter[normalized] += 1
            if ev.end and ev.start:
                durations.append((ev.end - ev.start).total_seconds() / 60)

        facts: List[SelfModelFact] = []
        privacy = self.settings.privacy_tier_for(FactCategory.MEETING_PATTERNS)

        for title, count in title_counter.items():
            if count >= 3:
                facts.append(SelfModelFact(
                    category=FactCategory.MEETING_PATTERNS.value,
                    content=f"Frequently has '{title}' meetings ({count} times)",
                    depth=SelfModelDepth.PATTERN_MEMORY.value,
                    privacy_tier=privacy.value,
                    confidence=min(0.4 + count * 0.1, 0.9),
                    provenance=f"{provenance}:meeting_patterns",
                ))

        if durations:
            avg_dur = sum(durations) / len(durations)
            if avg_dur > 0:
                facts.append(SelfModelFact(
                    category=FactCategory.MEETING_PATTERNS.value,
                    content=f"Average meeting duration is {avg_dur:.0f} minutes",
                    depth=SelfModelDepth.PATTERN_MEMORY.value,
                    privacy_tier=privacy.value,
                    confidence=0.6,
                    provenance=f"{provenance}:meeting_patterns",
                ))
        return facts

    def _extract_meeting_prefs(
        self, events: List[CalendarEventDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Infer meeting preferences from scheduling patterns."""
        if not self.settings.is_category_enabled(FactCategory.MEETING_PREFS):
            return []

        facts: List[SelfModelFact] = []
        privacy = self.settings.privacy_tier_for(FactCategory.MEETING_PREFS)

        # Detect preferred meeting times (morning vs afternoon)
        morning = sum(1 for e in events if e.start.hour < 12)
        afternoon = sum(1 for e in events if e.start.hour >= 12)
        total = morning + afternoon
        if total > 5:
            if morning > afternoon * 2:
                facts.append(SelfModelFact(
                    category=FactCategory.MEETING_PREFS.value,
                    content="Strongly prefers morning meetings",
                    depth=SelfModelDepth.ATTENTION_INTENT.value,
                    privacy_tier=privacy.value,
                    confidence=0.7,
                    provenance=f"{provenance}:meeting_prefs",
                ))
            elif afternoon > morning * 2:
                facts.append(SelfModelFact(
                    category=FactCategory.MEETING_PREFS.value,
                    content="Strongly prefers afternoon meetings",
                    depth=SelfModelDepth.ATTENTION_INTENT.value,
                    privacy_tier=privacy.value,
                    confidence=0.7,
                    provenance=f"{provenance}:meeting_prefs",
                ))

        # Detect async preference (lots of short events vs few long ones)
        short_events = sum(1 for e in events if (e.end - e.start).total_seconds() < 1800)
        if total > 10 and short_events / total > 0.6:
            facts.append(SelfModelFact(
                category=FactCategory.MEETING_PREFS.value,
                content="Tends toward short, frequent check-ins (async-friendly)",
                depth=SelfModelDepth.ATTENTION_INTENT.value,
                privacy_tier=privacy.value,
                confidence=0.5,
                provenance=f"{provenance}:meeting_prefs",
            ))
        return facts

    def _extract_relationships(
        self, events: List[CalendarEventDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Identify recurring contacts and their meeting context."""
        if not self.settings.is_category_enabled(FactCategory.RELATIONSHIPS):
            return []

        contact_counter: Counter[str] = Counter()
        for ev in events:
            for attendee in ev.attendees:
                email = attendee.get("email", "")
                if email:
                    contact_counter[email] += 1

        facts: List[SelfModelFact] = []
        privacy = self.settings.privacy_tier_for(FactCategory.RELATIONSHIPS)

        for email, count in contact_counter.items():
            if count >= 5:
                facts.append(SelfModelFact(
                    category=FactCategory.RELATIONSHIPS.value,
                    content=f"Meets frequently with {email} ({count} times)",
                    depth=SelfModelDepth.LONGITUDINAL_IDENTITY.value,
                    privacy_tier=privacy.value,
                    confidence=min(0.4 + count * 0.05, 0.9),
                    provenance=f"{provenance}:relationships",
                ))
        return facts

    def _extract_response_cadence(
        self, messages: List[EmailMessageDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Detect email response patterns (speed, time of day)."""
        if not self.settings.is_category_enabled(FactCategory.RESPONSE_CADENCE):
            return []

        facts: List[SelfModelFact] = []
        privacy = self.settings.privacy_tier_for(FactCategory.RESPONSE_CADENCE)

        # Detect active email hours
        hour_counter: Counter[int] = Counter()
        for msg in messages:
            if msg.received_at:
                hour_counter[msg.received_at.hour] += 1

        if hour_counter:
            peak_hour = hour_counter.most_common(1)[0][0]
            facts.append(SelfModelFact(
                category=FactCategory.RESPONSE_CADENCE.value,
                content=f"Most active on email around {peak_hour:02d}:00",
                depth=SelfModelDepth.PATTERN_MEMORY.value,
                privacy_tier=privacy.value,
                confidence=0.5,
                provenance=f"{provenance}:response_cadence",
            ))
        return facts

    def _extract_email_relationships(
        self, messages: List[EmailMessageDTO], provenance: str
    ) -> List[SelfModelFact]:
        """Identify frequent correspondents from email."""
        if not self.settings.is_category_enabled(FactCategory.RELATIONSHIPS):
            return []

        contact_counter: Counter[str] = Counter()
        for msg in messages:
            if msg.from_address:
                contact_counter[msg.from_address] += 1

        facts: List[SelfModelFact] = []
        privacy = self.settings.privacy_tier_for(FactCategory.RELATIONSHIPS)

        for addr, count in contact_counter.items():
            if count >= 10:
                facts.append(SelfModelFact(
                    category=FactCategory.RELATIONSHIPS.value,
                    content=f"Frequent email correspondent: {addr} ({count} messages)",
                    depth=SelfModelDepth.LONGITUDINAL_IDENTITY.value,
                    privacy_tier=privacy.value,
                    confidence=min(0.3 + count * 0.03, 0.85),
                    provenance=f"{provenance}:email_relationships",
                ))
        return facts
