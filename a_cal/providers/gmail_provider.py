"""Gmail email provider — direct Gmail API via OAuth tokens.

Works standalone (without atom's integration layer) by calling Google's
Gmail REST API directly using stored OAuth tokens. Token refresh is
handled automatically via ``oauth_api.ensure_valid_token``.
"""

from __future__ import annotations

import base64
import logging
from typing import List, Optional, Tuple

import httpx

from a_cal.providers.base import EmailMessageDTO, EmailProvider, ProviderCapability, register_email_provider
from a_cal.providers.oauth_api import ensure_valid_token, get_oauth_tokens

logger = logging.getLogger(__name__)

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


@register_email_provider("gmail")
class GmailEmailProvider(EmailProvider):
    """Gmail provider using direct REST API calls."""

    capabilities = ProviderCapability.READ_MAIL | ProviderCapability.SEND_MAIL

    def __init__(self, config: dict, credentials: dict) -> None:
        """Initialize with provider config and resolved credentials.

        Args:
            config: Provider connection config (includes oauth_tokens).
            credentials: Resolved credentials (may overlap with config).
        """
        self._config = {**config, **credentials}
        self._tokens = get_oauth_tokens(self._config, "gmail")

    async def _headers(self) -> dict[str, str]:
        """Return authorization headers with a valid access token."""
        token = await ensure_valid_token(self._config, "gmail")
        if not token:
            raise RuntimeError("No valid OAuth access token for Gmail")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def list_messages(
        self, since_cursor: str | None, folder: str = "INBOX", limit: int = 50,
    ) -> tuple[list[EmailMessageDTO], str | None]:
        """List email messages from Gmail.

        Fetches INBOX messages plus any STARRED messages that may have been
        archived (not in INBOX), so starred emails always appear even if the
        user moved them out of the inbox.
        """
        headers = await self._headers()

        # Query INBOX messages.
        inbox_params = {"maxResults": str(limit), "labelIds": ["INBOX"]}
        # Also query STARRED to catch archived starred emails.
        starred_params = {"maxResults": "20", "labelIds": ["STARRED"]}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                inbox_resp = await client.get(f"{_GMAIL_API}/messages", headers=headers, params=inbox_params)
                inbox_resp.raise_for_status()
                starred_resp = await client.get(f"{_GMAIL_API}/messages", headers=headers, params=starred_params)
                # Starred query failure is non-fatal.
                msg_list = inbox_resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Gmail API error: %s", exc.response.text[:200])
            return [], since_cursor
        except Exception as exc:
            logger.error("Gmail list_messages failed: %s", exc)
            return [], since_cursor

        # Merge message IDs from both queries, deduplicating.
        seen_ids: set[str] = set()
        msg_refs: list[dict] = []
        for ref in msg_list.get("messages", []):
            mid = ref.get("id", "")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                msg_refs.append(ref)
        try:
            for ref in starred_resp.json().get("messages", []):
                mid = ref.get("id", "")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    msg_refs.append(ref)
        except Exception:
            pass  # starred_resp may have failed

        messages: list[EmailMessageDTO] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for ref in msg_refs[:limit + 20]:
                msg_id = ref.get("id", "")
                try:
                    detail_resp = await client.get(
                        f"{_GMAIL_API}/messages/{msg_id}",
                        headers=headers,
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                    )
                    if detail_resp.status_code != 200:
                        continue
                    detail = detail_resp.json()
                except Exception as exc:
                    logger.debug("Failed to fetch message %s: %s", msg_id, exc)
                    continue

                headers_dict = {h["name"].lower(): h["value"] for h in detail.get("payload", {}).get("headers", [])}
                # Parse RFC 2822 date header.
                from email.utils import parsedate_to_datetime
                received_at = None
                try:
                    received_at = parsedate_to_datetime(headers_dict.get("date", ""))
                except Exception:
                    pass

                messages.append(EmailMessageDTO(
                    provider_message_id=msg_id,
                    provider_type="gmail",
                    subject=headers_dict.get("subject", detail.get("snippet", "")[:60]),
                    from_address=headers_dict.get("from", ""),
                    snippet=detail.get("snippet", ""),
                    received_at=received_at,
                    thread_id=detail.get("threadId"),
                    labels=detail.get("labelIds", []),
                    headers=headers_dict,
                ))

        # Sort: starred emails first, then newest first (stable sort).
        messages.sort(key=lambda m: m.received_at or "", reverse=True)
        messages.sort(key=lambda m: "STARRED" not in (m.labels or []))

        return messages[:limit], msg_list.get("nextPageToken")

    async def send_message(
        self, to: list[str], subject: str, body_text: str,
        in_reply_to: str | None = None, thread_id: str | None = None,
    ) -> str:
        """Send an email via Gmail API."""
        headers = await self._headers()
        headers["Content-Type"] = "application/json"

        # Build RFC 2822 message.
        from_line = f"From: me\r\n"
        to_line = f"To: {', '.join(to)}\r\n"
        subject_line = f"Subject: {subject}\r\n"
        if in_reply_to:
            from_line += f"In-Reply-To: {in_reply_to}\r\n"
        raw_email = f"{from_line}{to_line}{subject_line}Content-Type: text/plain; charset=utf-8\r\n\r\n{body_text}"
        encoded = base64.urlsafe_b64encode(raw_email.encode("utf-8")).decode("ascii")

        body = {"raw": encoded}
        if thread_id:
            body["threadId"] = thread_id

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{_GMAIL_API}/messages/send",
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                result = resp.json()
                return result.get("id", "")
        except httpx.HTTPStatusError as exc:
            logger.error("Gmail send error: %s", exc.response.text[:200])
            raise

    async def reply(self, provider_message_id: str, body_text: str) -> str:
        """Reply to a specific message.

        Args:
            provider_message_id: The Gmail message ID to reply to.
            body_text: The reply body text.

        Returns:
            The new message ID from Gmail.
        """
        return await self.send_message(
            to=[provider_message_id],
            subject="Re:",
            body_text=body_text,
            in_reply_to=provider_message_id,
        )

    async def star_message(self, provider_message_id: str, starred: bool) -> bool:
        """Star or unstar a Gmail message via label operations.

        Args:
            provider_message_id: The Gmail message ID.
            starred: True to add STARRED label, False to remove it.

        Returns:
            True if the label operation succeeded.
        """
        headers = await self._headers()
        op = "add" if starred else "remove"
        url = f"{_GMAIL_API}/messages/{provider_message_id}/{op}Label"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json={"labelListVisibility": "labelShow", "messageListVisibility": "show", "labelIds": ["STARRED"]})
                return resp.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Gmail star failed for %s: %s", provider_message_id, exc)
            return False

    async def mark_read(self, provider_message_id: str, read: bool) -> bool:
        """Mark a Gmail message as read or unread via label operations.

        Args:
            provider_message_id: The Gmail message ID.
            read: True to remove UNREAD label (mark read), False to add it.

        Returns:
            True if the label operation succeeded.
        """
        headers = await self._headers()
        if read:
            url = f"{_GMAIL_API}/messages/{provider_message_id}/removeLabel"
            labels = ["UNREAD"]
        else:
            url = f"{_GMAIL_API}/messages/{provider_message_id}/addLabel"
            labels = ["UNREAD"]
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json={"labelIds": labels})
                return resp.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Gmail mark_read failed for %s: %s", provider_message_id, exc)
            return False

    async def delete_message(self, provider_message_id: str) -> bool:
        """Trash a Gmail message (move to TRASH, not permanent delete).

        Args:
            provider_message_id: The Gmail message ID to trash.

        Returns:
            True if the trash operation succeeded.
        """
        headers = await self._headers()
        url = f"{_GMAIL_API}/messages/{provider_message_id}/trash"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers)
                return resp.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Gmail delete failed for %s: %s", provider_message_id, exc)
            return False

    async def search_messages(
        self, query: str, folder: str = "INBOX", limit: int = 50
    ) -> list[EmailMessageDTO]:
        """Search Gmail messages using Gmail's search syntax.

        Args:
            query: Gmail search query (e.g. "from:sarah subject:meeting").
            folder: The label/folder to search within (appended as label:).
            limit: Maximum number of results.

        Returns:
            List of matching EmailMessageDTOs.
        """
        headers = await self._headers()
        full_query = f"label:{folder} {query}" if folder != "ALL" else query
        params = {"q": full_query, "maxResults": str(limit)}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{_GMAIL_API}/messages", headers=headers, params=params)
                resp.raise_for_status()
                msg_list = resp.json()
        except Exception as exc:
            logger.warning("Gmail search failed: %s", exc)
            return []

        messages: list[EmailMessageDTO] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for ref in msg_list.get("messages", [])[:limit]:
                msg_id = ref.get("id", "")
                try:
                    detail_resp = await client.get(
                        f"{_GMAIL_API}/messages/{msg_id}",
                        headers=headers,
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                    )
                    if detail_resp.status_code != 200:
                        continue
                    detail = detail_resp.json()
                except Exception:
                    continue

                headers_dict = {h["name"].lower(): h["value"] for h in detail.get("payload", {}).get("headers", [])}
                from email.utils import parsedate_to_datetime
                received_at = None
                try:
                    received_at = parsedate_to_datetime(headers_dict.get("date", ""))
                except Exception:
                    pass

                messages.append(EmailMessageDTO(
                    provider_message_id=msg_id,
                    provider_type="gmail",
                    subject=headers_dict.get("subject", detail.get("snippet", "")[:60]),
                    from_address=headers_dict.get("from", ""),
                    snippet=detail.get("snippet", ""),
                    received_at=received_at,
                    thread_id=detail.get("threadId"),
                    labels=detail.get("labelIds", []),
                    headers=headers_dict,
                ))
        return messages

    async def list_folders(self) -> list[str]:
        """List Gmail labels that act as folders.

        Returns:
            List of label names including system labels (INBOX, STARRED, etc.).
        """
        headers = await self._headers()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{_GMAIL_API}/labels", headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return [lbl["name"] for lbl in data.get("labels", []) if lbl.get("name")]
        except Exception as exc:
            logger.warning("Gmail list_folders failed: %s", exc)
            return ["INBOX", "STARRED", "SENT", "DRAFT", "TRASH"]
