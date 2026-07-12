"""Config-as-code — export and import A-Cal configuration as JSON.

In Developer mode, users can export their entire A-Cal configuration
(sub-accounts, sync rules, model routing, self-model settings, skill mode,
agent specs, plugins) as a single JSON file, and import it into another
instance. This enables:
  - Version-controllable configurations (git-track your calendar setup)
  - Sharing complete configurations (not just individual marketplace items)
  - Backup and restore
  - Reproducible development environments
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from a_cal.settings.modes import get_mode_config
from a_cal.settings.model_routing import ModelRoutingConfig
from a_cal.self_model.settings import SelfModelSettings
from a_cal.agents.specs import A_CAL_AGENTS


# Schema version for exported configs — bump when the format changes.
CONFIG_SCHEMA_VERSION = "1.0.0"


class ConfigExporter:
    """Exports A-Cal configuration as a serializable dict (JSON-compatible)."""

    def __init__(
        self,
        mode: str = "simple",
        model_routing: Optional[ModelRoutingConfig] = None,
        self_model_settings: Optional[SelfModelSettings] = None,
        custom_agent_specs: Optional[list[Dict[str, Any]]] = None,
        plugins: Optional[list[Dict[str, Any]]] = None,
        sub_accounts: Optional[list[Dict[str, Any]]] = None,
    ) -> None:
        self.mode = mode
        self.model_routing = model_routing or ModelRoutingConfig()
        self.self_model_settings = self_model_settings or SelfModelSettings()
        self.custom_agent_specs = custom_agent_specs or []
        self.plugins = plugins or []
        self.sub_accounts = sub_accounts or []

    def export(self) -> Dict[str, Any]:
        """Export the full configuration as a JSON-serializable dict."""
        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "mode": get_mode_config(self.mode).to_dict(),
            "model_routing": self.model_routing.to_dict(),
            "self_model": self.self_model_settings.to_dict(),
            "custom_agent_specs": list(self.custom_agent_specs),
            "plugins": list(self.plugins),
            "sub_accounts": list(self.sub_accounts),
            "built_in_agent_count": len(A_CAL_AGENTS),
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as a JSON string."""
        return json.dumps(self.export(), indent=indent, sort_keys=True)


class ConfigImporter:
    """Imports A-Cal configuration from a serialized dict.

    Validates the schema version and reconstructs the typed config objects.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def import_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Import a configuration dict.

        Returns a dict of typed config objects:
          - mode: str
          - model_routing: ModelRoutingConfig
          - self_model: SelfModelSettings
          - custom_agent_specs: list[dict]
          - plugins: list[dict]
          - sub_accounts: list[dict]
        """
        self.errors = []
        self.warnings = []

        # Check schema version.
        version = data.get("schema_version", "unknown")
        if version != CONFIG_SCHEMA_VERSION:
            self.warnings.append(
                f"schema version mismatch: expected {CONFIG_SCHEMA_VERSION}, got {version}"
            )

        result: Dict[str, Any] = {}

        # Mode.
        mode_data = data.get("mode", {})
        if isinstance(mode_data, dict) and "mode" in mode_data:
            result["mode"] = mode_data["mode"]
        else:
            result["mode"] = "simple"
            self.warnings.append("mode not found, defaulting to simple")

        # Model routing.
        routing_data = data.get("model_routing", {})
        try:
            result["model_routing"] = ModelRoutingConfig.from_dict(routing_data)
        except Exception as exc:
            self.errors.append(f"model_routing import failed: {exc}")
            result["model_routing"] = ModelRoutingConfig()

        # Self-model settings.
        sm_data = data.get("self_model", {})
        try:
            result["self_model"] = SelfModelSettings.from_dict(sm_data)
        except Exception as exc:
            self.errors.append(f"self_model import failed: {exc}")
            result["self_model"] = SelfModelSettings()

        # Custom agent specs.
        result["custom_agent_specs"] = list(data.get("custom_agent_specs", []))

        # Plugins.
        result["plugins"] = list(data.get("plugins", []))

        # Sub-accounts.
        result["sub_accounts"] = list(data.get("sub_accounts", []))

        return result

    def import_json(self, json_str: str) -> Dict[str, Any]:
        """Import from a JSON string."""
        data = json.loads(json_str)
        return self.import_config(data)
