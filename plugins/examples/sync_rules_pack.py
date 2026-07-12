"""Example A-Cal plugin: Work-Life Balance Sync Rules

Provides a sync rule pack that keeps work events off the personal
sub-calendar during evenings and weekends. Demonstrates the
get_sync_rules hook.

Install: copy this file to ~/.a-cal/plugins/sync_rules_pack.py
"""

class Plugin:
    """Provides work-life balance sync rules."""

    name = "Work-Life Balance Rules"
    plugin_type = "sync_rule"
    enabled = True

    def get_sync_rules(self):
        """Return sync rules that enforce work-life boundaries."""
        return [
            {
                "name": "no_work_after_hours",
                "description": "Exclude work events from personal calendar after 6pm",
                "sub_account_filter": {"kind": "calendar", "name_contains": "personal"},
                "exclude_rules": [
                    {
                        "field": "title",
                        "contains_any": ["meeting", "standup", "review", "sync", "call"],
                        "time_condition": {"after": "18:00", "before": "08:00"},
                    },
                ],
            },
            {
                "name": "no_work_weekends",
                "description": "Exclude work events from personal calendar on weekends",
                "sub_account_filter": {"kind": "calendar", "name_contains": "personal"},
                "exclude_rules": [
                    {
                        "field": "title",
                        "contains_any": ["meeting", "standup", "review", "sync", "call"],
                        "day_condition": {"weekdays_only": True},
                    },
                ],
            },
            {
                "name": "personal_events_mirrored",
                "description": "Always mirror personal events to main calendar",
                "sub_account_filter": {"kind": "calendar", "name_contains": "personal"},
                "include_rules": [
                    {"field": "all", "action": "mirror"},
                ],
            },
        ]
