"""Tests for the A-Cal specialist agents and conductor."""

import pytest

from a_cal.agents import (
    AgentSpec,
    CognitiveTier,
    A_CAL_AGENTS,
    CONDUCTOR_SPEC,
    SYNC_AGENT_SPEC,
    SCHEDULE_AGENT_SPEC,
    EMAIL_AGENT_SPEC,
    NEGOTIATE_AGENT_SPEC,
    SELF_MODEL_AGENT_SPEC,
    ACalConductor,
    AgentRegistry,
)
from a_cal.agents.conductor import IntentType


class TestAgentSpecs:
    def test_all_six_agents_present(self):
        names = [a.name for a in A_CAL_AGENTS]
        assert "a_cal_conductor" in names
        assert "a_cal_sync_agent" in names
        assert "a_cal_schedule_agent" in names
        assert "a_cal_email_agent" in names
        assert "a_cal_negotiate_agent" in names
        assert "a_cal_self_model_agent" in names
        assert len(A_CAL_AGENTS) == 6

    def test_conductor_is_first(self):
        assert A_CAL_AGENTS[0].name == "a_cal_conductor"

    def test_email_agent_forced_local(self):
        assert EMAIL_AGENT_SPEC.privacy_force_local is True

    def test_self_model_agent_forced_local(self):
        assert SELF_MODEL_AGENT_SPEC.privacy_force_local is True

    def test_sync_agent_uses_micro_tier(self):
        assert SYNC_AGENT_SPEC.default_tier == CognitiveTier.MICRO

    def test_negotiate_agent_can_negotiate(self):
        assert NEGOTIATE_AGENT_SPEC.can_negotiate is True

    def test_schedule_agent_can_negotiate(self):
        assert SCHEDULE_AGENT_SPEC.can_negotiate is True

    def test_conductor_can_negotiate(self):
        assert CONDUCTOR_SPEC.can_negotiate is True

    def test_marketplace_metadata_present(self):
        for agent in A_CAL_AGENTS:
            meta = agent.marketplace_metadata
            assert "summary" in meta
            assert "what_it_does" in meta
            assert "gaps_and_limits" in meta
            assert "integration_notes" in meta
            assert meta["license"] == "AGPL-3.0-or-later"

    def test_spec_roundtrip(self):
        data = SCHEDULE_AGENT_SPEC.to_dict()
        restored = AgentSpec.from_dict(data)
        assert restored.name == SCHEDULE_AGENT_SPEC.name
        assert restored.default_tier == SCHEDULE_AGENT_SPEC.default_tier
        assert restored.system_prompt == SCHEDULE_AGENT_SPEC.system_prompt


