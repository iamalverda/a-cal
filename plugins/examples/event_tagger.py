"""Example A-Cal plugin: Event Tagger

Automatically tags events based on their title keywords. Demonstrates
the on_event_created hook by adding metadata to new events.

Install: copy this file to ~/.a-cal/plugins/event_tagger.py
"""

class Plugin:
    """Tags events with category metadata based on title keywords."""

    name = "Event Tagger"
    plugin_type = "agent"
    enabled = True

    TAG_RULES = {
        "meeting": "meeting",
        "call": "call",
        "lunch": "social",
        "dinner": "social",
        "workout": "health",
        "gym": "health",
        "doctor": "health",
        "flight": "travel",
        "trip": "travel",
        "conference": "travel",
        "deadline": "deadline",
        "review": "review",
        "standup": "recurring",
        "weekly": "recurring",
        "daily": "recurring",
    }

    def on_event_created(self, event):
        """Tag a newly created event based on its title."""
        title = (event.get("title") or "").lower()
        tags = []
        for keyword, tag in self.TAG_RULES.items():
            if keyword in title:
                tags.append(tag)
        if tags:
            metadata = event.get("metadata") or {}
            metadata["tags"] = tags
            event["metadata"] = metadata
            return event
        return None
