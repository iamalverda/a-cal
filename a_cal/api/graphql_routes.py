"""Minimal GraphQL API endpoint (Phase 6).

Provides a lightweight GraphQL query resolver without external dependencies.
Supports:
- Field selections with nested objects
- Simple arguments (id, limit, slug)
- Queries for: events, eventTypes, bookings, teams, emailAccounts

No mutations or subscriptions — this is a read-only query layer that
complements the REST API. For writes, use the REST endpoints.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from a_cal.db.store import PersistentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal/graphql", tags=["a-cal-graphql"])

_db = PersistentStore()


class GraphQLRequest(BaseModel):
    """Standard GraphQL request envelope."""
    query: str
    variables: dict[str, Any] | None = None
    operationName: str | None = None


# --- Minimal GraphQL parser ------------------------------------------------

def _parse_selection_set(text: str, pos: int) -> tuple[list[dict[str, Any]], int]:
    """Parse a GraphQL selection set (fields inside braces).

    Returns a list of field dicts and the position after the closing brace.
    Each field dict has: name, alias, args, selections.
    """
    fields: list[dict[str, Any]] = []
    while pos < len(text):
        # Skip whitespace
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= len(text) or text[pos] == "}":
            break

        # Parse alias (optional): name:
        m = re.match(r"(\w+)\s*:\s*", text[pos:])
        alias = None
        if m:
            alias = m.group(1)
            pos += m.end()

        # Parse field name
        m = re.match(r"\w+", text[pos:])
        if not m:
            pos += 1
            continue
        name = m.group(0)
        pos += m.end()

        # Skip whitespace
        while pos < len(text) and text[pos] in " \t":
            pos += 1

        # Parse arguments (optional): (key: value, ...)
        args: dict[str, Any] = {}
        if pos < len(text) and text[pos] == "(":
            pos += 1
            while pos < len(text) and text[pos] != ")":
                while pos < len(text) and text[pos] in " \t\n\r,":
                    pos += 1
                m = re.match(r"(\w+)\s*:\s*", text[pos:])
                if not m:
                    break
                key = m.group(1)
                pos += m.end()
                # Parse value (string or number)
                while pos < len(text) and text[pos] in " \t":
                    pos += 1
                if pos < len(text) and text[pos] == '"':
                    end = text.index('"', pos + 1)
                    val: Any = text[pos + 1:end]
                    pos = end + 1
                else:
                    m = re.match(r"-?\d+", text[pos:])
                    if m:
                        val = int(m.group(0))
                        pos += m.end()
                    else:
                        m = re.match(r"\w+", text[pos:])
                        if m:
                            val = m.group(0)
                            pos += m.end()
                        else:
                            break
                args[key] = val
            if pos < len(text) and text[pos] == ")":
                pos += 1

        # Skip whitespace
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1

        # Parse nested selection set (optional)
        selections: list[dict[str, Any]] | None = None
        if pos < len(text) and text[pos] == "{":
            pos += 1
            selections, pos = _parse_selection_set(text, pos)
            if pos < len(text) and text[pos] == "}":
                pos += 1

        fields.append({
            "name": name,
            "alias": alias,
            "args": args,
            "selections": selections,
        })

    return fields, pos


def _parse_query(query: str) -> list[dict[str, Any]]:
    """Parse a GraphQL query string into a list of top-level field dicts."""
    # Strip the leading "query" keyword if present
    query = query.strip()
    if query.startswith("query"):
        query = query[5:].strip()
    if query.startswith("{"):
        query = query[1:]
    if query.endswith("}"):
        query = query[:-1]
    fields, _ = _parse_selection_set(query, 0)
    return fields


# --- Resolvers -------------------------------------------------------------

def _resolve_events(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the `events` field."""
    days = args.get("limit", 30)
    return _db.get_all_events(days=days)


