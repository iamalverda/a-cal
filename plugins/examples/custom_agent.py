"""Example A-Cal plugin: Custom Project Tracker Agent

Registers a custom agent spec via the get_agent_spec hook. This agent
specializes in tracking project-related events and can be routed to
by the conductor when users ask about project timelines.

Install: copy this file to ~/.a-cal/plugins/custom_agent.py
"""

class Plugin:
    """Provides a custom project tracker agent spec."""

    name = "Project Tracker Agent"
    plugin_type = "agent"
    enabled = True

    def get_agent_spec(self):
        """Return a custom agent spec for project tracking."""
        return {
            "name": "project_tracker",
            "display_name": "Project Tracker",
            "description": "Tracks project milestones, deadlines, and sprint events.",
            "system_prompt": (
                "You are a project tracking specialist. You help users "
                "manage project timelines, identify approaching deadlines, "
                "and balance project work with other commitments. When "
                "discussing projects, always consider the user's other "
                "obligations and suggest realistic schedules."
            ),
            "tools": ["calendar.read", "calendar.create", "calendar.update"],
            "default_tier": "standard",
            "can_negotiate": True,
            "privacy_force_local": False,
            "capabilities": [
                "project_timeline_tracking",
                "deadline_detection",
                "sprint_planning",
                "milestone_management",
            ],
        }

    def on_event_created(self, event):
        """Tag project-related events."""
        title = (event.get("title") or "").lower()
        project_keywords = ["sprint", "milestone", "deadline", "project", "deliverable", "epic"]
        if any(kw in title for kw in project_keywords):
            metadata = event.get("metadata") or {}
            metadata["project_related"] = True
            event["metadata"] = metadata
            return event
        return None
