"""OAuth flow helpers for Google, Microsoft (Outlook), and Gmail providers.

Generates authorization URLs and exchanges authorization codes for tokens
in standalone mode (without atom's integration layer). In the full atom
deployment, atom handles OAuth with encrypted token storage.

OAuth requires a client_id and client_secret registered with the provider's
developer console. Users provide these in the Developer Studio or via
environment variables. The flow is:

  1. GET /providers/{id}/oauth/start → redirect to provider's auth page
  2. Provider redirects back to GET /providers/{id}/oauth/callback?code=...
  3. We exchange the code for access + refresh tokens
  4. Tokens are stored in the provider connection config

All token storage goes through the PersistentStore — never logged, never
exposed in API responses.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# OAuth endpoint URLs (publicly documented, not secrets).
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Default scopes per provider type.
OAUTH_SCOPES: dict[str, list[str]] = {
    "google_calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "openid",
        "email",
    ],
    "outlook_calendar": [
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "openid",
        "email",
        "offline_access",
    ],
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "openid",
        "email",
    ],
}

# In-memory state store for OAuth flows (state token → provider connection ID).
# In production with atom, this uses atom's session store.
_state_store: dict[str, str] = {}


def get_oauth_config(provider_type: str, connection_config: dict[str, Any]) -> dict[str, str]:
    """Resolve OAuth client_id and client_secret for a provider.

    Checks the connection config first, then falls back to environment
    variables (A_CAL_GOOGLE_CLIENT_ID, A_CAL_MS_CLIENT_ID, etc.).

    Returns a dict with 'client_id' and 'client_secret' (may be empty).
    """
    import os

    client_id = connection_config.get("client_id", "")
    client_secret = connection_config.get("client_secret", "")

    env_prefix = {
        "google_calendar": "A_CAL_GOOGLE",
        "gmail": "A_CAL_GOOGLE",
        "outlook_calendar": "A_CAL_MS",
    }.get(provider_type, "A_CAL_OAUTH")

    if not client_id:
        client_id = os.environ.get(f"{env_prefix}_CLIENT_ID", "")
    if not client_secret:
        client_secret = os.environ.get(f"{env_prefix}_CLIENT_SECRET", "")

    return {"client_id": client_id, "client_secret": client_secret}


def build_auth_url(
    provider_type: str,
    connection_id: str,
    redirect_uri: str,
    connection_config: dict[str, Any],
) -> tuple[str, str]:
    """Build the OAuth authorization URL for a provider.

    Returns (auth_url, state) where state is a random token used to
    prevent CSRF attacks during the callback.
    """
    oauth_cfg = get_oauth_config(provider_type, connection_config)
    if not oauth_cfg["client_id"]:
        raise ValueError(
            f"No OAuth client_id configured for {provider_type}. "
            f"Set it in Developer Studio or via the {provider_type.upper().replace('_', '_')}_CLIENT_ID env var."
        )

    state = secrets.token_urlsafe(32)
    _state_store[state] = connection_id

    scopes = OAUTH_SCOPES.get(provider_type, [])
    scope_str = " ".join(scopes)

    if provider_type in ("google_calendar", "gmail"):
        params = {
            "client_id": oauth_cfg["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
    elif provider_type == "outlook_calendar":
        params = {
            "client_id": oauth_cfg["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            "response_mode": "query",
        }
        auth_url = f"{_MICROSOFT_AUTH_URL}?{urlencode(params)}"
    else:
        raise ValueError(f"OAuth not supported for provider type: {provider_type}")

    return auth_url, state


async def exchange_code_for_tokens(
    provider_type: str,
    code: str,
    redirect_uri: str,
    connection_config: dict[str, Any],
) -> dict[str, Any]:
    """Exchange an authorization code for access/refresh tokens.

    Returns a dict with 'access_token', 'refresh_token' (if available),
    'token_type', 'expires_in', and any other provider-specific fields.

    Raises RuntimeError on failure.
    """
    oauth_cfg = get_oauth_config(provider_type, connection_config)
    if not oauth_cfg["client_id"] or not oauth_cfg["client_secret"]:
        raise ValueError("OAuth client credentials not configured")

    if provider_type in ("google_calendar", "gmail"):
        token_url = _GOOGLE_TOKEN_URL
        data = {
            "client_id": oauth_cfg["client_id"],
            "client_secret": oauth_cfg["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    elif provider_type == "outlook_calendar":
        token_url = _MICROSOFT_TOKEN_URL
        data = {
            "client_id": oauth_cfg["client_id"],
            "client_secret": oauth_cfg["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(OAUTH_SCOPES["outlook_calendar"]),
        }
    else:
        raise ValueError(f"OAuth not supported for provider type: {provider_type}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code != 200:
            error_detail = resp.text[:500]
            logger.error("OAuth token exchange failed (%d): %s", resp.status_code, error_detail)
            raise RuntimeError(f"Token exchange failed: {resp.status_code} — {error_detail}")

        tokens = resp.json()
        return tokens


def validate_state(state: str) -> str | None:
    """Validate an OAuth state token and return the associated connection ID.

    Returns None if the state is invalid or expired.
    """
    return _state_store.pop(state, None)


def build_redirect_uri(provider_id: str, base_url: str = "http://localhost:8000") -> str:
    """Build the OAuth callback redirect URI for a provider connection."""
    return f"{base_url}/api/a-cal/providers/{provider_id}/oauth/callback"
