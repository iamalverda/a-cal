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

_plugin_registries: dict[str, PluginRegistry] = {}
_agent_stores: dict[str, AgentSpecStore] = {}


def _get_plugin_registry(user_id: str) -> PluginRegistry:
    if user_id not in _plugin_registries:
        _plugin_registries[user_id] = PluginRegistry()
    return _plugin_registries[user_id]


def _get_agent_store(user_id: str) -> AgentSpecStore:
    if user_id not in _agent_stores:
        from a_cal.db.store import PersistentStore
        _agent_stores[user_id] = AgentSpecStore(db=PersistentStore())
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
    config_schema: dict[str, Any] = Field(default_factory=dict)
    default_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PluginConfigUpdate(BaseModel):
    config: dict[str, Any]


class AgentSpecInput(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    default_tier: str = "standard"
    can_negotiate: bool = False
    privacy_force_local: bool = False
    capabilities: list[str] = Field(default_factory=list)


class AgentSpecUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    default_tier: str | None = None
    can_negotiate: bool | None = None
    privacy_force_local: bool | None = None
    capabilities: list[str] | None = None


class ConfigExportRequest(BaseModel):
    """Export config — accepts optional overrides for what to include."""
    include_sub_accounts: bool = True
    include_plugins: bool = True
    include_custom_agents: bool = True


class ConfigImportRequest(BaseModel):
    """Import config from a JSON-compatible dict."""
    config: dict[str, Any]


# --- plugin endpoints ------------------------------------------------------

@router.get("/plugins")
def list_plugins(plugin_type: str | None = None, enabled_only: bool = False):
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

# --- Workflows ---------------------------------------------------------------

from a_cal.workflows.models import WorkflowDef, WorkflowNode
from a_cal.workflows.store import WorkflowStore
from a_cal.workflows.runner import WorkflowRunner

_workflow_stores: dict[str, WorkflowStore] = {}


def _get_workflow_store(user_id: str) -> WorkflowStore:
    """Get or create a WorkflowStore for the user."""
    if user_id not in _workflow_stores:
        from a_cal.db.store import PersistentStore as _DB
        _workflow_stores[user_id] = WorkflowStore(_DB())
    return _workflow_stores[user_id]


class WorkflowNodeInput(BaseModel):
    """Input for a single workflow node."""

    id: str = ""
    agent: str = ""
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    conditional: str | None = None


class WorkflowInput(BaseModel):
    """Input for creating/updating a workflow."""

    id: str = ""
    name: str
    description: str = ""
    nodes: list[WorkflowNodeInput] = Field(default_factory=list)
    trigger: str = "manual"
    version: str = "0.1.0"


class WorkflowRunInput(BaseModel):
    """Input for running a workflow directly (without saving)."""

    name: str = ""
    description: str = ""
    nodes: list[WorkflowNodeInput] = Field(default_factory=list)
    trigger: str = "manual"
    version: str = "0.1.0"
    initial_message: str = ""


@router.get("/workflows")
def list_workflows():
    """List all saved workflows."""
    store = _get_workflow_store(_current_user_id())
    return [w.to_dict() for w in store.list_workflows()]


@router.post("/workflows")
def save_workflow(body: WorkflowInput):
    """Create or update a workflow.

    If ``id`` is omitted, a new workflow is created. Otherwise the existing
    workflow with that ID is updated.
    """
    store = _get_workflow_store(_current_user_id())
    wf = WorkflowDef(
        id=body.id,
        name=body.name,
        description=body.description,
        nodes=[
            WorkflowNode(
                id=n.id,
                agent=n.agent,
                label=n.label,
                config=n.config,
                conditional=n.conditional,
            )
            for n in body.nodes
        ],
        trigger=body.trigger,
        version=body.version,
    )
    saved = store.save_workflow(wf)
    return saved.to_dict()


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    """Get a single workflow by ID."""
    store = _get_workflow_store(_current_user_id())
    wf = store.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf.to_dict()


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    """Delete a workflow by ID."""
    store = _get_workflow_store(_current_user_id())
    if not store.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"status": "deleted", "id": workflow_id}


