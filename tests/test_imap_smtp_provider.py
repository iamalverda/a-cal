"""Tests for the IMAP/SMTP email provider.

Uses unittest.mock to mock IMAP and SMTP connections so tests run without
a real email server.
"""

from __future__ import annotations

import asyncio
import email
import email.utils
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from a_cal.providers.imap_smtp_provider import ImapSmtpProvider
from a_cal.providers.base import EmailMessageDTO, ProviderCapability


def _make_raw_email(
    subject: str = "Test Subject",
    from_addr: str = "sender@example.com",
    to_addr: str = "user@example.com",
    body: str = "Hello, this is a test email body.",
    msg_id: str = "<test123@example.com>",
) -> bytes:
    """Build a raw email message as bytes for IMAP mock responses."""
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = msg_id
    msg.set_content(body)
    return msg.as_bytes()


def _make_multipart_email(
    subject: str = "Meeting Invite",
    from_addr: str = "organizer@example.com",
    body: str = "Please join the meeting.",
    with_calendar: bool = False,
) -> bytes:
    """Build a multipart email (text + optional calendar attachment)."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = "user@example.com"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(body, "plain"))

    if with_calendar:
        from email.mime.base import MIMEBase
        cal_part = MIMEBase("text", "calendar")
        cal_part.set_payload("BEGIN:VCALENDAR\r\nEND:VCALENDAR")
        msg.attach(cal_part)

    return msg.as_bytes()


class TestImapSmtpProviderInit:
    """Tests for provider initialization and capabilities."""

    def test_init_defaults(self):
        """Provider initializes with default port and SSL settings."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )
        assert provider._imap_host == "imap.example.com"
        assert provider._smtp_host == "smtp.example.com"
        assert provider._username == "user@example.com"
        assert provider._imap_port == 993
        assert provider._smtp_port == 587
        assert provider._use_ssl_imap is True
        assert provider._use_starttls_smtp is True

    def test_capabilities(self):
        """Provider declares READ_MAIL and SEND_MAIL capabilities."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )
        assert ProviderCapability.READ_MAIL in provider.capabilities
        assert ProviderCapability.SEND_MAIL in provider.capabilities


class TestListMessages:
    """Tests for the list_messages method."""

    def test_list_messages_returns_dtos(self):
        """list_messages returns EmailMessageDTO objects from IMAP."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        raw_email = _make_raw_email(subject="Hello World", body="Test body content")

        mock_conn = MagicMock()
        mock_conn.uid.side_effect = [
            # First call: search ALL -> returns UIDs
            ("OK", [b"100 101 102 103"]),
            # Second call: fetch those UIDs -> returns messages
            ("OK", [
                (b"1 (UID 100 FLAGS (\\Seen))", raw_email),
                (b"2 (UID 101 FLAGS (\\Seen))", raw_email),
                (b"3 (UID 102 FLAGS (\\Seen))", raw_email),
            ]),
        ]

        with patch.object(provider, "_connect_imap", return_value=mock_conn):
            msgs, cursor = asyncio.run(provider.list_messages(None, limit=50))

        assert len(msgs) == 3
        assert all(isinstance(m, EmailMessageDTO) for m in msgs)
        assert msgs[0].subject == "Hello World"
        assert msgs[0].from_address == "sender@example.com"
        assert msgs[0].provider_type == "imap_smtp"
        assert cursor is not None

    def test_list_messages_empty_folder(self):
        """list_messages returns empty list for empty folder."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        mock_conn = MagicMock()
        mock_conn.uid.return_value = ("OK", [b""])

        with patch.object(provider, "_connect_imap", return_value=mock_conn):
            msgs, cursor = asyncio.run(provider.list_messages(None))

        assert msgs == []
        assert cursor is None

    def test_list_messages_with_cursor(self):
        """list_messages fetches messages with UID > cursor."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        raw_email = _make_raw_email(subject="New Message")

        mock_conn = MagicMock()
        mock_conn.uid.return_value = ("OK", [
            (b"1 (UID 104 FLAGS (\\Seen))", raw_email),
        ])

        with patch.object(provider, "_connect_imap", return_value=mock_conn):
            msgs, cursor = asyncio.run(provider.list_messages("103"))

        assert len(msgs) == 1
        assert cursor == "104"

    def test_list_messages_calendar_invite_detected(self):
        """list_messages flags calendar invite emails with a label."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        raw_email = _make_multipart_email(subject="Meeting", with_calendar=True)

        mock_conn = MagicMock()
        mock_conn.uid.side_effect = [
            ("OK", [b"200"]),
            ("OK", [(b"1 (UID 200 FLAGS (\\Seen))", raw_email)]),
        ]

        with patch.object(provider, "_connect_imap", return_value=mock_conn):
            msgs, _ = asyncio.run(provider.list_messages(None))

        assert len(msgs) == 1
        assert "calendar_invite" in msgs[0].labels

    def test_list_messages_snippet_extracted(self):
        """list_messages extracts a snippet from the email body."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        raw_email = _make_raw_email(body="This is a long body that should be truncated in the snippet.")

        mock_conn = MagicMock()
        mock_conn.uid.side_effect = [
            ("OK", [b"300"]),
            ("OK", [(b"1 (UID 300 FLAGS (\\Seen))", raw_email)]),
        ]

        with patch.object(provider, "_connect_imap", return_value=mock_conn):
            msgs, _ = asyncio.run(provider.list_messages(None))

        assert len(msgs) == 1
        assert msgs[0].snippet is not None
        assert "long body" in msgs[0].snippet


