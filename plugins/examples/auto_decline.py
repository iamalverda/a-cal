"""Example A-Cal plugin: Auto-Decline Conflicts

When a new event conflicts with an existing high-priority event (marked
with metadata.priority == "high"), this plugin logs a warning and marks
the new event for review. Demonstrates the on_event_created hook with
conflict detection logic.

Install: copy this file to ~/.a-cal/plugins/auto_decline.py
"""

import logging

logger = logging.getLogger("a_cal.plugin.auto_decline")


class Plugin:
    """Flags events that conflict with high-priority existing events."""

    name = "Auto-Decline Conflicts"
    plugin_type = "agent"
    enabled = True

    def on_event_created(self, event):
        """Check if the new event overlaps with a high-priority event."""
        metadata = event.get("metadata") or {}
        conflicts = event.get("_conflicts") or []

        for conflict in conflicts:
            conflict_meta = conflict.get("metadata") or {}
            if conflict_meta.get("priority") == "high":
                metadata["conflict_flagged"] = True
                metadata["conflict_with"] = conflict.get("title", "unknown")
                metadata["needs_review"] = True
                event["metadata"] = metadata
                logger.warning(
                    "Event '%s' conflicts with high-priority event '%s' — flagged for review",
                    event.get("title"),
                    conflict.get("title"),
                )
                return event
        return None
