"""Standalone OAuth token helpers for direct Google API calls.

Retrieves OAuth tokens from the provider connection config and handles
access token refresh when tokens expire. Used by the standalone Google
Calendar and Gmail providers when atom's integration layer is not
available.

Tokens are stored in the provider connection's ``config`` JSON column
under the ``oauth_tokens`` key. They are never logged or returned in API
responses (see ``_serialize_provider`` which strips them).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def get_oauth_tokens(config: Dict[str, Any], provider_type: str) -> Dict[str, str]:
    """Extract OAuth tokens from provider connection config.

    Args:
        config: The provider connection's ``config`` dict.
        provider_type: Provider type for env var fallback.

    Returns:
        Dict with ``access_token`` and optionally ``refresh_token``.
        Returns empty dict if no tokens are configured.
    """
    tokens = config.get("oauth_tokens", {})
    if tokens and tokens.get("access_token"):
        return tokens

    # Fall back to env vars (rare, but possible for testing).
    env_prefix = {
        "google_calendar": "A_CAL_GOOGLE",
        "gmail": "A_CAL_GOOGLE",
        "outlook_calendar": "A_CAL_MS",
    }.get(provider_type, "A_CAL_OAUTH")
    client_id = os.environ.get(f"{env_prefix}_CLIENT_ID", "")
    client_secret = os.environ.get(f"{env_prefix}_CLIENT_SECRET", "")
    if not client_id:
        return {}

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": "",
        "refresh_token": "",
    }


def get_client_credentials(provider_type: str) -> tuple[str, str]:
    """Get OAuth client ID and secret from environment variables.

    Args:
        provider_type: The provider type (google_calendar, gmail, etc.).

    Returns:
        Tuple of (client_id, client_secret). May be empty strings.
    """
    env_prefix = {
        "google_calendar": "A_CAL_GOOGLE",
        "gmail": "A_CAL_GOOGLE",
        "outlook_calendar": "A_CAL_MS",
    }.get(provider_type, "A_CAL_OAUTH")
    return (
        os.environ.get(f"{env_prefix}_CLIENT_ID", ""),
        os.environ.get(f"{env_prefix}_CLIENT_SECRET", ""),
    )


async def ensure_valid_token(config: Dict[str, Any], provider_type: str) -> Optional[str]:
    """Return a valid access token, refreshing if necessary.

    If the stored access token is expired (or missing) and a refresh_token
    is available, this function calls Google's token endpoint to get a new
    access token. The refreshed tokens are written back into ``config``
    in-place so the caller can persist them.

    Args:
        config: The provider connection's ``config`` dict (mutated in-place
            on refresh).
        provider_type: Provider type for env var lookup.

    Returns:
        A valid access token string, or None if no tokens are available.
    """
    tokens = get_oauth_tokens(config, provider_type)
    if not tokens:
        return None

    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_at = tokens.get("expires_at")

    # Check if the access token is still valid (with 60s buffer).
    now = time.time()
    if access_token and (not expires_at or expires_at > now + 60):
        return access_token

    # Need to refresh.
    if not refresh_token:
        # No refresh token — return the access token if we have one
        # (it might still work briefly).
        return access_token or None

    client_id, client_secret = get_client_credentials(provider_type)
    if not client_id or not client_secret:
        logger.warning("Cannot refresh token: missing client credentials for %s", provider_type)
        return access_token or None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_GOOGLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Token refresh failed for %s: %s", provider_type, exc)
        return access_token or None

    new_access = data.get("access_token", "")
    new_expires_in = data.get("expires_in", 3600)
    new_tokens = {
        **tokens,
        "access_token": new_access,
        "expires_in": new_expires_in,
        "expires_at": now + new_expires_in,
    }
    # Preserve refresh_token (Google only returns it on first auth).
    if data.get("refresh_token"):
        new_tokens["refresh_token"] = data["refresh_token"]
    else:
        new_tokens["refresh_token"] = refresh_token

    # Write back to config in-place so caller can persist.
    config["oauth_tokens"] = new_tokens
    logger.info("Refreshed OAuth token for %s", provider_type)
    return new_access