class TestSendMessage:
    """Tests for the send_message method."""

    def test_send_message_returns_message_id(self):
        """send_message returns a Message-ID string."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.__exit__.return_value = False
        with patch("a_cal.providers.imap_smtp_provider.smtplib.SMTP", return_value=mock_smtp):
            msg_id = asyncio.run(provider.send_message(
                to=["recipient@example.com"],
                subject="Test Send",
                body_text="Hello from A-Cal!",
            ))

        assert msg_id is not None
        assert "@" in msg_id or msg_id.startswith("<")
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "secret")
        mock_smtp.sendmail.assert_called_once()

    def test_send_message_no_starttls(self):
        """send_message works without STARTTLS when configured."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
            use_starttls_smtp=False,
        )

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.__exit__.return_value = False
        with patch("a_cal.providers.imap_smtp_provider.smtplib.SMTP", return_value=mock_smtp):
            msg_id = asyncio.run(provider.send_message(
                to=["recipient@example.com"],
                subject="No TLS",
                body_text="Plain SMTP",
            ))

        assert msg_id is not None
        mock_smtp.starttls.assert_not_called()

    def test_send_message_multiple_recipients(self):
        """send_message handles multiple recipients."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.__exit__.return_value = False
        with patch("a_cal.providers.imap_smtp_provider.smtplib.SMTP", return_value=mock_smtp):
            asyncio.run(provider.send_message(
                to=["one@example.com", "two@example.com", "three@example.com"],
                subject="Multi",
                body_text="Hello all",
            ))

        mock_smtp.sendmail.assert_called_once()
        sent_args = mock_smtp.sendmail.call_args
        assert "one@example.com" in sent_args[0][1]


class TestReply:
    """Tests for the reply method."""

    def test_reply_fetches_original_and_sends(self):
        """reply fetches the original message headers and sends a reply."""
        provider = ImapSmtpProvider(
            imap_host="imap.example.com",
            smtp_host="smtp.example.com",
            username="user@example.com",
            password="secret",
        )

        # Mock IMAP for fetching original message headers
        header_bytes = b"From: sender@example.com\r\nSubject: Original\r\nMessage-ID: <orig123@example.com>\r\n\r\n"
        mock_conn = MagicMock()
        mock_conn.uid.return_value = ("OK", [(b"1 (UID 500)", header_bytes)])

        # Mock SMTP for sending the reply
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        mock_smtp.__exit__.return_value = False

        with patch.object(provider, "_connect_imap", return_value=mock_conn), \
             patch("a_cal.providers.imap_smtp_provider.smtplib.SMTP", return_value=mock_smtp):
            msg_id = asyncio.run(provider.reply("500", "Thanks for the email!"))

        assert msg_id is not None
        mock_smtp.sendmail.assert_called_once()
        sent_args = mock_smtp.sendmail.call_args
        # The reply should go to the original sender
        assert "sender@example.com" in sent_args[0][1]


class TestMsgToDto:
    """Tests for the _msg_to_dto static method."""

    def test_basic_conversion(self):
        """_msg_to_dto extracts fields from a simple email."""
        raw = _make_raw_email(
            subject="Test",
            from_addr="test@example.com",
            body="Body text here",
        )
        msg = email.message_from_bytes(raw)
        dto = ImapSmtpProvider._msg_to_dto(msg, "123")

        assert dto.provider_message_id == "123"
        assert dto.provider_type == "imap_smtp"
        assert dto.subject == "Test"
        assert dto.from_address == "test@example.com"
        assert dto.body_text is not None
        assert "Body text" in dto.body_text

    def test_missing_date(self):
        """_msg_to_dto handles missing Date header gracefully."""
        raw = _make_raw_email()
        msg = email.message_from_bytes(raw)
        # Remove Date header
        del msg["Date"]
        dto = ImapSmtpProvider._msg_to_dto(msg, "456")
        assert dto.received_at is None


class TestProviderRegistration:
    """Test that the provider is properly registered."""

    def test_registered_as_imap_smtp(self):
        """The provider is registered under the 'imap_smtp' key."""
        from a_cal.providers.base import get_email_provider
        cls = get_email_provider("imap_smtp")
        assert cls is ImapSmtpProvider
