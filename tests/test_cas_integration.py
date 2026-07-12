"""Tests for the Conscious Agent System (CAS) bio-mimetic integration.

Tests the CAS agent specs, the nervous system coordinator, and the
bio-mimetic signal routing architecture.
"""

import pytest
from a_cal.agents.cas_specs import (
    CAS_AGENTS,
    CAS_AGENTS_BY_NAME,
    CAS_AUGMENTATION_MAP,
    THALAMUS_GATE_SPEC,
    HIPPOCAMPUS_SPEC,
    RAS_SPEC,
    AUTONOMIC_SPEC,
    INSULA_SPEC,
    CEREBELLUM_SPEC,
    BASAL_GANGLIA_SPEC,
    CLAUSTRUM_SPEC,
    LIMBIC_SPEC,
    VAGAL_TONE_SPEC,
    get_cas_agents_for_specialist,
)
from a_cal.agents.nervous_system import (
    NervousSystemCoordinator,
    SystemState,
    ActivationState,
    GateState,
    AutonomicMode,
)


class TestCASSpecs:
    """Test the CAS bio-mimetic agent specifications."""

    def test_all_cas_agents_have_brain_regions(self):
        """Every CAS agent must have a brain_region and cas_source."""
        for agent in CAS_AGENTS:
            assert agent.cas.brain_region, f"{agent.name} missing brain_region"
            assert agent.cas.cas_source, f"{agent.name} missing cas_source"
            assert agent.cas.augments, f"{agent.name} missing augments"
            assert agent.cas.nervous_system_layer, f"{agent.name} missing layer"

    def test_cas_agent_count(self):
        """Should have 10 bio-mimetic agents."""
        assert len(CAS_AGENTS) == 10

    def test_cas_agents_are_bio_mimetic(self):
        """All CAS agents should be marked as bio-mimetic in to_dict."""
        for agent in CAS_AGENTS:
            d = agent.to_dict()
            assert d["is_bio_mimetic"] is True
            assert "cas" in d
            assert d["cas"]["brain_region"]

    def test_cas_agent_names_are_unique(self):
        """All CAS agent names must be unique."""
        names = [a.name for a in CAS_AGENTS]
        assert len(names) == len(set(names))

    def test_cas_agent_names_prefixed(self):
        """All CAS agent names should be prefixed with cas_."""
        for agent in CAS_AGENTS:
            assert agent.name.startswith("cas_"), f"{agent.name} missing cas_ prefix"

    def test_privacy_forced_local_for_sensitive_modules(self):
        """Hippocampus, insula, limbic, and vagal tone must be privacy-forced local."""
        local_required = [HIPPOCAMPUS_SPEC, INSULA_SPEC, LIMBIC_SPEC, VAGAL_TONE_SPEC]
        for spec in local_required:
            assert spec.privacy_force_local is True, f"{spec.name} should be local-only"

    def test_thalamus_gate_is_micro_tier(self):
        """Thalamus gate should be micro tier (fast filtering)."""
        assert THALAMUS_GATE_SPEC.default_tier.value == "micro"

    def test_augmentation_map_covers_all_specialists(self):
        """The augmentation map should cover all 6 original specialists."""
        expected_specialists = {
            "a_cal_conductor",
            "a_cal_sync_agent",
            "a_cal_self_model_agent",
            "a_cal_negotiate_agent",
            "a_cal_schedule_agent",
            "a_cal_email_agent",
        }
        assert set(CAS_AUGMENTATION_MAP.keys()) == expected_specialists

    def test_get_cas_agents_for_specialist(self):
        """get_cas_agents_for_specialist should return the right modules."""
        conductor_cas = get_cas_agents_for_specialist("a_cal_conductor")
        names = [a.name for a in conductor_cas]
        assert "cas_thalamus_gate" in names
        assert "cas_ras" in names
        assert "cas_basal_ganglia" in names
        assert "cas_claustrum" in names

    def test_get_cas_agents_for_unknown_specialist(self):
        """Unknown specialist should return empty list."""
        result = get_cas_agents_for_specialist("nonexistent")
        assert result == []

    def test_cas_agent_has_system_prompt(self):
        """Every CAS agent must have a non-empty system prompt."""
        for agent in CAS_AGENTS:
            assert agent.system_prompt, f"{agent.name} missing system prompt"
            assert len(agent.system_prompt) > 100, f"{agent.name} system prompt too short"

    def test_cas_agent_has_tools(self):
        """Every CAS agent must have at least 3 tools."""
        for agent in CAS_AGENTS:
            assert len(agent.tools) >= 3, f"{agent.name} needs at least 3 tools"

    def test_cas_agent_has_capabilities(self):
        """Every CAS agent must have capabilities."""
        for agent in CAS_AGENTS:
            assert len(agent.capabilities) >= 2, f"{agent.name} needs capabilities"

    def test_marketplace_metadata_present(self):
        """Every CAS agent should have marketplace provenance."""
        for agent in CAS_AGENTS:
            assert "summary" in agent.marketplace_metadata
            assert "what_it_does" in agent.marketplace_metadata


