"""Tests for the example plugins shipped with A-Cal.

Verifies that each example plugin loads correctly and its hooks
execute without errors. These tests use the real plugin files from
plugins/examples/.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

import pytest

from a_cal.developer.plugin_runtime import PluginRuntime

EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins",
    "examples",
)


@pytest.fixture
def runtime():
    """Return a PluginRuntime pointed at the examples directory."""
    return PluginRuntime(plugin_dir=EXAMPLES_DIR)


class TestExamplePluginsLoad:
    """Verify all example plugins load without errors."""

    def test_all_examples_load(self, runtime):
        """Every .py file in plugins/examples/ should load successfully."""
        results = runtime.scan_and_load()
        assert len(results) >= 5, f"Expected 5+ example plugins, got {len(results)}"
        for p in results:
            assert p.load_error is None, f"Plugin {p.id} failed to load: {p.load_error}"
            assert p.instance is not None, f"Plugin {p.id} has no instance"

    def test_event_tagger_loads(self, runtime):
        """Event Tagger plugin loads with on_event_created hook."""
        runtime.scan_and_load()
        p = runtime.get_plugin("event_tagger")
        assert p is not None
        assert "on_event_created" in p.hooks
        assert p.name == "Event Tagger"

    def test_conflict_notifier_loads(self, runtime):
        """Conflict Notifier plugin loads with on_event_created hook."""
        runtime.scan_and_load()
        p = runtime.get_plugin("conflict_notifier")
        assert p is not None
        assert "on_event_created" in p.hooks

    def test_response_enhancer_loads(self, runtime):
        """Response Enhancer plugin loads with on_conductor_response hook."""
        runtime.scan_and_load()
        p = runtime.get_plugin("response_enhancer")
        assert p is not None
        assert "on_conductor_response" in p.hooks

    def test_custom_agent_loads(self, runtime):
        """Custom Agent plugin loads with get_agent_spec and on_event_created."""
        runtime.scan_and_load()
        p = runtime.get_plugin("custom_agent")
        assert p is not None
        assert "get_agent_spec" in p.hooks
        assert "on_event_created" in p.hooks

    def test_sync_rules_pack_loads(self, runtime):
        """Sync Rules Pack plugin loads with get_sync_rules hook."""
        runtime.scan_and_load()
        p = runtime.get_plugin("sync_rules_pack")
        assert p is not None
        assert "get_sync_rules" in p.hooks


class TestExamplePluginHooks:
    """Verify example plugin hooks execute correctly."""

    def test_event_tagger_tags_meeting(self, runtime):
        """Event Tagger tags a meeting event correctly."""
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Team meeting", "metadata": {}})
        assert "event_tagger" in results
        result = results["event_tagger"]["result"]
        assert result is not None
        assert "meeting" in result["metadata"]["tags"]

    def test_event_tagger_tags_health(self, runtime):
        """Event Tagger tags a health event correctly."""
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Gym session", "metadata": {}})
        assert "event_tagger" in results
        result = results["event_tagger"]["result"]
        assert result is not None
        assert "health" in result["metadata"]["tags"]

    def test_event_tagger_no_tag_for_unrelated(self, runtime):
        """Event Tagger returns None for events with no matching keywords."""
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Random event", "metadata": {}})
        assert "event_tagger" in results
        assert results["event_tagger"]["result"] is None

    def test_response_enhancer_adds_footer(self, runtime):
        """Response Enhancer appends a quick-actions footer."""
        runtime.scan_and_load()
        result = runtime.on_conductor_response("Here are your events.", {})
        assert result is not None
        assert "Quick actions:" in result

    def test_response_enhancer_no_double_append(self, runtime):
        """Response Enhancer returns None if footer already present."""
        runtime.scan_and_load()
        result = runtime.on_conductor_response("Done. Quick actions: find a slot", {})
        assert result is None

    def test_conflict_notifier_detects_priority(self, runtime):
        """Conflict Notifier flags high-priority events."""
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Urgent board meeting"})
        assert "conflict_notifier" in results
        result = results["conflict_notifier"]["result"]
        assert result is not None
        assert result["notification"] == "high_priority_event"

    def test_custom_agent_spec(self, runtime):
        """Custom Agent returns a valid agent spec."""
        runtime.scan_and_load()
        specs = runtime.get_agent_specs()
        # Find the project_tracker spec
        tracker_specs = [s for s in specs if s.get("name") == "project_tracker"]
        assert len(tracker_specs) == 1
        assert tracker_specs[0]["display_name"] == "Project Tracker"
        assert "project_timeline_tracking" in tracker_specs[0]["capabilities"]

    def test_sync_rules_pack_returns_rules(self, runtime):
        """Sync Rules Pack returns sync rule dicts."""
        runtime.scan_and_load()
        packs = runtime.get_sync_rule_packs()
        assert len(packs) >= 3
        rule_names = [p["name"] for p in packs]
        assert "no_work_after_hours" in rule_names
        assert "no_work_weekends" in rule_names
