"""Agent autonomy levels (Q4).

Controls how much freedom agents have to act on the user's behalf.
Three levels, from most conservative to most permissive:

  SUGGEST_ONLY — agents propose actions but never execute. The user
  must approve every change. Safe for first-time users.

  CONFIRM — agents execute actions but ask for confirmation first.
  This is the default: agentic but secure.

  FULL_AUTO — agents execute actions automatically without asking.
  For experienced users who trust their agents.

Autonomy can be set globally (default for all sub-accounts) and
overridden per sub-account. The conductor checks the effective level
before executing actions.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Dict, Optional


class AutonomyLevel(str, enum.Enum):
    """Three autonomy tiers, from conservative to permissive."""

    SUGGEST_ONLY = "suggest_only"
    CONFIRM = "confirm"
    FULL_AUTO = "full_auto"


@dataclass
class AutonomyConfig:
    """Global autonomy settings."""

    default_level: str = AutonomyLevel.CONFIRM.value
    # Per-sub-account overrides: sub_account_id -> level
    per_sub_account: Dict[str, str] = None

    def __post_init__(self):
        if self.per_sub_account is None:
            self.per_sub_account = {}

    def resolve(self, sub_account_id: Optional[str] = None) -> AutonomyLevel:
        """Resolve the effective autonomy level for a sub-account.

        Per-sub-account override takes precedence; falls back to the
        global default.
        """
        if sub_account_id and sub_account_id in self.per_sub_account:
            try:
                return AutonomyLevel(self.per_sub_account[sub_account_id])
            except ValueError:
                pass
        try:
            return AutonomyLevel(self.default_level)
        except ValueError:
            return AutonomyLevel.CONFIRM

    def should_execute(self, sub_account_id: Optional[str] = None) -> bool:
        """Whether the agent should execute actions without asking.

        True for FULL_AUTO, False for SUGGEST_ONLY and CONFIRM.
        """
        return self.resolve(sub_account_id) == AutonomyLevel.FULL_AUTO

    def should_confirm(self, sub_account_id: Optional[str] = None) -> bool:
        """Whether the agent should ask for confirmation before executing.

        True for CONFIRM, False for SUGGEST_ONLY and FULL_AUTO.
        """
        return self.resolve(sub_account_id) == AutonomyLevel.CONFIRM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_level": self.default_level,
            "per_sub_account": dict(self.per_sub_account),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomyConfig":
        return cls(
            default_level=data.get("default_level", AutonomyLevel.CONFIRM.value),
            per_sub_account=dict(data.get("per_sub_account", {})),
        )
