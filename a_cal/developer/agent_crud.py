"""Custom agent spec CRUD — create, read, update, delete beyond the 6 built-ins.

In Developer mode, users can create custom agent specs that extend A-Cal's
agent system. These specs are registered with the AgentRegistry and become
available to the conductor for intent routing.

Custom specs can also be published to the marketplace as agent_spec items,
enabling the community to share and remix agents.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from a_cal.agents.specs import AgentSpec, CognitiveTier, A_CAL_AGENTS


class AgentSpecStore:
    """Store for custom agent specs with optional DB persistence.

    Built-in specs are always available. Custom specs are stored per-user
    and can be created, updated, deleted, and shared. When a ``db``
    (PersistentStore) is provided, custom specs persist to the settings
    table and survive server restarts. Without ``db``, specs are kept
    in-memory (useful for tests and ephemeral sessions).

    Args:
        db: Optional PersistentStore instance for persistence. When
            provided, custom specs are stored under the
            ``custom_agent_specs`` settings key as JSON.
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._custom_specs: Dict[str, AgentSpec] = {}
        if db is not None:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Load custom specs from the database settings table."""
        if self._db is None:
            return
        data = self._db.get_setting("custom_agent_specs", {})
        if not isinstance(data, dict):
            return
        for name, spec_dict in data.items():
            try:
                self._custom_specs[name] = AgentSpec.from_dict(spec_dict)
            except (KeyError, ValueError):
                continue

    def _persist(self) -> None:
        """Save custom specs to the database settings table."""
        if self._db is None:
            return
        data = {name: spec.to_dict() for name, spec in self._custom_specs.items()}
        self._db.set_setting("custom_agent_specs", data)

    def list_all(self, include_builtins: bool = True) -> List[AgentSpec]:
        """List all agent specs (built-in + custom)."""
        specs: List[AgentSpec] = []
        if include_builtins:
            specs.extend(A_CAL_AGENTS)
        specs.extend(self._custom_specs.values())
        return specs

    def list_custom(self) -> List[AgentSpec]:
        """List only custom agent specs."""
        return list(self._custom_specs.values())

    def get(self, name: str) -> Optional[AgentSpec]:
        """Get a spec by name. Checks custom first, then built-in."""
        if name in self._custom_specs:
            return self._custom_specs[name]
        for spec in A_CAL_AGENTS:
            if spec.name == name:
                return spec
        return None

    def create(self, spec: AgentSpec) -> AgentSpec:
        """Create a new custom agent spec.

        Raises ValueError if a spec with the same name already exists
        (built-in or custom).
        """
        # Check for name conflicts with built-ins.
        if any(s.name == spec.name for s in A_CAL_AGENTS):
            raise ValueError(
                f"agent spec name '{spec.name}' conflicts with a built-in spec"
            )
        if spec.name in self._custom_specs:
            raise ValueError(
                f"custom agent spec '{spec.name}' already exists"
            )

        self._custom_specs[spec.name] = spec
        self._persist()
        return spec

    def update(self, name: str, updates: Dict[str, Any]) -> AgentSpec:
        """Update a custom agent spec. Cannot update built-in specs.

        Raises KeyError if the spec doesn't exist.
        Raises ValueError if trying to update a built-in spec.
        """
        if any(s.name == name for s in A_CAL_AGENTS):
            raise ValueError(f"cannot modify built-in spec '{name}'")

        spec = self._custom_specs.get(name)
        if spec is None:
            raise KeyError(f"custom agent spec '{name}' not found")

        # Apply updates to mutable fields.
        if "display_name" in updates:
            spec.display_name = updates["display_name"]
        if "description" in updates:
            spec.description = updates["description"]
        if "system_prompt" in updates:
            spec.system_prompt = updates["system_prompt"]
        if "tools" in updates:
            spec.tools = list(updates["tools"])
        if "default_tier" in updates:
            try:
                spec.default_tier = CognitiveTier(updates["default_tier"])
            except ValueError:
                pass  # ignore invalid tier
        if "can_negotiate" in updates:
            spec.can_negotiate = bool(updates["can_negotiate"])
        if "privacy_force_local" in updates:
            spec.privacy_force_local = bool(updates["privacy_force_local"])
        if "capabilities" in updates:
            spec.capabilities = list(updates["capabilities"])

        self._persist()
        return spec

    def delete(self, name: str) -> bool:
        """Delete a custom agent spec. Cannot delete built-in specs.

        Returns True if deleted, False if not found.
        Raises ValueError if trying to delete a built-in spec.
        """
        if any(s.name == name for s in A_CAL_AGENTS):
            raise ValueError(f"cannot delete built-in spec '{name}'")

        deleted = self._custom_specs.pop(name, None) is not None
        if deleted:
            self._persist()
        return deleted

    def to_dict_list(self, include_builtins: bool = True) -> List[Dict[str, Any]]:
        """Serialize all specs for API response."""
        return [s.to_dict() for s in self.list_all(include_builtins)]
