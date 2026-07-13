"""End-to-end CalDAV integration tests against a real Radicale server.

These tests require a running Radicale instance (env-configurable via
A_CAL_TEST_RADICALE_HOST/PORT/USER/PASS, default 127.0.0.1:5233 no-auth). If Radicale is not running, the tests
skip gracefully.

Tests cover:
  - CalDAV provider construction (connects to Radicale, auto-creates calendar)
  - Event CRUD: create, list, update, delete
  - Sync engine integration: pull_window stamps provenance
  - Incremental sync (sync-token fallback to date search)
  - API endpoint integration: create provider via REST, sync, verify events
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from a_cal.providers.base import CalendarEventDTO, SyncPage, CalendarProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Radicale connection params are env-configurable so tests work against
# any local Radicale instance (different ports, auth or no-auth).
_RADICALE_HOST = os.environ.get("A_CAL_TEST_RADICALE_HOST", "127.0.0.1")
_RADICALE_PORT = int(os.environ.get("A_CAL_TEST_RADICALE_PORT", "5233"))
_RADICALE_USER = os.environ.get("A_CAL_TEST_RADICALE_USER", "testuser")
_RADICALE_PASS = os.environ.get("A_CAL_TEST_RADICALE_PASS", "testpass")


def _radicale_running() -> bool:
    """Check if a Radicale server is listening on the expected port."""
    try:
        with socket.create_connection((_RADICALE_HOST, _RADICALE_PORT), timeout=1):
            return True
    except (ConnectionRefusedError, OSError):
        return False


# Skip all tests in this module if Radicale isn't running.
pytestmark = pytest.mark.skipif(
    not _radicale_running(),
    reason=f"Radicale not running on {_RADICALE_HOST}:{_RADICALE_PORT} — "
           "start with `radicale -C /tmp/radicale-test/config`",
)


def _caldav_available() -> bool:
    """Check if the caldav package is installed."""
    try:
        import caldav  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# Also skip if caldav isn't installed.
if not _caldav_available():
    pytestmark = pytest.mark.skip(reason="caldav package not installed")


def _make_provider():
    """Create a CalDAVProvider connected to the test Radicale."""
    from a_cal.providers.caldav_provider import CalDAVProvider
    return CalDAVProvider(
        server_url=f"http://{_RADICALE_HOST}:{_RADICALE_PORT}",
        username=_RADICALE_USER or None,
        password=_RADICALE_PASS or None,
    )


def _make_event(uid: str, title: str, day: int = 15) -> CalendarEventDTO:
    """Create a test event DTO."""
    return CalendarEventDTO(
        provider_event_id=uid,
        provider_type="caldav",
        title=title,
        start=datetime(2026, 7, day, 10, 0),
        end=datetime(2026, 7, day, 11, 0),
        description=f"Test event: {title}",
        location="Test Location",
    )


# ---------------------------------------------------------------------------
# CalDAV provider CRUD tests
# ---------------------------------------------------------------------------

class TestCalDAVProviderCRUD:
    """Test create, read, update, delete against a real Radicale server."""

    def test_create_and_list_event(self):
        """Create an event and verify it appears in the list."""
        provider = _make_provider()
        ev = _make_event("crud-test-001", "CRUD Test Event")

        asyncio.run(provider.create_event(ev))

        events = asyncio.run(provider.list_events(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))
        found = [e for e in events if e.provider_event_id == "crud-test-001"]
        assert len(found) == 1
        assert found[0].title == "CRUD Test Event"

        # Cleanup
        asyncio.run(provider.cancel_event("crud-test-001"))

    def test_update_event(self):
        """Update an event and verify the change is reflected."""
        provider = _make_provider()
        ev = _make_event("crud-test-002", "Original Title")
        asyncio.run(provider.create_event(ev))

        ev.title = "Updated Title"
        asyncio.run(provider.update_event(ev))

        events = asyncio.run(provider.list_events(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))
        found = [e for e in events if e.provider_event_id == "crud-test-002"]
        assert len(found) == 1
        assert found[0].title == "Updated Title"

        asyncio.run(provider.cancel_event("crud-test-002"))

    def test_delete_event(self):
        """Delete an event and verify it's gone."""
        provider = _make_provider()
        ev = _make_event("crud-test-003", "Delete Me")
        asyncio.run(provider.create_event(ev))

        asyncio.run(provider.cancel_event("crud-test-003"))

        events = asyncio.run(provider.list_events(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))
        assert not any(e.provider_event_id == "crud-test-003" for e in events)

    def test_multiple_events(self):
        """Create multiple events and verify all are listed."""
        provider = _make_provider()
        uids = [f"multi-test-{i:03d}" for i in range(3)]
        for i, uid in enumerate(uids):
            ev = _make_event(uid, f"Multi Test {i}", day=20 + i)
            asyncio.run(provider.create_event(ev))

        events = asyncio.run(provider.list_events(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))
        found_uids = {e.provider_event_id for e in events}
        for uid in uids:
            assert uid in found_uids, f"{uid} not found in events"

        for uid in uids:
            asyncio.run(provider.cancel_event(uid))


