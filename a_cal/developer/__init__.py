"""Developer layer — plugin system, config-as-code, and agent spec CRUD.

These modules power the Developer mode in A-Cal's skill progression:
  - Plugin system: register custom agents, providers, sync rules
  - Config-as-code: export/import entire A-Cal configuration as JSON
  - Agent spec CRUD: create, read, update, delete custom agent specs
    (beyond the 6 built-in ones)
"""

from a_cal.developer.plugins import (
    PluginBase,
    PluginRegistry,
    PluginType,
)
from a_cal.developer.config_io import ConfigExporter, ConfigImporter
from a_cal.developer.agent_crud import AgentSpecStore

__all__ = [
    "PluginBase",
    "PluginRegistry",
    "PluginType",
    "ConfigExporter",
    "ConfigImporter",
    "AgentSpecStore",
]
