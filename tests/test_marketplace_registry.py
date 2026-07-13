"""Tests for the marketplace registry — export/import bundles, manifests,
and remote registry browsing.

These tests verify that marketplace items can be exported as portable JSON
bundles, imported into another store, and that the registry manifest format
works correctly for browsing. Remote registry fetching is tested with mock
HTTP responses since we don't have a live registry server.
"""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from a_cal.marketplace.types import (
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
)
from a_cal.marketplace.store import MarketplaceStore
from a_cal.marketplace.registry import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    REGISTRY_FORMAT,
    REGISTRY_VERSION,
    RegistryBundle,
    RegistryManifest,
    RegistryClient,
    build_manifest_from_store,
)


# --- helpers ----------------------------------------------------------------

def _make_item(name: str = "Test Agent", item_id: str = None) -> MarketplaceItem:
    """Create a test marketplace item."""
    return MarketplaceItem(
        id=item_id or "test-id-1",
        name=name,
        item_type=MarketplaceItemType.AGENT_SPEC.value,
        author="test-user",
        description="A test agent spec for unit testing.",
        provenance=Provenance(
            summary="Test agent",
            what_it_does="Does test things",
            gaps_and_limits="Only for testing",
            integration_notes="No integration needed",
        ),
        config={"system_prompt": "You are a test agent."},
        tags=["test", "agent"],
    )


# --- RegistryBundle tests ---------------------------------------------------

class TestRegistryBundle:
    """Tests for the portable bundle format."""

    def test_create_bundle(self):
        """A bundle wraps a list of items with metadata."""
        items = [_make_item("Agent A"), _make_item("Agent B")]
        bundle = RegistryBundle(items=items, exported_by="user-1")
        assert len(bundle.items) == 2
        assert bundle.exported_by == "user-1"
        assert bundle.exported_at  # ISO timestamp

    def test_bundle_to_dict_has_correct_format(self):
        """Bundle dict has the right format identifier and version."""
        bundle = RegistryBundle(items=[_make_item()])
        data = bundle.to_dict()
        assert data["format"] == BUNDLE_FORMAT
        assert data["version"] == BUNDLE_VERSION
        assert "exported_at" in data
        assert "exported_by" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 1

    def test_bundle_to_json_roundtrip(self):
        """Bundle survives JSON serialization roundtrip."""
        items = [_make_item("Roundtrip Agent", "rt-1")]
        bundle = RegistryBundle(items=items, exported_by="rt-user")
        json_str = bundle.to_json()
        restored = RegistryBundle.from_json(json_str)
        assert len(restored.items) == 1
        assert restored.items[0].name == "Roundtrip Agent"
        assert restored.items[0].id == "rt-1"
        assert restored.exported_by == "rt-user"

    def test_bundle_from_dict_rejects_wrong_format(self):
        """Importing a non-bundle dict raises ValueError."""
        with pytest.raises(ValueError, match="not a marketplace bundle"):
            RegistryBundle.from_dict({"format": "something-else"})

    def test_bundle_from_dict_rejects_unsupported_version(self):
        """Importing a future version raises ValueError."""
        data = {
            "format": BUNDLE_FORMAT,
            "version": "2.0.0",
            "items": [],
        }
        with pytest.raises(ValueError, match="unsupported bundle version"):
            RegistryBundle.from_dict(data)

    def test_bundle_save_and_load_file(self):
        """Bundle can be saved to and loaded from a file."""
        items = [_make_item("File Agent", "file-1")]
        bundle = RegistryBundle(items=items, exported_by="file-user")

        with tempfile.NamedTemporaryFile(
            suffix=".acal-pack", mode="w", delete=False
        ) as f:
            path = f.name
        try:
            bundle.save(path)
            loaded = RegistryBundle.load(path)
            assert len(loaded.items) == 1
            assert loaded.items[0].name == "File Agent"
            assert loaded.exported_by == "file-user"
        finally:
            os.unlink(path)

    def test_bundle_preserves_item_config(self):
        """Bundle preserves the full item config through export/import."""
        item = _make_item()
        item.config = {
            "system_prompt": "You are a scheduling agent.",
            "tools": ["create_event", "delete_event"],
            "nested": {"key": "value", "list": [1, 2, 3]},
        }
        bundle = RegistryBundle(items=[item])
        restored = RegistryBundle.from_dict(bundle.to_dict())
        assert restored.items[0].config["system_prompt"] == "You are a scheduling agent."
        assert restored.items[0].config["tools"] == ["create_event", "delete_event"]
        assert restored.items[0].config["nested"]["key"] == "value"
        assert restored.items[0].config["nested"]["list"] == [1, 2, 3]

    def test_bundle_preserves_provenance(self):
        """Bundle preserves provenance metadata through roundtrip."""
        item = _make_item()
        item.provenance = Provenance(
            summary="Detailed summary",
            what_it_does="Does X, Y, Z",
            gaps_and_limits="Can't do W",
            integration_notes="Connects to sync engine",
            version="2.1.0",
            license="MIT",
        )
        bundle = RegistryBundle(items=[item])
        restored = RegistryBundle.from_dict(bundle.to_dict())
        assert restored.items[0].provenance.summary == "Detailed summary"
        assert restored.items[0].provenance.version == "2.1.0"
        assert restored.items[0].provenance.license == "MIT"

    def test_empty_bundle(self):
        """An empty bundle is valid."""
        bundle = RegistryBundle(items=[])
        data = bundle.to_dict()
        assert data["items"] == []
        restored = RegistryBundle.from_dict(data)
        assert len(restored.items) == 0


