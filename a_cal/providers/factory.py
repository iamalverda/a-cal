"""Provider factory — build a live provider from a ProviderConnection row.

Resolves encrypted credentials from atom's token storage and instantiates the
registered provider implementation for the connection's ``provider_type``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from a_cal.providers.base import CalendarProvider, EmailProvider, get_calendar_provider, get_email_provider

logger = logging.getLogger(__name__)


def _resolve_credentials(credentials_ref: str | None, config: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve an opaque credentials handle into concrete fields.

    Delegates to atom's encrypted token_storage when available; for local-only
    standalone mode, falls back to values stored in the connection config.
    Never logs the resolved values.
    """
    if not credentials_ref:
        # Standalone mode: use config values directly (local-only, user's machine).
        if config:
            creds: dict[str, str] = {}
            for key in ("password", "username", "token", "refresh_token", "email"):
                val = config.get(key)
                if val:
                    creds[key] = str(val)
            return creds
        return {}
    try:
        from core.token_storage import token_storage  # type: ignore

        creds = token_storage.load(credentials_ref)
        if isinstance(creds, dict):
            return creds
        return {"credentials": creds}
    except Exception as exc:
        logger.debug("token_storage unavailable for %s: %s", credentials_ref, exc)
        # Fall back to config if token_storage fails.
        if config:
            return {k: str(v) for k, v in config.items() if k in ("password", "username", "token", "email")}
        return {}


def build_calendar_provider(connection: Any) -> CalendarProvider:
    """Instantiate a CalendarProvider from a ProviderConnection-like dict/row."""
    provider_type = connection["provider_type"] if isinstance(connection, dict) else connection.provider_type
    config = connection.get("config", {}) if isinstance(connection, dict) else (connection.config or {})
    creds = _resolve_credentials(connection.get("credentials_ref") if isinstance(connection, dict) else connection.credentials_ref, config)

    cls = get_calendar_provider(provider_type)
    if provider_type == "caldav":
        return cls(
            server_url=config["server_url"],
            username=creds.get("username", config.get("username", "")),
            password=creds.get("password", ""),
            calendar_url=config.get("calendar_url"),
        )
    if provider_type == "google_calendar":
        # Wraps atom's existing GoogleCalendarService.
        from a_cal.providers.google_provider import GoogleCalendarProvider

        return GoogleCalendarProvider(config=config, credentials=creds)
    if provider_type == "outlook_calendar":
        from a_cal.providers.outlook_provider import OutlookCalendarProvider

        return OutlookCalendarProvider(config=config, credentials=creds)
    # Fallback: pass config + creds as kwargs.
    return cls(**config, **creds)


def build_email_provider(connection: Any) -> EmailProvider:
    provider_type = connection["provider_type"] if isinstance(connection, dict) else connection.provider_type
    config = connection.get("config", {}) if isinstance(connection, dict) else (connection.config or {})
    creds = _resolve_credentials(connection.get("credentials_ref") if isinstance(connection, dict) else connection.credentials_ref, config)

    cls = get_email_provider(provider_type)
    if provider_type == "imap_smtp":
        return cls(
            imap_host=config["imap_host"],
            smtp_host=config["smtp_host"],
            username=creds.get("username", config.get("username", "")),
            password=creds.get("password", ""),
            imap_port=config.get("imap_port", 993),
            smtp_port=config.get("smtp_port", 587),
        )
    if provider_type == "gmail":
        from a_cal.providers.gmail_provider import GmailEmailProvider

        return GmailEmailProvider(config=config, credentials=creds)
    return cls(**config, **creds)
