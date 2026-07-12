"""Developer API routes — plugins, config-as-code, and agent spec CRUD.

These endpoints are gated behind Developer mode in the frontend. The backend
doesn't enforce the mode gate (that's a UI concern), but the endpoints are
documented as developer-only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from a_cal.developer.plugins import PluginBase, PluginRegistry, PluginType
from a_cal.developer.config_io import ConfigExporter, ConfigImporter
from a_cal.developer.agent_crud import AgentSpecStore
from a_cal.agents.specs import AgentSpec, CognitiveTier
from a_cal.settings.modes import get_mode_config
from a_cal.settings.model_routing import ModelRoutingConfig
from a_cal.self_model.settings import SelfModelSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal/developer", tags=["a-cal-developer"])


# --- per-user stores (standalone mode) --------------------------------------

_plugin_registries: Dict[str, PluginRegistry] = {}
_agent_stores: Dict[str, AgentSpecStore] = {}


def _get_plugin_registry(user_id: str) -> PluginRegistry:
    if user_id not in _plugin_registries:
        _plugin_registries[user_id] = PluginRegistry()
    return _plugin_registries[user_id]


def _get_agent_store(user_id: str) -> AgentSpecStore:
    if user_id not in _agent_stores:
        _agent_stores[user_id] = AgentSpecStore()
    return _agent_stores[user_id]


def _current_user_id() -> str:
    """Placeholder — wired to atom's auth in production."""
    return "local-dev-user"


# --- request/response models -----------------------------------------------

class PluginInput(BaseModel):
    name: str
    plugin_type: str  # PluginType value
    version: str = "0.1.0"
    description: str = ""
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    default_config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PluginConfigUpdate(BaseModel):
    config: Dict[str, Any]


class AgentSpecInput(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: List[str] = Field(default_factory=list)
    default_tier: str = "standard"
    can_negotiate: bool = False
    privacy_force_local: bool = False
    capabilities: List[str] = Field(default_factory=list)


class AgentSpecUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[List[str]] = None
    default_tier: Optional[str] = None
    can_negotiate: Optional[bool] = None
    privacy_force_local: Optional[bool] = None
    capabilities: Optional[List[str]] = None


class ConfigExportRequest(BaseModel):
    """Export config — accepts optional overrides for what to include."""
    include_sub_accounts: bool = True
    include_plugins: bool = True
    include_custom_agents: bool = True


class ConfigImportRequest(BaseModel):
    """Import config from a JSON-compatible dict."""
    config: Dict[str, Any]


# --- plugin endpoints ------------------------------------------------------

@router.get("/plugins")
def list_plugins(plugin_type: Optional[str] = None, enabled_only: bool = False):
    """List registered plugins."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    plugins = registry.list_plugins(plugin_type=plugin_type, enabled_only=enabled_only)
    return [p.to_dict() for p in plugins]


@router.post("/plugins")
def register_plugin(body: PluginInput):
    """Register a new plugin."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    plugin = PluginBase(
        name=body.name,
        plugin_type=body.plugin_type,
        version=body.version,
        author=user_id,
        description=body.description,
        config_schema=body.config_schema,
        default_config=body.default_config,
        enabled=body.enabled,
    )
    registered = registry.register(plugin)
    return registered.to_dict()


@router.delete("/plugins/{plugin_id}")
def unregister_plugin(plugin_id: str):
    """Unregister a plugin."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    if not registry.unregister(plugin_id):
        raise HTTPException(status_code=404, detail="plugin not found")
    return {"deleted": True}


@router.post("/plugins/{plugin_id}/enable")
def enable_plugin(plugin_id: str):
    """Enable a plugin."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    plugin = registry.enable(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return plugin.to_dict()


@router.post("/plugins/{plugin_id}/disable")
def disable_plugin(plugin_id: str):
    """Disable a plugin."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    plugin = registry.disable(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return plugin.to_dict()


@router.patch("/plugins/{plugin_id}/config")
def update_plugin_config(plugin_id: str, body: PluginConfigUpdate):
    """Update a plugin's default configuration."""
    user_id = _current_user_id()
    registry = _get_plugin_registry(user_id)
    plugin = registry.update_config(plugin_id, body.config)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return plugin.to_dict()


# --- agent spec CRUD endpoints ---------------------------------------------

@router.get("/agents")
def list_agent_specs():
    """List all agent specs (built-in + custom)."""
    user_id = _current_user_id()
    store = _get_agent_store(user_id)
    return store.to_dict_list(include_builtins=True)


@router.post("/agents")
def create_agent_spec(body: AgentSpecInput):
    """Create a custom agent spec."""
    user_id = _current_user_id()
    store = _get_agent_store(user_id)

    try:
        tier = CognitiveTier(body.default_tier)
    except ValueError:
        tier = CognitiveTier.STANDARD

    spec = AgentSpec(
        name=body.name,
        display_name=body.display_name or body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        tools=body.tools,
        default_tier=tier,
        can_negotiate=body.can_negotiate,
        privacy_force_local=body.privacy_force_local,
        capabilities=body.capabilities,
    )

    try:
        created = store.create(spec)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return created.to_dict()


