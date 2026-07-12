"""Unified calendar + email provider abstraction."""

from a_cal.providers.base import (
    CalendarEventDTO,
    CalendarProvider,
    EmailProvider,
    EmailMessageDTO,
    ProviderCapability,
    get_calendar_provider,
    register_calendar_provider,
)

__all__ = [
    "CalendarEventDTO",
    "CalendarProvider",
    "EmailProvider",
    "EmailMessageDTO",
    "ProviderCapability",
    "get_calendar_provider",
    "register_calendar_provider",
]