def _resolve_event_types(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the `eventTypes` field."""
    return _db.list_event_types()


def _resolve_bookings(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the `bookings` field."""
    et_id = args.get("eventTypeId") or args.get("event_type_id")
    return _db.list_bookings(event_type_id=et_id)


def _resolve_teams(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the `teams` field."""
    return _db.list_teams()


def _resolve_event_type(args: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a single `eventType` by id or slug."""
    if "id" in args:
        return _db.get_event_type(args["id"])
    if "slug" in args:
        return _db.get_event_type_by_slug(args["slug"])
    return None


def _resolve_booking(args: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a single `booking` by id."""
    if "id" in args:
        return _db.get_booking(args["id"])
    return None


_RESOLVERS = {
    "events": _resolve_events,
    "eventTypes": _resolve_event_types,
    "bookings": _resolve_bookings,
    "teams": _resolve_teams,
    "eventType": _resolve_event_type,
    "booking": _resolve_booking,
}


def _project(data: Any, selections: list[dict[str, Any]] | None) -> Any:
    """Project only the requested fields from the resolved data.

    Args:
        data: A dict or list of dicts from the resolver.
        selections: The GraphQL field selections to keep.

    Returns:
        Filtered dict/list with only requested fields.
    """
    if selections is None:
        return data
    if isinstance(data, list):
        return [_project(item, selections) for item in data]
    if not isinstance(data, dict):
        return data

    result: dict[str, Any] = {}
    for sel in selections:
        key = sel["alias"] or sel["name"]
        field_name = sel["name"]
        if field_name not in data:
            result[key] = None
            continue
        val = data[field_name]
        if sel["selections"] and isinstance(val, dict):
            result[key] = _project(val, sel["selections"])
        elif sel["selections"] and isinstance(val, list):
            result[key] = [_project(v, sel["selections"]) for v in val]
        else:
            result[key] = val
    return result


# --- Endpoint ---------------------------------------------------------------

@router.post("")
def graphql_endpoint(body: GraphQLRequest) -> dict[str, Any]:
    """Execute a GraphQL query.

    Supports read-only queries for events, eventTypes, bookings, and teams.
    Field selections are projected from the REST API responses.
    """
    try:
        fields = _parse_query(body.query)
    except Exception as exc:
        return {"errors": [{"message": f"Parse error: {exc}"}]}

    data: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    for field in fields:
        key = field["alias"] or field["name"]
        name = field["name"]
        if name not in _RESOLVERS:
            errors.append({"message": f"Cannot query field '{name}'"})
            continue
        try:
            resolved = _RESOLVERS[name](field["args"])
            data[key] = _project(resolved, field["selections"])
        except Exception as exc:
            errors.append({"message": f"Error resolving '{name}': {exc}"})
            data[key] = None

    result: dict[str, Any] = {"data": data}
    if errors:
        result["errors"] = errors
    return result


@router.get("/schema")
def graphql_schema() -> dict[str, Any]:
    """Return the GraphQL schema as introspection-style JSON."""
    return {
        "types": {
            "Query": {
                "fields": [
                    {"name": "events", "args": [{"name": "limit", "type": "Int"}], "type": "[Event!]!"},
                    {"name": "eventTypes", "args": [], "type": "[EventType!]!"},
                    {"name": "bookings", "args": [{"name": "eventTypeId", "type": "ID"}], "type": "[Booking!]!"},
                    {"name": "teams", "args": [], "type": "[Team!]!"},
                    {"name": "eventType", "args": [{"name": "id", "type": "ID"}, {"name": "slug", "type": "String"}], "type": "EventType"},
                    {"name": "booking", "args": [{"name": "id", "type": "ID"}], "type": "Booking"},
                ],
            },
            "Event": {"fields": ["id", "title", "start_time", "end_time", "is_all_day", "color", "attendees"]},
            "EventType": {"fields": ["id", "title", "slug", "duration_minutes", "description", "color", "is_paid", "price_cents", "currency", "team_id", "assignment_strategy"]},
            "Booking": {"fields": ["id", "event_type_id", "attendee_name", "attendee_email", "start_time", "end_time", "status", "payment_status", "assigned_member_id", "video_link"]},
            "Team": {"fields": ["id", "name", "slug", "description", "members"]},
        },
    }
