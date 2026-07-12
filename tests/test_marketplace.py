"""Tests for the marketplace store — publish, install, remix, search, rate."""

from __future__ import annotations

import pytest

from a_cal.marketplace import (
    MarketplaceItem,
    MarketplaceItemType,
    MarketplaceStore,
    Provenance,
)


def _make_item(
    name: str = "Test Agent",
    item_type: str = MarketplaceItemType.AGENT_SPEC.value,
    author: str = "test-user",
    tags: list[str] | None = None,
) -> MarketplaceItem:
    return MarketplaceItem(
        name=name,
        item_type=item_type,
        author=author,
        description="A test marketplace item",
        provenance=Provenance(
            summary="Test summary",
            what_it_does="Does test things",
            gaps_and_limits="Can't do everything",
            integration_notes="Plugs into the test system",
        ),
        config={"key": "value"},
        tags=tags or ["test"],
    )


class TestPublish:
    def test_publish_item(self):
        store = MarketplaceStore()
        item = _make_item("My Agent")
        published = store.publish(item)
        assert published.id == item.id
        assert store.get_item(item.id) is item

    def test_get_nonexistent_returns_none(self):
        store = MarketplaceStore()
        assert store.get_item("nonexistent") is None


class TestSeed:
    def test_seeds_on_first_access(self):
        store = MarketplaceStore()
        items = store.list_items()
        assert len(items) >= 3  # seeded built-ins

    def test_seeds_only_once(self):
        store = MarketplaceStore()
        store.list_items()
        count_after_first = len(store.list_items())
        store.list_items()
        count_after_second = len(store.list_items())
        assert count_after_first == count_after_second

    def test_seeded_items_have_provenance(self):
        store = MarketplaceStore()
        items = store.list_items()
        for item in items:
            assert item.provenance.summary  # non-empty
            assert item.provenance.license  # non-empty


class TestInstall:
    def test_install_creates_record(self):
        store = MarketplaceStore()
        item = store.publish(_make_item())
        record = store.install("user-1", item.id)

        assert record.user_id == "user-1"
        assert record.item_id == item.id
        assert record.installed_config == item.config

    def test_install_increments_count(self):
        store = MarketplaceStore()
        item = store.publish(_make_item())
        store.install("user-1", item.id)
        store.install("user-2", item.id)

        updated = store.get_item(item.id)
        assert updated.install_count == 2

    def test_install_nonexistent_raises(self):
        store = MarketplaceStore()
        with pytest.raises(KeyError):
            store.install("user-1", "nonexistent")

    def test_get_user_installs(self):
        store = MarketplaceStore()
        item1 = store.publish(_make_item("Agent A"))
        item2 = store.publish(_make_item("Agent B"))

        store.install("user-1", item1.id)
        store.install("user-1", item2.id)
        store.install("user-2", item1.id)

        user1_installs = store.get_user_installs("user-1")
        assert len(user1_installs) == 2

        user2_installs = store.get_user_installs("user-2")
        assert len(user2_installs) == 1

    def test_installed_config_is_independent_of_marketplace(self):
        """Modifying the marketplace item after install doesn't affect the installed copy."""
        store = MarketplaceStore()
        item = store.publish(_make_item())
        record = store.install("user-1", item.id)

        # Modify the marketplace item
        item.config["new_key"] = "modified"

        # The installed config should be unchanged
        assert "new_key" not in record.installed_config