# --- RegistryManifest tests -------------------------------------------------

class TestRegistryManifest:
    """Tests for the registry manifest format."""

    def test_create_manifest(self):
        """A manifest has a name, description, and item summaries."""
        manifest = RegistryManifest(
            name="Test Registry",
            description="A test registry",
            items=[{"id": "1", "name": "Item 1"}],
        )
        assert manifest.name == "Test Registry"
        assert len(manifest.items) == 1

    def test_manifest_to_dict_has_correct_format(self):
        """Manifest dict has the right format identifier."""
        manifest = RegistryManifest(name="Test")
        data = manifest.to_dict()
        assert data["format"] == REGISTRY_FORMAT
        assert data["version"] == REGISTRY_VERSION
        assert data["name"] == "Test"

    def test_manifest_from_dict_rejects_wrong_format(self):
        """Importing a non-manifest dict raises ValueError."""
        with pytest.raises(ValueError, match="not a registry manifest"):
            RegistryManifest.from_dict({"format": "wrong"})

    def test_manifest_find_by_name(self):
        """Manifest search matches by name."""
        manifest = RegistryManifest(
            items=[
                {"id": "1", "name": "Focus Scheduler", "tags": []},
                {"id": "2", "name": "Email Triage", "tags": []},
            ]
        )
        results = manifest.find("focus")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_manifest_find_by_tags(self):
        """Manifest search matches by tags."""
        manifest = RegistryManifest(
            items=[
                {"id": "1", "name": "Agent A", "tags": ["scheduling", "calendar"]},
                {"id": "2", "name": "Agent B", "tags": ["email"]},
            ]
        )
        results = manifest.find("calendar")
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_manifest_find_no_results(self):
        """Manifest search returns empty list for no matches."""
        manifest = RegistryManifest(items=[{"id": "1", "name": "Agent A"}])
        results = manifest.find("nonexistent")
        assert results == []

    def test_manifest_find_ranks_by_relevance(self):
        """Name match scores higher than tag match."""
        manifest = RegistryManifest(
            items=[
                {"id": "1", "name": "Other", "tags": ["focus"]},
                {"id": "2", "name": "Focus Agent", "tags": ["misc"]},
            ]
        )
        results = manifest.find("focus")
        assert results[0]["id"] == "2"  # Name match ranks first


# --- build_manifest_from_store tests ----------------------------------------

class TestBuildManifestFromStore:
    """Tests for building a manifest from a marketplace store."""

    def test_build_manifest_from_store(self):
        """Building a manifest from a store includes all items."""
        store = MarketplaceStore()
        items = store.list_items()  # Seeded with built-in items
        manifest = build_manifest_from_store(
            store, name="Test Registry", description="Test"
        )
        assert manifest.name == "Test Registry"
        assert len(manifest.items) == len(items)
        # Each item summary has the expected fields
        for summary in manifest.items:
            assert "id" in summary
            assert "name" in summary
            assert "item_type" in summary
            assert "author" in summary
            assert "provenance" in summary

    def test_manifest_from_empty_store(self):
        """Building a manifest from an empty store produces an empty manifest."""
        store = MarketplaceStore()
        store._items = {}  # Clear seeded items
        store._seeded = True  # Prevent re-seeding
        manifest = build_manifest_from_store(store)
        assert len(manifest.items) == 0


# --- RegistryClient tests (mocked) ------------------------------------------

