"""Marketplace registry — portable export/import and remote registry browsing.

Enables the A-Cal community to share marketplace items beyond a single
instance. Users can:

  1. **Export** one or more items as a portable JSON bundle (``.acal-pack``).
  2. **Import** items from a bundle file or a remote URL.
  3. **Browse** a remote registry's manifest (catalog of available items).
  4. **Pull** specific items from a remote registry into the local store.

This is the local foundation for the hosted community registry. A registry
server is just an HTTP endpoint that serves a manifest and individual items
in the same JSON format. Any static file host (GitHub Pages, S3, etc.) can
serve as a registry — no special server software needed.

Bundle format (``.acal-pack``):

    {
      "format": "acal-marketplace-bundle",
      "version": "1.0.0",
      "exported_at": "2026-07-12T...",
      "exported_by": "user-id",
      "items": [ MarketplaceItem.to_dict(), ... ]
    }

Registry manifest format:

    {
      "format": "acal-marketplace-registry",
      "version": "1.0.0",
      "name": "A-Cal Community Registry",
      "description": "Curated community configs for A-Cal",
      "registry_url": "https://example.com/acal-registry",
      "items": [
        {
          "id": "...",
          "name": "...",
          "item_type": "...",
          "author": "...",
          "description": "...",
          "tags": [...],
          "install_count": 123,
          "rating": 4.5,
          "provenance": { ... }
        },
        ...
      ]
    }

The manifest includes enough metadata for browsing without downloading
every item's full config. The full item is fetched on demand via
``{registry_url}/items/{item_id}``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from a_cal.marketplace.types import (
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
)

logger = logging.getLogger(__name__)

BUNDLE_FORMAT = "acal-marketplace-bundle"
BUNDLE_VERSION = "1.0.0"
REGISTRY_FORMAT = "acal-marketplace-registry"
REGISTRY_VERSION = "1.0.0"


class RegistryBundle:
    """A portable bundle of marketplace items for sharing.

    A bundle is a self-contained JSON file that can be shared via any
    file-transfer mechanism (email, Git, shared drive, etc.) and imported
    into another A-Cal instance.
    """

    def __init__(
        self,
        items: List[MarketplaceItem],
        exported_by: str = "local-dev-user",
    ) -> None:
        """Create a bundle from a list of marketplace items.

        Args:
            items: The marketplace items to include in the bundle.
            exported_by: The user ID of the exporter (for provenance).
        """
        self.items = list(items)
        self.exported_by = exported_by
        self.exported_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the bundle to a JSON-compatible dict."""
        return {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "exported_at": self.exported_at,
            "exported_by": self.exported_by,
            "items": [item.to_dict() for item in self.items],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the bundle to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryBundle":
        """Deserialize a bundle from a dict.

        Validates the format and version, raising ValueError on mismatch.

        Args:
            data: The parsed bundle dict.

        Returns:
            A RegistryBundle with the deserialized items.

        Raises:
            ValueError: If the format is wrong or version is unsupported.
        """
        fmt = data.get("format", "")
        if fmt != BUNDLE_FORMAT:
            raise ValueError(
                f"not a marketplace bundle (expected format '{BUNDLE_FORMAT}', "
                f"got '{fmt}')"
            )

        version = data.get("version", "")
        if not version.startswith("1."):
            raise ValueError(
                f"unsupported bundle version: {version}"
            )

        items = [
            MarketplaceItem.from_dict(item_data)
            for item_data in data.get("items", [])
        ]
        bundle = cls.__new__(cls)
        bundle.items = items
        bundle.exported_by = data.get("exported_by", "unknown")
        bundle.exported_at = data.get("exported_at", "")
        return bundle

    @classmethod
    def from_json(cls, json_str: str) -> "RegistryBundle":
        """Deserialize a bundle from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    def save(self, path: str) -> None:
        """Save the bundle to a file.

        Args:
            path: File path to write the bundle to.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "RegistryBundle":
        """Load a bundle from a file.

        Args:
            path: File path to read the bundle from.

        Returns:
            The loaded RegistryBundle.
        """
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())


