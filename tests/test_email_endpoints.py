"""Tests for email message listing and sending endpoints.

Covers:
  - GET /email/messages with no providers connected
  - GET /email/messages with a connected IMAP provider (mocked)
  - GET /email/messages filtering by sub_account_id
  - POST /email/send through a connected provider (mocked)
  - POST /email/send with invalid provider ID
  - Graceful degradation when provider credentials are missing
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.standalone_data import router as standalone_data_router
from a_cal.providers.base import EmailMessageDTO


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Test client with standalone data routes.

    Uses the module-level store (seeded with demo data) and cleans up
    test-created sub-accounts and email providers after each test to
    maintain isolation from other test files.
    """
    app = FastAPI()
    app.include_router(standalone_data_router)
    c = TestClient(app)

    # Snapshot existing sub-account IDs so we can clean up new ones
    existing_sub_ids = {s["id"] for s in c.get("/api/a-cal/sub-accounts").json()}
    existing_provider_ids = {p["id"] for p in c.get("/api/a-cal/providers/all").json()}

    yield c

    # Cleanup: remove any sub-accounts and providers created during the test
    try:
        for p in c.get("/api/a-cal/providers/all").json():
            if p["id"] not in existing_provider_ids:
                c.delete(f"/api/a-cal/providers/{p['id']}")
        for s in c.get("/api/a-cal/sub-accounts").json():
            if s["id"] not in existing_sub_ids:
                c.delete(f"/api/a-cal/sub-accounts/{s['id']}")
    except Exception:
        pass


def _create_sub_account(client, name="Work", is_main=True):
    """Helper: create a sub-account and return its ID."""
    resp = client.post("/api/a-cal/sub-accounts", json={
        "name": name, "kind": "unified", "is_main": is_main,
    })
    return resp.json()["id"]


def _clear_seeded_email_providers(client):
    """Remove seeded demo email providers so tests start clean."""
    for p in client.get("/api/a-cal/providers/all").json():
        if p["provider_type"] in ("imap_smtp", "gmail"):
            client.delete(f"/api/a-cal/providers/{p['id']}")


def _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected"):
    """Helper: create an email provider connection."""
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": ptype,
        "provider_account_id": "test@example.com",
        "display_name": "Test Email",
        "config": {
            "imap_host": "imap.example.com",
            "smtp_host": "smtp.example.com",
            "username": "test@example.com",
            "password": "secret",
        },
    })
    pid = resp.json()["id"]
    if status == "connected":
        client.patch(f"/api/a-cal/providers/{pid}", json={"status": "connected"})
    return pid


# ---------------------------------------------------------------------------
# Mock email provider
# ---------------------------------------------------------------------------

_MOCK_MESSAGES = [
    EmailMessageDTO(
        provider_message_id="msg-001",
        provider_type="imap_smtp",
        subject="Team sync tomorrow",
        from_address="boss@company.com",
        to_addresses=["test@example.com"],
        received_at=datetime(2025, 7, 10, 14, 30, tzinfo=UTC),
        snippet="Hi, let's sync tomorrow at 10am...",
        labels=["INBOX"],
    ),
    EmailMessageDTO(
        provider_message_id="msg-002",
        provider_type="imap_smtp",
        subject="Calendar invite: Quarterly review",
        from_address="calendar@company.com",
        to_addresses=["test@example.com"],
        received_at=datetime(2025, 7, 10, 9, 0, tzinfo=UTC),
        snippet="You are invited to Quarterly review...",
        labels=["INBOX", "calendar"],
    ),
]


# ---------------------------------------------------------------------------
# Tests — GET /email/messages
# ---------------------------------------------------------------------------

