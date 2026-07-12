"""Plugin system — extensible interface for custom agents, providers, and rules.

A plugin is a self-contained module that extends A-Cal with new functionality.
Plugins are registered with the PluginRegistry, which the conductor and sync
engine query to discover available extensions.

Plugin types:
  - AGENT: adds a new specialist agent to the conductor's routing
  - PROVIDER: adds a new calendar/email provider
  - SYNC_RULE: adds a new sync rule type
  - UI_COMPONENT: adds a custom UI component to the frontend
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


class PluginType(str, enum.Enum):
    """What kind of thing a plugin provides."""

    AGENT = "agent"
    PROVIDER = "provider"
    SYNC_RULE = "sync_rule"
    UI_COMPONENT = "ui_component"


@dataclass
class PluginBase:
    """Base specification for a plugin.

    A plugin is data (a declarative spec) plus an optional factory callable
    that produces the runtime object. This lets plugins be:
      - Registered and discovered by the conductor/sync engine
      - Exported/imported as JSON (config-as-code)
      - Shared on the marketplace (as plugin_config items)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    plugin_type: str = ""  # PluginType value
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    # The plugin's configuration schema (what settings it accepts).
    config_schema: Dict[str, Any] = field(default_factory=dict)
    # Default config values.
    default_config: Dict[str, Any] = field(default_factory=dict)
    # Whether the plugin is enabled.
    enabled: bool = True
    # Factory function that produces the runtime object (agent, provider, etc.).
    # In standalone mode, this may be None (data-only plugin).
    factory: Optional[Callable] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plugin_type": self.plugin_type,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "config_schema": dict(self.config_schema),
            "default_config": dict(self.default_config),
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginBase":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            plugin_type=data.get("plugin_type", ""),
            version=data.get("version", "0.1.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            config_schema=dict(data.get("config_schema", {})),
            default_config=dict(data.get("default_config", {})),
            enabled=data.get("enabled", True),
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        )


class PluginRegistry:
    """In-memory plugin registry.

    In the full atom deployment, plugins are persisted in the database.
    In standalone mode, plugins are registered in memory and lost on restart.
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginBase] = {}

    def register(self, plugin: PluginBase) -> PluginBase:
        """Register a plugin."""
        self._plugins[plugin.id] = plugin
        return plugin

    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin. Returns True if it existed."""
        return self._plugins.pop(plugin_id, None) is not None

    def get(self, plugin_id: str) -> Optional[PluginBase]:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def list_plugins(
        self,
        plugin_type: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[PluginBase]:
        """List plugins, optionally filtered by type or enabled status."""
        plugins = list(self._plugins.values())
        if plugin_type:
            plugins = [p for p in plugins if p.plugin_type == plugin_type]
        if enabled_only:
            plugins = [p for p in plugins if p.enabled]
        return plugins

    def enable(self, plugin_id: str) -> Optional[PluginBase]:
        """Enable a plugin."""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.enabled = True
        return plugin

    def disable(self, plugin_id: str) -> Optional[PluginBase]:
        """Disable a plugin."""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.enabled = False
        return plugin

    def update_config(
        self, plugin_id: str, config: Dict[str, Any]
    ) -> Optional[PluginBase]:
        """Update a plugin's default config."""
        plugin = self._plugins.get(plugin_id)
        if plugin:
            plugin.default_config.update(config)
        return plugin

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serialize all plugins for API response."""
        return [p.to_dict() for p in self._plugins.values()]