# ---------------------------------------------------------------------------
# Sync engine integration tests
# ---------------------------------------------------------------------------

class TestCalDAVSyncEngine:
    """Test the sync engine with a real CalDAV provider."""

    def test_pull_window_stamps_provenance(self):
        """Sync engine should stamp events with sub-account provenance."""
        from a_cal.sync.engine import SubAccountSyncEngine

        provider = _make_provider()
        ev = _make_event("sync-prov-001", "Sync Provenance Test")
        asyncio.run(provider.create_event(ev))

        sub_account = {
            "id": "sa-caldav-sync-test",
            "name": "CalDAV Sync Test",
            "sync_mode": "mirror_filter",
            "sync_rules": [],
        }
        engine = SubAccountSyncEngine(sub_account, [provider])
        events = asyncio.run(engine.pull_window(
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))

        assert len(events) >= 1
        synced = [e for e in events if e.provider_event_id == "sync-prov-001"]
        assert len(synced) == 1
        assert synced[0].source_sub_account_id == "sa-caldav-sync-test"

        asyncio.run(provider.cancel_event("sync-prov-001"))

    def test_incremental_sync(self):
        """list_changes should return events (sync-token or date fallback)."""
        provider = _make_provider()
        ev = _make_event("sync-inc-001", "Incremental Sync Test")
        asyncio.run(provider.create_event(ev))

        page = asyncio.run(provider.list_changes(
            since_cursor=None,
            start=datetime(2026, 7, 1),
            end=datetime(2026, 7, 31),
        ))
        assert isinstance(page, SyncPage)
        assert len(page.events) >= 1
        assert any(e.provider_event_id == "sync-inc-001" for e in page.events)

        asyncio.run(provider.cancel_event("sync-inc-001"))


# ---------------------------------------------------------------------------
# API integration test
# ---------------------------------------------------------------------------

class TestCalDAVAPIIntegration:
    """Test creating a CalDAV provider via the REST API and syncing."""

    def test_create_caldav_provider_via_api(self):
        """Create a CalDAV provider via API, verify it persists."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from a_cal.api.standalone_data import router as data_router

        app = FastAPI()
        app.include_router(data_router)
        client = TestClient(app)

        existing = {p["id"] for p in client.get("/api/a-cal/providers/all").json()}

        # Create a sub-account first
        sub_resp = client.post("/api/a-cal/sub-accounts", json={
            "name": "CalDAV API Test",
            "kind": "calendar",
        })
        sub_id = sub_resp.json()["id"]

        # Create a CalDAV provider
        resp = client.post("/api/a-cal/providers", json={
            "sub_account_id": sub_id,
            "provider_type": "caldav",
            "provider_account_id": "testuser@radicale",
            "config": {
                "server_url": f"http://{_RADICALE_HOST}:{_RADICALE_PORT}",
                "username": _RADICALE_USER,
                "password": _RADICALE_PASS,
            },
        })
        assert resp.status_code == 200
        prov = resp.json()
        assert prov["provider_type"] == "caldav"
        assert prov["status"] == "pending"

        # Verify it appears in the list
        all_provs = client.get("/api/a-cal/providers/all").json()
        assert any(p["id"] == prov["id"] for p in all_provs)

        # Cleanup
        client.delete(f"/api/a-cal/providers/{prov['id']}")
        client.delete(f"/api/a-cal/sub-accounts/{sub_id}")
