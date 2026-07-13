"""Example A-Cal plugin: Conductor Response Translator

Transforms conductor responses to add helpful context. Demonstrates the
on_conductor_response hook for customizing how the agent communicates
with the user.

Install: copy this file to ~/.a-cal/plugins/response_translator.py
"""

import datetime


class Plugin:
    """Adds a timestamp and quick-action footer to conductor responses."""

    name = "Response Translator"
    plugin_type = "agent"
    enabled = True

    def on_conductor_response(self, response, context):
        """Append a timestamp and quick-action hints to conductor responses."""
        # Don't double-append if a footer is already present
        if "\n---\n" in response or "Quick actions:" in response:
            return None

        now = datetime.datetime.now().strftime("%H:%M")

        # Add quick actions based on intent
        intent = context.get("intent", "chat")
        actions = {
            "schedule": "Try: 'What does my week look like?' or 'Move my 3pm to 4pm'",
            "sync": "Try: 'Sync my work calendar' or 'What accounts are connected?'",
            "email": "Try: 'Scan my inbox for meeting invites' or 'Draft a reply to Sarah'",
            "negotiate": "Try: 'Resolve the conflict between my work and personal calendars'",
            "self_model": "Try: 'What do you know about me?' or 'Delete my meeting pattern data'",
        }
        hint = actions.get(intent, "")

        footer = f"\n\n---\n_{now}_"
        if hint:
            footer += f"\n{hint}"

        return response + footer
