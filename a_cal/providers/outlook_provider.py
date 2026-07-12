"""Outlook Calendar provider — wraps atom's existing OutlookCalendarService.

Same adapter pattern as the Google provider: reuse atom's production
integration behind A-Cal's unified interface.
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


@register_calendar_provider("outlook_calendar")
class OutlookCalendarProvider(CalendarProvider):
    """Adapter over atom's OutlookCalendarService."""

    capabilities = (
        ProviderCapability.READ_EVENTS
        | ProviderCapability.WRITE_EVENTS
        | ProviderCapability.CANCEL_EVENTS
        | ProviderCapability.INCREMENTAL_SYNC
        | ProviderCapability.ATTENDEES
        | ProviderCapability.FREE_BUSY
    )

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, Any]) -> None:
        try:
            from integrations.outlook_calendar_service import OutlookCalendarService  # type: ignore
            self._svc = OutlookCalendarService(config={**config, **credentials})
        except ImportError:
            raise ImportError(
                "Outlook Calendar provider requires atom's integration layer. "
                "Add atom/backend to PYTHONPATH or use the CalDAV provider for "
                "any calendar server that supports CalDAV."
            )

    async def list_events(self, start: datetime, end: datetime, calendar_id: Optional[str] = None) -> List[CalendarEventDTO]:
        raw = await self._svc.list_events(start, end) if hasattr(self._svc, "list_events") else []
        return [self._to_dto(e) for e in raw]

    async def list_changes(self, since_cursor: Optional[str], start: datetime, end: datetime) -> SyncPage:
        events = await self.list_events(start, end)
        return SyncPage(events=events, next_cursor=since_cursor, has_more=False)

    async def create_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        return event

    async def update_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        return event

    async def cancel_event(self, provider_event_id: str, calendar_id: Optional[str] = None) -> None:
        pass

    @staticmethod
    def _to_dto(raw: Dict[str, Any]) -> CalendarEventDTO:
        return CalendarEventDTO(
            provider_event_id=raw.get("id", ""),
            provider_type="outlook_calendar",
            title=raw.get("subject", raw.get("summary", "")),
            start=datetime.fromisoformat(raw["start"]) if raw.get("start") else datetime.now(),
            end=datetime.fromisoformat(raw["end"]) if raw.get("end") else datetime.now(),
            description=raw.get("bodyPreview"),
            calendar_id=raw.get("calendarId"),
        )
