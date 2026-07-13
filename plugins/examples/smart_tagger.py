"""Example A-Cal plugin: Smart Event Tagger

Analyzes event titles and metadata to automatically categorize events.
Demonstrates the on_event_created and on_event_updated hooks working
together to maintain consistent tags.

Install: copy this file to ~/.a-cal/plugins/smart_tagger.py
"""

# Keyword-based category mapping
CATEGORIES = {
    "meeting": ["meeting", "sync", "standup", "catch up", "check-in", "1:1", "one on one"],
    "focus": ["focus", "deep work", "coding", "writing", "review", "planning"],
    "social": ["lunch", "coffee", "dinner", "drinks", "hangout", "social"],
    "travel": ["flight", "travel", "drive", "commute", "trip"],
    "health": ["gym", "workout", "run", "yoga", "doctor", "dentist", "therapy"],
    "personal": ["birthday", "anniversary", "family", "personal", "errand"],
    "work": ["sprint", "deadline", "deliverable", "project", "epic", "review", "demo", "launch"],
}


def _categorize(title: str) -> list[str]:
    """Return list of matching category tags for a title."""
    lower = title.lower()
    tags = []
    for category, keywords in CATEGORIES.items():
        if any(kw in lower for kw in keywords):
            tags.append(category)
    return tags


class Plugin:
    """Automatically tags events with category metadata."""

    name = "Smart Event Tagger"
    plugin_type = "agent"
    enabled = True

    def on_event_created(self, event):
        """Tag new events based on their title."""
        title = event.get("title") or ""
        tags = _categorize(title)
        if tags:
            metadata = event.get("metadata") or {}
            existing = metadata.get("tags") or []
            merged = list(set(existing + tags))
            metadata["tags"] = sorted(merged)
            event["metadata"] = metadata
            return event
        return None

    def on_event_updated(self, event):
        """Re-tag updated events (title may have changed)."""
        title = event.get("title") or ""
        tags = _categorize(title)
        if tags:
            metadata = event.get("metadata") or {}
            metadata["tags"] = sorted(tags)
            event["metadata"] = metadata
            return event
        return None
