"""Calendar event routes for standalone A-Cal.

Split from ``standalone_data.py``. These endpoints manage the unified
calendar timeline and event CRUD.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, UTC
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from a_cal.api._helpers import _fire_plugin_hook
from a_cal.api.store import _store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a-cal-data"])


# --- request/response models -----------------------------------------------

class UnifiedEvent(BaseModel):
    """A calendar event in the unified timeline."""
    provider_event_id: str
    provider_type: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    source_sub_account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_all_day: bool = False
    recurrence_rule: str | None = None
    attendees: list[dict[str, Any]] | None = None
    color: str | None = None


class EventCreate(BaseModel):
    """Payload for creating a calendar event."""
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    source_sub_account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_all_day: bool = False
    recurrence_rule: str | None = None
    attendees: list[dict[str, Any]] | None = None
    color: str | None = None


class EventUpdate(BaseModel):
    """Payload for updating a calendar event."""
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    metadata: dict[str, Any] | None = None
    is_all_day: bool | None = None
    recurrence_rule: str | None = None
    attendees: list[dict[str, Any]] | None = None
    color: str | None = None


# --- unified main-calendar view --------------------------------------------

@router.get("/calendar/unified", response_model=list[UnifiedEvent])
async def unified_calendar(days: int = Query(7, ge=1, le=90)) -> list[UnifiedEvent]:
    """Return the unified calendar timeline for the next N days.

    In standalone mode, this returns the seeded demo events. In production
    with atom, this pulls from real providers via the sync engine.
    """
    events = _store.get_unified_calendar(days)
    result: list[UnifiedEvent] = []
    for evt in events:
        evt_start = evt["start"]
        if isinstance(evt_start, str):
            evt_start = datetime.fromisoformat(evt_start)
        if evt_start.tzinfo is None:
            evt_start = evt_start.replace(tzinfo=UTC)
        evt_end = evt["end"]
        if isinstance(evt_end, str):
            evt_end = datetime.fromisoformat(evt_end)
        result.append(UnifiedEvent(
            provider_event_id=evt["provider_event_id"],
            provider_type=evt["provider_type"],
            title=evt["title"],
            start=evt_start,
            end=evt_end,
            description=evt.get("description"),
            location=evt.get("location"),
            source_sub_account_id=evt.get("source_sub_account_id"),
            metadata=evt.get("metadata", {}),
        ))
    return result


# --- event CRUD endpoints --------------------------------------------------

@router.post("/calendar/events", response_model=UnifiedEvent)
def create_event(body: EventCreate) -> UnifiedEvent:
    """Create a new calendar event.

    In standalone mode, this creates the event in the local SQLite store.
    In production with atom, this would also push to the connected provider
    via the sync engine.
    """
    evt = _store.create_event({
        "title": body.title,
        "start": body.start,
        "end": body.end,
        "description": body.description,
        "location": body.location,
        "source_sub_account_id": body.source_sub_account_id,
        "metadata": body.metadata,
        "is_all_day": body.is_all_day,
        "recurrence_rule": body.recurrence_rule,
        "attendees": body.attendees,
        "color": body.color,
    })
    _fire_plugin_hook("on_event_created", evt)
    return _event_to_response(evt)


@router.patch("/calendar/events/{event_id}", response_model=UnifiedEvent)
def update_event(event_id: str, body: EventUpdate) -> UnifiedEvent:
    """Update an existing calendar event by provider_event_id."""
    patch: dict[str, Any] = {}
    if body.title is not None:
        patch["title"] = body.title
    if body.start is not None:
        patch["start"] = body.start
    if body.end is not None:
        patch["end"] = body.end
    if body.description is not None:
        patch["description"] = body.description
    if body.location is not None:
        patch["location"] = body.location
    if body.metadata is not None:
        patch["metadata"] = body.metadata
    if body.is_all_day is not None:
        patch["is_all_day"] = body.is_all_day
    if body.recurrence_rule is not None:
        patch["recurrence_rule"] = body.recurrence_rule
    if body.attendees is not None:
        patch["attendees"] = body.attendees
    if body.color is not None:
        patch["color"] = body.color

    evt = _store.update_event(event_id, patch)
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")
    _fire_plugin_hook("on_event_updated", evt)
    return _event_to_response(evt)


@router.delete("/calendar/events/{event_id}")
def delete_event(event_id: str) -> dict[str, str]:
    """Delete a calendar event by provider_event_id."""
    if not _store.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    _fire_plugin_hook("on_event_deleted", event_id)
    return {"status": "deleted", "event_id": event_id}


@router.get("/calendar/events", response_model=list[UnifiedEvent])
def list_events(days: int = Query(30, ge=1, le=365)) -> list[UnifiedEvent]:
    """List all events within the next N days (wider window for agents)."""
    events = _store.get_all_events(days)
    return [_event_to_response(evt) for evt in events]


def _event_to_response(evt: dict[str, Any]) -> UnifiedEvent:
    """Convert a store event dict to a UnifiedEvent response."""
    evt_start = evt["start"]
    if isinstance(evt_start, str):
        evt_start = datetime.fromisoformat(evt_start)
    if evt_start.tzinfo is None:
        evt_start = evt_start.replace(tzinfo=UTC)
    evt_end = evt["end"]
    if isinstance(evt_end, str):
        evt_end = datetime.fromisoformat(evt_end)
    return UnifiedEvent(
        provider_event_id=evt["provider_event_id"],
        provider_type=evt.get("provider_type", "local"),
        title=evt["title"],
        start=evt_start,
        end=evt_end,
        description=evt.get("description"),
        location=evt.get("location"),
        source_sub_account_id=evt.get("source_sub_account_id"),
        metadata=evt.get("metadata", {}),
        is_all_day=evt.get("is_all_day", False),
        recurrence_rule=evt.get("recurrence_rule"),
        attendees=evt.get("attendees"),
        color=evt.get("color"),
    )
