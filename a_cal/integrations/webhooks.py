"""Webhook delivery service — sends event payloads to configured endpoints.

When an event fires (e.g. booking.created), this service looks up all active
webhooks subscribed to that event, signs the payload with the webhook's
secret (HMAC-SHA256), and POSTs the JSON body to the configured URL. Delivery
results are recorded for audit and debugging.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from a_cal.db.store import PersistentStore

logger = logging.getLogger(__name__)

_store = PersistentStore()


def _sign_payload(payload: bytes, secret: str) -> str:
    """Compute an HMAC-SHA256 signature for the webhook payload.

    Args:
        payload: Raw JSON bytes of the request body.
        secret: The webhook's shared secret.

    Returns:
        Hex-encoded signature.
    """
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def dispatch_event(
    event_type: str, payload: dict[str, Any], owner_user_id: str,
) -> list[dict[str, Any]]:
    """Dispatch an event to a single owner's subscribed active webhooks.

    Args:
        event_type: Event name (e.g. ``booking.created``, ``booking.cancelled``).
        payload: Event data to send as JSON body.
        owner_user_id: The user who owns the resource that fired the event
            (e.g. the event-type owner for a public booking). Only this
            user's webhooks receive the payload, so bookings never fan out
            to other tenants' endpoints.

    Returns:
        List of delivery result dicts (one per webhook).
    """
    webhooks = _store.list_active_webhooks_for_event(event_type, owner_user_id)
    if not webhooks:
        return []

    results: list[dict[str, Any]] = []
    body = json.dumps({"event": event_type, "data": payload}, default=str)
    body_bytes = body.encode()

    for hook in webhooks:
        headers = {"Content-Type": "application/json"}
        if hook.get("secret"):
            signature = _sign_payload(body_bytes, hook["secret"])
            headers["X-Acal-Signature"] = signature

        status_code: int | None = None
        response_body: str | None = None
        try:
            resp = httpx.post(
                hook["url"],
                content=body_bytes,
                headers=headers,
                timeout=10,
            )
            status_code = resp.status_code
            response_body = resp.text[:500]
        except Exception as exc:
            logger.warning("Webhook delivery to %s failed: %s", hook["url"], exc)
            response_body = str(exc)[:500]

        delivery = _store.record_webhook_delivery({
            "webhook_id": hook["id"],
            "event_type": event_type,
            "payload": {"event": event_type, "data": payload},
            "status_code": status_code,
            "response_body": response_body,
        })

        _store.mark_webhook_delivered(hook["id"], status_code)

        results.append(delivery)

    return results
