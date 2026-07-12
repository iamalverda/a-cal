"""Tests for the SQLite-backed persistent marketplace store."""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from a_cal.db.models import Base
from a_cal.marketplace.persistent_store import PersistentMarketplaceStore
from a_cal.marketplace.types import (
    InstallRecord,
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
)


@pytest.fixture
def store():
    """Create a persistent marketplace store with an in-memory SQLite DB."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return PersistentMarketplaceStore(session_factory=SessionLocal)


def test_seed_on_first_access(store):
    """Built-in items are seeded on first access."""
    items = store.list_items()
    assert len(items) >= 3
    names = [i.name for i in items]
    assert "Focus-First Scheduler" in names
    assert "Privacy-First Sync Rules" in names
    assert "Aggressive Negotiator" in names


def test_publish_and_retrieve(store):
    """A published item can be retrieved by ID."""
    item = MarketplaceItem(
        name="Test Plugin",
        item_type=MarketplaceItemType.PLUGIN_CONFIG.value,
        author="tester",
        description="A test plugin",
        provenance=Provenance(summary="test"),
        config={"key": "value"},
        tags=["test", "plugin"],
    )
    published = store.publish(item)

    retrieved = store.get_item(published.id)
    assert retrieved is not None
    assert retrieved.name == "Test Plugin"
    assert retrieved.author == "tester"
    assert retrieved.config == {"key": "value"}
    assert "test" in retrieved.tags


def test_install_increments_count(store):
    """Installing an item increments its install count."""
    items = store.list_items()
    first = items[0]
    original_count = first.install_count

    record = store.install(user_id="test-user", item_id=first.id)
    assert isinstance(record, InstallRecord)
    assert record.item_id == first.id
    assert record.user_id == "test-user"

    updated = store.get_item(first.id)
    assert updated.install_count == original_count + 1


def test_get_user_installs(store):
    """User installs are retrievable."""
    items = store.list_items()
    first = items[0]

    store.install(user_id="alice", item_id=first.id)
    store.install(user_id="alice", item_id=items[1].id)
    store.install(user_id="bob", item_id=first.id)

    alice_installs = store.get_user_installs("alice")
    assert len(alice_installs) == 2

    bob_installs = store.get_user_installs("bob")
    assert len(bob_installs) == 1


def test_remix_creates_child_with_parent_config(store):
    """Remixing copies parent config and applies overrides."""
    items = store.list_items()
    parent = items[0]

    child = store.remix(
        user_id="remixer",
        parent_item_id=parent.id,
        name="My Custom Version",
        description="Modified for my use case",
        config_overrides={"extra_key": "extra_value"},
        changes_summary="Added extra_key",
    )

    assert child.name == "My Custom Version"
    assert child.remixed_from == parent.id
    assert child.author == "remixer"
    assert "remix" in child.tags
    # Parent config should be preserved
    for key in parent.config:
        assert key in child.config
    # Override should be applied
    assert child.config.get("extra_key") == "extra_value"


def test_remix_chain_traces_ancestry(store):
    """Remix chain traces back through multiple levels."""
    items = store.list_items()
    parent = items[0]

    child = store.remix(
        user_id="user1",
        parent_item_id=parent.id,
        name="V2",
        description="v2",
        config_overrides={},
    )

    grandchild = store.remix(
        user_id="user2",
        parent_item_id=child.id,
        name="V3",
        description="v3",
        config_overrides={},
    )

    chain = store.get_remix_chain(grandchild.id)
    assert len(chain) == 2
    assert chain[0]["name"] == "V2"
    assert chain[1]["name"] == parent.name


def test_remixes_of_parent(store):
    """get_remixes_of returns all items remixed from a given item."""
    items = store.list_items()
    parent = items[0]

    store.remix("u1", parent.id, "R1", "d", {})
    store.remix("u2", parent.id, "R2", "d", {})

    remixes = store.get_remixes_of(parent.id)
    assert len(remixes) == 2
    names = [r.name for r in remixes]
    assert "R1" in names
    assert "R2" in names


def test_rate_item_updates_average(store):
    """Rating updates the rolling average."""
    items = store.list_items()
    item = items[0]

    store.rate_item(item.id, 4.0)
    store.rate_item(item.id, 5.0)

    updated = store.get_item(item.id)
    assert updated.rating_count == 2
    assert updated.rating == pytest.approx(4.5, abs=0.01)


def test_search_by_name(store):
    """Search finds items by name."""
    results = store.search("Focus")
    assert len(results) >= 1
    assert any("Focus" in r.name for r in results)


def test_search_by_tag(store):
    """Search finds items by tag."""
    results = store.search("privacy")
    assert len(results) >= 1
    assert any("privacy" in r.tags for r in results)


def test_list_items_filtered_by_type(store):
    """list_items filters by item_type."""
    agent_specs = store.list_items(item_type=MarketplaceItemType.AGENT_SPEC.value)
    assert len(agent_specs) >= 1
    assert all(i.item_type == MarketplaceItemType.AGENT_SPEC.value for i in agent_specs)


def test_persistence_across_sessions():
    """Items survive across store instances (simulating server restart)."""
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")

    # First session: publish an item
    from a_cal.db.models import create_engine_and_session
    engine, SessionLocal = create_engine_and_session(db_path)
    store1 = PersistentMarketplaceStore(session_factory=SessionLocal)
    item = MarketplaceItem(
        name="Persistent Test",
        item_type=MarketplaceItemType.AGENT_SPEC.value,
        author="persistence-test",
        description="Should survive restart",
        provenance=Provenance(summary="test"),
        config={"survives": True},
        tags=["persistence"],
    )
    store1.publish(item)

    # Second session: same DB, new store instance
    engine2, SessionLocal2 = create_engine_and_session(db_path)
    store2 = PersistentMarketplaceStore(session_factory=SessionLocal2)
    items = store2.list_items()
    found = [i for i in items if i.name == "Persistent Test"]
    assert len(found) == 1
    assert found[0].config == {"survives": True}
    assert found[0].author == "persistence-test"

    # Cleanup
    os.unlink(db_path)
