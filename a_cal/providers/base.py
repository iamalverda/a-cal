"""Provider abstraction layer.

This replaces atom's mocked ``unified_calendar_endpoints`` ``MOCK_EVENTS``
with a real, provider-agnostic interface. Every calendar backend (Google,
Outlook, CalDAV/Radicale, ...) implements ``CalendarProvider``; every email
backend (Gmail OAuth, IMAP/SMTP gateway, ...) implements ``EmailProvider``.

The abstraction is intentionally narrow: list events, get/update/create/cancel
a single event, and pull incremental changes via a cursor. The sync engine
composes these primitives into the four sub-account models.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


class ProviderCapability(enum.Flag):
    """Feature flags a provider declares so the sync engine can degrade gracefully."""

    READ_EVENTS = enum.auto()
    WRITE_EVENTS = enum.auto()
    CANCEL_EVENTS = enum.auto()
    INCREMENTAL_SYNC = enum.auto()
    ATTENDEES = enum.auto()
    FREE_BUSY = enum.auto()
    SEND_MAIL = enum.auto()
    READ_MAIL = enum.auto()


@dataclass
class CalendarEventDTO:
    """Provider-agnostic calendar event.

    ``provider_event_id`` + ``provider_type`` together uniquely identify the
    event on its origin provider. ``source_sub_account_id`` is stamped by the
    sync engine so the main view always knows where an event came from.
    """

    provider_event_id: str
    provider_type: str
    title: str
    start: datetime
    end: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: List[Dict[str, str]] = field(default_factory=list)
    status: str = "confirmed"
    calendar_id: Optional[str] = None  # the provider's own calendar id
    color: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_sub_account_id: Optional[str] = None
    etag: Optional[str] = None  # for optimistic concurrency on writes

    def to_storage_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for caching/mirroring in the local store."""
        return {
            "provider_event_id": self.provider_event_id,
            "provider_type": self.provider_type,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "description": self.description,
            "location": self.location,
            "attendees": self.attendees,
            "status": self.status,
            "calendar_id": self.calendar_id,
            "color": self.color,
            "metadata": self.metadata,
            "source_sub_account_id": self.source_sub_account_id,
            "etag": self.etag,
        }


@dataclass
class SyncPage:
    """One page of incremental results from a provider."""

    events: List[CalendarEventDTO]
    next_cursor: Optional[str] = None  # None => no more pages
    has_more: bool = False


@dataclass
class EmailMessageDTO:
    """Provider-agnostic email message (minimal fields the agents need)."""

    provider_message_id: str
    provider_type: str
    subject: str
    from_address: str
    to_addresses: List[str] = field(default_factory=list)
    received_at: Optional[datetime] = None
    snippet: Optional[str] = None
    body_text: Optional[str] = None
    thread_id: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)


class CalendarProvider(ABC):
    """Interface every calendar backend implements.

    Implementations are constructed with a ``ProviderConnection`` row (which
    carries the ``credentials_ref`` and provider ``config``) and a way to
    resolve encrypted credentials from atom's token storage.
    """

    capabilities: ProviderCapability = ProviderCapability.READ_EVENTS

    @abstractmethod
    async def list_events(
        self, start: datetime, end: datetime, calendar_id: Optional[str] = None
    ) -> List[CalendarEventDTO]:
        """Return events in [start, end)."""

    @abstractmethod
    async def list_changes(
        self, since_cursor: Optional[str], start: datetime, end: datetime
    ) -> SyncPage:
        """Incremental change pull. If the provider lacks INCREMENTAL_SYNC,
        fall back to a full list and return the whole window as one page."""

    @abstractmethod
    async def create_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        """Create on the provider and return the event with its new id/etag."""

    @abstractmethod
    async def update_event(self, event: CalendarEventDTO) -> CalendarEventDTO:
        """Update an existing event (uses provider_event_id + etag)."""

    @abstractmethod
    async def cancel_event(self, provider_event_id: str, calendar_id: Optional[str] = None) -> None:
        """Cancel/delete an event."""

    def supports(self, cap: ProviderCapability) -> bool:
        return bool(self.capabilities & cap)


class EmailProvider(ABC):
    """Interface every email backend implements (Gmail OAuth or IMAP/SMTP)."""

    capabilities: ProviderCapability = ProviderCapability.READ_MAIL

    @abstractmethod
    async def list_messages(
        self, since_cursor: Optional[str], folder: str = "INBOX", limit: int = 50
    ) -> tuple[List[EmailMessageDTO], Optional[str]]:
        """Return a page of messages and a next cursor."""

    @abstractmethod
    async def send_message(
        self, to: List[str], subject: str, body_text: str,
        in_reply_to: Optional[str] = None, thread_id: Optional[str] = None,
    ) -> str:
        """Send a message; return the provider message id."""

    @abstractmethod
    async def reply(
        self, provider_message_id: str, body_text: str
    ) -> str:
        """Reply to a specific message; return the new message id."""


# --- provider registry -----------------------------------------------------

_CALENDAR_PROVIDERS: Dict[str, type] = {}
_EMAIL_PROVIDERS: Dict[str, type] = {}


def register_calendar_provider(provider_type: str) -> Any:
    """Class decorator: register a CalendarProvider implementation."""

    def _decorator(cls: type) -> type:
        if not issubclass(cls, CalendarProvider):
            raise TypeError(f"{cls.__name__} must subclass CalendarProvider")
        _CALENDAR_PROVIDERS[provider_type] = cls
        return cls

    return _decorator


def register_email_provider(provider_type: str) -> Any:
    def _decorator(cls: type) -> type:
        if not issubclass(cls, EmailProvider):
            raise TypeError(f"{cls.__name__} must subclass EmailProvider")
        _EMAIL_PROVIDERS[provider_type] = cls
        return cls

    return _decorator


def get_calendar_provider(provider_type: str) -> type:
    try:
        return _CALENDAR_PROVIDERS[provider_type]
    except KeyError as exc:
        raise KeyError(f"No calendar provider registered for '{provider_type}'") from exc


def get_email_provider(provider_type: str) -> type:
    try:
        return _EMAIL_PROVIDERS[provider_type]
    except KeyError as exc:
        raise KeyError(f"No email provider registered for '{provider_type}'") from exc
