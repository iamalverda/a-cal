"""IMAP/SMTP email provider — the "any provider" email backend.

Uses Python's standard library (``imaplib``, ``smtplib``, ``email``) to talk
to literally any email server that supports IMAP for reading and SMTP for
sending. No external dependencies, no OAuth dance — just credentials.

This is what makes A-Cal's "link to any email provider" literally true:
Gmail, Fastmail, ProtonMail Bridge, Zoho, Yahoo, any self-hosted
Postfix/Dovecot, etc. If it speaks IMAP + SMTP, it works.

Typical config::

    {
        "imap_host": "imap.fastmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.fastmail.com",
        "smtp_port": 587,
        "username": "user@example.com",
        "password": "app-specific-password"
    }
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import logging
import smtplib
from datetime import datetime, timezone, UTC
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

from a_cal.providers.base import (
    EmailMessageDTO,
    EmailProvider,
    ProviderCapability,
    register_email_provider,
)

logger = logging.getLogger(__name__)


@register_email_provider("imap_smtp")
class ImapSmtpProvider(EmailProvider):
    """IMAP/SMTP email provider using only the Python standard library.

    Args:
        imap_host: IMAP server hostname (e.g. ``imap.gmail.com``).
        smtp_host: SMTP server hostname (e.g. ``smtp.gmail.com``).
        username: Account username / email address.
        password: Account password or app-specific password.
        imap_port: IMAP port (default 993 for IMAPS).
        smtp_port: SMTP port (default 587 for STARTTLS).
        use_ssl_imap: Use SSL for IMAP connection (default True).
        use_starttls_smtp: Use STARTTLS for SMTP connection (default True).
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
        use_ssl_imap: bool = True,
        use_starttls_smtp: bool = True,
    ) -> None:
        self._imap_host = imap_host
        self._smtp_host = smtp_host
        self._username = username
        self._password = password
        self._imap_port = imap_port
        self._smtp_port = smtp_port
        self._use_ssl_imap = use_ssl_imap
        self._use_starttls_smtp = use_starttls_smtp

    def _connect_imap(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Create and authenticate an IMAP connection."""
        if self._use_ssl_imap:
            conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        else:
            conn = imaplib.IMAP4(self._imap_host, self._imap_port)
        conn.login(self._username, self._password)
        return conn

    async def list_messages(
        self,
        since_cursor: str | None,
        folder: str = "INBOX",
        limit: int = 50,
    ) -> tuple[list[EmailMessageDTO], str | None]:
        """Fetch a page of messages from the IMAP folder.

        Args:
            since_cursor: UIDs returned previously; fetch messages with
                higher UIDs. If None, fetch the most recent messages.
            folder: IMAP folder name (default ``INBOX``).
            limit: Maximum number of messages to return.

        Returns:
            Tuple of (message DTOs, next cursor — the highest UID fetched).
        """
        conn = self._connect_imap()
        try:
            conn.select(folder, readonly=True)

            # Build UID search query
            if since_cursor:
                # Fetch messages with UID greater than the cursor
                search_criteria = f"UID {int(since_cursor) + 1}:*"
            else:
                # Fetch the most recent messages
                status, data = conn.uid("search", None, "ALL")
                if status != "OK" or not data or not data[0]:
                    return [], None
                all_uids = data[0].split()
                # Take the last `limit` UIDs (most recent)
                recent_uids = all_uids[-limit:]
                if not recent_uids:
                    return [], None
                search_criteria = ",".join(uid.decode() for uid in recent_uids)

            status, data = conn.uid("fetch", search_criteria, "(UID FLAGS BODY.PEEK[])")
            if status != "OK" or not data:
                return [], None

            messages: list[EmailMessageDTO] = []
            next_cursor = since_cursor

            for item in data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw_email = item[1]
                if isinstance(raw_email, bytes):
                    msg = email.message_from_bytes(raw_email)
                else:
                    continue

                uid = self._extract_uid(item[0])
                if uid is None:
                    continue

                dto = self._msg_to_dto(msg, uid)
                messages.append(dto)

                # Track highest UID as cursor
                if next_cursor is None or int(uid) > int(next_cursor):
                    next_cursor = uid

            # Sort by UID descending (newest first)
            messages.sort(key=lambda m: int(m.provider_message_id), reverse=True)
            return messages, next_cursor
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def send_message(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> str:
        """Send a plain-text email via SMTP.

        Args:
            to: List of recipient email addresses.
            subject: Email subject line.
            body_text: Plain-text body content.
            in_reply_to: Message-ID to reply to (for threading).
            thread_id: Unused for IMAP/SMTP (kept for interface compat).

        Returns:
            The generated Message-ID of the sent email.
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = self._username
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        message_id = email.utils.make_msgid(domain=self._username.split("@")[-1] if "@" in self._username else None)
        msg["Message-ID"] = message_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
            if self._use_starttls_smtp:
                server.starttls()
            server.login(self._username, self._password)
            server.sendmail(self._username, to, msg.as_string())

        logger.info("Sent email to %s with subject '%s'", ", ".join(to), subject)
        return message_id

    async def reply(
        self, provider_message_id: str, body_text: str
    ) -> str:
        """Reply to a specific message by fetching its headers and sending a reply.

        Args:
            provider_message_id: The UID of the message to reply to.
            body_text: Reply body text.

        Returns:
            The generated Message-ID of the reply.
        """
        conn = self._connect_imap()
        try:
            conn.select("INBOX", readonly=True)
            status, data = conn.uid("fetch", provider_message_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)])")
            if status != "OK" or not data:
                # Fallback: just send a new message
                return await self.send_message([], "Re:", body_text)

            header_bytes = b""
            for item in data:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                    header_bytes = item[1]
                    break

            header_msg = email.message_from_bytes(header_bytes)
            from_addr = header_msg.get("From", "")
            subject = header_msg.get("Subject", "")
            original_msg_id = header_msg.get("Message-ID", "")

            # Build reply subject
            if not subject.lower().startswith("re:"):
                reply_subject = f"Re: {subject}"
            else:
                reply_subject = subject

            # Extract email address from From header
            reply_to = email.utils.parseaddr(from_addr)[1]
            if not reply_to:
                return await self.send_message([], reply_subject, body_text)

            return await self.send_message(
                [reply_to], reply_subject, body_text,
                in_reply_to=original_msg_id or None,
            )
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def star_message(self, provider_message_id: str, starred: bool) -> bool:
        """Star or unstar a message via IMAP \\Flagged flag.

        Args:
            provider_message_id: The IMAP UID of the message.
            starred: True to set \\Flagged, False to remove it.

        Returns:
            True if the flag operation succeeded.
        """
        conn = self._connect_imap()
        try:
            conn.select("INBOX")
            op = "+FLAGS" if starred else "-FLAGS"
            typ, _ = conn.uid("STORE", provider_message_id, f"({op}\\Flagged)")
            return typ == "OK"
        except Exception as exc:
            logger.warning("IMAP star failed for %s: %s", provider_message_id, exc)
            return False
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def mark_read(self, provider_message_id: str, read: bool) -> bool:
        """Mark a message as read or unread via IMAP \\Seen flag.

        Args:
            provider_message_id: The IMAP UID of the message.
            read: True to add \\Seen (mark read), False to remove it.

        Returns:
            True if the flag operation succeeded.
        """
        conn = self._connect_imap()
        try:
            conn.select("INBOX")
            op = "+FLAGS" if read else "-FLAGS"
            typ, _ = conn.uid("STORE", provider_message_id, f"({op}\\Seen)")
            return typ == "OK"
        except Exception as exc:
            logger.warning("IMAP mark_read failed for %s: %s", provider_message_id, exc)
            return False
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def delete_message(self, provider_message_id: str) -> bool:
        """Delete a message by marking it \\Deleted and expunging.

        Args:
            provider_message_id: The IMAP UID of the message to delete.

        Returns:
            True if the delete operation succeeded.
        """
        conn = self._connect_imap()
        try:
            conn.select("INBOX")
            try:
                conn.uid("COPY", provider_message_id, "Trash")
            except Exception:
                pass
            typ, _ = conn.uid("STORE", provider_message_id, "(+FLAGS\\Deleted)")
            if typ == "OK":
                conn.expunge()
                return True
            return False
        except Exception as exc:
            logger.warning("IMAP delete failed for %s: %s", provider_message_id, exc)
            return False
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def search_messages(
        self, query: str, folder: str = "INBOX", limit: int = 50
    ) -> list[EmailMessageDTO]:
        """Search messages via IMAP SEARCH across FROM, SUBJECT, and BODY.

        Args:
            query: Search text.
            folder: The IMAP folder to search in.
            limit: Maximum number of results.

        Returns:
            List of matching EmailMessageDTOs.
        """
        conn = self._connect_imap()
        try:
            conn.select(folder, readonly=True)
            criteria = f'OR OR FROM "{query}" SUBJECT "{query}" BODY "{query}"'
            status, data = conn.uid("search", None, criteria)
            if status != "OK" or not data or not data[0]:
                return []
            uid_list = data[0].split()[-limit:]
            messages: list[EmailMessageDTO] = []
            for uid in uid_list:
                uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
                status, fetch_data = conn.uid("fetch", uid_s, "(UID FLAGS BODY.PEEK[])")
                if status != "OK" or not fetch_data:
                    continue
                for item in fetch_data:
                    if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                        msg = email.message_from_bytes(item[1])
                        uid_val = self._extract_uid(item[0]) or uid_s
                        messages.append(self._msg_to_dto(msg, uid_val))
                        break
            return messages
        except Exception as exc:
            logger.warning("IMAP search failed: %s", exc)
            return []
        finally:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass

    async def list_folders(self) -> list[str]:
        """List available IMAP folders.

        Returns:
            List of folder names.
        """
        conn = self._connect_imap()
        try:
            typ, folders = conn.list()
            if typ != "OK":
                return ["INBOX"]
            result: list[str] = []
            for f in folders:
                if isinstance(f, bytes):
                    decoded = f.decode("utf-8", errors="replace")
                    parts = decoded.split('"')
                    if len(parts) >= 2:
                        result.append(parts[-2])
                    elif "INBOX" in decoded:
                        result.append("INBOX")
            return result or ["INBOX"]
        except Exception as exc:
            logger.warning("IMAP list_folders failed: %s", exc)
            return ["INBOX"]
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    @staticmethod
    def _extract_uid(flag_data: object) -> str | None:
        """Extract the UID from a FETCH response flag string."""
        if isinstance(flag_data, bytes):
            text = flag_data.decode("utf-8", errors="replace")
        elif isinstance(flag_data, str):
            text = flag_data
        else:
            return None
        # IMAP FETCH response looks like: b'1 (UID 12345 FLAGS (\\Seen))'
        import re
        match = re.search(r"UID (\d+)", text)
        return match.group(1) if match else None

    @staticmethod
    def _msg_to_dto(msg: email.message.Message, uid: str) -> EmailMessageDTO:
        """Convert an email.message.Message to an EmailMessageDTO.

        Args:
            msg: Parsed email message from imaplib.
            uid: The IMAP UID for this message.

        Returns:
            EmailMessageDTO with extracted fields.
        """
        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")
        to_raw = msg.get("To", "")
        to_list = [addr.strip() for addr in to_raw.split(",")] if to_raw else []

        # Parse date
        date_str = msg.get("Date", "")
        received_at = None
        if date_str:
            try:
                dt_tuple = email.utils.parsedate_tz(date_str)
                if dt_tuple:
                    received_at = datetime.fromtimestamp(
                        email.utils.mktime_tz(dt_tuple), tz=UTC
                    )
            except Exception:
                pass

        # Extract text body
        body_text = None
        snippet = None
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body_text = payload.decode(charset, errors="replace")

        if body_text:
            snippet = body_text[:200].replace("\n", " ").strip()
        elif subject:
            snippet = subject

        # Check for calendar invite
        labels: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/calendar":
                    labels.append("calendar_invite")
                    break

        return EmailMessageDTO(
            provider_message_id=uid,
            provider_type="imap_smtp",
            subject=subject,
            from_address=from_addr,
            to_addresses=to_list,
            received_at=received_at,
            snippet=snippet,
            body_text=body_text,
            labels=labels,
            headers={
                "Message-ID": msg.get("Message-ID", ""),
                "In-Reply-To": msg.get("In-Reply-To", ""),
            },
        )
