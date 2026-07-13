"""Core types for the self-model.

The depth hierarchy, fact categories, privacy tiers, and the SelfModelFact
data structure that the store and extractor operate on.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Any, Dict, Optional


class SelfModelDepth(str, enum.Enum):
    """Escalating depth levels for the self-model (Q2).

    Each level is a superset of the one below it. The user's chosen depth gates
    which fact categories the extractor is allowed to derive.
    """

    PATTERN_MEMORY = "pattern_memory"
    ATTENTION_INTENT = "attention_intent"
    LONGITUDINAL_IDENTITY = "longitudinal_identity"

    @classmethod
    def levels(cls) -> list[SelfModelDepth]:
        """Ordered from shallowest to deepest."""
        return [cls.PATTERN_MEMORY, cls.ATTENTION_INTENT, cls.LONGITUDINAL_IDENTITY]

    def includes(self, other: SelfModelDepth) -> bool:
        """Whether this depth level encompasses another."""
        order = {d: i for i, d in enumerate(self.levels())}
        return order[self] >= order[other]


class FactCategory(str, enum.Enum):
    """What the self-model can learn about the user.

    Each category is tagged with the minimum depth required to extract it.
    The user can toggle individual categories off within their chosen depth.
    """

    # --- pattern_memory level ---
    BUSY_TIMES = "busy_times"               # recurring busy slots, cadence
    MEETING_PATTERNS = "meeting_patterns"    # frequent meeting types, durations
    TIMEZONE_HABITS = "timezone_habits"      # travel, TZ shifts
    RESPONSE_CADENCE = "response_cadence"    # how fast you reply, when

    # --- attention_intent level ---
    WORK_FOCUS = "work_focus"                # current projects, priorities
    ENERGY_PATTERNS = "energy_patterns"       # morning person, post-lunch slump
    MEETING_PREFS = "meeting_prefs"           # prefers async, no mornings, etc.
    ATTENTION_SIGNALS = "attention_signals"  # what you prioritize, deprioritize

    # --- longitudinal_identity level ---
    GOALS = "goals"                           # evolving short/long-term goals
    RELATIONSHIPS = "relationships"           # recurring contacts, their context
    ROLE_CONTEXT = "role_context"             # job title, team, responsibilities
    LIFE_CONTEXT = "life_context"             # personal commitments, constraints

    @classmethod
    def for_depth(cls, depth: SelfModelDepth) -> list[FactCategory]:
        """Categories available at a given depth level."""
        result: list[FactCategory] = []
        for cat in cls:
            if cat.min_depth().includes(depth) or cat.min_depth() == depth:
                if depth.includes(cat.min_depth()):
                    result.append(cat)
        return result

    def min_depth(self) -> SelfModelDepth:
        """The minimum depth at which this category becomes available."""
        _PATTERN = {
            FactCategory.BUSY_TIMES,
            FactCategory.MEETING_PATTERNS,
            FactCategory.TIMEZONE_HABITS,
            FactCategory.RESPONSE_CADENCE,
        }
        _ATTENTION = {
            FactCategory.WORK_FOCUS,
            FactCategory.ENERGY_PATTERNS,
            FactCategory.MEETING_PREFS,
            FactCategory.ATTENTION_SIGNALS,
        }
        if self in _PATTERN:
            return SelfModelDepth.PATTERN_MEMORY
        if self in _ATTENTION:
            return SelfModelDepth.ATTENTION_INTENT
        return SelfModelDepth.LONGITUDINAL_IDENTITY


class PrivacyTier(str, enum.Enum):
    """How sensitive a fact is — drives model routing (Q4 privacy-tiered).

    TIER_LOCAL forces the fact to local-only models regardless of the global
    model setting. This is the mechanism that keeps personal/identity content
    off cloud models.
    """

    TIER_LOCAL = "local"          # forced local — personal, identity, email content
    TIER_PREFERENCE = "preference"  # local by default, user can opt to cloud
    TIER_PATTERN = "pattern"      # can go to cloud if global setting allows

    @property
    def forces_local(self) -> bool:
        return self == PrivacyTier.TIER_LOCAL


@dataclass
class SelfModelFact:
    """One piece of knowledge the self-model holds about the user.

    Every fact is transparent and correctable: it carries provenance (where it
    was learned), confidence, a timestamp, and can be superseded or deleted by
    the user at any time.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = ""               # FactCategory value
    content: str = ""                # human-readable statement
    depth: str = ""                   # SelfModelDepth at which it was extracted
    privacy_tier: str = ""           # PrivacyTier value
    confidence: float = 0.0          # 0.0–1.0, EWMA-updated on re-observation
    provenance: str = ""             # "calendar:google:2026-07-10" etc.
    source_event_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str | None = None
    superseded_by: str | None = None  # id of a newer fact that replaced this
    status: str = "active"           # active | superseded | deleted

    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "content": self.content,
            "depth": self.depth,
            "privacy_tier": self.privacy_tier,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "source_event_ids": self.source_event_ids,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "superseded_by": self.superseded_by,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelfModelFact:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            category=data.get("category", ""),
            content=data.get("content", ""),
            depth=data.get("depth", ""),
            privacy_tier=data.get("privacy_tier", ""),
            confidence=data.get("confidence", 0.0),
            provenance=data.get("provenance", ""),
            source_event_ids=data.get("source_event_ids", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at"),
            superseded_by=data.get("superseded_by"),
            status=data.get("status", "active"),
        )

    def content_hash(self) -> str:
        """Stable hash for dedup — category + normalized content."""
        import hashlib
        normalized = f"{self.category}:{self.content.strip().lower()}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
