"""IMAP/SMTP email provider — the "any email provider" gateway (Q5-D).

Uses ONLY the Python standard library (imaplib, smtplib, email) so it works
with literally any provider that exposes IMAP/SMTP — no per-provider
integration needed. This complements atom's Gmail OAuth service: mainstream
providers use OAuth, everything else uses this.

IMAP UIDVALIDITY + last-seen UID form the incremental sync cursor, so we only
fetch new messages on each pull. Sending goes through SMTP with STARTTLS.
"""

from __future__ import annotations

import email
import imaplib
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from a_cal.providers.base import (
    EmailMessageDTO,
    EmailProvider,
    ProviderCapability,
    register_email_provider,
)

logger = logging.getLogger(__name__)


@register_email_provider("imap_smtp")
class IMAPSMTPProvider(EmailProvider):
    """IMAP read + SMTP send against any provider.

    Constructed from a ``ProviderConnection`` config carrying imap_host,
    imap_port, smtp_host, smtp_port, and the credentials_ref resolving to
    username + password (or app-specific password for providers like Gmail
    that disable plain password auth).
    """

    capabilities = ProviderCapability.READ_MAIL | ProviderCapability.SEND_MAIL

    def __init__(
        self,
        imap_host: str,
        smtp_host: str,
        username: str,
        password: str,
        imap_port: int = 993,
        smtp_port: int = 587,
    ) -> None:
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self._password = password

    # --- reading ------------------------------------------------------------

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.username, self._password)
        return conn

    async def list_messages(
        self, since_cursor: Optional[str], folder: str = "INBOX", limit: int = 50
    ) -> Tuple[List[EmailMessageDTO], Optional[str]]:
        """Fetch new messages since the cursor.

        Cursor format: ``<uidvalidity>:<last_uid>``. On first run (no cursor)
        we fetch the most recent ``limit`` messages.
        """
        conn = self._connect_imap()
        try:
            conn.select(folder, readonly=True)
            uidvalidity = conn.response("UIDVALIDITY")[1] or conn.status(folder, "(UIDVALIDITY)")[1]
            cursor_uidvalidity: Optional[str] = None
            last_uid: Optional[int] = None
            if since_cursor and ":" in since_cursor:
                cursor_uidvalidity, last_str = since_cursor.split(":", 1)
                last_uid = int(last_str) if last_str.isdigit() else None

            # If UIDVALIDITY changed, the cursor is invalid — start fresh.
            search_since = last_uid + 1 if (last_uid and cursor_uidvalidity == str(uidvalidity)) else 1
            _, uids = conn.uid("search", None, f"UID {search_since}:*")
            uid_list = (uids[0].split() if uids and uids[0] else [])[-limit:]

            messages: List[EmailMessageDTO] = []
            max_uid = last_uid or 0
            for uid in uid_list:
                uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
                _, data = conn.uid("fetch", uid_s, "(RFC822)")
                if not data or not data[0]:
                    continue
                raw = data[0][1]
                msg = email.message_from_bytes(raw)
                dto = self._parse_message(msg, uid_s)
                messages.append(dto)
                max_uid = max(max_uid, int(uid_s))

            next_cursor = f"{uidvalidity}:{max_uid}"
            return messages, next_cursor
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _parse_message(self, msg: email.message.Message, uid: str) -> EmailMessageDTO:
        from_header = msg.get("From", "")
        # Extract the bare email address from "Name <addr@x>".
        from_addr = email.utils.parseaddr(from_header)[1]
        to_addrs = [a[1] for a in email.utils.getaddresses(msg.get_all("To", []))]
        date_hdr = msg.get("Date", "")
        received = None
        try:
            if date_hdr:
                received = email.utils.parsedate_to_datetime(date_hdr)
        except Exception:
            received = None

        body_text = None
        snippet = None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
        else:
            body_text = msg.get_payload(decode=True)
            if body_text:
                body_text = body_text.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if body_text:
            snippet = body_text[:200]

        return EmailMessageDTO(
            provider_message_id=msg.get("Message-ID", uid),
            provider_type="imap_smtp",
            subject=msg.get("Subject", ""),
            from_address=from_addr,
            to_addresses=to_addrs,
            received_at=received,
            snippet=snippet,
            body_text=body_text,
            thread_id=msg.get("References", "").split()[0] if msg.get("References") else None,
            headers={k: v for k, v in msg.items()},
        )

    # --- sending ------------------------------------------------------------

    async def send_message(
        self, to: List[str], subject: str, body_text: str,
        in_reply_to: Optional[str] = None, thread_id: Optional[str] = None,
    ) -> str:
        msg = MIMEMultipart("alternative")
        msg["From"] = self.username
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = thread_id or in_reply_to
        msg.attach(MIMEText(body_text, "plain"))
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self.username, self._password)
            smtp.sendmail(self.username, to, msg.as_string())
        return msg["Message-ID"]

    async def reply(self, provider_message_id: str, body_text: str) -> str:
        # Minimal reply: subject prefixed with Re:, threading headers set.
        return await self.send_message(
            to=[],
            subject="Re: ",
            body_text=body_text,
            in_reply_to=provider_message_id,
        )
