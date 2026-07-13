"""Google Calendar provider — wraps atom's existing GoogleCalendarService.

atom already has a production Google Calendar integration
(``backend/integrations/google_calendar_service.py``). Rather than duplicate it,
this adapter wraps it behind A-Cal's unified ``CalendarProvider`` interface so
the sync engine treats Google identically to CalDAV/Outlook.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from a_cal.providers.base import (
    CalendarEventDTO,
    CalendarProvider,
    ProviderCapability,
    SyncPage,
    register_calendar_provider,
)

logger = logging.getLogger(__name__)


@register_calendar_provider("google_calendar")
class GoogleCalendarProvider(CalendarProvider):
    """Adapter over atom's GoogleCalendarService."""

    capabilities = (
        ProviderCapability.READ_EVENTS
        | ProviderCapability.WRITE_EVENTS
        | ProviderCapability.CANCEL_EVENTS
        | ProviderCapability.INCREMENTAL_SYNC
        | ProviderCapability.ATTENDEES
        | ProviderCapability.FREE_BUSY
    )

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any]) -> None:
        try:
            from integrations.google_calendar_service import GoogleCalendarService  # type: ignore
            self._svc = GoogleCalendarService(config={**config, **credentials})
        except ImportError:
            raise ImportError(
                "Google Calendar provider requires atom's integration layer. "
                "Add atom/backend to PYTHONPATH or use the CalDAV provider for "
                "any calendar server that supports CalDAV."
            )

    async def list_events(self, start: datetime, end: datetime, calendar_id: str | None = None) -> list[CalendarEventDTO]:
        raw = await self._svc.list_events(start, end, calendar_id) if hasattr(self._svc, "list_events") else []
        return [self._to_dto(e, calendar_id) for e in raw]

    async def list_changes(self, since_cursor: str | None, start: datetime, end: datetime) -> SyncPage:
        events = await self.list_events(start, end)
        return SyncPage(events=events, next_cursor=since_cursor, has_more=False)

    async def create_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        if hasattr(self._svc, "create_event"):
            await self._svc.create_event(self._from_dto(event))
        return event

    async def update_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        return await self.create_event(event)

    async def cancel_event(self, provider_event_id: str, calendar_id: str | None = None) -> None:
        if hasattr(self._svc, "delete_event"):
            await self._svc.delete_event(provider_event_id, calendar_id)

    @staticmethod
    def _to_dto(raw: dict[str, Any], calendar_id: str | None) -> CalendarEventDTO:
        return CalendarEventDTO(
            provider_event_id=raw.get("id", ""),
            provider_type="google_calendar",
            title=raw.get("summary", ""),
            start=datetime.fromisoformat(raw["start"]["dateTime"]) if raw.get("start", {}).get("dateTime") else datetime.now(),
            end=datetime.fromisoformat(raw["end"]["dateTime"]) if raw.get("end", {}).get("dateTime") else datetime.now(),
            description=raw.get("description"),
            location=raw.get("location"),
            attendees=[{"email": a.get("email"), "name": a.get("displayName", "")} for a in raw.get("attendees", [])],
            calendar_id=calendar_id or raw.get("organizer", {}).get("email"),
            etag=raw.get("etag"),
        )

    @staticmethod
    def _from_dto(dto: CalendarEventDTO) -> dict[str, Any]:
        return {
            "id": dto.provider_event_id,
            "summary": dto.title,
            "start": {"dateTime": dto.start.isoformat()},
            "end": {"dateTime": dto.end.isoformat()},
            "description": dto.description,
            "location": dto.location,
        }
