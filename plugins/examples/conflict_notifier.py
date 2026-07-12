"""Example A-Cal plugin: Conflict Notifier

Monitors event creation and logs a warning when an event title suggests
a high-priority meeting that might conflict with existing events.
Demonstrates the on_event_created hook with a read-only reaction.

Install: copy this file to ~/.a-cal/plugins/conflict_notifier.py
"""

class Plugin:
    """Logs warnings for high-priority event creation."""

    name = "Conflict Notifier"
    plugin_type = "agent"
    enabled = True

    PRIORITY_KEYWORDS = ["urgent", "critical", "board", "executive", "investor"]

    def on_event_created(self, event):
        """Check if a new event looks high-priority and log a warning."""
        title = (event.get("title") or "").lower()
        is_priority = any(kw in title for kw in self.PRIORITY_KEYWORDS)
        if is_priority:
            # In a real plugin, this could send a notification, write to a
            # webhook, or trigger the swarm negotiation protocol.
            print(f"[Conflict Notifier] High-priority event created: {event.get('title')}")
            return {"notification": "high_priority_event", "event_title": event.get("title")}
        return None