class TestRegistryClient:
    """Tests for the remote registry client (with mocked HTTP)."""

    def test_client_creation(self):
        """RegistryClient stores the base URL."""
        client = RegistryClient("https://example.com/registry/")
        assert client.registry_url == "https://example.com/registry"

    def test_get_manifest_mocked(self):
        """RegistryClient.get_manifest fetches and parses the manifest."""
        manifest_data = {
            "format": REGISTRY_FORMAT,
            "version": REGISTRY_VERSION,
            "name": "Remote Registry",
            "description": "A remote test registry",
            "registry_url": "https://example.com/registry",
            "items": [{"id": "1", "name": "Remote Agent"}],
        }
        client = RegistryClient("https://example.com/registry")

        with patch.object(client, "_fetch", return_value=manifest_data):
            manifest = client.get_manifest()
            assert manifest.name == "Remote Registry"
            assert len(manifest.items) == 1

    def test_get_item_mocked(self):
        """RegistryClient.get_item fetches a full item."""
        item_data = _make_item("Remote Item", "remote-1").to_dict()
        client = RegistryClient("https://example.com/registry")

        with patch.object(client, "_fetch", return_value=item_data):
            item = client.get_item("remote-1")
            assert item.name == "Remote Item"
            assert item.id == "remote-1"

    def test_pull_item_mocked(self):
        """RegistryClient.pull_item returns the full item for local publishing."""
        item_data = _make_item("Pulled Item", "pull-1").to_dict()
        client = RegistryClient("https://example.com/registry")

        with patch.object(client, "_fetch", return_value=item_data):
            item = client.pull_item("pull-1")
            assert item.name == "Pulled Item"

    def test_search_mocked(self):
        """RegistryClient.search searches the remote manifest."""
        manifest_data = {
            "format": REGISTRY_FORMAT,
            "version": REGISTRY_VERSION,
            "name": "Remote",
            "items": [
                {"id": "1", "name": "Focus Agent", "tags": ["scheduling"]},
                {"id": "2", "name": "Other Agent", "tags": ["misc"]},
            ],
        }
        client = RegistryClient("https://example.com/registry")

        with patch.object(client, "_fetch", return_value=manifest_data):
            results = client.search("focus")
            assert len(results) == 1
            assert results[0]["id"] == "1"

    def test_get_manifest_no_valid_manifest_raises(self):
        """get_manifest raises ValueError if no valid manifest is found."""
        client = RegistryClient("https://example.com/registry")

        with patch.object(
            client, "_fetch", side_effect=ValueError("bad format")
        ):
            with pytest.raises(ValueError, match="no valid manifest"):
                client.get_manifest()


# --- API endpoint tests -----------------------------------------------------

class TestRegistryAPI:
    """Tests for the registry API endpoints."""

    def test_export_all_items(self):
        """POST /marketplace/export with no IDs exports all items."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/export",
            json={"item_ids": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == BUNDLE_FORMAT
        assert data["version"] == BUNDLE_VERSION
        assert len(data["items"]) > 0  # Seeded items

    def test_export_specific_items(self):
        """POST /marketplace/export with IDs exports only those items."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        # First, list items to get an ID
        items_response = client.get("/api/a-cal/marketplace/items")
        items = items_response.json()
        assert len(items) > 0
        first_id = items[0]["id"]

        response = client.post(
            "/api/a-cal/marketplace/export",
            json={"item_ids": [first_id]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == first_id

    def test_export_nonexistent_item_404(self):
        """Exporting a nonexistent item ID returns 404."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/export",
            json={"item_ids": ["nonexistent-id"]},
        )
        assert response.status_code == 404

    def test_import_bundle(self):
        """POST /marketplace/import imports items from a bundle."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        # Create a bundle with a new item
        item = _make_item("Imported Agent", "import-test-1")
        bundle = RegistryBundle(items=[item])
        bundle_json = bundle.to_json()

        response = client.post(
            "/api/a-cal/marketplace/import",
            json={"bundle_json": bundle_json},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["skipped"] == 0

    def test_import_existing_item_skipped(self):
        """Importing an item that already exists skips it."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        # Get an existing item
        items_response = client.get("/api/a-cal/marketplace/items")
        items = items_response.json()
        existing_item = items[0]

        bundle = RegistryBundle(
            items=[MarketplaceItem.from_dict(existing_item)]
        )
        response = client.post(
            "/api/a-cal/marketplace/import",
            json={"bundle_json": bundle.to_json()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] == 1
        assert data["imported"] == 0

    def test_import_invalid_json_400(self):
        """Importing invalid JSON returns 400."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/import",
            json={"bundle_json": "not valid json"},
        )
        assert response.status_code == 400

    def test_import_wrong_format_400(self):
        """Importing a non-bundle format returns 400."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/import",
            json={"bundle_json": json.dumps({"format": "wrong"})},
        )
        assert response.status_code == 400

    def test_get_registry_manifest(self):
        """GET /marketplace/registry/manifest returns the local manifest."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.get("/api/a-cal/marketplace/registry/manifest")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == REGISTRY_FORMAT
        assert data["version"] == REGISTRY_VERSION
        assert len(data["items"]) > 0

    def test_browse_remote_registry_bad_url(self):
        """POST /registry/browse with an unreachable URL returns 502."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/registry/browse",
            json={"registry_url": "http://localhost:1/nonexistent"},
        )
        assert response.status_code == 502

    def test_pull_from_remote_registry_bad_url(self):
        """POST /registry/pull with an unreachable URL returns 502."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = TestClient(app)
        response = client.post(
            "/api/a-cal/marketplace/registry/pull",
            json={
                "registry_url": "http://localhost:1/nonexistent",
                "item_id": "test-id",
            },
        )
        assert response.status_code == 502