class RegistryManifest:
    """A catalog of available items from a registry.

    The manifest contains enough metadata to browse items without downloading
    their full configs. Full items are fetched on demand from
    ``{registry_url}/items/{item_id}``.
    """

    def __init__(
        self,
        name: str = "",
        description: str = "",
        registry_url: str = "",
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Create a manifest.

        Args:
            name: Human-readable registry name.
            description: What this registry curates.
            registry_url: Base URL for fetching full items.
            items: List of item summary dicts (id, name, type, author, etc.).
        """
        self.name = name
        self.description = description
        self.registry_url = registry_url
        self.items = items or []

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the manifest to a JSON-compatible dict."""
        return {
            "format": REGISTRY_FORMAT,
            "version": REGISTRY_VERSION,
            "name": self.name,
            "description": self.description,
            "registry_url": self.registry_url,
            "items": list(self.items),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the manifest to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryManifest":
        """Deserialize a manifest from a dict.

        Args:
            data: The parsed manifest dict.

        Returns:
            A RegistryManifest.

        Raises:
            ValueError: If the format is wrong.
        """
        fmt = data.get("format", "")
        if fmt != REGISTRY_FORMAT:
            raise ValueError(
                f"not a registry manifest (expected format "
                f"'{REGISTRY_FORMAT}', got '{fmt}')"
            )
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            registry_url=data.get("registry_url", ""),
            items=data.get("items", []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "RegistryManifest":
        """Deserialize a manifest from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    def find(self, query: str) -> List[Dict[str, Any]]:
        """Search manifest items by name, description, or tags.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching item summary dicts, sorted by relevance.
        """
        q = query.lower()
        scored: List[tuple[float, Dict[str, Any]]] = []
        for item in self.items:
            score = 0.0
            if q in item.get("name", "").lower():
                score += 3.0
            if q in item.get("description", "").lower():
                score += 2.0
            if any(q in tag.lower() for tag in item.get("tags", [])):
                score += 2.0
            if q in item.get("author", "").lower():
                score += 1.0
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]


class RegistryClient:
    """Client for browsing and pulling from a remote marketplace registry.

    A registry is any HTTP endpoint that serves:
      - ``GET /`` or ``GET /manifest.json`` → RegistryManifest JSON
      - ``GET /items/{item_id}`` → full MarketplaceItem JSON

    This means any static file host (GitHub Pages, S3, Netlify) can serve
    as a registry without special server software.
    """

    def __init__(self, registry_url: str, timeout: float = 10.0) -> None:
        """Create a registry client.

        Args:
            registry_url: Base URL of the registry (no trailing slash).
            timeout: Request timeout in seconds.
        """
        self.registry_url = registry_url.rstrip("/")
        self.timeout = timeout

    def _fetch(self, path: str) -> Dict[str, Any]:
        """Fetch JSON from the registry.

        Args:
            path: Path relative to the registry base URL.

        Returns:
            Parsed JSON dict.

        Raises:
            URLError: If the request fails.
            ValueError: If the response is not valid JSON.
        """
        url = f"{self.registry_url}/{path.lstrip('/')}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=self.timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)

    def get_manifest(self) -> RegistryManifest:
        """Fetch the registry's manifest (catalog of available items).

        Returns:
            The registry manifest.

        Raises:
            URLError: If the request fails.
            ValueError: If the response is not a valid manifest.
        """
        # Try /manifest.json first, then / (root)
        for path in ("manifest.json", ""):
            try:
                data = self._fetch(path)
                manifest = RegistryManifest.from_dict(data)
                # Ensure registry_url is set for item fetching
                if not manifest.registry_url:
                    manifest.registry_url = self.registry_url
                return manifest
            except (ValueError, KeyError):
                continue
        raise ValueError(
            f"no valid manifest found at {self.registry_url}"
        )

    def get_item(self, item_id: str) -> MarketplaceItem:
        """Fetch a full item from the registry by ID.

        Args:
            item_id: The marketplace item ID.

        Returns:
            The full MarketplaceItem with config.

        Raises:
            URLError: If the request fails.
        """
        data = self._fetch(f"items/{item_id}")
        return MarketplaceItem.from_dict(data)

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the registry's manifest for items matching the query.

        Args:
            query: Search string.

        Returns:
            List of matching item summaries from the manifest.
        """
        manifest = self.get_manifest()
        return manifest.find(query)

    def pull_item(self, item_id: str) -> MarketplaceItem:
        """Fetch a full item and return it (caller publishes to local store).

        This is the "install from remote registry" flow:
          1. pull_item(id) → MarketplaceItem
          2. local_store.publish(item) → adds to local marketplace
          3. local_store.install(user_id, item.id) → installs for user

        Args:
            item_id: The item ID in the remote registry.

        Returns:
            The full MarketplaceItem ready to publish locally.
        """
        return self.get_item(item_id)


def build_manifest_from_store(store, name: str = "", description: str = "") -> RegistryManifest:
    """Build a registry manifest from a marketplace store.

    Creates a browsable catalog from the store's items, suitable for serving
    as a static registry. Each item in the manifest includes enough metadata
    for browsing without the full config.

    Args:
        store: A MarketplaceStore or PersistentMarketplaceStore instance.
        name: Registry name (defaults to "A-Cal Local Registry").
        description: Registry description.

    Returns:
        A RegistryManifest with item summaries.
    """
    items = store.list_items(limit=200)
    summaries: List[Dict[str, Any]] = []
    for item in items:
        summaries.append({
            "id": item.id,
            "name": item.name,
            "item_type": item.item_type,
            "author": item.author,
            "description": item.description,
            "tags": list(item.tags),
            "install_count": item.install_count,
            "rating": item.rating,
            "rating_count": item.rating_count,
            "provenance": item.provenance.to_dict(),
            "remixed_from": item.remixed_from,
        })
    return RegistryManifest(
        name=name or "A-Cal Local Registry",
        description=description or f"{len(summaries)} items available",
        registry_url="",  # Set by the server when serving
        items=summaries,
    )
