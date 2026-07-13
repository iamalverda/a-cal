"""In-memory marketplace store — publish, install, remix, search, rate.

In standalone mode, items are stored in memory. In the full atom deployment,
these become database rows. The store interface is the same either way.

The store also seeds a few built-in items on first access so the marketplace
isn't empty when a user first opens it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from a_cal.marketplace.types import (
    InstallRecord,
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
    RemixRecord,
)

logger = logging.getLogger(__name__)


class MarketplaceStore:
    """In-memory marketplace with publish, install, remix, search, and rating.

    Thread-safe enough for single-user development. In production, this is
    replaced by atom's database-backed store.
    """

    def __init__(self) -> None:
        self._items: Dict[str, MarketplaceItem] = {}
        self._installs: Dict[str, InstallRecord] = {}  # record_id → record
        self._installs_by_user: Dict[str, List[str]] = {}  # user_id → record_ids
        self._remixes: List[RemixRecord] = []
        self._seeded = False

    # --- seeding -------------------------------------------------------------

    def _seed(self) -> None:
        """Populate with a few built-in items so the marketplace isn't empty."""
        if self._seeded:
            return
        self._seeded = True

        builtins = [
            MarketplaceItem(
                name="Focus-First Scheduler",
                item_type=MarketplaceItemType.AGENT_SPEC.value,
                author="A-Cal Team",
                description="An agent spec that prioritizes deep-work blocks and batches meetings into afternoons.",
                provenance=Provenance(
                    summary="Scheduling agent tuned for makers, not managers.",
                    what_it_does="Blocks mornings for focus, batches meetings 1–4pm, leaves 4–6pm open for review.",
                    gaps_and_limits="Not suited for roles with frequent morning standups.",
                    integration_notes="Overrides the default Schedule Agent system prompt and tool list.",
                    version="1.0.0",
                ),
                config={
                    "agent_name": "a_cal_schedule_agent",
                    "system_prompt": "You prioritize deep-work blocks in the morning and batch meetings into afternoons...",
                    "tools": ["find_open_slots", "detect_conflicts", "get_self_model_context"],
                    "default_tier": "versatile",
                },
                tags=["scheduling", "focus", "deep-work", "maker-schedule"],
            ),
            MarketplaceItem(
                name="Privacy-First Sync Rules",
                item_type=MarketplaceItemType.SYNC_RULE_PACK.value,
                author="A-Cal Team",
                description="Sync rules that keep personal events as title-only blocks on the main calendar.",
                provenance=Provenance(
                    summary="Keep personal commitments visible but private.",
                    what_it_does="Transforms personal sub-account events to 'Busy' with no title on the main calendar.",
                    gaps_and_limits="Doesn't apply to sub-accounts using intelligent merge mode.",
                    integration_notes="Works with mirror_filter and layered_federation sync modes.",
                    version="1.0.0",
                ),
                config={
                    "rules": [
                        {"type": "transform", "field": "title", "value": "Busy", "condition": "sub_account == 'personal'"},
                        {"type": "exclude", "condition": "sub_account == 'personal' and title contains 'private'"},
                    ],
                },
                tags=["privacy", "sync-rules", "personal"],
            ),
            MarketplaceItem(
                name="Aggressive Negotiator",
                item_type=MarketplaceItemType.NEGOTIATION_STRATEGY.value,
                author="A-Cal Team",
                description="A negotiation strategy that pushes hard for the user's preferred slots.",
                provenance=Provenance(
                    summary="Win more negotiation rounds by holding firm.",
                    what_it_does="Sets high priority claims, rejects first proposal, only concedes on counter-proposal.",
                    gaps_and_limits="May escalate more often — requires user to be available for tie-breaking.",
                    integration_notes="Modifies the Negotiate Agent's acceptance threshold and counter-proposal logic.",
                    version="0.9.0",
                ),
                config={
                    "accept_first_proposal": False,
                    "min_priority_to_claim": "normal",
                    "always_counter_propose": True,
                    "escalation_threshold": 3,
                },
                tags=["negotiation", "aggressive", "conflict-resolution"],
            ),
        ]

        for item in builtins:
            self._items[item.id] = item

        logger.info("marketplace seeded with %d built-in items", len(builtins))

    def _ensure_seeded(self) -> None:
        if not self._seeded:
            self._seed()

    # --- publish -------------------------------------------------------------

    def publish(self, item: MarketplaceItem) -> MarketplaceItem:
        """Publish a new item to the marketplace."""
        self._ensure_seeded()
        self._items[item.id] = item
        logger.info("published marketplace item: %s (%s)", item.name, item.id)
        return item

    # --- install -------------------------------------------------------------

    def install(self, user_id: str, item_id: str) -> InstallRecord:
        """Install a marketplace item for a user.

        Returns an InstallRecord that captures the config at install time.
        The user can modify the config after installation without affecting
        the marketplace version.
        """
        self._ensure_seeded()
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"marketplace item not found: {item_id}")

        item.record_install()
        record = InstallRecord(
            user_id=user_id,
            item_id=item_id,
            installed_config=dict(item.config),
        )
        self._installs[record.id] = record
        self._installs_by_user.setdefault(user_id, []).append(record.id)
        logger.info("user %s installed item %s", user_id, item_id)
        return record

    # --- remix ---------------------------------------------------------------

    def remix(
        self,
        user_id: str,
        parent_item_id: str,
        name: str,
        description: str,
        config_overrides: Dict[str, Any],
        changes_summary: str = "",
    ) -> MarketplaceItem:
        """Fork an existing item, apply overrides, and publish the remix.

        The new item references the original via ``remixed_from``.
        """
        self._ensure_seeded()
        parent = self._items.get(parent_item_id)
        if parent is None:
            raise KeyError(f"parent item not found: {parent_item_id}")

        # Start from parent's config, apply overrides.
        merged_config = dict(parent.config)
        merged_config.update(config_overrides)

        child = MarketplaceItem(
            name=name,
            item_type=parent.item_type,
            author=user_id,
            description=description,
            provenance=Provenance(
                summary=f"Remix of '{parent.name}' by {user_id}",
                what_it_does=parent.provenance.what_it_does,
                gaps_and_limits=parent.provenance.gaps_and_limits,
                integration_notes=parent.provenance.integration_notes,
                version="0.1.0",
            ),
            config=merged_config,
            tags=list(parent.tags) + ["remix"],
            remixed_from=parent_item_id,
        )

        self._items[child.id] = child

        remix_record = RemixRecord(
            parent_item_id=parent_item_id,
            child_item_id=child.id,
            remixed_by=user_id,
            changes_summary=changes_summary,
        )
        self._remixes.append(remix_record)

        logger.info("user %s remixed item %s → %s", user_id, parent_item_id, child.id)
        return child

    # --- search / browse -----------------------------------------------------

    def list_items(
        self,
        item_type: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[MarketplaceItem]:
        """Browse marketplace items, optionally filtered by type or tag."""
        self._ensure_seeded()
        items = list(self._items.values())

        if item_type:
            items = [i for i in items if i.item_type == item_type]
        if tag:
            items = [i for i in items if tag in i.tags]

        # Sort by install_count desc, then rating desc.
        items.sort(key=lambda i: (i.install_count, i.rating), reverse=True)
        return items[:limit]

    def get_item(self, item_id: str) -> Optional[MarketplaceItem]:
        """Get a single marketplace item by ID."""
        self._ensure_seeded()
        return self._items.get(item_id)

    def search(self, query: str, limit: int = 20) -> List[MarketplaceItem]:
        """Search items by name, description, tags, or author."""
        self._ensure_seeded()
        q = query.lower()
        scored: List[Tuple[float, MarketplaceItem]] = []

        for item in self._items.values():
            score = 0.0
            if q in item.name.lower():
                score += 3.0
            if q in item.description.lower():
                score += 2.0
            if any(q in t.lower() for t in item.tags):
                score += 2.0
            if q in item.author.lower():
                score += 1.0
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    # --- rating --------------------------------------------------------------

    def rate_item(self, item_id: str, stars: float) -> MarketplaceItem:
        """Rate an item (1–5 stars). Updates the rolling average."""
        self._ensure_seeded()
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"marketplace item not found: {item_id}")
        item.add_rating(stars)
        return item

    # --- user installs -------------------------------------------------------

    def get_items_by_author(self, author: str) -> List[MarketplaceItem]:
        """Get all items authored by a user (includes their remixes)."""
        self._ensure_seeded()
        return [i for i in self._items.values() if i.author == author]

    def get_user_installs(self, user_id: str) -> List[InstallRecord]:
        """Get all items a user has installed."""
        self._ensure_seeded()
        record_ids = self._installs_by_user.get(user_id, [])
        return [self._installs[rid] for rid in record_ids if rid in self._installs]

    # --- remix history -------------------------------------------------------

    def get_remix_chain(self, item_id: str) -> List[Dict[str, Any]]:
        """Trace the remix ancestry of an item (parent → child chain)."""
        self._ensure_seeded()
        chain: List[Dict[str, Any]] = []
        current = self._items.get(item_id)
        while current and current.remixed_from:
            parent = self._items.get(current.remixed_from)
            if parent:
                chain.append({
                    "item_id": parent.id,
                    "name": parent.name,
                    "author": parent.author,
                })
                current = parent
            else:
                break
        return chain

    def get_remixes_of(self, item_id: str) -> List[MarketplaceItem]:
        """Get all items that were remixed from the given item."""
        self._ensure_seeded()
        return [i for i in self._items.values() if i.remixed_from == item_id]