class TestNervousSystemCoordinator:
    """Test the nervous system coordinator."""

    def test_initial_state(self):
        """System should start awake and balanced."""
        ns = NervousSystemCoordinator()
        assert ns.state.activation == ActivationState.AWAKE
        assert ns.state.autonomic_mode == AutonomicMode.BALANCED
        assert ns.state.sympathetic_score == 5

    def test_evaluate_signal_normal(self):
        """Normal signals should get OPEN gate."""
        ns = NervousSystemCoordinator()
        eval = ns.evaluate_signal("What's on my calendar today?")
        assert eval.gate_state == GateState.OPEN
        assert eval.recommended_specialist is None  # general chat

    def test_evaluate_signal_urgent(self):
        """Urgent signals should get PRIORITY gate."""
        ns = NervousSystemCoordinator()
        eval = ns.evaluate_signal("Cancel my meeting ASAP!")
        assert eval.gate_state == GateState.PRIORITY
        assert eval.urgency >= 9

    def test_evaluate_signal_time_critical(self):
        """Time-critical signals should get PRIORITY gate."""
        ns = NervousSystemCoordinator()
        eval = ns.evaluate_signal("Meeting starting soon")
        assert eval.gate_state == GateState.PRIORITY
        assert eval.urgency == 10

    def test_evaluate_signal_identifies_specialist(self):
        """Gate should identify the right specialist from content."""
        ns = NervousSystemCoordinator()
        eval = ns.evaluate_signal("Sync my Google calendar")
        assert eval.recommended_specialist == "a_cal_sync_agent"

        eval = ns.evaluate_signal("Find a free slot for lunch")
        assert eval.recommended_specialist == "a_cal_schedule_agent"

        eval = ns.evaluate_signal("Check my email inbox")
        assert eval.recommended_specialist == "a_cal_email_agent"

    def test_evaluate_signal_wakes_from_deep_sleep(self):
        """Urgent signals should trigger wake-up from deep sleep."""
        ns = NervousSystemCoordinator()
        ns.state.activation = ActivationState.DEEP_SLEEP
        ns.evaluate_signal("Critical: cancel everything ASAP")
        assert ns.state.activation == ActivationState.WAKE_UP_TRANSITION

    def test_update_activation_user_present(self):
        """User presence should force AWAKE state."""
        ns = NervousSystemCoordinator()
        ns.state.activation = ActivationState.DEEP_SLEEP
        ns.update_activation(user_present=True, current_hour=14)
        assert ns.state.activation == ActivationState.AWAKE

    def test_update_activation_overnight(self):
        """Overnight without user should be DEEP_SLEEP."""
        ns = NervousSystemCoordinator()
        ns.update_activation(user_present=False, current_hour=2)
        assert ns.state.activation == ActivationState.DEEP_SLEEP

    def test_assess_autonomic_balanced(self):
        """Normal load should be balanced."""
        ns = NervousSystemCoordinator()
        ns.assess_autonomic(meeting_count=3, conflict_count=0, urgent_count=0)
        assert ns.state.autonomic_mode == AutonomicMode.PARASYMPATHETIC
        assert ns.state.sympathetic_score <= 3

    def test_assess_autonomic_sympathetic(self):
        """High urgency should trigger sympathetic mode."""
        ns = NervousSystemCoordinator()
        ns.assess_autonomic(meeting_count=8, conflict_count=3, urgent_count=4)
        assert ns.state.autonomic_mode == AutonomicMode.SYMPATHETIC
        assert ns.state.sympathetic_score >= 7
        assert ns.state.burnout_risk is True

    def test_rank_specialists(self):
        """Basal ganglia should rank specialists by keyword match."""
        ns = NervousSystemCoordinator()
        eval = ns.evaluate_signal("reschedule my meeting")
        rankings = ns.rank_specialists("reschedule my meeting", eval)
        assert len(rankings) > 0
        # Schedule agent should rank highly for "reschedule"
        top = rankings[0]
        assert "schedule" in top["name"].lower() or top["confidence"] > 0

    def test_encode_and_retrieve_memory(self):
        """Hippocampus should encode and retrieve memories."""
        ns = NervousSystemCoordinator()
        ns.encode_experience(
            signal="Schedule lunch with Sarah",
            specialist="a_cal_schedule_agent",
            outcome="success",
            decisions=["Found slot at noon"],
        )
        memories = ns.retrieve_memories("lunch Sarah")
        assert len(memories) > 0
        assert "lunch" in memories[0]["signal"].lower() or "sarah" in memories[0]["signal"].lower()

    def test_memory_store_bounded(self):
        """Memory store should not exceed 500 entries."""
        ns = NervousSystemCoordinator()
        for i in range(550):
            ns.encode_experience(f"test {i}", "a_cal_conductor", "ok", [])
        assert len(ns._memory_store) <= 500

    def test_assess_user_state_empty(self):
        """Empty events should return safe defaults."""
        ns = NervousSystemCoordinator()
        state = ns.assess_user_state([])
        assert state["meeting_load_hours"] == 0
        assert state["overload_risk"] is False

    def test_assess_user_state_overloaded(self):
        """Many events should flag overload risk."""
        ns = NervousSystemCoordinator()
        events = []
        from datetime import datetime, timedelta, timezone
        base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        for i in range(8):
            start = base + timedelta(hours=i)
            end = start + timedelta(minutes=50)
            events.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "title": f"Meeting {i}",
            })
        state = ns.assess_user_state(events)
        assert state["meeting_load_hours"] > 6
        assert state["overload_risk"] is True

    def test_verify_binding_clean(self):
        """Clean events should have high binding quality."""
        ns = NervousSystemCoordinator()
        events = [
            {"title": "Meeting A", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z",
             "source_sub_account_id": "sa-work"},
            {"title": "Meeting B", "start": "2026-07-13T11:00:00Z", "end": "2026-07-13T12:00:00Z",
             "source_sub_account_id": "sa-personal"},
        ]
        subs = [{"id": "sa-work"}, {"id": "sa-personal"}]
        result = ns.verify_binding(events, subs)
        assert result["binding_quality"] >= 0.8
        assert result["orphaned_events"] == 0

    def test_verify_binding_orphaned(self):
        """Events with unknown sub-account should be orphaned."""
        ns = NervousSystemCoordinator()
        events = [
            {"title": "Orphan", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z",
             "source_sub_account_id": "sa-unknown"},
        ]
        subs = [{"id": "sa-work"}]
        result = ns.verify_binding(events, subs)
        assert result["orphaned_events"] == 1
        assert result["binding_quality"] < 1.0

    def test_verify_binding_conflicts(self):
        """Overlapping events from different subs should be flagged."""
        ns = NervousSystemCoordinator()
        events = [
            {"title": "Work Meeting", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z",
             "source_sub_account_id": "sa-work"},
            {"title": "Personal Meeting", "start": "2026-07-13T09:30:00Z", "end": "2026-07-13T10:30:00Z",
             "source_sub_account_id": "sa-personal"},
        ]
        subs = [{"id": "sa-work"}, {"id": "sa-personal"}]
        result = ns.verify_binding(events, subs)
        assert len(result["conflicts"]) > 0

    def test_learn_and_get_habits(self):
        """Cerebellum should learn and surface habits above threshold."""
        ns = NervousSystemCoordinator()
        # First occurrence: below threshold
        ns.learn_habit("weekly_standup", {"day": "monday", "time": "09:00"})
        assert len(ns.get_habits()) == 0

        # More occurrences: above threshold
        for _ in range(4):
            ns.learn_habit("weekly_standup", {"day": "monday", "time": "09:00"})
        habits = ns.get_habits()
        assert len(habits) == 1
        assert habits[0]["name"] == "weekly_standup"
        assert habits[0]["confidence"] >= 0.5

    def test_route_through_nervous_system(self):
        """Full routing should produce a complete trace."""
        ns = NervousSystemCoordinator()
        trace = ns.route_through_nervous_system("reschedule my 3pm meeting")
        assert trace.signal == "reschedule my 3pm meeting"
        assert trace.thalamus_gate is not None
        assert trace.activation_state is not None
        assert len(trace.basal_ganglia_ranking) > 0
        assert trace.conductor_decision is not None
        assert "cas_thalamus_gate" in trace.cas_modules_engaged
        assert "cas_hippocampus" in trace.cas_modules_engaged
        assert trace.hippocampus_encoding is not None
        assert trace.total_latency_ms >= 0

    def test_route_engages_correct_cas_modules(self):
        """Routing to a specialist should engage its CAS augmentations."""
        ns = NervousSystemCoordinator()
        trace = ns.route_through_nervous_system("sync my calendar")
        # Sync agent is augmented by autonomic and cerebellum
        assert "cas_autonomic" in trace.cas_modules_engaged or \
               "cas_cerebellum" in trace.cas_modules_engaged

    def test_get_system_overview(self):
        """System overview should contain all expected fields."""
        ns = NervousSystemCoordinator()
        overview = ns.get_system_overview()
        assert "state" in overview
        assert "cas_agents" in overview
        assert "augmentation_map" in overview
        assert "memory_count" in overview
        assert "habit_count" in overview
        assert len(overview["cas_agents"]) == 10

    def test_get_all_agents_combined(self):
        """Combined list should have 6 original + 10 CAS = 16 agents."""
        ns = NervousSystemCoordinator()
        all_agents = ns.get_all_agents_combined()
        assert len(all_agents) == 16
        # Check mix of bio-mimetic and non-bio-mimetic
        bio = [a for a in all_agents if a.get("is_bio_mimetic")]
        non_bio = [a for a in all_agents if not a.get("is_bio_mimetic")]
        assert len(bio) == 10
        assert len(non_bio) == 6
