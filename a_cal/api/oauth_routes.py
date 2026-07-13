"""OAuth start/callback endpoints for Google, Microsoft, and Gmail providers.

These routes expose the OAuth flow defined in ``a_cal.providers.oauth`` as
FastAPI endpoints so the frontend can initiate a real provider connection:

  1. ``GET /api/a-cal/providers/{id}/oauth/start``
     → validates the provider exists, builds the authorization URL, and
       returns it as JSON (the frontend opens it in a new tab/redirect).

  2. ``GET /api/a-cal/providers/{id}/oauth/callback?code=...&state=...``
     → validates state, exchanges the code for tokens, stores them in the
       provider connection config (never logged, never returned in API
       responses), marks the provider as connected, and redirects to the
       frontend with a success/failure query param.

OAuth client credentials come from the provider connection config or
environment variables (see ``oauth.get_oauth_config``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from a_cal.db.store import PersistentStore
from a_cal.integrations.atom_bridge import get_atom_token_storage
from a_cal.providers.oauth import (
    build_auth_url,
    build_redirect_uri,
    exchange_code_for_tokens,
    validate_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-oauth"])

_store = PersistentStore()

# When atom is available, OAuth tokens are encrypted via atom's
# ConnectionService (Fernet at rest). Otherwise, stored in SQLite config.
# Initialized lazily so atom detection runs at first use, not at import.
_atom_token_storage = None


def _get_token_storage():
    """Lazily initialize atom token storage on first use."""
    global _atom_token_storage
    if _atom_token_storage is None:
        _atom_token_storage = get_atom_token_storage()
    return _atom_token_storage

# Configurable URLs so the flow works in dev, self-hosted, or cloud.
USER_ID = "local-dev-user"

_BACKEND_URL = os.environ.get("A_CAL_BASE_URL", "http://localhost:8000")
_FRONTEND_URL = os.environ.get("A_CAL_FRONTEND_URL", "http://localhost:3456")


class OAuthStartResponse(BaseModel):
    """Response for the OAuth start endpoint."""

    authorization_url: str
    provider_id: str
    provider_type: str
    redirect_uri: str


@router.get("/providers/{provider_id}/oauth/start", response_model=OAuthStartResponse)
def oauth_start(provider_id: str) -> OAuthStartResponse:
    """Initiate an OAuth flow for a provider connection.

    Looks up the provider connection, builds the authorization URL for the
    appropriate provider (Google, Microsoft, Gmail), and returns it. The
    frontend should redirect the user to this URL.

    Args:
        provider_id: The provider connection ID to authorize.

    Returns:
        OAuthStartResponse with the authorization URL.

    Raises:
        HTTPException 404: Provider connection not found.
        HTTPException 400: Provider type does not support OAuth, or no
            client_id configured.
    """
    provider = _store.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider connection not found")

    provider_type = provider["provider_type"]
    if provider_type not in ("google_calendar", "outlook_calendar", "gmail"):
        raise HTTPException(
            status_code=400,
            detail=f"OAuth not supported for provider type '{provider_type}'. "
            f"Supported: google_calendar, outlook_calendar, gmail.",
        )

    redirect_uri = build_redirect_uri(provider_id, _BACKEND_URL)
    config = provider.get("config", {})

    try:
        auth_url, state = build_auth_url(provider_type, provider_id, redirect_uri, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("OAuth start for provider %s (%s)", provider_id, provider_type)
    return OAuthStartResponse(
        authorization_url=auth_url,
        provider_id=provider_id,
        provider_type=provider_type,
        redirect_uri=redirect_uri,
    )


@router.get("/providers/{provider_id}/oauth/callback")
async def oauth_callback(
    provider_id: str,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    """Handle the OAuth callback from the provider.

    The provider redirects here after the user authorizes (or denies).
    On success, exchanges the code for tokens, stores them in the provider
    connection config, marks it connected, and redirects to the frontend.

    Args:
        provider_id: The provider connection ID (from the redirect URI path).
        code: The authorization code from the provider.
        state: The state token we generated in ``oauth_start``.
        error: Error message if the user denied authorization.

    Returns:
        RedirectResponse to the frontend settings page with a status query.
    """
    frontend_settings = f"{_FRONTEND_URL}/?oauth_result="

    if error:
        logger.warning("OAuth denied for provider %s: %s", provider_id, error)
        return RedirectResponse(
            f"{frontend_settings}denied&provider_id={provider_id}&error={error}",
            status_code=302,
        )

    if not code or not state:
        return RedirectResponse(
            f"{frontend_settings}error&provider_id={provider_id}&error=missing_code_or_state",
            status_code=302,
        )

    # Validate state to prevent CSRF.
    expected_provider_id = validate_state(state)
    if expected_provider_id is None or expected_provider_id != provider_id:
        logger.warning("OAuth state mismatch for provider %s", provider_id)
        return RedirectResponse(
            f"{frontend_settings}error&provider_id={provider_id}&error=invalid_state",
            status_code=302,
        )

    provider = _store.get_provider(provider_id)
    if not provider:
        return RedirectResponse(
            f"{frontend_settings}error&provider_id={provider_id}&error=provider_not_found",
            status_code=302,
        )

    provider_type = provider["provider_type"]
    config = provider.get("config", {})
    redirect_uri = build_redirect_uri(provider_id, _BACKEND_URL)

    try:
        tokens = await exchange_code_for_tokens(provider_type, code, redirect_uri, config)
    except (RuntimeError, ValueError) as exc:
        logger.error("OAuth token exchange failed for %s: %s", provider_id, exc)
        _store.update_provider_status(provider_id, "error")
        return RedirectResponse(
            f"{frontend_settings}error&provider_id={provider_id}&error=token_exchange_failed",
            status_code=302,
        )

    # Store tokens. When atom is available, use encrypted ConnectionService.
    # In standalone, store in the provider config column (SQLite, not exposed
    # in API responses).
    token_data: dict[str, Any] = {
        "access_token": tokens.get("access_token", ""),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in"),
        "refresh_token": tokens.get("refresh_token", ""),
        "oauth_connected": True,
    }
    token_storage = _get_token_storage()
    if token_storage:
        token_storage.save_oauth_tokens(
            user_id=USER_ID,
            provider_type=provider_type,
            tokens=token_data,
        )
        # Store a reference (not the tokens themselves) in the provider config
        _store.update_provider_config(provider_id, {
            "token_storage": "atom",
            "oauth_connected": True,
        })
    else:
        _store.update_provider_config(provider_id, {"oauth_tokens": token_data})
    _store.update_provider_status(provider_id, "connected")

    logger.info("OAuth success for provider %s (%s)", provider_id, provider_type)
    return RedirectResponse(
        f"{frontend_settings}success&provider_id={provider_id}",
        status_code=302,
    )
