"""Tests for the self-model module."""

import pytest
from datetime import datetime, timedelta

from a_cal.providers.base import CalendarEventDTO, EmailMessageDTO
from a_cal.self_model import (
    SelfModelDepth,
    FactCategory,
    PrivacyTier,
    SelfModelFact,
    SelfModelSettings,
    SelfModelStore,
    SelfModelExtractor,
    SelfModel,
)


@pytest.fixture
def temp_store(tmp_path):
    return SelfModelStore("test-user", data_dir=str(tmp_path))


@pytest.fixture
def pattern_settings():
    return SelfModelSettings.default_for_depth(SelfModelDepth.PATTERN_MEMORY)


@pytest.fixture
def identity_settings():
    return SelfModelSettings.default_for_depth(SelfModelDepth.LONGITUDINAL_IDENTITY)


def _make_event(title, start, hours=1, attendees=None):
    return CalendarEventDTO(
        provider_event_id=f"evt-{title}-{start.isoformat()}",
        provider_type="google_calendar",
        title=title,
        start=start,
        end=start + timedelta(hours=hours),
        attendees=attendees or [],
    )


class TestDepthHierarchy:
    def test_pattern_is_shallowest(self):
        assert SelfModelDepth.PATTERN_MEMORY.includes(SelfModelDepth.PATTERN_MEMORY)
        assert not SelfModelDepth.PATTERN_MEMORY.includes(SelfModelDepth.ATTENTION_INTENT)

    def test_identity_includes_all(self):
        assert SelfModelDepth.LONGITUDINAL_IDENTITY.includes(SelfModelDepth.PATTERN_MEMORY)
        assert SelfModelDepth.LONGITUDINAL_IDENTITY.includes(SelfModelDepth.ATTENTION_INTENT)
        assert SelfModelDepth.LONGITUDINAL_IDENTITY.includes(SelfModelDepth.LONGITUDINAL_IDENTITY)

    def test_attention_includes_pattern(self):
        assert SelfModelDepth.ATTENTION_INTENT.includes(SelfModelDepth.PATTERN_MEMORY)
        assert not SelfModelDepth.ATTENTION_INTENT.includes(SelfModelDepth.LONGITUDINAL_IDENTITY)


class TestFactCategories:
    def test_pattern_categories_available_at_pattern_depth(self):
        cats = FactCategory.for_depth(SelfModelDepth.PATTERN_MEMORY)
        assert FactCategory.BUSY_TIMES in cats
        assert FactCategory.MEETING_PATTERNS in cats
        assert FactCategory.WORK_FOCUS not in cats
        assert FactCategory.GOALS not in cats

    def test_attention_categories_available_at_attention_depth(self):
        cats = FactCategory.for_depth(SelfModelDepth.ATTENTION_INTENT)
        assert FactCategory.WORK_FOCUS in cats
        assert FactCategory.ENERGY_PATTERNS in cats
        assert FactCategory.GOALS not in cats

    def test_identity_categories_available_at_identity_depth(self):
        cats = FactCategory.for_depth(SelfModelDepth.LONGITUDINAL_IDENTITY)
        assert FactCategory.GOALS in cats
        assert FactCategory.RELATIONSHIPS in cats
        assert FactCategory.LIFE_CONTEXT in cats


class TestPrivacyTiers:
    def test_identity_categories_are_local(self, identity_settings):
        tier = identity_settings.privacy_tier_for(FactCategory.GOALS)
        assert tier == PrivacyTier.TIER_LOCAL
        assert tier.forces_local

    def test_pattern_categories_can_cloud(self, pattern_settings):
        tier = pattern_settings.privacy_tier_for(FactCategory.BUSY_TIMES)
        assert tier == PrivacyTier.TIER_PATTERN
        assert not tier.forces_local

    def test_attention_categories_are_preference(self, identity_settings):
        tier = identity_settings.privacy_tier_for(FactCategory.WORK_FOCUS)
        assert tier == PrivacyTier.TIER_PREFERENCE


class TestSelfModelStore:
    def test_insert_and_retrieve(self, temp_store):
        fact = SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy on Monday 09:00",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.8,
        )
        temp_store.upsert(fact)
        retrieved = temp_store.get(fact.id)
        assert retrieved is not None
        assert retrieved.content == "Busy on Monday 09:00"

    def test_confidence_bump_on_duplicate(self, temp_store):
        fact1 = SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy on Monday 09:00",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.5,
        )
        temp_store.upsert(fact1)
        original_confidence = temp_store.get(fact1.id).confidence

        # Same content, same confidence — should bump (EWMA)
        fact2 = SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy on Monday 09:00",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.5,
        )
        temp_store.upsert(fact2)
        bumped = temp_store.get(fact1.id)
        assert bumped.confidence >= original_confidence

    def test_supersede_on_higher_confidence(self, temp_store):
        fact1 = SelfModelFact(
            category=FactCategory.MEETING_PATTERNS.value,
            content="Avg meeting 30 min",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.3,
        )
        temp_store.upsert(fact1)

        fact2 = SelfModelFact(
            category=FactCategory.MEETING_PATTERNS.value,
            content="Avg meeting 30 min",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.9,
        )
        temp_store.upsert(fact2)

        old = temp_store.get(fact1.id)
        assert old.status == "superseded"
        assert old.superseded_by == fact2.id
        assert temp_store.get(fact2.id).is_active()

    def test_soft_delete(self, temp_store):
        fact = SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Test fact",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.7,
        )
        temp_store.upsert(fact)
        assert temp_store.delete(fact.id)
        assert not temp_store.get(fact.id).is_active()
        assert temp_store.all_active() == []

    def test_search(self, temp_store):
        for content in ["Busy Monday morning", "Prefers afternoons", "Meets with team"]:
            temp_store.upsert(SelfModelFact(
                category=FactCategory.BUSY_TIMES.value,
                content=content,
                depth=SelfModelDepth.PATTERN_MEMORY.value,
                privacy_tier=PrivacyTier.TIER_PATTERN.value,
                confidence=0.7,
            ))
        results = temp_store.search("Monday")
        assert len(results) == 1
        assert "Monday" in results[0].content

    def test_persistence_across_instances(self, tmp_path):
        store1 = SelfModelStore("persist-user", data_dir=str(tmp_path))
        store1.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Persistent fact",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.8,
        ))
        # New store instance pointing at the same dir
        store2 = SelfModelStore("persist-user", data_dir=str(tmp_path))
        active = store2.all_active()
        assert len(active) == 1
        assert active[0].content == "Persistent fact"


