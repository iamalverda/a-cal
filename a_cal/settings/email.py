"""Email integration depth settings.

Controls how deeply A-Cal's agents integrate with the user's email.
Three depth levels (charter §5):

  1. **SYNC_NOTIFY** — read the inbox for events/invites, send notifications.
     No agent-mediated actions; the user handles everything manually.
  2. **AGENT_MEDIATED** — parse emails into events/contacts/actions and draft
     replies for the user to approve. Agents suggest but do not send.
  3. **FULL_TWO_WAY** — send/decline/renegotiate within per-provider
     permissions; email-side memory is tied to events. Agents can act
     autonomously (subject to the autonomy settings).

The depth is a separate setting from the provider connection — a user can
have Gmail connected for sync & notify only, or fully agent-mediated.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict


class EmailDepth(str, enum.Enum):
    """How deeply agents integrate with email."""

    SYNC_NOTIFY = "sync_notify"
    AGENT_MEDIATED = "agent_mediated"
    FULL_TWO_WAY = "full_two_way"

    @classmethod
    def default(cls) -> "EmailDepth":
        return cls.SYNC_NOTIFY


# Human-readable labels for the UI.
EMAIL_DEPTH_LABELS: Dict[str, str] = {
    EmailDepth.SYNC_NOTIFY.value: "Sync & Notify",
    EmailDepth.AGENT_MEDIATED.value: "Agent-Mediated Inbox",
    EmailDepth.FULL_TWO_WAY.value: "Full Two-Way Agent",
}

EMAIL_DEPTH_DESCRIPTIONS: Dict[str, str] = {
    EmailDepth.SYNC_NOTIFY.value: (
        "Read inbox for events and invites. Send notifications. "
        "No agent actions — you handle everything manually."
    ),
    EmailDepth.AGENT_MEDIATED.value: (
        "Parse emails into events, contacts, and actions. Draft replies "
        "for your approval. Agents suggest but do not send."
    ),
    EmailDepth.FULL_TWO_WAY.value: (
        "Send, decline, and renegotiate within provider permissions. "
        "Email-side memory tied to events. Agents act autonomously "
        "(subject to autonomy settings)."
    ),
}


@dataclass
class EmailIntegrationConfig:
    """User's email integration depth and per-provider overrides.

    The ``depth`` field is the global default. ``per_provider`` lets the
    user set a different depth for specific providers (e.g. Gmail on
    full two-way but work Exchange on sync & notify only).
    """

    depth: str = EmailDepth.SYNC_NOTIFY.value
    per_provider: Dict[str, str] = field(default_factory=dict)
    # Whether to scan the inbox for scheduling content (meeting proposals,
    # invites, reschedules). Off in sync_notify by default since the user
    # is handling things manually.
    auto_scan_enabled: bool = False

    def effective_depth(self, provider_type: str | None = None) -> EmailDepth:
        """Resolve the depth for a given provider, falling back to global."""
        if provider_type and provider_type in self.per_provider:
            try:
                return EmailDepth(self.per_provider[provider_type])
            except ValueError:
                pass
        try:
            return EmailDepth(self.depth)
        except ValueError:
            return EmailDepth.default()

    def allows_agent_actions(self, provider_type: str | None = None) -> bool:
        """True if the current depth permits agent-mediated actions."""
        return self.effective_depth(provider_type) in (
            EmailDepth.AGENT_MEDIATED,
            EmailDepth.FULL_TWO_WAY,
        )

    def allows_autonomous_send(self, provider_type: str | None = None) -> bool:
        """True if agents may send without explicit per-message approval."""
        return self.effective_depth(provider_type) == EmailDepth.FULL_TWO_WAY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depth": self.depth,
            "per_provider": dict(self.per_provider),
            "auto_scan_enabled": self.auto_scan_enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailIntegrationConfig":
        return cls(
            depth=data.get("depth", EmailDepth.SYNC_NOTIFY.value),
            per_provider=dict(data.get("per_provider", {})),
            auto_scan_enabled=data.get("auto_scan_enabled", False),
        )