@router.post("/workflows/run")
async def run_workflow_direct(body: WorkflowRunInput):
    """Execute a workflow definition without saving it.

    Useful for testing a workflow before saving. The workflow is executed
    immediately and the results are returned.
    """
    from a_cal.api.agent_routes import _store as _agent_store

    user_id = _current_user_id()
    conductor = _agent_store.get_conductor(user_id)

    wf = WorkflowDef(
        name=body.name,
        description=body.description,
        nodes=[
            WorkflowNode(
                id=n.id,
                agent=n.agent,
                label=n.label,
                config=n.config,
                conditional=n.conditional,
            )
            for n in body.nodes
        ],
        trigger=body.trigger,
        version=body.version,
    )

    runner = WorkflowRunner(conductor)
    result = await runner.run(wf, initial_message=body.initial_message)
    return result.to_dict()


@router.post("/workflows/{workflow_id}/run")
async def run_saved_workflow(workflow_id: str, body: WorkflowRunInput):
    """Execute a saved workflow by ID.

    Optionally pass an ``initial_message`` to seed the first node.
    """
    store = _get_workflow_store(_current_user_id())
    wf = store.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")

    from a_cal.api.agent_routes import _store as _agent_store
    conductor = _agent_store.get_conductor(_current_user_id())

    runner = WorkflowRunner(conductor)
    result = await runner.run(wf, initial_message=body.initial_message)
    return result.to_dict()


# --- API Explorer ------------------------------------------------------------

@router.get("/api-routes")
def list_api_routes():
    """List all registered API routes for the API Explorer.

    Introspects the FastAPI app's route table and returns structured
    metadata for each endpoint: method, path, summary, parameters,
    request body schema, and response schema.

    Returns:
        List of route dicts grouped by tag.
    """
    from a_cal.api.standalone import app
    import inspect

    # Collect all route objects — FastAPI wraps included routers in
    # _IncludedRouter objects whose actual routes live on original_router.
    all_routes: list = []
    for route in app.routes:
        if hasattr(route, "original_router"):
            all_routes.extend(route.original_router.routes)
        elif hasattr(route, "methods") and hasattr(route, "path"):
            all_routes.append(route)

    routes: list[dict] = []
    for route in all_routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        # Skip non-API routes (health, docs, etc.)
        if "/api/a-cal" not in route.path and "/health" not in route.path:
            continue
        methods = sorted(route.methods - {"HEAD", "OPTIONS"}) if route.methods else []
        if not methods:
            continue

        # Extract summary from the route's endpoint function
        summary = ""
        doc = ""
        endpoint = getattr(route, "endpoint", None)
        if endpoint and endpoint.__doc__:
            lines = endpoint.__doc__.strip().split("\n")
            summary = lines[0].strip() if lines else ""
            doc = endpoint.__doc__.strip()

        # Extract path parameters
        path_params: list[dict] = []
        if hasattr(route, "path_convertors"):
            for segment in route.path.split("/"):
                if segment.startswith("{") and segment.endswith("}"):
                    param_name = segment[1:-1]
                    path_params.append({"name": param_name, "in": "path", "required": True})

        # Extract query/body parameters from the endpoint signature
        query_params: list[dict] = []
        body_schema: dict | None = None
        if endpoint:
            sig = inspect.signature(endpoint)
            # Resolve string forward references (from __future__ import annotations)
            try:
                import typing
                hints = typing.get_type_hints(endpoint)
            except Exception:
                hints = {}
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "request", "response"):
                    continue
                # Resolve the annotation — get_type_hints may have resolved it
                annotation = hints.get(param_name, param.annotation)
                # Check if it's a Pydantic model (request body)
                if hasattr(annotation, "model_fields"):
                    body_schema = {
                        "name": param_name,
                        "fields": {
                            fname: {
                                "type": str(finfo.annotation),
                                "default": str(finfo.default) if finfo.default is not None else None,
                                "required": finfo.is_required(),
                            }
                            for fname, finfo in annotation.model_fields.items()
                        },
                    }
                elif param.default is not inspect.Parameter.empty:
                    query_params.append({
                        "name": param_name,
                        "in": "query",
                        "required": False,
                        "default": str(param.default) if param.default is not None else None,
                    })
                elif f"{{{param_name}}}" in route.path:
                    # Path parameter not yet captured
                    path_params.append({
                        "name": param_name,
                        "in": "path",
                        "required": True,
                    })

        tag = ""
        if hasattr(route, "tags") and route.tags:
            tag = route.tags[0]

        routes.append({
            "method": methods[0] if len(methods) == 1 else ",".join(methods),
            "path": route.path,
            "summary": summary,
            "description": doc,
            "tag": tag,
            "path_params": path_params,
            "query_params": query_params,
            "body_schema": body_schema,
        })

    # Sort by tag then path
    routes.sort(key=lambda r: (r["tag"], r["path"]))
    return routes