class TestConductorRouting:
    def test_classify_sync_intent(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("sync my Google calendar") == IntentType.SYNC
        assert conductor.classify_intent("refresh providers") == IntentType.SYNC

    def test_classify_schedule_intent(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("find a free slot tomorrow") == IntentType.SCHEDULE
        assert conductor.classify_intent("reschedule my 3pm") == IntentType.SCHEDULE

    def test_classify_email_intent(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("check my inbox") == IntentType.EMAIL
        assert conductor.classify_intent("reply to the invite") == IntentType.EMAIL

    def test_classify_negotiate_intent(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("negotiate a new time with them") == IntentType.NEGOTIATE

    def test_classify_self_model_intent(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("what do you know about me") == IntentType.SELF_MODEL

    def test_classify_chat_fallback(self):
        conductor = ACalConductor()
        assert conductor.classify_intent("hello there") == IntentType.CHAT

    def test_route_to_schedule_specialist(self):
        conductor = ACalConductor()
        decision = conductor.route("find a free slot next Tuesday")
        assert decision.specialist.name == "a_cal_schedule_agent"
        assert decision.tier == CognitiveTier.VERSATILE

    def test_route_email_forced_local(self):
        conductor = ACalConductor()
        decision = conductor.route("check my inbox for invites")
        assert decision.force_local is True
        assert decision.specialist.name == "a_cal_email_agent"

    def test_route_self_model_forced_local(self):
        conductor = ACalConductor()
        decision = conductor.route("what do you know about me")
        assert decision.force_local is True

    def test_route_sync_uses_micro_tier(self):
        conductor = ACalConductor()
        decision = conductor.route("sync all providers")
        assert decision.tier == CognitiveTier.MICRO
        assert not decision.force_local  # sync is not privacy-sensitive

    def test_route_chat_to_conductor(self):
        conductor = ACalConductor()
        decision = conductor.route("hello there")
        assert decision.specialist.name == "a_cal_conductor"

    def test_route_with_self_model_context(self, tmp_path):
        from a_cal.self_model import SelfModel, SelfModelFact, SelfModelDepth, PrivacyTier, FactCategory
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.BUSY_TIMES.value,
            content="Busy on Monday mornings",
            depth=SelfModelDepth.PATTERN_MEMORY.value,
            privacy_tier=PrivacyTier.TIER_PATTERN.value,
            confidence=0.8,
        ))
        conductor = ACalConductor(self_model=model)
        decision = conductor.route("find a slot next week")
        assert "Busy on Monday mornings" in decision.self_model_context

    def test_route_force_local_when_self_model_has_local_facts(self, tmp_path):
        from a_cal.self_model import SelfModel, SelfModelFact, SelfModelDepth, PrivacyTier, FactCategory
        model = SelfModel("test-user", data_dir=str(tmp_path))
        model.store.upsert(SelfModelFact(
            category=FactCategory.GOALS.value,
            content="Wants to become team lead",
            depth=SelfModelDepth.LONGITUDINAL_IDENTITY.value,
            privacy_tier=PrivacyTier.TIER_LOCAL.value,
            confidence=0.7,
        ))
        conductor = ACalConductor(self_model=model)
        decision = conductor.route("check my inbox")
        assert decision.force_local is True

    @pytest.mark.asyncio
    async def test_handle_standalone_returns_routing(self):
        conductor = ACalConductor()
        result = await conductor.handle("find a free slot tomorrow")
        assert result["standalone"] is True
        assert result["routing"]["specialist"] == "a_cal_schedule_agent"
        assert result["response"] is not None  # real rule-based response
        assert "slot" in result["response"].lower()
        assert "actions" in result
        assert len(result["actions"]) > 0

    @pytest.mark.asyncio
    async def test_handle_standalone_sync_response(self):
        conductor = ACalConductor()
        result = await conductor.handle("sync all my providers")
        assert result["standalone"] is True
        assert result["routing"]["specialist"] == "a_cal_sync_agent"
        assert result["response"] is not None
        assert "provider" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_handle_standalone_email_response(self):
        conductor = ACalConductor()
        result = await conductor.handle("check inbox for invites")
        assert result["standalone"] is True
        assert result["routing"]["specialist"] == "a_cal_email_agent"
        assert result["response"] is not None

    @pytest.mark.asyncio
    async def test_handle_standalone_chat_response(self):
        conductor = ACalConductor()
        result = await conductor.handle("hello there")
        assert result["standalone"] is True
        assert result["response"] is not None
        assert "conductor" in result["response"].lower() or "help" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_handle_with_nervous_system(self):
        from a_cal.agents.nervous_system import NervousSystemCoordinator
        ns = NervousSystemCoordinator()
        conductor = ACalConductor(nervous_system=ns)
        result = await conductor.handle("find a free slot tomorrow")
        assert result["standalone"] is True
        assert result["routing_trace"] is not None
        assert "thalamus_gate" in result["routing_trace"]
        assert len(result["cas_modules_engaged"]) > 0

    def test_list_specialists(self):
        conductor = ACalConductor()
        specs = conductor.list_specialists()
        assert len(specs) == 6
        assert specs[0]["name"] == "a_cal_conductor"


class TestAgentRegistry:
    def test_list_agents_conductor_first(self):
        registry = AgentRegistry()
        agents = registry.list_agents()
        assert agents[0].name == "a_cal_conductor"
        assert len(agents) == 6

    def test_get_by_name(self):
        registry = AgentRegistry()
        spec = registry.get("a_cal_schedule_agent")
        assert spec is not None
        assert spec.display_name == "Schedule Agent"

    def test_register_custom_agent(self):
        registry = AgentRegistry()
        custom = AgentSpec(
            name="a_cal_custom_agent",
            display_name="My Custom Agent",
            description="User-created specialist",
            system_prompt="You are a custom agent.",
        )
        registry.register(custom)
        assert registry.get("a_cal_custom_agent") is not None
        assert len(registry.list_agents()) == 7

    def test_unregister_custom_only(self):
        registry = AgentRegistry()
        custom = AgentSpec(
            name="a_cal_custom_agent",
            display_name="Custom",
            description="Custom",
            system_prompt="Custom",
        )
        registry.register(custom)
        # Can unregister custom
        assert registry.unregister("a_cal_custom_agent") is True
        # Cannot unregister built-in
        assert registry.unregister("a_cal_sync_agent") is False

    def test_to_dict_list(self):
        registry = AgentRegistry()
        dicts = registry.to_dict_list()
        assert len(dicts) == 6
        assert all("name" in d and "system_prompt" in d for d in dicts)
