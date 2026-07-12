"""Agent registry — bridges A-Cal agents into atom's agent system.

In the full atom deployment, this registers A-Cal's conductor and specialists
with atom's AgentRegistry / AtomMetaAgent so they appear in atom's agent
management UI and can be dispatched by atom's intent classifier.

In standalone mode (no atom), the registry is a simple in-memory store that
the API layer uses to list available agents and their specs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from a_cal.agents.specs import A_CAL_AGENTS, A_CAL_AGENTS_BY_NAME, AgentSpec

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry of A-Cal agents — the bridge to atom's agent system.

    Usage in atom:
        registry = AgentRegistry()
        registry.register_with_atom(atom_meta_agent)

    Usage standalone:
        registry = AgentRegistry()
        specs = registry.list_agents()
        spec = registry.get("a_cal_schedule_agent")
    """

    def __init__(self, custom_specs: Optional[List[AgentSpec]] = None) -> None:
        """Initialize with the built-in agents plus any user customizations.

        Custom specs (from the marketplace or Developer Studio) override
        built-ins by name, allowing users to customize agent behavior without
        forking the codebase.
        """
        self._agents: Dict[str, AgentSpec] = {a.name: a for a in A_CAL_AGENTS}
        if custom_specs:
            for spec in custom_specs:
                self._agents[spec.name] = spec

    def list_agents(self) -> List[AgentSpec]:
        """All registered agents, conductor first."""
        result = []
        if "a_cal_conductor" in self._agents:
            result.append(self._agents["a_cal_conductor"])
        for name, spec in self._agents.items():
            if name != "a_cal_conductor":
                result.append(spec)
        return result

    def get(self, name: str) -> Optional[AgentSpec]:
        return self._agents.get(name)

    def register(self, spec: AgentSpec) -> None:
        """Register or override an agent spec (used by Developer Studio / marketplace)."""
        self._agents[spec.name] = spec
        logger.info("registered agent: %s", spec.name)

    def unregister(self, name: str) -> bool:
        """Remove an agent (only custom agents, not built-in specialists)."""
        if name in self._agents and name not in A_CAL_AGENTS_BY_NAME:
            del self._agents[name]
            return True
        return False

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serialize all agents for the API/UI."""
        return [a.to_dict() for a in self.list_agents()]

    def register_with_atom(self, atom_meta_agent: Any) -> None:
        """Register A-Cal agents with atom's AtomMetaAgent.

        This is called during atom integration (Phase 0 wiring). It registers
        the conductor as an intent handler and the specialists as dispatchable
        agents in atom's agent registry.

        Gracefully degrades if atom's interfaces don't match exactly — the A-Cal
        agents still work standalone via the API router.
        """
        try:
            for spec in self.list_agents():
                # Atom's AgentRegistry expects a dict with specific fields.
                # We map our spec to atom's expected format.
                agent_record = {
                    "agent_name": spec.display_name,
                    "agent_type": "a_cal_specialist",
                    "system_prompt": spec.system_prompt,
                    "tools": spec.tools,
                    "cognitive_tier": spec.default_tier.value,
                    "capabilities": spec.capabilities,
                    "metadata": spec.marketplace_metadata,
                }
                # Attempt registration — atom's interface may vary by version.
                if hasattr(atom_meta_agent, "register_specialist"):
                    atom_meta_agent.register_specialist(spec.name, agent_record)
                elif hasattr(atom_meta_agent, "register_agent"):
                    atom_meta_agent.register_agent(agent_record)
                else:
                    logger.warning(
                        "atom_meta_agent has no register method; "
                        "agent %s registered in A-Cal registry only",
                        spec.name,
                    )
        except Exception as exc:
            logger.warning("atom registration failed (A-Cal agents still work standalone): %s", exc)