class TestExtractor:
    @pytest.mark.asyncio
    async def test_extract_busy_times(self, temp_store, pattern_settings):
        pattern_settings.enabled_categories[FactCategory.BUSY_TIMES.value] = True
        extractor = SelfModelExtractor(pattern_settings, temp_store)

        # 4 events on Monday at 9am — should trigger busy_times pattern
        base = datetime(2026, 7, 6, 9, 0)  # a Monday
        events = [_make_event("Standup", base + timedelta(weeks=i)) for i in range(4)]

        facts = await extractor.extract_from_events(events)
        busy = [f for f in facts if f.category == FactCategory.BUSY_TIMES.value]
        assert len(busy) > 0
        assert "Monday" in busy[0].content

    @pytest.mark.asyncio
    async def test_extract_meeting_patterns(self, temp_store, pattern_settings):
        pattern_settings.enabled_categories[FactCategory.MEETING_PATTERNS.value] = True
        extractor = SelfModelExtractor(pattern_settings, temp_store)

        base = datetime(2026, 7, 6, 10, 0)
        events = [_make_event("Sprint Planning", base + timedelta(weeks=i)) for i in range(4)]

        facts = await extractor.extract_from_events(events)
        patterns = [f for f in facts if f.category == FactCategory.MEETING_PATTERNS.value]
        assert len(patterns) > 0

    @pytest.mark.asyncio
    async def test_depth_gating_blocks_deeper_categories(self, temp_store, pattern_settings):
        """At pattern_memory depth, longitudinal categories should NOT be extracted."""
        pattern_settings.enabled_categories[FactCategory.RELATIONSHIPS.value] = True
        extractor = SelfModelExtractor(pattern_settings, temp_store)

        attendees = [{"email": "colleague@work.com"}]
        base = datetime(2026, 7, 6, 14, 0)
        events = [_make_event("1:1", base + timedelta(weeks=i), attendees=attendees) for i in range(6)]

        facts = await extractor.extract_from_events(events)
        # RELATIONSHIPS should NOT be extracted because depth is pattern_memory
        relationships = [f for f in facts if f.category == FactCategory.RELATIONSHIPS.value]
        assert len(relationships) == 0

    @pytest.mark.asyncio
    async def test_depth_allows_deeper_categories(self, temp_store, identity_settings):
        """At longitudinal_identity depth, relationships should be extracted."""
        identity_settings.enabled_categories[FactCategory.RELATIONSHIPS.value] = True
        identity_settings.enabled_categories[FactCategory.BUSY_TIMES.value] = True
        extractor = SelfModelExtractor(identity_settings, temp_store)

        attendees = [{"email": "colleague@work.com"}]
        base = datetime(2026, 7, 6, 14, 0)
        events = [_make_event("1:1", base + timedelta(weeks=i), attendees=attendees) for i in range(6)]

        facts = await extractor.extract_from_events(events)
        relationships = [f for f in facts if f.category == FactCategory.RELATIONSHIPS.value]
        assert len(relationships) > 0
        assert "colleague@work.com" in relationships[0].content


class TestSelfModel:
    def test_inject_into_prompt(self, tmp_path):
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy on Monday mornings",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.8,
        ))
        prompt = model.inject_into_prompt()
        assert "Busy on Monday mornings" in prompt
        assert "Self-model context" in prompt

    def test_inject_disabled_when_feed_off(self, tmp_path):
        settings = SelfModelSettings(feed_into_agents=False)
        model = SelfModel("test-user", settings=settings, data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Test",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.8,
        ))
        assert model.inject_into_prompt() == ""

    def test_has_local_only_facts(self, tmp_path):
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.GOALS.value,
            content="Wants to become a team lead",
            depth=SelfModelDepth.LONGITUDINAL_IDENTITY.value,
            privacy_tier=PrivacyTier.TIER_LOCAL.value,
            confidence=0.7,
        ))
        assert model.has_local_only_facts()

    def test_no_local_only_facts(self, tmp_path):
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy Monday",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.7,
        ))
        assert not model.has_local_only_facts()

    def test_export_includes_settings_and_facts(self, tmp_path):
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Test",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.7,
        ))
        export = model.export()
        assert export["user_id"] == "test-user"
        assert export["store"]["fact_count"] == 1
        assert "settings" in export
        assert len(export["store"]["facts"]) == 1

    def test_clear_all(self, tmp_path):
        model = SelfModel("test-user", data_dir=str(tmp_path))
        for i in range(3):
            model.store.upsert(SelfModelFact(
                category=FactCategory.BUSY_TIMES.value,
                content=f"Fact {i}",
                depth=SelfModelDepth.PATTERN_MEMORY.value,
                privacy_tier=PrivacyTier.TIER_PATTERN.value,
                confidence=0.7,
            ))
        count = model.clear_all()
        assert count == 3
        assert model.store.all_active() == []