@router.patch("/agents/{name}")
def update_agent_spec(name: str, body: AgentSpecUpdate):
    """Update a custom agent spec. Cannot modify built-in specs."""
    user_id = _current_user_id()
    store = _get_agent_store(user_id)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = store.update(name, updates)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="agent spec not found")

    return updated.to_dict()


@router.delete("/agents/{name}")
def delete_agent_spec(name: str):
    """Delete a custom agent spec. Cannot delete built-in specs."""
    user_id = _current_user_id()
    store = _get_agent_store(user_id)

    try:
        deleted = store.delete(name)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=404, detail="agent spec not found")

    return {"deleted": True}


# --- config-as-code endpoints ----------------------------------------------

@router.post("/config/export")
def export_config(body: ConfigExportRequest):
    """Export the full A-Cal configuration as JSON."""
    user_id = _current_user_id()
    agent_store = _get_agent_store(user_id)
    plugin_registry = _get_plugin_registry(user_id)

    custom_agents = []
    if body.include_custom_agents:
        custom_agents = [s.to_dict() for s in agent_store.list_custom()]

    plugins = []
    if body.include_plugins:
        plugins = plugin_registry.to_dict_list()

    exporter = ConfigExporter(
        mode="developer",
        custom_agent_specs=custom_agents,
        plugins=plugins,
    )
    return exporter.export()


@router.post("/config/import")
def import_config(body: ConfigImportRequest):
    """Import an A-Cal configuration from JSON."""
    importer = ConfigImporter()
    result = importer.import_config(body.config)

    return {
        "imported": {
            "mode": result["mode"],
            "model_routing": result["model_routing"].to_dict(),
            "self_model": result["self_model"].to_dict(),
            "custom_agent_count": len(result["custom_agent_specs"]),
            "plugin_count": len(result["plugins"]),
            "sub_account_count": len(result["sub_accounts"]),
        },
        "errors": importer.errors,
        "warnings": importer.warnings,
    }


# --- plugin runtime (code execution) ----------------------------------------

@router.get("/plugins/runtime/list")
def list_runtime_plugins():
    """List all plugins loaded by the runtime (actual code, not just specs).

    Scans ~/.a-cal/plugins/ for .py files, loads each one, and reports
    which hooks are implemented. Failed loads are included with error messages.
    """
    from a_cal.developer.plugin_runtime import get_runtime
    runtime = get_runtime()
    loaded = runtime.scan_and_load()
    return [p.to_dict() for p in loaded]


@router.post("/plugins/runtime/scan")
def scan_plugins():
    """Trigger a fresh scan of the plugin directory and load all plugins."""
    from a_cal.developer.plugin_runtime import get_runtime
    runtime = get_runtime()
    loaded = runtime.scan_and_load()
    return {
        "scanned": len(loaded),
        "loaded": sum(1 for p in loaded if not p.load_error),
        "failed": sum(1 for p in loaded if p.load_error),
        "plugins": [p.to_dict() for p in loaded],
    }


@router.post("/plugins/runtime/{plugin_id}/reload")
def reload_plugin(plugin_id: str):
    """Reload a single plugin from disk (useful during development)."""
    from a_cal.developer.plugin_runtime import get_runtime
    runtime = get_runtime()
    result = runtime.reload(plugin_id)
    if result is None:
        raise HTTPException(status_code=404, detail="plugin not loaded")
    return result.to_dict()


@router.post("/plugins/runtime/{plugin_id}/enable")
def enable_runtime_plugin(plugin_id: str):
    """Enable a loaded runtime plugin."""
    from a_cal.developer.plugin_runtime import get_runtime
    runtime = get_runtime()
    if not runtime.enable(plugin_id):
        raise HTTPException(status_code=404, detail="plugin not loaded")
    return {"status": "enabled", "plugin_id": plugin_id}


@router.post("/plugins/runtime/{plugin_id}/disable")
def disable_runtime_plugin(plugin_id: str):
    """Disable a loaded runtime plugin."""
    from a_cal.developer.plugin_runtime import get_runtime
    runtime = get_runtime()
    if not runtime.disable(plugin_id):
        raise HTTPException(status_code=404, detail="plugin not loaded")
    return {"status": "disabled", "plugin_id": plugin_id}


@router.get("/plugins/runtime/hooks")
def list_supported_hooks():
    """List all supported plugin hooks that the runtime can call."""
    from a_cal.developer.plugin_runtime import SUPPORTED_HOOKS
    return {"hooks": SUPPORTED_HOOKS}