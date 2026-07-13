"""Tests for the marketplace trust and moderation system.

Verifies content integrity hashing, flagging, trust score computation,
and verification status management.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from a_cal.api.standalone import app
from a_cal.marketplace.store import MarketplaceStore
from a_cal.marketplace.trust import (
    FlagRecord,
    VerificationStatus,
    compute_content_hash,
    compute_trust_score,
)
from a_cal.marketplace.types import MarketplaceItem, MarketplaceItemType, Provenance


client = TestClient(app)


class TestContentHash:
    """Content integrity hash tests."""

    def test_hash_is_deterministic(self):
        """Same config produces the same hash."""
        config = {"name": "test", "rules": ["a", "b"]}
        h1 = compute_content_hash(config)
        h2 = compute_content_hash(config)
        assert h1 == h2

    def test_different_configs_different_hash(self):
        """Different configs produce different hashes."""
        h1 = compute_content_hash({"name": "a"})
        h2 = compute_content_hash({"name": "b"})
        assert h1 != h2

    def test_key_order_irrelevant(self):
        """Hash is the same regardless of key insertion order."""
        h1 = compute_content_hash({"a": 1, "b": 2})
        h2 = compute_content_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_hash_length(self):
        """Hash is 16 characters (truncated SHA-256)."""
        h = compute_content_hash({"test": True})
        assert len(h) == 16

    def test_compute_hash_on_item(self):
        """MarketplaceItem.compute_hash sets the content_hash field."""
        item = MarketplaceItem(name="test", config={"key": "value"})
        h = item.compute_hash()
        assert item.content_hash == h
        assert len(h) == 16


class TestTrustScore:
    """Trust score computation tests."""

    def test_unverified_unrated_item(self):
        """New items start with a base trust score."""
        score = compute_trust_score(
            rating=0, rating_count=0, install_count=0,
            flag_count=0, verification_status="unverified",
        )
        assert 0 < score < 30

    def test_high_rating_boosts_score(self):
        """High rating with many reviews increases trust."""
        score_low = compute_trust_score(
            rating=2.0, rating_count=10, install_count=0,
            flag_count=0, verification_status="unverified",
        )
        score_high = compute_trust_score(
            rating=5.0, rating_count=10, install_count=0,
            flag_count=0, verification_status="unverified",
        )
        assert score_high > score_low

    def test_verification_boosts_score(self):
        """Verified items have higher trust than unverified."""
        score_unverified = compute_trust_score(
            rating=4.0, rating_count=5, install_count=10,
            flag_count=0, verification_status="unverified",
        )
        score_verified = compute_trust_score(
            rating=4.0, rating_count=5, install_count=10,
            flag_count=0, verification_status="author_verified",
        )
        assert score_verified > score_unverified

    def test_flags_reduce_score(self):
        """Flags reduce the trust score."""
        score_clean = compute_trust_score(
            rating=4.0, rating_count=5, install_count=10,
            flag_count=0, verification_status="unverified",
        )
        score_flagged = compute_trust_score(
            rating=4.0, rating_count=5, install_count=10,
            flag_count=2, verification_status="unverified",
        )
        assert score_flagged < score_clean

    def test_score_clamped_to_100(self):
        """Trust score never exceeds 100."""
        score = compute_trust_score(
            rating=5.0, rating_count=100, install_count=10000,
            flag_count=0, verification_status="community_verified",
            author_item_count=50,
        )
        assert score <= 100.0

    def test_score_never_negative(self):
        """Trust score never goes below 0."""
        score = compute_trust_score(
            rating=1.0, rating_count=1, install_count=0,
            flag_count=10, verification_status="flagged",
        )
        assert score >= 0.0


class TestInMemoryFlagging:
    """Flagging tests on the in-memory store."""

    def test_flag_item_increments_count(self):
        """Flagging an item increments its flag count."""
        store = MarketplaceStore()
        items = store.list_items()
        item = items[0]
        assert item.flag_count == 0

        flag = store.flag_item(item.id, "user1", "spam", "looks spammy")
        assert flag is not None
        assert item.flag_count == 1

    def test_flag_nonexistent_item_returns_none(self):
        """Flagging a non-existent item returns None."""
        store = MarketplaceStore()
        flag = store.flag_item("nonexistent", "user1", "spam")
        assert flag is None

    def test_three_flags_marks_flagged(self):
        """Three unresolved flags auto-marks item as flagged."""
        store = MarketplaceStore()
        items = store.list_items()
        item = items[0]

        for i in range(3):
            store.flag_item(item.id, f"user{i}", "spam", f"flag {i}")

        assert item.flag_count == 3
        assert item.verification_status == VerificationStatus.FLAGGED.value

    def test_resolve_flag_decrements_count(self):
        """Resolving a flag decrements the unresolved count."""
        store = MarketplaceStore()
        items = store.list_items()
        item = items[0]

        flag = store.flag_item(item.id, "user1", "spam", "test")
        assert item.flag_count == 1

        resolved = store.resolve_flag(flag.id, "dismissed")
        assert resolved is not None
        assert resolved.resolved is True
        assert item.flag_count == 0

    def test_verify_item_sets_status(self):
        """Verifying an item updates its verification status."""
        store = MarketplaceStore()
        items = store.list_items()
        item = items[0]

        verified = store.verify_item(item.id, "author_verified")
        assert verified is not None
        assert verified.verification_status == "author_verified"

    def test_verify_nonexistent_returns_none(self):
        """Verifying a non-existent item returns None."""
        store = MarketplaceStore()
        result = store.verify_item("nonexistent", "author_verified")
        assert result is None

    def test_get_flags_returns_item_flags(self):
        """get_flags returns all flags for an item."""
        store = MarketplaceStore()
        items = store.list_items()
        item = items[0]

        store.flag_item(item.id, "user1", "spam")
        store.flag_item(item.id, "user2", "broken")

        flags = store.get_flags(item.id)
        assert len(flags) == 2


class TestTrustAPI:
    """API endpoint tests for trust and moderation."""

    def test_get_trust_info(self):
        """GET /items/{id}/trust returns trust metadata."""
        r = client.get("/api/a-cal/marketplace/items")
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0

        item_id = items[0]["id"]
        r = client.get(f"/api/a-cal/marketplace/items/{item_id}/trust")
        assert r.status_code == 200
        data = r.json()
        assert "trust_score" in data
        assert "verification_status" in data
        assert "flag_count" in data
        assert "content_hash" in data

    def test_flag_item_via_api(self):
        """POST /items/{id}/flag creates a flag."""
        r = client.get("/api/a-cal/marketplace/items")
        items = r.json()
        item_id = items[0]["id"]

        r = client.post(
            f"/api/a-cal/marketplace/items/{item_id}/flag",
            json={"reason": "spam", "detail": "test flag"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reason"] == "spam"
        assert data["item_id"] == item_id

    def test_flag_nonexistent_item_404(self):
        """Flagging a non-existent item returns 404."""
        r = client.post(
            "/api/a-cal/marketplace/items/nonexistent/flag",
            json={"reason": "spam"},
        )
        assert r.status_code == 404

    def test_verify_item_via_api(self):
        """POST /items/{id}/verify sets verification status."""
        r = client.get("/api/a-cal/marketplace/items")
        items = r.json()
        item_id = items[0]["id"]

        r = client.post(
            f"/api/a-cal/marketplace/items/{item_id}/verify",
            json={"status": "author_verified"},
        )
        assert r.status_code == 200
        assert r.json()["verification_status"] == "author_verified"

    def test_trust_info_404_for_nonexistent(self):
        """GET /items/{id}/trust returns 404 for non-existent item."""
        r = client.get("/api/a-cal/marketplace/items/nonexistent/trust")
        assert r.status_code == 404

    def test_published_item_has_content_hash(self):
        """Published items have a non-empty content hash."""
        r = client.post(
            "/api/a-cal/marketplace/items",
            json={
                "name": "Trust Test Item",
                "item_type": "agent_spec",
                "author": "test@example.com",
                "description": "Test item for trust verification",
                "config": {"test": "config"},
                "tags": ["test"],
            },
        )
        assert r.status_code == 200
        item = r.json()
        assert item.get("content_hash", "") != ""

    def test_marketplace_item_includes_trust_score(self):
        """Listed items include trust_score in their response."""
        r = client.get("/api/a-cal/marketplace/items")
        items = r.json()
        for item in items:
            assert "trust_score" in item
            assert "verification_status" in item
            assert "flag_count" in item


class TestRemixHash:
    """Verify that remixed items also get content hashes (bug fix)."""

    def test_in_memory_remix_has_hash(self):
        """Remixed items in the in-memory store get a content hash."""
        from a_cal.marketplace.store import MarketplaceStore
        store = MarketplaceStore()
        # Publish a parent item
        parent = store.publish(MarketplaceItem(
            name="Parent Item",
            item_type=MarketplaceItemType.AGENT_SPEC.value,
            author="test@example.com",
            description="Parent for remix test",
            provenance=Provenance(
                summary="Parent",
                what_it_does="Does things",
                gaps_and_limits="None",
                integration_notes="None",
                version="1.0.0",
            ),
            config={"key": "value"},
            tags=["test"],
        ))
        assert parent.content_hash != ""

        # Remix it
        child = store.remix(
            user_id="test@example.com",
            parent_item_id=parent.id,
            name="Remixed Child",
            description="A remix of the parent",
            config_overrides={"key": "overridden"},
        )
        assert child.content_hash != ""
        assert child.content_hash != parent.content_hash  # different config = different hash

    def test_api_remix_has_hash(self):
        """Remixed items via the API include a non-empty content_hash."""
        # Publish a parent
        r1 = client.post(
            "/api/a-cal/marketplace/items",
            json={
                "name": "API Remix Parent",
                "item_type": "agent_spec",
                "author": "test@example.com",
                "description": "Parent for API remix test",
                "config": {"strategy": "aggressive"},
                "tags": ["test", "remix-parent"],
            },
        )
        assert r1.status_code == 200
        parent = r1.json()
        parent_id = parent["id"]

        # Remix it
        r2 = client.post(
            f"/api/a-cal/marketplace/items/{parent_id}/remix",
            json={
                "name": "API Remix Child",
                "description": "A remix via the API",
                "config_overrides": {"strategy": "conservative"},
            },
        )
        assert r2.status_code == 200
        child = r2.json()
        assert child.get("content_hash", "") != ""
        assert child["content_hash"] != parent["content_hash"]
