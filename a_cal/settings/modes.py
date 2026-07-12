"""Skill progression modes — Simple / Pro / Developer (Q9).

Each mode is a configuration that gates which features, settings, and UI
surfaces are visible. Modes are additive — Pro includes everything in Simple,
Developer includes everything in Pro. The user can switch modes at any time
from settings; the switch is reversible and non-destructive.

Mode configs drive both the frontend (which panels to show) and the backend
(which settings to enforce as defaults).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class SkillMode(str, enum.Enum):
    """The three named modes (Q9)."""

    SIMPLE = "simple"
    PRO = "pro"
    DEVELOPER = "developer"


@dataclass
class ModeConfig:
    """Configuration for one skill mode.

    Drives the UI (which panels/settings are visible) and the backend (which
    defaults are enforced, which features are gated).
    """

    mode: SkillMode
    display_name: str
    description: str
    # UI surfaces visible in this mode
    visible_panels: List[str] = field(default_factory=list)
    # Settings that are shown (others are hidden but still effective)
    visible_settings: List[str] = field(default_factory=list)
    # Default sync mode for new sub-accounts
    default_sync_mode: str = "mirror_filter"
    # Whether per-task model routing is exposed
    per_task_model_routing: bool = False
    # Whether the Developer Studio is accessible
    developer_studio: bool = False
    # Whether config-as-code (export/import JSON) is available
    config_as_code: bool = False
    # Whether the visual workflow builder is available
    visual_builder: bool = False
    # Whether the plugin system is accessible
    plugin_system: bool = False
    # Whether the API/SDK is documented and accessible
    api_sdk: bool = False
    # Whether marketplace/community features are visible
    marketplace: bool = False
    # Default self-model depth
    default_self_model_depth: str = "pattern_memory"
    # Whether proactive suggestions are on by default
    default_proactive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "display_name": self.display_name,
            "description": self.description,
            "visible_panels": self.visible_panels,
            "visible_settings": self.visible_settings,
            "default_sync_mode": self.default_sync_mode,
            "per_task_model_routing": self.per_task_model_routing,
            "developer_studio": self.developer_studio,
            "config_as_code": self.config_as_code,
            "visual_builder": self.visual_builder,
            "plugin_system": self.plugin_system,
            "api_sdk": self.api_sdk,
            "marketplace": self.marketplace,
            "default_self_model_depth": self.default_self_model_depth,
            "default_proactive": self.default_proactive,
        }


SIMPLE_MODE = ModeConfig(
    mode=SkillMode.SIMPLE,
    display_name="Simple",
    description="For beginners and non-technical users. Clean calendar, basic settings, one model.",
    visible_panels=["calendar", "command_bar", "basic_settings", "sub_accounts"],
    visible_settings=["model", "theme", "notifications", "sub_account_visibility"],
    default_sync_mode="mirror_filter",
    per_task_model_routing=False,
    developer_studio=False,
    config_as_code=False,
    visual_builder=True,
    plugin_system=False,
    api_sdk=False,
    marketplace=False,
    default_self_model_depth="pattern_memory",
    default_proactive=False,
)

PRO_MODE = ModeConfig(
    mode=SkillMode.PRO,
    display_name="Pro",
    description="For power users. Plugins, advanced settings, per-task model overrides, config-as-code.",
    visible_panels=[
        "calendar", "command_bar", "chat_panel", "advanced_settings",
        "sub_accounts", "sync_rules", "self_model_settings", "proactive_settings",
    ],
    visible_settings=[
        "model", "per_task_models", "theme", "notifications", "sub_account_visibility",
        "sync_mode", "sync_rules", "self_model_depth", "self_model_categories",
        "privacy_tiers", "proactive_suggestions", "interaction_model",
    ],
    default_sync_mode="mirror_filter",
    per_task_model_routing=True,
    developer_studio=False,
    config_as_code=True,
    visual_builder=True,
    plugin_system=True,
    api_sdk=False,
    marketplace=True,
    default_self_model_depth="attention_intent",
    default_proactive=True,
)

DEVELOPER_MODE = ModeConfig(
    mode=SkillMode.DEVELOPER,
    display_name="Developer",
    description="For developers. Everything in Pro plus API/SDK, Developer Studio, and full customization.",
    visible_panels=[
        "calendar", "command_bar", "chat_panel", "advanced_settings",
        "sub_accounts", "sync_rules", "self_model_settings", "proactive_settings",
        "developer_studio", "api_explorer", "plugin_manager", "marketplace_dev",
    ],
    visible_settings=[
        "model", "per_task_models", "theme", "notifications", "sub_account_visibility",
        "sync_mode", "sync_rules", "self_model_depth", "self_model_categories",
        "privacy_tiers", "proactive_suggestions", "interaction_model",
        "api_keys", "webhook_urls", "plugin_dev", "agent_specs",
    ],
    default_sync_mode="mirror_filter",
    per_task_model_routing=True,
    developer_studio=True,
    config_as_code=True,
    visual_builder=True,
    plugin_system=True,
    api_sdk=True,
    marketplace=True,
    default_self_model_depth="attention_intent",
    default_proactive=True,
)

ALL_MODES: Dict[str, ModeConfig] = {
    SkillMode.SIMPLE.value: SIMPLE_MODE,
    SkillMode.PRO.value: PRO_MODE,
    SkillMode.DEVELOPER.value: DEVELOPER_MODE,
}


def get_mode_config(mode: str) -> ModeConfig:
    """Get the config for a mode string. Falls back to SIMPLE."""
    return ALL_MODES.get(mode, SIMPLE_MODE)
