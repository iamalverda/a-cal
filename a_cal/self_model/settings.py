"""Self-model settings — the user's control panel.

This is the configuration object that gates what the self-model is allowed to
learn, at what depth, and with what privacy constraints. It is stored per-user
and exposed in the A-Cal settings UI (Simple mode shows depth slider; Pro mode
shows granular category toggles).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from a_cal.self_model.types import FactCategory, PrivacyTier, SelfModelDepth


@dataclass
class SelfModelSettings:
    """User-controlled configuration for the self-model.

    Defaults are conservative (pattern_memory depth, cloud sync off, most
    sensitive categories off). Escalation is always opt-in.
    """

    # The user's chosen depth level.
    depth: str = SelfModelDepth.PATTERN_MEMORY.value

    # Granular category toggles. If a category is not in this dict, it defaults
    # to off. The UI populates this with all categories at the chosen depth,
    # pre-checked for pattern-level categories and unchecked for deeper ones.
    enabled_categories: Dict[str, bool] = field(default_factory=dict)

    # Privacy controls.
    cloud_sync_enabled: bool = False       # encrypted sync of the model, off by default
    cloud_sync_encryption_key_ref: str = ""  # handle into atom's encrypted storage
    proactive_suggestions_enabled: bool = False

    # Which interaction surfaces the self-model feeds into.
    feed_into_calendar_view: bool = True   # color-code by energy, show context
    feed_into_agents: bool = True          # inject context into agent prompts
    feed_into_proactive: bool = False      # unprompted nudges (opt-in)

    # Retention: how long to keep facts before they age out (days). 0 = forever.
    retention_days: int = 0

    def effective_depth(self) -> SelfModelDepth:
        """Parse the depth string into the enum."""
        try:
            return SelfModelDepth(self.depth)
        except ValueError:
            return SelfModelDepth.PATTERN_MEMORY

    def is_category_enabled(self, category: FactCategory) -> bool:
        """Whether the user has enabled a specific category.

        A category is enabled only if:
        1. The user's depth level includes the category's minimum depth, AND
        2. The user hasn't explicitly toggled it off.
        """
        if not self.effective_depth().includes(category.min_depth()):
            return False
        return self.enabled_categories.get(category.value, False)

    def available_categories(self) -> List[FactCategory]:
        """All categories available at the current depth (before user toggles)."""
        return FactCategory.for_depth(self.effective_depth())

    def enabled_category_list(self) -> List[FactCategory]:
        """Only the categories the user has actually turned on."""
        return [c for c in FactCategory if self.is_category_enabled(c)]

    def privacy_tier_for(self, category: FactCategory) -> PrivacyTier:
        """Determine the privacy tier for a category.

        Longitudinal-identity categories are always TIER_LOCAL (forced local).
        Attention/intent categories are TIER_PREFERENCE (local by default).
        Pattern categories are TIER_PATTERN (can go to cloud).
        """
        if category.min_depth() == SelfModelDepth.LONGITUDINAL_IDENTITY:
            return PrivacyTier.TIER_LOCAL
        if category.min_depth() == SelfModelDepth.ATTENTION_INTENT:
            return PrivacyTier.TIER_PREFERENCE
        return PrivacyTier.TIER_PATTERN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depth": self.depth,
            "enabled_categories": dict(self.enabled_categories),
            "cloud_sync_enabled": self.cloud_sync_enabled,
            "cloud_sync_encryption_key_ref": self.cloud_sync_encryption_key_ref,
            "proactive_suggestions_enabled": self.proactive_suggestions_enabled,
            "feed_into_calendar_view": self.feed_into_calendar_view,
            "feed_into_agents": self.feed_into_agents,
            "feed_into_proactive": self.feed_into_proactive,
            "retention_days": self.retention_days,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelfModelSettings":
        return cls(
            depth=data.get("depth", SelfModelDepth.PATTERN_MEMORY.value),
            enabled_categories=dict(data.get("enabled_categories", {})),
            cloud_sync_enabled=data.get("cloud_sync_enabled", False),
            cloud_sync_encryption_key_ref=data.get("cloud_sync_encryption_key_ref", ""),
            proactive_suggestions_enabled=data.get("proactive_suggestions_enabled", False),
            feed_into_calendar_view=data.get("feed_into_calendar_view", True),
            feed_into_agents=data.get("feed_into_agents", True),
            feed_into_proactive=data.get("feed_into_proactive", False),
            retention_days=data.get("retention_days", 0),
        )

    @classmethod
    def default_for_depth(cls, depth: SelfModelDepth) -> "SelfModelSettings":
        """Create settings at a given depth with sensible category defaults.

        Pattern-level categories are on by default; deeper categories require
        explicit opt-in (off by default).
        """
        cats: Dict[str, bool] = {}
        for cat in FactCategory.for_depth(depth):
            # Only pattern-level categories are auto-enabled. Deeper ones are off.
            cats[cat.value] = cat.min_depth() == SelfModelDepth.PATTERN_MEMORY
        return cls(depth=depth.value, enabled_categories=cats)
