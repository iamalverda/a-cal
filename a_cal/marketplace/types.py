"""Marketplace types — shared config items, provenance, and install/remix records.

The marketplace lets the A-Cal community share, install, and remix:
  - Agent specs (custom agents with system prompts, tools, routing)
  - Sync rule packs (include/exclude/transform rules for sub-accounts)
  - Negotiation strategies (how conflict resolution behaves)
  - UI themes (visual customization)
  - Plugin configs (third-party integrations)

Every item carries structured provenance (from the meta-cognition protocol's
methodology output format) so the community can audit what a shared config
actually does before installing it.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Any, Dict, List, Optional

from a_cal.marketplace.trust import (
    compute_content_hash,
    compute_trust_score,
    VerificationStatus,
)


class MarketplaceItemType(str, enum.Enum):
    """What kind of thing can be shared on the marketplace."""

    AGENT_SPEC = "agent_spec"
    SYNC_RULE_PACK = "sync_rule_pack"
    NEGOTIATION_STRATEGY = "negotiation_strategy"
    UI_THEME = "ui_theme"
    PLUGIN_CONFIG = "plugin_config"


@dataclass
class Provenance:
    """Structured provenance metadata for a marketplace item.

    Borrowed from the meta-cognition research protocol's methodology output
    format (structured research synthesis → structured config synthesis).
    The community can read this to understand what a shared config does,
    what it can't do, and how it connects to other components — before
    installing it.
    """

    summary: str = ""
    what_it_does: str = ""
    gaps_and_limits: str = ""
    integration_notes: str = ""
    version: str = "0.1.0"
    license: str = "AGPL-3.0-or-later"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "what_it_does": self.what_it_does,
            "gaps_and_limits": self.gaps_and_limits,
            "integration_notes": self.integration_notes,
            "version": self.version,
            "license": self.license,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            summary=data.get("summary", ""),
            what_it_does=data.get("what_it_does", ""),
            gaps_and_limits=data.get("gaps_and_limits", ""),
            integration_notes=data.get("integration_notes", ""),
            version=data.get("version", "0.1.0"),
            license=data.get("license", "AGPL-3.0-or-later"),
        )


@dataclass
class MarketplaceItem:
    """One shared configuration on the marketplace.

    An item is a self-contained, serializable config that can be installed
    into a user's A-Cal instance. Items can be remixed (forked + modified),
    creating a new item that references the original as its parent.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    item_type: str = ""  # MarketplaceItemType value
    author: str = ""
    description: str = ""
    provenance: Provenance = field(default_factory=Provenance)
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    # Remix chain: if this item was forked from another, that item's id.
    remixed_from: str | None = None
    # Community metrics.
    install_count: int = 0
    rating_sum: float = 0.0
    rating_count: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str | None = None
    # Trust & moderation fields.
    content_hash: str = ""
    verification_status: str = VerificationStatus.UNVERIFIED.value
    flag_count: int = 0

    @property
    def rating(self) -> float:
        """Average rating (0.0–5.0), or 0 if unrated."""
        if self.rating_count == 0:
            return 0.0
        return self.rating_sum / self.rating_count

    def add_rating(self, stars: float) -> None:
        """Add a rating (1–5 stars). Updates the rolling average."""
        clamped = max(0.0, min(5.0, stars))
        self.rating_sum += clamped
        self.rating_count += 1
        self.updated_at = datetime.now(UTC).isoformat()

    @property
    def trust_score(self) -> float:
        """Computed trust score (0.0–100.0) based on ratings, installs,
        verification status, flags, and author track record."""
        return compute_trust_score(
            rating=self.rating,
            rating_count=self.rating_count,
            install_count=self.install_count,
            flag_count=self.flag_count,
            verification_status=self.verification_status,
        )

    def compute_hash(self) -> str:
        """Compute and store the content hash for integrity verification."""
        self.content_hash = compute_content_hash(self.config)
        return self.content_hash

    def record_install(self) -> None:
        """Increment the install counter."""
        self.install_count += 1
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type,
            "author": self.author,
            "description": self.description,
            "provenance": self.provenance.to_dict(),
            "config": dict(self.config),
            "tags": list(self.tags),
            "remixed_from": self.remixed_from,
            "install_count": self.install_count,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content_hash": self.content_hash,
            "verification_status": self.verification_status,
            "flag_count": self.flag_count,
            "trust_score": self.trust_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceItem:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            item_type=data.get("item_type", ""),
            author=data.get("author", ""),
            description=data.get("description", ""),
            provenance=Provenance.from_dict(data.get("provenance", {})),
            config=dict(data.get("config", {})),
            tags=list(data.get("tags", [])),
            remixed_from=data.get("remixed_from"),
            install_count=data.get("install_count", 0),
            rating_sum=data.get("rating_sum", 0.0),
            rating_count=data.get("rating_count", 0),
            created_at=data.get(
                "created_at", datetime.now(UTC).isoformat()
            ),
            updated_at=data.get("updated_at"),
            content_hash=data.get("content_hash", ""),
            verification_status=data.get(
                "verification_status", VerificationStatus.UNVERIFIED.value
            ),
            flag_count=data.get("flag_count", 0),
        )


@dataclass
class InstallRecord:
    """Tracks that a user has installed a marketplace item."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    item_id: str = ""
    installed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    # The config as installed (may differ from the current marketplace version
    # if the user modified it after installing).
    installed_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "item_id": self.item_id,
            "installed_at": self.installed_at,
            "installed_config": dict(self.installed_config),
        }


@dataclass
class RemixRecord:
    """Tracks that one item was remixed (forked) from another."""

    parent_item_id: str = ""
    child_item_id: str = ""
    remixed_by: str = ""  # user_id
    remixed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    # What changed in the remix (human-readable diff summary).
    changes_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_item_id": self.parent_item_id,
            "child_item_id": self.child_item_id,
            "remixed_by": self.remixed_by,
            "remixed_at": self.remixed_at,
            "changes_summary": self.changes_summary,
        }
