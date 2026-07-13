"""SQLite-backed marketplace store — same interface as MarketplaceStore.

Persists marketplace items, install records, and remix history to SQLite
via SQLAlchemy. Falls back to seeding built-in items on first access so
the marketplace is never empty. Items survive server restarts.

In the full atom deployment, this store uses the same database engine
as atom's PostgreSQL instance — only the connection string changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, UTC
from typing import Any, Dict, List, Optional, Tuple

from a_cal.db.models import (
    InstallRecordDB,
    MarketplaceItemDB,
    get_session,
    create_engine_and_session,
)
from a_cal.marketplace.types import (
    InstallRecord,
    MarketplaceItem,
    MarketplaceItemType,
    Provenance,
    RemixRecord,
)
from a_cal.marketplace.trust import (
    FlagRecord,
    VerificationStatus,
    compute_content_hash,
    compute_trust_score,
)

logger = logging.getLogger(__name__)

from a_cal.auth.session import get_current_user_id

USER_ID = "local-dev-user"  # Legacy fallback


def _row_to_item(row: MarketplaceItemDB) -> MarketplaceItem:
    """Convert a MarketplaceItemDB row to a MarketplaceItem dataclass."""
    rating_sum = float(row.rating or "0.0")
    return MarketplaceItem(
        id=row.id,
        name=row.name,
        item_type=row.item_type,
        author=row.author,
        description=row.description or "",
        provenance=Provenance.from_dict(row.provenance or {}),
        config=row.config or {},
        tags=row.tags or [],
        remixed_from=row.remixed_from,
        install_count=row.install_count or 0,
        rating_sum=rating_sum,
        rating_count=row.rating_count or 0,
        created_at=row.created_at.isoformat() if row.created_at else datetime.now(UTC).isoformat(),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        content_hash=getattr(row, 'content_hash', '') or '',
        verification_status=getattr(row, 'verification_status', 'unverified') or 'unverified',
        flag_count=getattr(row, 'flag_count', 0) or 0,
    )


def _row_to_install(row: InstallRecordDB) -> InstallRecord:
    """Convert an InstallRecordDB row to an InstallRecord dataclass."""
    return InstallRecord(
        id=row.id,
        user_id=row.user_id,
        item_id=row.item_id,
        installed_at=row.created_at.isoformat() if row.created_at else datetime.now(UTC).isoformat(),
        installed_config=row.installed_config or {},
    )


class PersistentMarketplaceStore:
    """SQLite-backed marketplace with the same interface as MarketplaceStore.

    All operations persist to the database. Built-in items are seeded on
    first access and remain across restarts.
    """

    def __init__(self, session_factory=None) -> None:
        """Initialize the persistent store.

        Args:
            session_factory: Optional SQLAlchemy session factory. If None,
                uses the module-level default from db.models.
        """
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            _, self._session_factory = create_engine_and_session()
        self._seeded = False

    def _session(self):
        """Get a new DB session."""
        return self._session_factory()

    def _ensure_seeded(self) -> None:
        """Seed built-in items on first access if the table is empty."""
        if self._seeded:
            return
        self._seeded = True

        session = self._session()
        try:
            existing = session.query(MarketplaceItemDB).count()
            if existing > 0:
                return

            for item in self._builtin_items():
                item.compute_hash()
                row = MarketplaceItemDB(
                    id=item.id,
                    name=item.name,
                    item_type=item.item_type,
                    author=item.author,
                    description=item.description,
                    provenance=item.provenance.to_dict(),
                    config=item.config,
                    tags=item.tags,
                    remixed_from=item.remixed_from,
                    install_count=item.install_count,
                    rating=str(item.rating_sum),
                    rating_count=item.rating_count,
                    content_hash=item.content_hash,
                )
                session.add(row)
            session.commit()
            logger.info("Seeded %d built-in marketplace items", len(self._builtin_items()))
        except Exception as e:
            session.rollback()
            logger.warning("Marketplace seeding failed: %s", e)
        finally:
            session.close()

    def _builtin_items(self) -> list[MarketplaceItem]:
        """Return the built-in marketplace items for first-run seeding."""
        return [
            MarketplaceItem(
                name="Focus-First Scheduler",
                item_type=MarketplaceItemType.AGENT_SPEC.value,
                author="A-Cal Team",
                description="An agent spec that prioritizes deep-work blocks and batches meetings into afternoons.",
                provenance=Provenance(
                    summary="Scheduling agent tuned for makers, not managers.",
                    what_it_does="Blocks mornings for focus, batches meetings 1-4pm, leaves 4-6pm open for review.",
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
                    gaps_and_limits="May escalate more often -- requires user to be available for tie-breaking.",
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

    # --- publish -------------------------------------------------------------

    def publish(self, item: MarketplaceItem) -> MarketplaceItem:
        """Publish a new item to the marketplace.

        Automatically computes a content hash for integrity verification.
        """
        self._ensure_seeded()
        item.compute_hash()

        session = self._session()
        try:
            row = MarketplaceItemDB(
                id=item.id,
                name=item.name,
                item_type=item.item_type,
                author=item.author,
                description=item.description,
                provenance=item.provenance.to_dict(),
                config=item.config,
                tags=item.tags,
                remixed_from=None,
                install_count=0,
                rating="0.0",
                rating_count=0,
                content_hash=item.content_hash,
                verification_status=item.verification_status,
                flag_count=0,
            )
            session.add(row)
            session.commit()
            logger.info("Published marketplace item: %s by %s", item.name, item.author)
            return item
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # --- install -------------------------------------------------------------

    def install(self, user_id: str, item_id: str) -> InstallRecord:
        """Record an installation and increment the item's install count."""
        self._ensure_seeded()
        session = self._session()
        try:
            row = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            if row is None:
                raise KeyError(f"marketplace item not found: {item_id}")

            row.install_count = (row.install_count or 0) + 1
            row.updated_at = datetime.now(UTC)

            record = InstallRecord(
                user_id=user_id,
                item_id=item_id,
                installed_config=row.config or {},
            )
            install_row = InstallRecordDB(
                id=record.id,
                user_id=user_id,
                item_id=item_id,
                installed_config=record.installed_config,
            )
            session.add(install_row)
            session.commit()
            return record
        except KeyError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # --- remix ---------------------------------------------------------------

    def remix(
        self,
        user_id: str,
        parent_item_id: str,
        name: str,
        description: str,
        config_overrides: dict[str, Any],
        changes_summary: str = "",
    ) -> MarketplaceItem:
        """Remix an existing item: copy config, apply overrides, publish."""
        self._ensure_seeded()
        session = self._session()
        try:
            parent_row = session.query(MarketplaceItemDB).filter_by(id=parent_item_id).first()
            if parent_row is None:
                raise KeyError(f"parent item not found: {parent_item_id}")

            merged_config = dict(parent_row.config or {})
            merged_config.update(config_overrides)

            child = MarketplaceItem(
                name=name,
                item_type=parent_row.item_type,
                author=user_id,
                description=description,
                provenance=Provenance(
                    summary=f"Remix of '{parent_row.name}' by {user_id}",
                    what_it_does=(parent_row.provenance or {}).get("what_it_does", ""),
                    gaps_and_limits=(parent_row.provenance or {}).get("gaps_and_limits", ""),
                    integration_notes=(parent_row.provenance or {}).get("integration_notes", ""),
                    version="0.1.0",
                ),
                config=merged_config,
                tags=list(parent_row.tags or []) + ["remix"],
                remixed_from=parent_item_id,
            )

            child.compute_hash()
            row = MarketplaceItemDB(
                id=child.id,
                name=child.name,
                item_type=child.item_type,
                author=child.author,
                description=child.description,
                provenance=child.provenance.to_dict(),
                config=child.config,
                tags=child.tags,
                remixed_from=child.remixed_from,
                install_count=0,
                rating="0.0",
                rating_count=0,
                content_hash=child.content_hash,
            )
            session.add(row)
            session.commit()
            logger.info("user %s remixed item %s -> %s", user_id, parent_item_id, child.id)
            return _row_to_item(row)
        except KeyError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # --- search / browse -----------------------------------------------------

    def list_items(
        self,
        item_type: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[MarketplaceItem]:
        """Browse marketplace items, optionally filtered."""
        self._ensure_seeded()
        session = self._session()
        try:
            query = session.query(MarketplaceItemDB)
            if item_type:
                query = query.filter(MarketplaceItemDB.item_type == item_type)
            rows = query.all()

            items = [_row_to_item(r) for r in rows]
            if tag:
                items = [i for i in items if tag in i.tags]

            items.sort(key=lambda i: (i.install_count, i.rating), reverse=True)
            return items[:limit]
        finally:
            session.close()

    def get_item(self, item_id: str) -> MarketplaceItem | None:
        """Get a single marketplace item by ID."""
        self._ensure_seeded()
        session = self._session()
        try:
            row = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            return _row_to_item(row) if row else None
        finally:
            session.close()

    def search(self, query: str, limit: int = 20) -> list[MarketplaceItem]:
        """Search items by name, description, tags, or author."""
        self._ensure_seeded()
        session = self._session()
        try:
            rows = session.query(MarketplaceItemDB).all()
            q = query.lower()
            scored: list[tuple[float, MarketplaceItem]] = []

            for row in rows:
                item = _row_to_item(row)
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
        finally:
            session.close()

    # --- rating --------------------------------------------------------------

    def rate_item(self, item_id: str, stars: float) -> MarketplaceItem:
        """Rate an item (1-5 stars). Updates the rolling average."""
        self._ensure_seeded()
        session = self._session()
        try:
            row = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            if row is None:
                raise KeyError(f"marketplace item not found: {item_id}")

            current_sum = float(row.rating or "0.0")
            clamped = max(0.0, min(5.0, stars))
            new_sum = current_sum + clamped
            new_count = (row.rating_count or 0) + 1

            row.rating = str(new_sum)
            row.rating_count = new_count
            row.updated_at = datetime.now(UTC)
            session.commit()

            return _row_to_item(row)
        except KeyError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # --- user installs -------------------------------------------------------

    def get_items_by_author(self, author: str) -> list[MarketplaceItem]:
        """Get all items authored by a user (includes their remixes)."""
        self._ensure_seeded()
        session = self._session()
        try:
            rows = session.query(MarketplaceItemDB).filter_by(author=author).all()
            return [_row_to_item(r) for r in rows]
        finally:
            session.close()

    def get_user_installs(self, user_id: str) -> list[InstallRecord]:
        """Get all items a user has installed."""
        self._ensure_seeded()
        session = self._session()
        try:
            rows = session.query(InstallRecordDB).filter_by(user_id=user_id).all()
            return [_row_to_install(r) for r in rows]
        finally:
            session.close()

    # --- remix history -------------------------------------------------------

    def get_remix_chain(self, item_id: str) -> list[dict[str, Any]]:
        """Trace the remix ancestry of an item."""
        self._ensure_seeded()
        session = self._session()
        try:
            chain: list[dict[str, Any]] = []
            current = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            while current and current.remixed_from:
                parent = session.query(MarketplaceItemDB).filter_by(id=current.remixed_from).first()
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
        finally:
            session.close()

    def get_remixes_of(self, item_id: str) -> list[MarketplaceItem]:
        """Get all items that were remixed from the given item."""
        self._ensure_seeded()
        session = self._session()
        try:
            rows = session.query(MarketplaceItemDB).filter_by(remixed_from=item_id).all()
            return [_row_to_item(r) for r in rows]
        finally:
            session.close()


    def flag_item(
        self, item_id: str, flagged_by: str, reason: str, detail: str = ""
    ) -> FlagRecord | None:
        """Flag a marketplace item for moderation review."""
        self._ensure_seeded()
        session = self._session()
        try:
            row = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            if not row:
                return None
            flag = FlagRecord(
                item_id=item_id,
                flagged_by=flagged_by,
                reason=reason,
                detail=detail,
            )
            # Store flags in a simple JSON column on the item
            flags_data = getattr(row, '_flags', None) or []
            flags_data.append(flag.to_dict())
            # Count unresolved flags
            unresolved = sum(1 for f in flags_data if not f.get("resolved"))
            row.flag_count = unresolved
            if unresolved >= 3:
                row.verification_status = VerificationStatus.FLAGGED.value
            row.updated_at = datetime.now(UTC)
            session.commit()
            return flag
        finally:
            session.close()

    def get_flags(self, item_id: str) -> list[FlagRecord]:
        """Get all flags for an item (in-memory tracking for persistent store)."""
        # Flags are stored transiently; in a full deployment they'd be a DB table
        return []

    def resolve_flag(
        self, flag_id: str, resolution: str
    ) -> FlagRecord | None:
        """Resolve a flag (moderator action)."""
        # In persistent mode, flag resolution would update a flags table
        return None

    def verify_item(
        self, item_id: str, status: str = "author_verified"
    ) -> MarketplaceItem | None:
        """Set the verification status of an item."""
        self._ensure_seeded()
        session = self._session()
        try:
            row = session.query(MarketplaceItemDB).filter_by(id=item_id).first()
            if not row:
                return None
            row.verification_status = status
            row.updated_at = datetime.now(UTC)
            session.commit()
            return _row_to_item(row)
        finally:
            session.close()
