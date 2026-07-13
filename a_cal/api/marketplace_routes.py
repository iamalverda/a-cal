"""Marketplace API routes — browse, publish, install, remix, rate.

Exposes the community marketplace over HTTP so the frontend can browse
shared configs, search, install, remix, and rate items.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from a_cal.marketplace.store import MarketplaceStore
from a_cal.marketplace.persistent_store import PersistentMarketplaceStore
from a_cal.marketplace.types import (
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal/marketplace", tags=["a-cal-marketplace"])


# --- singleton store — uses SQLite persistence, falls back to in-memory -----

_store: Optional[MarketplaceStore] = None


def _get_store():
    """Get the marketplace store, preferring persistent (SQLite) storage.

    Falls back to in-memory store if the database is unavailable.
    """
    global _store
    if _store is None:
        try:
            _store = PersistentMarketplaceStore()
            logger.info("Marketplace using persistent SQLite store")
        except Exception as e:
            logger.warning("Falling back to in-memory marketplace store: %s", e)
            _store = MarketplaceStore()
    return _store


def _current_user_id() -> str:
    """Placeholder — wired to atom's auth in production."""
    return "local-dev-user"


# --- request/response models -----------------------------------------------

class ProvenanceInput(BaseModel):
    summary: str = ""
    what_it_does: str = ""
    gaps_and_limits: str = ""
    integration_notes: str = ""
    version: str = "0.1.0"
    license: str = "AGPL-3.0-or-later"


class PublishItemRequest(BaseModel):
    name: str
    item_type: str  # MarketplaceItemType value
    description: str = ""
    provenance: ProvenanceInput = Field(default_factory=ProvenanceInput)
    config: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class RemixRequest(BaseModel):
    # parent_item_id is redundant with the path param but kept for SDK compat.
    parent_item_id: str = ""
    name: str
    description: str = ""
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
    changes_summary: str = ""


class RateRequest(BaseModel):
    stars: float  # 1.0–5.0


# --- helpers ----------------------------------------------------------------

def _item_from_request(body: PublishItemRequest, author: str) -> MarketplaceItem:
    """Convert a publish request to a MarketplaceItem."""
    return MarketplaceItem(
        name=body.name,
        item_type=body.item_type,
        author=author,
        description=body.description,
        provenance=Provenance(
            summary=body.provenance.summary,
            what_it_does=body.provenance.what_it_does,
            gaps_and_limits=body.provenance.gaps_and_limits,
            integration_notes=body.provenance.integration_notes,
            version=body.provenance.version,
            license=body.provenance.license,
        ),
        config=body.config,
        tags=body.tags,
    )


# --- endpoints --------------------------------------------------------------