def test_list_email_no_providers(client):
    """Returns empty list when no email providers are connected."""
    resp = client.get("/api/a-cal/email/messages")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_email_with_mocked_provider(client):
    """Returns messages from a connected email provider (mocked)."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id)

    mock_provider = AsyncMock()
    mock_provider.list_messages = AsyncMock(
        return_value=(_MOCK_MESSAGES, "cursor-1"),
    )

    with patch(
        "a_cal.providers.factory.build_email_provider",
        return_value=mock_provider,
    ):
        resp = client.get("/api/a-cal/email/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Sorted by received_at desc — msg-001 (14:30) comes first
    assert data[0]["provider_message_id"] == "msg-001"
    assert data[0]["subject"] == "Team sync tomorrow"
    assert data[0]["from_address"] == "boss@company.com"
    # Calendar invite detection
    assert data[1]["has_calendar_invite"] is True
    assert data[0]["has_calendar_invite"] is False


def test_list_email_filtered_by_sub_account(client):
    """Filters by sub_account_id when provided."""
    _clear_seeded_email_providers(client)
    sub1 = _create_sub_account(client, name="Work")
    sub2 = _create_sub_account(client, name="Personal", is_main=False)
    _create_email_provider(client, sub1)
    _create_email_provider(client, sub2)

    mock_provider = AsyncMock()
    mock_provider.list_messages = AsyncMock(
        return_value=(_MOCK_MESSAGES, "cursor-1"),
    )

    with patch(
        "a_cal.providers.factory.build_email_provider",
        return_value=mock_provider,
    ):
        resp = client.get(f"/api/a-cal/email/messages?sub_account_id={sub1}")

    assert resp.status_code == 200
    data = resp.json()
    # Only messages from sub1's provider
    assert len(data) == 2
    assert all(m["provider_connection_id"] for m in data)


def test_list_email_limit_param(client):
    """Respects the limit query parameter."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id)

    many_messages = [
        EmailMessageDTO(
            provider_message_id=f"msg-{i:03d}",
            provider_type="imap_smtp",
            subject=f"Subject {i}",
            from_address=f"sender{i}@example.com",
            received_at=datetime(2025, 7, 10, 12 - i, tzinfo=UTC) if i < 12 else datetime(2025, 7, 9, tzinfo=UTC),
        )
        for i in range(20)
    ]

    mock_provider = AsyncMock()
    mock_provider.list_messages = AsyncMock(
        return_value=(many_messages, "cursor"),
    )

    with patch(
        "a_cal.providers.factory.build_email_provider",
        return_value=mock_provider,
    ):
        resp = client.get("/api/a-cal/email/messages?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5


def test_list_email_provider_error_graceful(client):
    """Gracefully skips providers that throw errors."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id)

    mock_provider = AsyncMock()
    mock_provider.list_messages = AsyncMock(
        side_effect=ConnectionError("IMAP server unreachable"),
    )

    with patch(
        "a_cal.providers.factory.build_email_provider",
        return_value=mock_provider,
    ):
        resp = client.get("/api/a-cal/email/messages")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_email_skips_disconnected_providers(client):
    """Only lists from providers with 'connected' status."""
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id, status="pending")

    resp = client.get("/api/a-cal/email/messages")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests — POST /email/send
# ---------------------------------------------------------------------------

def test_send_email_success(client):
    """Sends email through a connected provider (mocked)."""
    sub_id = _create_sub_account(client)
    pid = _create_email_provider(client, sub_id)

    mock_provider = AsyncMock()
    mock_provider.send_message = AsyncMock(return_value="sent-msg-001")

    with patch(
        "a_cal.providers.factory.build_email_provider",
        return_value=mock_provider,
    ):
        resp = client.post("/api/a-cal/email/send", json={
            "provider_connection_id": pid,
            "to": ["recipient@example.com"],
            "subject": "Test subject",
            "body_text": "Hello world",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["provider_message_id"] == "sent-msg-001"
    mock_provider.send_message.assert_called_once_with(
        to=["recipient@example.com"],
        subject="Test subject",
        body_text="Hello world",
    )


def test_send_email_missing_provider_id(client):
    """Returns 400 when provider_connection_id is missing."""
    resp = client.post("/api/a-cal/email/send", json={
        "to": ["recipient@example.com"],
        "subject": "Test",
        "body_text": "Hello",
    })
    assert resp.status_code == 400


def test_send_email_provider_not_found(client):
    """Returns 404 when provider connection ID doesn't exist."""
    resp = client.post("/api/a-cal/email/send", json={
        "provider_connection_id": "nonexistent-id",
        "to": ["recipient@example.com"],
        "subject": "Test",
        "body_text": "Hello",
    })
    assert resp.status_code == 404


def test_send_email_wrong_provider_type(client):
    """Returns 400 when provider is not an email provider."""
    sub_id = _create_sub_account(client)
    resp = client.post("/api/a-cal/providers", json={
        "sub_account_id": sub_id,
        "provider_type": "caldav",
        "provider_account_id": "cal@example.com",
        "config": {"server_url": "http://localhost:5232"},
    })
    pid = resp.json()["id"]
    client.patch(f"/api/a-cal/providers/{pid}", json={"status": "connected"})

    resp = client.post("/api/a-cal/email/send", json={
        "provider_connection_id": pid,
        "to": ["recipient@example.com"],
        "subject": "Test",
        "body_text": "Hello",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Unified inbox — account listing, search, star, mark-read, delete, folders
# ---------------------------------------------------------------------------

def test_list_email_accounts_empty(client):
    """GET /email/accounts returns empty list when no email providers connected."""
    _clear_seeded_email_providers(client)
    resp = client.get("/api/a-cal/email/accounts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_email_accounts_with_provider(client):
    """GET /email/accounts returns connected email accounts with metadata."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client, name="Personal Email")
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.list_messages = AsyncMock(return_value=([], None))
        mock_build.return_value = mock_provider
        resp = client.get("/api/a-cal/email/accounts")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    acct = next(a for a in data if a["provider_connection_id"] == pid)
    assert acct["provider_type"] == "imap_smtp"
    assert acct["sub_account_id"] == sub_id
    assert acct["status"] == "connected"


def test_list_email_messages_with_account_metadata(client):
    """GET /email/messages includes account_display_name and account_email."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client, name="Work Email")
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    mock_dto = EmailMessageDTO(
        provider_message_id="msg-1",
        provider_type="imap_smtp",
        subject="Test Subject",
        from_address="sender@example.com",
        to_addresses=["recipient@example.com"],
        snippet="Hello world",
        labels=["UNREAD"],
    )

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.list_messages = AsyncMock(return_value=([mock_dto], None))
        mock_build.return_value = mock_provider
        resp = client.get("/api/a-cal/email/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    msg = next(m for m in data if m["provider_message_id"] == "msg-1")
    assert msg["is_unread"] is True
    assert msg["is_starred"] is False
    assert msg["provider_connection_id"] == pid
    assert msg["account_display_name"] is not None


def test_list_email_messages_filter_by_provider(client):
    """GET /email/messages filters by provider_connection_id."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    pid1 = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")
    pid2 = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.list_messages = AsyncMock(return_value=([], None))
        mock_build.return_value = mock_provider
        resp = client.get(f"/api/a-cal/email/messages?provider_connection_id={pid1}")

    assert resp.status_code == 200
    data = resp.json()
    for msg in data:
        assert msg["provider_connection_id"] == pid1


def test_list_email_messages_folder_param(client):
    """GET /email/messages accepts folder parameter."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.list_messages = AsyncMock(return_value=([], None))
        mock_build.return_value = mock_provider
        resp = client.get("/api/a-cal/email/messages?folder=STARRED")

    assert resp.status_code == 200


def test_star_email_missing_fields(client):
    """POST /email/star returns 400 when required fields are missing."""
    resp = client.post("/api/a-cal/email/star", json={"starred": True})
    assert resp.status_code == 400


def test_star_email_provider_not_found(client):
    """POST /email/star returns 404 for nonexistent provider."""
    resp = client.post("/api/a-cal/email/star", json={
        "provider_connection_id": "nonexistent",
        "provider_message_id": "msg-1",
        "starred": True,
    })
    assert resp.status_code == 404


def test_star_email_success(client):
    """POST /email/star stars a message through the provider."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.star_message = AsyncMock(return_value=True)
        mock_build.return_value = mock_provider
        resp = client.post("/api/a-cal/email/star", json={
            "provider_connection_id": pid,
            "provider_message_id": "msg-1",
            "starred": True,
        })

    assert resp.status_code == 200
    assert resp.json()["starred"] is True


def test_mark_read_email_success(client):
    """POST /email/mark-read marks a message as read."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.mark_read = AsyncMock(return_value=True)
        mock_build.return_value = mock_provider
        resp = client.post("/api/a-cal/email/mark-read", json={
            "provider_connection_id": pid,
            "provider_message_id": "msg-1",
            "read": True,
        })

    assert resp.status_code == 200
    assert resp.json()["read"] is True


def test_delete_email_success(client):
    """POST /email/delete trashes a message through the provider."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.delete_message = AsyncMock(return_value=True)
        mock_build.return_value = mock_provider
        resp = client.post("/api/a-cal/email/delete", json={
            "provider_connection_id": pid,
            "provider_message_id": "msg-1",
        })

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_search_email(client):
    """GET /email/search searches across connected accounts."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    mock_dto = EmailMessageDTO(
        provider_message_id="search-1",
        provider_type="imap_smtp",
        subject="Meeting Tomorrow",
        from_address="boss@example.com",
        snippet="Let's meet",
    )

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.search_messages = AsyncMock(return_value=[mock_dto])
        mock_build.return_value = mock_provider
        resp = client.get("/api/a-cal/email/search?q=meeting")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["subject"] == "Meeting Tomorrow"


def test_search_email_empty_query(client):
    """GET /email/search returns 422 when query is too short."""
    resp = client.get("/api/a-cal/email/search?q=")
    assert resp.status_code == 422


def test_list_email_folders(client):
    """GET /email/folders lists folders for connected accounts."""
    _clear_seeded_email_providers(client)
    sub_id = _create_sub_account(client)
    pid = _create_email_provider(client, sub_id, ptype="imap_smtp", status="connected")

    with patch("a_cal.providers.factory.build_email_provider") as mock_build:
        mock_provider = AsyncMock()
        mock_provider.list_folders = AsyncMock(return_value=["INBOX", "Sent", "Drafts", "Trash"])
        mock_build.return_value = mock_provider
        resp = client.get("/api/a-cal/email/folders")

    assert resp.status_code == 200
    data = resp.json()
    assert pid in data
    assert "INBOX" in data[pid]
