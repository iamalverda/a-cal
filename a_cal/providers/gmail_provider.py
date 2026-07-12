"""Gmail email provider — wraps atom's existing GmailService behind EmailProvider."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from a_cal.providers.base import EmailMessageDTO, EmailProvider, ProviderCapability, register_email_provider

logger = logging.getLogger(__name__)


@register_email_provider("gmail")
class GmailEmailProvider(EmailProvider):
    capabilities = ProviderCapability.READ_MAIL | ProviderCapability.SEND_MAIL

    def __init__(self, config: dict, credentials: dict) -> None:
        try:
            from integrations.gmail_service import GmailService  # type: ignore
            self._svc = GmailService(config={**config, **credentials})
        except ImportError:
            raise ImportError(
                "Gmail OAuth provider requires atom's integration layer. "
                "Add atom/backend to PYTHONPATH or use the IMAP/SMTP provider "
                "for any email server that supports IMAP/SMTP."
            )

    async def list_messages(self, since_cursor: Optional[str], folder: str = "INBOX", limit: int = 50) -> Tuple[List[EmailMessageDTO], Optional[str]]:
        raw = await self._svc.list_messages() if hasattr(self._svc, "list_messages") else []
        return [self._to_dto(m) for m in raw], since_cursor

    async def send_message(self, to: List[str], subject: str, body_text: str, in_reply_to: Optional[str] = None, thread_id: Optional[str] = None) -> str:
        return await self._svc.send_email(to, subject, body_text) if hasattr(self._svc, "send_email") else ""

    async def reply(self, provider_message_id: str, body_text: str) -> str:
        return await self.send_message([provider_message_id], "Re: ", body_text)

    @staticmethod
    def _to_dto(raw: dict) -> EmailMessageDTO:
        return EmailMessageDTO(
            provider_message_id=raw.get("id", ""),
            provider_type="gmail",
            subject=raw.get("subject", raw.get("snippet", "")),
            from_address=raw.get("from", ""),
            snippet=raw.get("snippet"),
        )
