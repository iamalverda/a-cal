"""Sync rule evaluation.

Each ``SubCalendarSyncRule`` is an INCLUDE / EXCLUDE / TRANSFORM / AGENT rule
matched against a field of a ``CalendarEventDTO``. Rules run in priority order
(lowest first). The first INCLUDE/EXCLUDE that matches decides the event's
fate; TRANSFORM rules mutate the event on match; AGENT rules defer to the
sub's agent (the engine marks the event for agent review).
"""

from __future__ import annotations

import enum
import fnmatch
import re
from dataclasses import dataclass
from typing import List, Optional

from a_cal.providers.base import CalendarEventDTO


class RuleType(str, enum.Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    TRANSFORM = "transform"
    AGENT = "agent"


class RuleAction(str, enum.Enum):
    TAG = "tag"
    RECOLOR = "recolor"
    RENAME = "rename"


@dataclass
class RuleOutcome:
    """Result of evaluating one event against a sub-account's rule set."""

    included: bool = True
    agent_review: bool = False
    transformed_event: CalendarEventDTO | None = None


def _field_value(event: CalendarEventDTO, field: str) -> str:
    """Extract the comparable string for a rule field."""
    if field == "title":
        return event.title
    if field == "calendar_id":
        return event.calendar_id or ""
    if field == "category":
        return str(event.metadata.get("category", ""))
    if field == "attendee":
        return " ".join(a.get("email", "") for a in event.attendees)
    if field == "keyword":
        # Match against title + description.
        return f"{event.title} {event.description or ''}"
    return str(event.metadata.get(field, ""))


def _matches(pattern: str, value: str) -> bool:
    """Match a rule pattern against a field value.

    * regex if the pattern anchors with ^ or $ (re.search)
    * glob if it contains wildcards (* ? [) (fnmatch over the whole value)
    * otherwise a case-insensitive substring match
    """
    if pattern.startswith("^") or pattern.endswith("$"):
        return re.search(pattern, value) is not None
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(value, pattern)
    return pattern.lower() in value.lower()


def evaluate_rules(event: CalendarEventDTO, rules: list) -> RuleOutcome:
    """Run a sub-account's rules against one event.

    ``rules`` is a list of dicts (from SubCalendarSyncRule rows) with keys:
    rule_type, field, pattern, action, priority, is_active. Sorted by priority.
    Returns the outcome: included flag, agent-review flag, and possibly a
    transformed copy of the event.
    """
    outcome = RuleOutcome(included=True)
    current = event

    for rule in sorted(rules, key=lambda r: r.get("priority", 0)):
        if not rule.get("is_active", True):
            continue
        rtype = rule.get("rule_type")
        value = _field_value(current, rule.get("field", "title"))
        if not _matches(rule.get("pattern", "*"), value):
            continue

        if rtype == RuleType.EXCLUDE.value:
            outcome.included = False
            return outcome
        if rtype == RuleType.INCLUDE.value:
            outcome.included = True
        elif rtype == RuleType.AGENT.value:
            outcome.agent_review = True
        elif rtype == RuleType.TRANSFORM.value:
            current = _apply_transform(current, rule.get("action", {}))
            outcome.transformed_event = current

    return outcome


def _apply_transform(event: CalendarEventDTO, action: dict) -> CalendarEventDTO:
    """Return a copy of the event with a transform action applied."""
    import copy
    ev = copy.copy(event)
    ev.metadata = dict(event.metadata)
    if action.get("tag"):
        ev.metadata["tags"] = ev.metadata.get("tags", []) + [action["tag"]]
    if action.get("color"):
        ev.color = action["color"]
    if action.get("rename"):
        ev.title = action["rename"].replace("{title}", event.title)
    return ev
