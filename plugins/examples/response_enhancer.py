"""Example A-Cal plugin: Response Enhancer

Transforms the conductor's response by adding a helpful footer with
quick action suggestions. Demonstrates the on_conductor_response hook.

Install: copy this file to ~/.a-cal/plugins/response_enhancer.py
"""

class Plugin:
    """Adds a quick-actions footer to conductor responses."""

    name = "Response Enhancer"
    plugin_type = "agent"
    enabled = True

    FOOTER = (
        "\n\n---\n"
        "Quick actions: 'find a free slot' | 'sync my accounts' | "
        "'check my inbox' | 'what do you know about me?'"
    )

    def on_conductor_response(self, response, context):
        """Append a quick-actions footer to the response."""
        # Don't double-append if the footer is already present
        if "Quick actions:" in response:
            return None
        return response + self.FOOTER