@router.get("/items")
def list_items(
    item_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Browse marketplace items, optionally filtered by type or tag."""
    store = _get_store()
    items = store.list_items(item_type=item_type, tag=tag, limit=limit)
    return [i.to_dict() for i in items]


@router.get("/items/{item_id}")
def get_item(item_id: str):
    """Get a single marketplace item by ID."""
    store = _get_store()
    item = store.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item.to_dict()


@router.get("/search")
def search_items(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    """Search marketplace items by name, description, tags, or author."""
    store = _get_store()
    results = store.search(q, limit=limit)
    return [i.to_dict() for i in results]


@router.post("/items")
def publish_item(body: PublishItemRequest):
    """Publish a new item to the marketplace."""
    store = _get_store()
    user_id = _current_user_id()
    item = _item_from_request(body, author=user_id)
    published = store.publish(item)
    return published.to_dict()


@router.post("/items/{item_id}/install")
def install_item(item_id: str):
    """Install a marketplace item for the current user."""
    store = _get_store()
    user_id = _current_user_id()
    try:
        record = store.install(user_id, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="item not found")
    return record.to_dict()


@router.get("/installs")
def get_user_installs():
    """Get all items the current user has installed."""
    store = _get_store()
    user_id = _current_user_id()
    records = store.get_user_installs(user_id)
    return [r.to_dict() for r in records]


@router.post("/items/{item_id}/remix")
def remix_item(item_id: str, body: RemixRequest):
    """Fork an existing item, apply overrides, and publish the remix."""
    store = _get_store()
    user_id = _current_user_id()
    try:
        child = store.remix(
            user_id=user_id,
            parent_item_id=item_id,
            name=body.name,
            description=body.description,
            config_overrides=body.config_overrides,
            changes_summary=body.changes_summary,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="parent item not found")
    return child.to_dict()


@router.get("/items/{item_id}/remixes")
def get_remixes(item_id: str):
    """Get all items that were remixed from the given item."""
    store = _get_store()
    remixes = store.get_remixes_of(item_id)
    return [i.to_dict() for i in remixes]


@router.get("/items/{item_id}/remix-chain")
def get_remix_chain(item_id: str):
    """Trace the remix ancestry of an item."""
    store = _get_store()
    chain = store.get_remix_chain(item_id)
    return chain


@router.post("/items/{item_id}/rate")
def rate_item(item_id: str, body: RateRequest):
    """Rate an item (1–5 stars)."""
    store = _get_store()
    try:
        item = store.rate_item(item_id, body.stars)
    except KeyError:
        raise HTTPException(status_code=404, detail="item not found")
    return item.to_dict()


# --- registry endpoints (export / import / remote browsing) -----------------

from a_cal.marketplace.registry import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    REGISTRY_FORMAT,
    REGISTRY_VERSION,
    RegistryBundle,
    RegistryClient,
    RegistryManifest,
    build_manifest_from_store,
)


class ExportRequest(BaseModel):
    """Request to export marketplace items as a portable bundle."""
    item_ids: List[str] = Field(default_factory=list)
    # If empty, exports all items in the store.


class ImportBundleRequest(BaseModel):
    """Request to import items from a bundle (JSON string)."""
    bundle_json: str


class RemoteRegistryRequest(BaseModel):
    """Request to browse or pull from a remote registry."""
    registry_url: str


class PullItemRequest(BaseModel):
    """Request to pull a specific item from a remote registry."""
    registry_url: str
    item_id: str


@router.get("/registry/manifest")
def get_registry_manifest():
    """Get the local registry manifest (catalog of all items).

    This endpoint serves the manifest that a remote RegistryClient would
    fetch. It can be used as a static registry by pointing other A-Cal
    instances at this server's URL.
    """
    store = _get_store()
    manifest = build_manifest_from_store(store)
    # Set the registry_url to the current server (best effort)
    manifest.registry_url = "/api/a-cal/marketplace/registry"
    return manifest.to_dict()


@router.post("/export")
def export_items(body: ExportRequest):
    """Export marketplace items as a portable JSON bundle.

    If ``item_ids`` is empty, exports all items in the store. The bundle
    can be shared as a file and imported into another A-Cal instance via
    the ``POST /import`` endpoint.
    """
    store = _get_store()
    user_id = _current_user_id()

    if body.item_ids:
        items = []
        for item_id in body.item_ids:
            item = store.get_item(item_id)
            if item is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"item not found: {item_id}",
                )
            items.append(item)
    else:
        items = store.list_items(limit=200)

    bundle = RegistryBundle(items=items, exported_by=user_id)
    return bundle.to_dict()


@router.post("/import")
def import_items(body: ImportBundleRequest):
    """Import marketplace items from a JSON bundle.

    Parses the bundle, validates the format, and publishes each item to
    the local store. Items that already exist (by ID) are skipped.

    Returns a summary of imported and skipped items.
    """
    store = _get_store()

    try:
        bundle = RegistryBundle.from_json(body.bundle_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    imported = 0
    skipped = 0
    errors: List[str] = []

    for item in bundle.items:
        existing = store.get_item(item.id)
        if existing is not None:
            skipped += 1
            continue
        try:
            store.publish(item)
            imported += 1
        except Exception as exc:
            errors.append(f"{item.name}: {exc}")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "exported_by": bundle.exported_by,
        "exported_at": bundle.exported_at,
    }


@router.post("/registry/browse")
def browse_remote_registry(body: RemoteRegistryRequest):
    """Fetch a remote registry's manifest for browsing.

    Returns the manifest with item summaries (no full configs). Use
    ``POST /registry/pull`` to fetch and install a specific item.
    """
    try:
        client = RegistryClient(body.registry_url)
        manifest = client.get_manifest()
        return manifest.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"failed to fetch registry: {exc}",
        )


@router.post("/registry/pull")
def pull_from_remote_registry(body: PullItemRequest):
    """Pull a specific item from a remote registry and publish it locally.

    Fetches the full item config from the remote registry, then publishes
    it to the local store. If the item already exists locally, it is
    skipped.
    """
    store = _get_store()

    try:
        client = RegistryClient(body.registry_url)
        item = client.pull_item(body.item_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"failed to pull item: {exc}",
        )

    existing = store.get_item(item.id)
    if existing is not None:
        return {
            "published": False,
            "item": existing.to_dict(),
            "message": "item already exists locally",
        }

    published = store.publish(item)
    return {
        "published": True,
        "item": published.to_dict(),
    }
