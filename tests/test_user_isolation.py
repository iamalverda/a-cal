"""Tests for multi-user data isolation.

Verifies that user_id filtering in the PersistentStore correctly isolates
data between different users. When user A is logged in, they cannot see
or modify user B's sub-accounts, events, settings, or self-model facts.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone, UTC

from a_cal.auth.session import set_current_user_id, reset_current_user_id
from a_cal.db.store import PersistentStore


@pytest.fixture
def store():
    """Fresh in-memory store for isolation tests."""
    return PersistentStore(in_memory=True)


@pytest.fixture
def user_a():
    """Set current user to user-a and reset after test."""
    token = set_current_user_id("user-a")
    yield "user-a"
    reset_current_user_id(token)


@pytest.fixture
def user_b():
    """Set current user to user-b and reset after test."""
    token = set_current_user_id("user-b")
    yield "user-b"
    reset_current_user_id(token)


class TestSubAccountIsolation:
    """Sub-accounts are isolated per user."""

    def test_user_only_sees_own_sub_accounts(self, store, user_a):
        """User A creates a sub-account; user B should not see it."""
        # User A creates a sub-account
        store.create_sub_account({"name": "A's Calendar", "kind": "calendar"})

        # Switch to user B
        token_b = set_current_user_id("user-b")
        try:
            store.create_sub_account({"name": "B's Calendar", "kind": "calendar"})
            subs = store.list_sub_accounts()
            titles = [s["name"] for s in subs]
            assert "B's Calendar" in titles
            assert "A's Calendar" not in titles
        finally:
            reset_current_user_id(token_b)

        # Back to user A
        subs = store.list_sub_accounts()
        titles = [s["name"] for s in subs]
        assert "A's Calendar" in titles
        assert "B's Calendar" not in titles

    def test_user_cannot_delete_others_sub_account(self, store, user_a):
        """User A creates a sub-account; user B cannot delete it."""
        sa = store.create_sub_account({"name": "A's Calendar", "kind": "calendar"})
        sa_id = sa["id"]

        token_b = set_current_user_id("user-b")
        try:
            result = store.delete_sub_account(sa_id)
            assert result is False
        finally:
            reset_current_user_id(token_b)

        # User A can still see it
        subs = store.list_sub_accounts()
        assert any(s["id"] == sa_id for s in subs)

    def test_user_cannot_update_others_sub_account(self, store, user_a):
        """User A creates a sub-account; user B cannot update it."""
        sa = store.create_sub_account({"name": "A's Calendar", "kind": "calendar"})
        sa_id = sa["id"]

        token_b = set_current_user_id("user-b")
        try:
            result = store.update_sub_account(sa_id, {"name": "Hacked!"})
            assert result is None
        finally:
            reset_current_user_id(token_b)

        # User A's sub-account name is unchanged
        subs = store.list_sub_accounts()
        target = [s for s in subs if s["id"] == sa_id][0]
        assert target["name"] == "A's Calendar"


class TestEventIsolation:
    """Calendar events are isolated per user."""

    def test_user_only_sees_own_events(self, store, user_a):
        """User A creates an event; user B should not see it in unified calendar."""
        now = datetime.now(UTC)
        store.create_event({
            "title": "A's Meeting",
            "start": now + timedelta(hours=2),
            "end": now + timedelta(hours=3),
        })

        token_b = set_current_user_id("user-b")
        try:
            store.create_event({
                "title": "B's Meeting",
                "start": now + timedelta(hours=2),
                "end": now + timedelta(hours=3),
            })
            events = store.get_unified_calendar(7)
            titles = [e["title"] for e in events]
            assert "B's Meeting" in titles
            assert "A's Meeting" not in titles
        finally:
            reset_current_user_id(token_b)

        events = store.get_unified_calendar(7)
        titles = [e["title"] for e in events]
        assert "A's Meeting" in titles
        assert "B's Meeting" not in titles

    def test_user_cannot_delete_others_event(self, store, user_a):
        """User A creates an event; user B cannot delete it."""
        now = datetime.now(UTC)
        evt = store.create_event({
            "title": "A's Meeting",
            "start": now + timedelta(hours=2),
            "end": now + timedelta(hours=3),
        })
        evt_id = evt["provider_event_id"]

        token_b = set_current_user_id("user-b")
        try:
            result = store.delete_event(evt_id)
            assert result is False
        finally:
            reset_current_user_id(token_b)

        # User A can still see the event
        events = store.get_all_events(30)
        assert any(e["provider_event_id"] == evt_id for e in events)

    def test_find_event_by_title_is_isolated(self, store, user_a):
        """find_event_by_title only searches the current user's events."""
        now = datetime.now(UTC)
        store.create_event({
            "title": "Unique Title Alpha",
            "start": now + timedelta(hours=2),
            "end": now + timedelta(hours=3),
        })

        token_b = set_current_user_id("user-b")
        try:
            result = store.find_event_by_title("Unique Title Alpha")
            assert result is None
        finally:
            reset_current_user_id(token_b)

        # User A can find it
        result = store.find_event_by_title("Unique Title Alpha")
        assert result is not None
        assert result["title"] == "Unique Title Alpha"


class TestSettingsIsolation:
    """Settings are isolated per user."""

    def test_user_only_sees_own_settings(self, store, user_a):
        """User A sets a setting; user B gets the default."""
        store.set_setting("test_key", "user_a_value")

        token_b = set_current_user_id("user-b")
        try:
            val = store.get_setting("test_key", "default")
            assert val == "default"
        finally:
            reset_current_user_id(token_b)

        val = store.get_setting("test_key", "default")
        assert val == "user_a_value"