class TestRemix:
    def test_remix_creates_child_with_parent_config(self):
        store = MarketplaceStore()
        parent = store.publish(_make_item("Original"))
        child = store.remix(
            user_id="remixer",
            parent_item_id=parent.id,
            name="Remixed Version",
            description="My improved version",
            config_overrides={"new_key": "new_value"},
            changes_summary="Added new_key",
        )

        assert child.name == "Remixed Version"
        assert child.remixed_from == parent.id
        assert child.config["key"] == "value"  # inherited from parent
        assert child.config["new_key"] == "new_value"  # override applied
        assert "remix" in child.tags

    def test_remix_nonexistent_parent_raises(self):
        store = MarketplaceStore()
        with pytest.raises(KeyError):
            store.remix("user-1", "nonexistent", "Name", "Desc", {})

    def test_get_remixes_of(self):
        store = MarketplaceStore()
        parent = store.publish(_make_item("Original"))

        store.remix("user-1", parent.id, "Remix 1", "D1", {})
        store.remix("user-2", parent.id, "Remix 2", "D2", {})

        remixes = store.get_remixes_of(parent.id)
        assert len(remixes) == 2

    def test_remix_chain_traces_ancestry(self):
        store = MarketplaceStore()
        grandparent = store.publish(_make_item("V1"))
        parent = store.remix("user-1", grandparent.id, "V2", "D", {})
        child = store.remix("user-2", parent.id, "V3", "D", {})

        chain = store.get_remix_chain(child.id)
        assert len(chain) == 2
        assert chain[0]["name"] == "V2"
        assert chain[1]["name"] == "V1"


class TestSearch:
    def test_search_by_name(self):
        store = MarketplaceStore()
        my_item = store.publish(_make_item("Focus Scheduler"))
        store.publish(_make_item("Relax Scheduler"))

        results = store.search("Focus")
        # Seeded items may also match; verify our item is in results.
        names = [r.name for r in results]
        assert "Focus Scheduler" in names
        assert "Relax Scheduler" not in names

    def test_search_by_tag(self):
        store = MarketplaceStore()
        my_item = store.publish(_make_item("Agent 1", tags=["scheduling", "focus"]))
        store.publish(_make_item("Agent 2", tags=["privacy"]))

        results = store.search("scheduling")
        # Seeded items may also match; verify our item is in results.
        names = [r.name for r in results]
        assert "Agent 1" in names
        assert "Agent 2" not in names

    def test_search_no_results(self):
        store = MarketplaceStore()
        store.publish(_make_item("Agent"))
        results = store.search("nonexistent-term")
        assert len(results) == 0

    def test_search_finds_seeded_items(self):
        store = MarketplaceStore()
        results = store.search("focus")
        assert len(results) >= 1  # "Focus-First Scheduler" is seeded


class TestFiltering:
    def test_filter_by_type(self):
        store = MarketplaceStore()
        store.publish(_make_item("Agent", item_type=MarketplaceItemType.AGENT_SPEC.value))
        store.publish(_make_item("Theme", item_type=MarketplaceItemType.UI_THEME.value))

        agents = store.list_items(item_type=MarketplaceItemType.AGENT_SPEC.value)
        assert all(i.item_type == MarketplaceItemType.AGENT_SPEC.value for i in agents)

    def test_filter_by_tag(self):
        store = MarketplaceStore()
        store.publish(_make_item("Tagged", tags=["special"]))
        store.publish(_make_item("Untagged", tags=["other"]))

        results = store.list_items(tag="special")
        assert all("special" in i.tags for i in results)


class TestRating:
    def test_rate_item(self):
        store = MarketplaceStore()
        item = store.publish(_make_item())
        store.rate_item(item.id, 4.0)
        store.rate_item(item.id, 5.0)

        updated = store.get_item(item.id)
        assert updated.rating_count == 2
        assert updated.rating == pytest.approx(4.5)

    def test_rating_clamps_to_5(self):
        store = MarketplaceStore()
        item = store.publish(_make_item())
        store.rate_item(item.id, 10.0)  # clamped to 5
        updated = store.get_item(item.id)
        assert updated.rating == 5.0

    def test_rate_nonexistent_raises(self):
        store = MarketplaceStore()
        with pytest.raises(KeyError):
            store.rate_item("nonexistent", 3.0)

    def test_unrated_item_has_zero_rating(self):
        store = MarketplaceStore()
        item = store.publish(_make_item())
        assert item.rating == 0.0
        assert item.rating_count == 0
