"""Google Calendar provider — direct Google Calendar API via OAuth tokens.

Works standalone (without atom's integration layer) by calling Google's
REST API directly using stored OAuth tokens. Token refresh is handled
automatically via ``oauth_api.ensure_valid_token``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from a_cal.providers.base import (
    CalendarEventDTO,
    CalendarProvider,
    ProviderCapability,
    SyncPage,
    register_calendar_provider,
)
from a_cal.providers.oauth_api import ensure_valid_token, get_oauth_tokens

logger = logging.getLogger(__name__)

_GOOGLE_CAL_API = "https://www.googleapis.com/calendar/v3"


@register_calendar_provider("google_calendar")
class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar provider using direct REST API calls."""

    capabilities = (
        ProviderCapability.READ_EVENTS
        | ProviderCapability.WRITE_EVENTS
        | ProviderCapability.CANCEL_EVENTS
        | ProviderCapability.INCREMENTAL_SYNC
    )

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, Any]) -> None:
        """Initialize with provider config and resolved credentials.

        Args:
            config: Provider connection config (includes oauth_tokens).
            credentials: Resolved credentials (may overlap with config).
        """
        self._config = {**config, **credentials}
        self._tokens = get_oauth_tokens(self._config, "google_calendar")

    async def _headers(self) -> dict[str, str]:
        """Return authorization headers with a valid access token."""
        token = await ensure_valid_token(self._config, "google_calendar")
        if not token:
            raise RuntimeError("No valid OAuth access token for Google Calendar")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def list_events(
        self, start: datetime, end: datetime, calendar_id: str | None = None
    ) -> list[CalendarEventDTO]:
        """List events from Google Calendar within the given time range."""
        cal_id = calendar_id or "primary"
        headers = await self._headers()
        params = {
            "timeMin": start.astimezone(timezone.utc).isoformat(),
            "timeMax": end.astimezone(timezone.utc).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{_GOOGLE_CAL_API}/calendars/{cal_id}/events",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Google Calendar API error: %s", exc.response.text[:200])
            return []
        except Exception as exc:
            logger.error("Google Calendar list_events failed: %s", exc)
            return []

        return [self._to_dto(e, cal_id) for e in data.get("items", [])]

    async def list_changes(
        self, since_cursor: str | None, start: datetime, end: datetime
    ) -> SyncPage:
        """List changes since the last sync cursor."""
        events = await self.list_events(start, end)
        return SyncPage(events=events, next_cursor=since_cursor, has_more=False)

    async def create_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        """Create an event in Google Calendar."""
        cal_id = event.calendar_id or "primary"
        headers = await self._headers()
        headers["Content-Type"] = "application/json"
        body = self._from_dto(event)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{_GOOGLE_CAL_API}/calendars/{cal_id}/events",
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                created = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Google Calendar create error: %s", exc.response.text[:200])
            raise
        return self._to_dto(created, cal_id)

    async def cancel_event(
        self, provider_event_id: str, calendar_id: str | None = None
    ) -> None:
        """Cancel/delete an event from Google Calendar."""
        cal_id = calendar_id or "primary"
        headers = await self._headers()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.delete(
                    f"{_GOOGLE_CAL_API}/calendars/{cal_id}/events/{provider_event_id}",
                    headers=headers,
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Google Calendar cancel error: %s", exc.response.text[:200])
            raise

    async def update_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        """Update an existing event in Google Calendar."""
        cal_id = event.calendar_id or "primary"
        headers = await self._headers()
        headers["Content-Type"] = "application/json"
        body = self._from_dto(event)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.patch(
                    f"{_GOOGLE_CAL_API}/calendars/{cal_id}/events/{event.provider_event_id}",
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                updated = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Google Calendar update error: %s", exc.response.text[:200])
            raise
        return self._to_dto(updated, cal_id)

    @staticmethod
    def _to_dto(raw: dict[str, Any], calendar_id: str | None = None) -> CalendarEventDTO:
        """Convert a Google Calendar API event dict to a CalendarEventDTO."""
        start_raw = raw.get("start", {})
        end_raw = raw.get("end", {})
        start_str = start_raw.get("dateTime") or start_raw.get("date", "")
        end_str = end_raw.get("dateTime") or end_raw.get("date", "")

        def _parse_dt(s: str) -> datetime | None:
            if not s:
                return None
            try:
                # Handle date-only (all-day events).
                if "T" not in s:
                    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
                return datetime.fromisoformat(s)
            except ValueError:
                return None

        attendees = [
            {"email": a.get("email", ""), "response": a.get("responseStatus", "")}
            for a in raw.get("attendees", [])
        ]

        return CalendarEventDTO(
            provider_event_id=raw.get("id", ""),
            provider_type="google_calendar",
            calendar_id=calendar_id,
            title=raw.get("summary", "(No title)"),
            description=raw.get("description", ""),
            start=_parse_dt(start_str),
            end=_parse_dt(end_str),
            location=raw.get("location", ""),
            attendees=attendees,
            metadata=raw,
        )

    @staticmethod
    def _from_dto(event: CalendarEventDTO) -> dict[str, Any]:
        """Convert a CalendarEventDTO to a Google Calendar API event body."""
        body: dict[str, Any] = {
            "summary": event.title or "",
        }
        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location
        if event.start:
            if event.start.tzinfo:
                body["start"] = {"dateTime": event.start.isoformat()}
            else:
                body["start"] = {"dateTime": event.start.replace(tzinfo=timezone.utc).isoformat()}
        if event.end:
            if event.end.tzinfo:
                body["end"] = {"dateTime": event.end.isoformat()}
            else:
                body["end"] = {"dateTime": event.end.replace(tzinfo=timezone.utc).isoformat()}
        if event.attendees:
            body["attendees"] = [{"email": a["email"]} for a in event.attendees if a.get("email")]
        return body