class TestSelfModelFactIsolation:
    """Self-model facts are isolated per user."""

    def test_user_only_sees_own_facts(self, store, user_a):
        """User A adds a fact; user B should not see it."""
        store.add_self_model_fact({
            "category": "pattern",
            "content": "User A prefers morning meetings",
        })

        token_b = set_current_user_id("user-b")
        try:
            facts = store.list_self_model_facts()
            assert len(facts) == 0
        finally:
            reset_current_user_id(token_b)

        facts = store.list_self_model_facts()
        assert len(facts) == 1
        assert "User A" in facts[0]["content"]


class TestProviderIsolation:
    """Provider connections are isolated per user via their sub-account."""

    def _make_provider(self, store):
        sa = store.create_sub_account({"name": "A's Calendar", "kind": "calendar"})
        return store.create_provider({
            "sub_account_id": sa["id"],
            "provider_type": "google_calendar",
            "provider_account_id": "a@example.com",
        })

    def test_user_cannot_read_or_mutate_others_provider(self, store, user_a):
        """User B cannot get, delete, or update user A's provider by ID."""
        prov = self._make_provider(store)
        pid = prov["id"]

        token_b = set_current_user_id("user-b")
        try:
            assert store.get_provider(pid) is None
            assert store.delete_provider(pid) is False
            assert store.update_provider_status(pid, "connected") is None
            assert store.update_provider_config(pid, {"oauth_tokens": {"x": 1}}) is None
        finally:
            reset_current_user_id(token_b)

        # User A still owns an intact, non-deleted provider.
        still = store.get_provider(pid)
        assert still is not None
        assert still["status"] != "connected"
        assert "oauth_tokens" not in (still["config"] or {})

    def test_user_cannot_attach_provider_to_others_sub_account(self, store, user_a):
        """User B cannot create a provider on user A's sub-account."""
        sa = store.create_sub_account({"name": "A's Calendar", "kind": "calendar"})

        token_b = set_current_user_id("user-b")
        try:
            with pytest.raises(ValueError):
                store.create_provider({
                    "sub_account_id": sa["id"],
                    "provider_type": "google_calendar",
                    "provider_account_id": "hacker@example.com",
                })
        finally:
            reset_current_user_id(token_b)


class TestWebhookIsolation:
    """Webhooks and their deliveries are isolated per user."""

    def test_dispatch_lookup_scoped_to_owner(self, store, user_a):
        """list_active_webhooks_for_event only returns the named owner's hooks."""
        store.create_webhook({"url": "https://a.example/hook", "events": ["*"]})

        token_b = set_current_user_id("user-b")
        try:
            store.create_webhook({"url": "https://b.example/hook", "events": ["*"]})
            hooks_b = store.list_active_webhooks_for_event("booking.created", "user-b")
            assert [h["url"] for h in hooks_b] == ["https://b.example/hook"]
        finally:
            reset_current_user_id(token_b)

        hooks_a = store.list_active_webhooks_for_event("booking.created", "user-a")
        assert [h["url"] for h in hooks_a] == ["https://a.example/hook"]

    def test_user_cannot_read_others_webhook_deliveries(self, store, user_a):
        """User B cannot read user A's webhook delivery history."""
        hook = store.create_webhook({"url": "https://a.example/hook", "events": ["*"]})
        store.record_webhook_delivery({
            "webhook_id": hook["id"],
            "event_type": "booking.created",
            "status_code": 200,
        })

        token_b = set_current_user_id("user-b")
        try:
            assert store.list_webhook_deliveries(hook["id"]) == []
        finally:
            reset_current_user_id(token_b)

        assert len(store.list_webhook_deliveries(hook["id"])) == 1

    def test_secret_returned_on_create_but_omitted_from_list(self, store, user_a):
        """The signing secret is shown once at creation, never in list responses."""
        created = store.create_webhook({
            "url": "https://a.example/hook", "events": ["*"], "secret": "shh-secret",
        })
        assert created["secret"] == "shh-secret"

        listed = store.list_webhooks()
        assert "secret" not in listed[0]
        assert listed[0]["has_secret"] is True


class TestTeamMemberIsolation:
    """Team members can only be read/modified by the team's owner."""

    def test_user_cannot_list_or_modify_others_team_members(self, store, user_a):
        team = store.create_team({"name": "A Team", "slug": "a-team"})
        member = store.add_team_member({"team_id": team["id"], "email": "m@a.example"})

        token_b = set_current_user_id("user-b")
        try:
            assert store.list_team_members(team["id"]) == []
            assert store.update_team_member(member["id"], {"role": "admin"}) is None
            assert store.remove_team_member(member["id"]) is False
        finally:
            reset_current_user_id(token_b)

        members = store.list_team_members(team["id"])
        assert len(members) == 1
        assert members[0]["role"] == "member"


class TestEventTypeSlugUniqueness:
    """Public booking slugs are globally unique so bookings never misroute."""

    def test_duplicate_slug_is_suffixed_across_users(self, store, user_a):
        et_a = store.create_event_type({"title": "Intro Call", "slug": "intro"})
        assert et_a["slug"] == "intro"

        token_b = set_current_user_id("user-b")
        try:
            et_b = store.create_event_type({"title": "Intro Call", "slug": "intro"})
            assert et_b["slug"] == "intro-2"
        finally:
            reset_current_user_id(token_b)

        # Each public slug resolves deterministically to its true owner.
        assert store.get_event_type_by_slug("intro")["id"] == et_a["id"]
        assert store.get_event_type_by_slug("intro-2")["id"] == et_b["id"]
