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
    description: str | None = None
    location: str | None = None
    attendees: list[dict[str, str]] = field(default_factory=list)
    status: str = "confirmed"
    calendar_id: str | None = None  # the provider's own calendar id
    color: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_sub_account_id: str | None = None
    etag: str | None = None  # for optimistic concurrency on writes

    def to_storage_dict(self) -> dict[str, Any]:
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

    events: list[CalendarEventDTO]
    next_cursor: str | None = None  # None => no more pages
    has_more: bool = False


@dataclass
class AttachmentDTO:
    """Metadata for an email attachment (filename, type, size).

    ``content`` is populated only when the attachment is being sent or
    explicitly downloaded; it is left empty during listing to avoid
    downloading large payloads on every inbox refresh.
    """

    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0
    content: bytes | None = None
    content_id: str | None = None  # for inline images


@dataclass
class EmailMessageDTO:
    """Provider-agnostic email message (minimal fields the agents need)."""

    provider_message_id: str
    provider_type: str
    subject: str
    from_address: str
    to_addresses: list[str] = field(default_factory=list)
    received_at: datetime | None = None
    snippet: str | None = None
    body_text: str | None = None
    thread_id: str | None = None
    labels: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    attachments: list[AttachmentDTO] = field(default_factory=list)


class CalendarProvider(ABC):
    """Interface every calendar backend implements.

    Implementations are constructed with a ``ProviderConnection`` row (which
    carries the ``credentials_ref`` and provider ``config``) and a way to
    resolve encrypted credentials from atom's token storage.
    """

    capabilities: ProviderCapability = ProviderCapability.READ_EVENTS

    @abstractmethod
    async def list_events(
        self, start: datetime, end: datetime, calendar_id: str | None = None
    ) -> list[CalendarEventDTO]:
        """Return events in [start, end)."""

    @abstractmethod
    async def list_changes(
        self, since_cursor: str | None, start: datetime, end: datetime
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
    async def cancel_event(self, provider_event_id: str, calendar_id: str | None = None) -> None:
        """Cancel/delete an event."""

    def supports(self, cap: ProviderCapability) -> bool:
        return bool(self.capabilities & cap)


class EmailProvider(ABC):
    """Interface every email backend implements (Gmail OAuth or IMAP/SMTP)."""

    capabilities: ProviderCapability = ProviderCapability.READ_MAIL

    @abstractmethod
    async def list_messages(
        self, since_cursor: str | None, folder: str = "INBOX", limit: int = 50
    ) -> tuple[list[EmailMessageDTO], str | None]:
        """Return a page of messages and a next cursor."""

    @abstractmethod
    async def send_message(
        self, to: list[str], subject: str, body_text: str,
        in_reply_to: str | None = None, thread_id: str | None = None,
    ) -> str:
        """Send a message; return the provider message id."""

    @abstractmethod
    async def reply(
        self, provider_message_id: str, body_text: str
    ) -> str:
        """Reply to a specific message; return the new message id."""

    async def star_message(self, provider_message_id: str, starred: bool) -> bool:
        """Star or unstar a message. Returns True on success.

        Args:
            provider_message_id: The provider-specific message identifier.
            starred: True to star, False to unstar.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        return False

    async def mark_read(self, provider_message_id: str, read: bool) -> bool:
        """Mark a message as read or unread. Returns True on success.

        Args:
            provider_message_id: The provider-specific message identifier.
            read: True to mark as read, False to mark as unread.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        return False

    async def delete_message(self, provider_message_id: str) -> bool:
        """Delete or trash a message. Returns True on success.

        Args:
            provider_message_id: The provider-specific message identifier.

        Returns:
            True if the operation succeeded, False otherwise.
        """
        return False

    async def search_messages(
        self, query: str, folder: str = "INBOX", limit: int = 50
    ) -> list[EmailMessageDTO]:
        """Search messages by query string.

        Args:
            query: Search query (subject, from, body text).
            folder: The folder to search in.
            limit: Maximum number of results.

        Returns:
            List of matching EmailMessageDTOs.
        """
        return []

    async def list_folders(self) -> list[str]:
        """List available folders/labels for this provider.

        Returns:
            List of folder names.
        """
        return ["INBOX"]


# --- provider registry -----------------------------------------------------

_CALENDAR_PROVIDERS: dict[str, type] = {}
_EMAIL_PROVIDERS: dict[str, type] = {}


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
