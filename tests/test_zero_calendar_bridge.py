"""Tests for zero-calendar integration bridge.

Tests the CALENDAR_TOOLS catalog structure and get_enhanced_schedule_prompt.
"""

from __future__ import annotations

from a_cal.integrations.zero_calendar_bridge import (
    CALENDAR_TOOLS,
    get_enhanced_schedule_prompt,
)


class TestCalendarTools:
    """Tests for the CALENDAR_TOOLS catalog."""

    def test_tool_count(self):
        """There are 12 tools in the catalog."""
        assert len(CALENDAR_TOOLS) == 12

    def test_tool_names(self):
        """All expected tool names are present."""
        names = {t["name"] for t in CALENDAR_TOOLS}
        expected = {
            "getEvents", "getTodayEvents", "createEvent", "updateEvent",
            "deleteEvent", "findEvents", "findAvailableTimeSlots",
            "findFreeTimeSlots", "checkForConflicts", "analyzeBusyTimes",
            "getCalendarAnalytics", "suggestRescheduling",
        }
        assert names == expected

    def test_each_tool_has_name_and_description(self):
        """Every tool has a name and description."""
        for tool in CALENDAR_TOOLS:
            assert "name" in tool
            assert isinstance(tool["name"], str)
            assert len(tool["name"]) > 0
            assert "description" in tool
            assert isinstance(tool["description"], str)
            assert len(tool["description"]) > 0

    def test_each_tool_has_parameters(self):
        """Every tool has a parameters dict."""
        for tool in CALENDAR_TOOLS:
            assert "parameters" in tool
            assert isinstance(tool["parameters"], dict)

    def test_create_event_has_required_params(self):
        """createEvent has required title, start_time, end_time."""
        tool = next(t for t in CALENDAR_TOOLS if t["name"] == "createEvent")
        params = tool["parameters"]
        assert params["title"]["required"] is True
        assert params["start_time"]["required"] is True
        assert params["end_time"]["required"] is True

    def test_delete_event_has_required_event_id(self):
        """deleteEvent requires event_id."""
        tool = next(t for t in CALENDAR_TOOLS if t["name"] == "deleteEvent")
        assert tool["parameters"]["event_id"]["required"] is True

    def test_no_duplicate_tool_names(self):
        """No duplicate tool names in the catalog."""
        names = [t["name"] for t in CALENDAR_TOOLS]
        assert len(names) == len(set(names))


class TestGetEnhancedSchedulePrompt:
    """Tests for get_enhanced_schedule_prompt."""

    def test_default_prompt_contains_context(self):
        """Default prompt includes date, time, and timezone context."""
        prompt = get_enhanced_schedule_prompt()
        assert "Current date:" in prompt
        assert "Current time:" in prompt
        assert "User timezone: UTC" in prompt

    def test_custom_timezone(self):
        """Custom timezone appears in the prompt."""
        prompt = get_enhanced_schedule_prompt(user_timezone="America/Chicago")
        assert "America/Chicago" in prompt

    def test_prompt_contains_rules(self):
        """Prompt includes calendar assistant rules."""
        prompt = get_enhanced_schedule_prompt()
        assert "Calendar assistant rules:" in prompt
        assert "Never invent calendar state" in prompt
        assert "concise" in prompt.lower()
        assert "timezone" in prompt.lower()

    def test_prompt_contains_anti_hallucination_directives(self):
        """Prompt has anti-hallucination directives."""
        prompt = get_enhanced_schedule_prompt()
        assert "Do not claim a mutation succeeded" in prompt
        assert "anti-hallucination" not in prompt.lower()  # not literally named

    def test_prompt_with_current_date(self):
        """Passing current_date uses it for context."""
        prompt = get_enhanced_schedule_prompt(current_date="2025-06-15T12:00:00")
        assert "2025" in prompt or "June" in prompt

    def test_prompt_is_nonempty_string(self):
        """Prompt is a non-empty string."""
        prompt = get_enhanced_schedule_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
