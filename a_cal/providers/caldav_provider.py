"""CalDAV calendar provider — the "any provider" calendar backend.

Talks to any CalDAV server (Radicale, Nextcloud, Fastmail, Baïkal, ...). This
is what makes A-Cal's "link to any provider" literally true for calendars: any
provider that speaks CalDAV works without a bespoke integration.

The `caldav` library is an OPTIONAL dependency — imported lazily so A-Cal boots
even when it isn't installed. The provider raises a clear, actionable error on
first use if the library is missing, rather than failing at import time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from a_cal.providers.base import (
    CalendarEventDTO,
    CalendarProvider,
    ProviderCapability,
    SyncPage,
    register_calendar_provider,
)

logger = logging.getLogger(__name__)

# Optional dependency — graceful degradation until the user installs it.
try:
    import caldav  # type: ignore
    _CALDAV_AVAILABLE = True
except ImportError:  # pragma: no cover
    caldav = None  # type: ignore
    _CALDAV_AVAILABLE = False


def _require_caldav() -> None:
    """Raise a clear error if the optional `caldav` package is not installed."""
    if not _CALDAV_AVAILABLE:
        raise ImportError(
            "CalDAV support requires the `caldav` package. Install it with "
            "`pip install caldav` (pending dependency confirmation)."
        )


def _parse_vtodo_event(component: Any, provider_type: str) -> CalendarEventDTO | None:
    """Convert an icalendar VEVENT component to a CalendarEventDTO."""
    from icalendar import vRecur  # type: ignore  # comes with the caldav package

    uid = str(component.get("uid", ""))
    if not uid:
        return None

    def _dt(key: str) -> datetime | None:
        val = component.get(key)
        if val is None:
            return None
        dt = val.dt if hasattr(val, "dt") else val
        # icalendar returns date for all-day events; normalize to datetime.
        if hasattr(dt, "hour"):
            return dt  # type: ignore
        return datetime(dt.year, dt.month, dt.day)  # type: ignore

    start = _dt("dtstart")
    end = _dt("dtend")
    if start is None:
        return None
    if end is None:
        end = start + timedelta(hours=1)

    attendees = []
    for a in component.get("attendee", []) or []:
        attendees.append({"email": str(a).replace("mailto:", ""), "name": a.params.get("CN", "")})

    return CalendarEventDTO(
        provider_event_id=uid,
        provider_type=provider_type,
        title=str(component.get("summary", "")),
        start=start,
        end=end,
        description=str(component.get("description", "")) or None,
        location=str(component.get("location", "")) or None,
        attendees=attendees,
        status=str(component.get("status", "confirmed")).lower(),
        calendar_id=str(component.get("x-wr-calendarname", "default")),
        etag=str(component.get("sequence", "0")),
    )


@register_calendar_provider("caldav")
class CalDAVProvider(CalendarProvider):
    """CalDAV calendar backend.

    Constructed from a ``ProviderConnection`` whose ``config`` carries the
    server URL, and whose ``credentials_ref`` resolves to the username/password
    (CalDAV uses HTTP basic auth, not OAuth).
    """

    capabilities = (
        ProviderCapability.READ_EVENTS
        | ProviderCapability.WRITE_EVENTS
        | ProviderCapability.CANCEL_EVENTS
        | ProviderCapability.INCREMENTAL_SYNC
        | ProviderCapability.ATTENDEES
        | ProviderCapability.FREE_BUSY
    )

    def __init__(self, server_url: str, username: str, password: str, calendar_url: str | None = None) -> None:
        _require_caldav()
        self._client = caldav.DAVClient(  # type: ignore
            url=server_url, username=username, password=password
        )
        principal = self._client.principal()
        if calendar_url:
            self._calendar = self._client.calendar(url=calendar_url)
        else:
            calendars = principal.calendars()
            if not calendars:
                # Auto-create a default calendar on the server (Radicale allows this).
                self._calendar = principal.make_calendar(name="A-Cal")
            else:
                self._calendar = calendars[0]

    async def list_events(self, start: datetime, end: datetime, calendar_id: str | None = None) -> list[CalendarEventDTO]:
        events = self._calendar.search(start=start, end=end, event=True, expand=True)
        results: list[CalendarEventDTO] = []
        for ev in events:
            for comp in ev.icalendar_component.walk("VEVENT"):
                dto = _parse_vtodo_event(comp, "caldav")
                if dto is not None:
                    results.append(dto)
        return results

    async def list_changes(self, since_cursor: str | None, start: datetime, end: datetime) -> SyncPage:
        # CalDAV sync via sync-token; fall back to date search if unsupported.
        try:
            sync_token = since_cursor if since_cursor else None
            updated, new_token = self._calendar.objects_by_sync_token(sync_token)  # type: ignore
            events: list[CalendarEventDTO] = []
            for ev in updated:
                for comp in ev.icalendar_component.walk("VEVENT"):
                    dto = _parse_vtodo_event(comp, "caldav")
                    if dto is not None:
                        events.append(dto)
            return SyncPage(events=events, next_cursor=new_token, has_more=False)
        except Exception:
            # Provider doesn't support sync-token — degrade to windowed full list.
            events = await self.list_events(start, end)
            return SyncPage(events=events, next_cursor=None, has_more=False)

    async def create_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        from icalendar import Calendar, Event  # type: ignore

        cal = Calendar()
        cal.add("prodid", "-//A-Cal//a-cal//EN")
        cal.add("version", "2.0")
        e = Event()
        e.add("uid", event.provider_event_id)
        e.add("summary", event.title)
        e.add("dtstart", event.start)
        e.add("dtend", event.end)
        if event.description:
            e.add("description", event.description)
        if event.location:
            e.add("location", event.location)
        cal.add_component(e)
        self._calendar.save_event(str(cal.to_ical(), "utf-8"))
        event.etag = "1"
        return event

    async def update_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        # CalDAV update = re-save with the same UID.
        return await self.create_event(event)

    async def cancel_event(self, provider_event_id: str, calendar_id: str | None = None) -> None:
        self._calendar.event_by_uid(provider_event_id).delete()
