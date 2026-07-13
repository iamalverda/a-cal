"""Payment processing service — Stripe via REST API with mock fallback.

When a Stripe API key is configured (``STRIPE_SECRET_KEY`` env var), this
service creates real Stripe PaymentIntents. Without a key, it falls back to
a mock mode that generates fake payment IDs — useful for development and
testing without a Stripe account.

Uses httpx (already a dependency) to call Stripe's REST API directly, so no
additional ``stripe`` package is needed.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"


class PaymentService:
    """Stripe payment integration with mock fallback.

    Args:
        secret_key: Stripe secret key. If None, reads from
            ``STRIPE_SECRET_KEY`` env var. If neither is set, operates in
            mock mode.
    """

    def __init__(self, secret_key: str | None = None) -> None:
        """Initialize the payment service."""
        self._key = secret_key or os.getenv("STRIPE_SECRET_KEY", "")
        self._mock = not bool(self._key)

    @property
    def is_mock(self) -> bool:
        """True when operating in mock mode (no Stripe key configured)."""
        return self._mock

    def create_payment_intent(
        self,
        amount_cents: int,
        currency: str = "usd",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe PaymentIntent for the given amount.

        Args:
            amount_cents: Amount in cents (e.g. 5000 = $50.00).
            currency: ISO 4217 currency code (lowercase).
            metadata: Optional metadata to attach to the intent.

        Returns:
            Dict with ``id``, ``client_secret``, ``amount``, ``currency``,
            and ``status``.
        """
        if self._mock:
            intent_id = f"pi_mock_{uuid.uuid4().hex[:24]}"
            logger.info("Mock payment intent created: %s (%d %s)", intent_id, amount_cents, currency)
            return {
                "id": intent_id,
                "client_secret": f"{intent_id}_secret_mock",
                "amount": amount_cents,
                "currency": currency,
                "status": "requires_confirmation",
            }

        resp = httpx.post(
            f"{STRIPE_API_BASE}/payment_intents",
            headers={"Authorization": f"Bearer {self._key}"},
            data={
                "amount": str(amount_cents),
                "currency": currency,
                **{f"metadata[{k}]": v for k, v in (metadata or {}).items()},
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "id": data["id"],
            "client_secret": data.get("client_secret"),
            "amount": data["amount"],
            "currency": data["currency"],
            "status": data["status"],
        }

    def confirm_payment(self, payment_intent_id: str) -> dict[str, Any]:
        """Check the status of a payment intent.

        In mock mode, always returns ``succeeded``.

        Args:
            payment_intent_id: The Stripe PaymentIntent ID.

        Returns:
            Dict with ``id``, ``status``.
        """
        if self._mock:
            return {"id": payment_intent_id, "status": "succeeded"}

        resp = httpx.get(
            f"{STRIPE_API_BASE}/payment_intents/{payment_intent_id}",
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"id": data["id"], "status": data["status"]}

    def create_product(
        self,
        name: str,
        description: str = "",
        amount_cents: int = 0,
        currency: str = "usd",
    ) -> dict[str, Any]:
        """Create a Stripe Product + Price for a paid event type.

        In mock mode, returns a fake product ID.

        Args:
            name: Product name (event type title).
            description: Product description.
            amount_cents: Price in cents.
            currency: ISO currency code.

        Returns:
            Dict with ``product_id`` and ``price_id``.
        """
        if self._mock:
            pid = f"prod_mock_{uuid.uuid4().hex[:16]}"
            return {"product_id": pid, "price_id": f"price_mock_{uuid.uuid4().hex[:16]}"}

        # Create product
        resp = httpx.post(
            f"{STRIPE_API_BASE}/products",
            headers={"Authorization": f"Bearer {self._key}"},
            data={"name": name, "description": description},
            timeout=15,
        )
        resp.raise_for_status()
        product = resp.json()

        # Create price for the product
        resp2 = httpx.post(
            f"{STRIPE_API_BASE}/prices",
            headers={"Authorization": f"Bearer {self._key}"},
            data={
                "product": product["id"],
                "unit_amount": str(amount_cents),
                "currency": currency,
                "recurring[interval]": "month",
            },
            timeout=15,
        )
        resp2.raise_for_status()
        price = resp2.json()
        return {"product_id": product["id"], "price_id": price["id"]}
