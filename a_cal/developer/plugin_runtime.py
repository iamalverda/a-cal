"""Plugin execution runtime — loads and runs custom plugin code.

The runtime is the bridge between plugin specs (data) and running code.
It loads plugins from the plugin directory (~/.a-cal/plugins/), validates
them against the expected interface, and executes their hooks when events
fire.

Plugin hooks:
  - on_event_created(event: dict) -> Optional[dict]  — transform or react to new events
  - on_event_updated(event: dict) -> Optional[dict]  — transform or react to event updates
  - on_event_deleted(event_id: str) -> None           — react to event deletion
  - on_sync_complete(sub_account_id: str, events: list) -> None  — post-sync hook
  - on_intent_classified(message: str, intent: str) -> Optional[str]  — override intent
  - on_conductor_response(response: str, context: dict) -> Optional[str]  — transform response
  - get_agent_spec() -> dict  — return an AgentSpec dict for agent plugins
  - get_sync_rules() -> list  — return sync rule dicts for sync_rule plugins

Security:
  - Plugins are loaded from ~/.a-cal/plugins/ or a configured directory
  - Each plugin is a Python file with a Plugin class
  - The Plugin class must implement at least one hook
  - Plugin code runs in the same process (sandboxing is a future concern)
  - Plugin execution errors are caught and logged, never crashing the host
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Plugin directory: ~/.a-cal/plugins/ by default, override with A_CAL_PLUGIN_DIR
DEFAULT_PLUGIN_DIR = os.path.join(os.path.expanduser("~"), ".a-cal", "plugins")

# Required: a plugin file must define a class named "Plugin"
PLUGIN_CLASS_NAME = "Plugin"

# Supported hooks
SUPPORTED_HOOKS = [
    "on_event_created",
    "on_event_updated",
    "on_event_deleted",
    "on_sync_complete",
    "on_intent_classified",
    "on_conductor_response",
    "get_agent_spec",
    "get_sync_rules",
]


@dataclass
class LoadedPlugin:
    """A plugin that has been loaded into memory with its code instance."""
    id: str
    name: str
    plugin_type: str
    file_path: str
    instance: Any  # The Plugin class instance
    hooks: List[str] = field(default_factory=list)
    enabled: bool = True
    load_error: Optional[str] = None
    loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plugin_type": self.plugin_type,
            "file_path": self.file_path,
            "hooks": list(self.hooks),
            "enabled": self.enabled,
            "load_error": self.load_error,
            "loaded_at": self.loaded_at,
        }


class PluginRuntime:
    """Loads, manages, and executes plugin code.

    The runtime scans the plugin directory for .py files, loads each one,
    instantiates the Plugin class, and registers its hooks. When events fire,
    the runtime calls the appropriate hook on each enabled plugin.
    """

    def __init__(self, plugin_dir: Optional[str] = None) -> None:
        """Initialize the plugin runtime.

        Args:
            plugin_dir: Directory to scan for plugins. Defaults to
                ~/.a-cal/plugins/ or A_CAL_PLUGIN_DIR env var.
        """
        self._plugin_dir = plugin_dir or os.environ.get("A_CAL_PLUGIN_DIR", DEFAULT_PLUGIN_DIR)
        self._loaded: Dict[str, LoadedPlugin] = {}  # plugin_id -> LoadedPlugin
        self._scanned = False  # Track whether we've done the initial scan

    def _ensure_dir(self) -> None:
        """Create the plugin directory if it doesn't exist."""
        os.makedirs(self._plugin_dir, exist_ok=True)

    def scan_and_load(self) -> List[LoadedPlugin]:
        """Scan the plugin directory and load all valid plugins.

        Returns a list of LoadedPlugin objects (including failed loads
        with load_error set).
        """
        self._ensure_dir()
        results: List[LoadedPlugin] = []

        for filename in sorted(os.listdir(self._plugin_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            file_path = os.path.join(self._plugin_dir, filename)
            plugin_id = filename[:-3]  # Remove .py extension

            loaded = self._load_plugin_file(plugin_id, file_path)
            if loaded:
                self._loaded[plugin_id] = loaded
                results.append(loaded)

        logger.info("Plugin scan complete: %d loaded, %d failed",
                     sum(1 for r in results if not r.load_error),
                     sum(1 for r in results if r.load_error))
        self._scanned = True
        return results

    def _load_plugin_file(self, plugin_id: str, file_path: str) -> Optional[LoadedPlugin]:
        """Load a single plugin file.

        Args:
            plugin_id: Identifier for the plugin (filename without .py).
            file_path: Absolute path to the plugin .py file.

        Returns:
            LoadedPlugin with either an instance or a load_error.
        """
        try:
            # Remove any cached module entry so reloads pick up file changes
            sys.modules.pop(f"a_cal_plugin_{plugin_id}", None)

            # Load the module using importlib
            spec = importlib.util.spec_from_file_location(
                f"a_cal_plugin_{plugin_id}", file_path
            )
            if spec is None or spec.loader is None:
                return LoadedPlugin(
                    id=plugin_id,
                    name=plugin_id,
                    plugin_type="unknown",
                    file_path=file_path,
                    instance=None,
                    load_error="Could not create module spec",
                )

            # Read source directly and exec to avoid stale bytecode caches.
            # Using spec.loader.exec_module can return cached code objects
            # from __pycache__ even after the source file changes, which
            # breaks hot-reload during development.
            with open(file_path, "r", encoding="utf-8") as src_file:
                source_code = src_file.read()
            code_obj = compile(source_code, file_path, "exec")

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"a_cal_plugin_{plugin_id}"] = module
            exec(code_obj, module.__dict__)

            # Find the Plugin class
            plugin_class = getattr(module, PLUGIN_CLASS_NAME, None)
            if plugin_class is None:
                return LoadedPlugin(
                    id=plugin_id,
                    name=plugin_id,
                    plugin_type="unknown",
                    file_path=file_path,
                    instance=None,
                    load_error=f"No '{PLUGIN_CLASS_NAME}' class defined",
                )

            # Instantiate the plugin
            instance = plugin_class()

            # Determine which hooks are implemented
            hooks = [h for h in SUPPORTED_HOOKS if callable(getattr(instance, h, None))]

            if not hooks:
                return LoadedPlugin(
                    id=plugin_id,
                    name=getattr(instance, "name", plugin_id),
                    plugin_type=getattr(instance, "plugin_type", "unknown"),
                    file_path=file_path,
                    instance=None,
                    load_error="No supported hooks implemented",
                )

            # Get metadata
            name = getattr(instance, "name", plugin_id)
            plugin_type = getattr(instance, "plugin_type", "agent")
            enabled = getattr(instance, "enabled", True)

            logger.info("Loaded plugin: %s (%s) with hooks: %s", name, plugin_type, hooks)
            return LoadedPlugin(
                id=plugin_id,
                name=name,
                plugin_type=plugin_type,
                file_path=file_path,
                instance=instance,
                hooks=hooks,
                enabled=enabled,
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error("Failed to load plugin %s: %s", plugin_id, error_msg)
            return LoadedPlugin(
                id=plugin_id,
                name=plugin_id,
                plugin_type="unknown",
                file_path=file_path,
                instance=None,
                load_error=error_msg,
            )

    def get_plugin(self, plugin_id: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by ID."""
        return self._loaded.get(plugin_id)

    def list_loaded(self) -> List[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._loaded.values())

    def enable(self, plugin_id: str) -> bool:
        """Enable a loaded plugin."""
        plugin = self._loaded.get(plugin_id)
        if plugin:
            plugin.enabled = True
            return True
        return False

    def disable(self, plugin_id: str) -> bool:
        """Disable a loaded plugin."""
        plugin = self._loaded.get(plugin_id)
        if plugin:
            plugin.enabled = False
            return True
        return False

    def reload(self, plugin_id: str) -> Optional[LoadedPlugin]:
        """Reload a single plugin from disk."""
        plugin = self._loaded.get(plugin_id)
        if plugin is None:
            return None
        loaded = self._load_plugin_file(plugin_id, plugin.file_path)
        if loaded:
            self._loaded[plugin_id] = loaded
        return loaded

    # --- Hook execution -----------------------------------------------------

    def _execute_hook(
        self,
        hook_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a hook on all enabled plugins.

        Returns a dict mapping plugin_id -> result. Errors are caught
        and logged; the plugin is not disabled on error (but the error
        is recorded).

        Args:
            hook_name: Name of the hook to call (e.g., "on_event_created").
            *args, **kwargs: Arguments to pass to the hook.

        Returns:
            Dict of plugin_id -> {"result": Any, "error": Optional[str]}.
        """
        results: Dict[str, Any] = {}

        for plugin_id, plugin in self._loaded.items():
            if not plugin.enabled or plugin.instance is None:
                continue
            if hook_name not in plugin.hooks:
                continue

            try:
                hook: Callable = getattr(plugin.instance, hook_name)
                result = hook(*args, **kwargs)
                results[plugin_id] = {"result": result, "error": None}
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.warning("Plugin %s hook %s failed: %s", plugin_id, hook_name, error_msg)
                results[plugin_id] = {"result": None, "error": error_msg}

        return results

    def on_event_created(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Fire on_event_created hook on all enabled plugins."""
        return self._execute_hook("on_event_created", event)

    def on_event_updated(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Fire on_event_updated hook on all enabled plugins."""
        return self._execute_hook("on_event_updated", event)

    def on_event_deleted(self, event_id: str) -> Dict[str, Any]:
        """Fire on_event_deleted hook on all enabled plugins."""
        return self._execute_hook("on_event_deleted", event_id)

    def on_sync_complete(self, sub_account_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fire on_sync_complete hook on all enabled plugins."""
        return self._execute_hook("on_sync_complete", sub_account_id, events)

    def on_intent_classified(self, message: str, intent: str) -> Optional[str]:
        """Fire on_intent_classified hook. First non-None result wins.

        This allows agent plugins to override the conductor's intent
        classification.
        """
        results = self._execute_hook("on_intent_classified", message, intent)
        for plugin_id, data in results.items():
            if data["result"] is not None and data["error"] is None:
                logger.info("Plugin %s overrode intent: %s -> %s", plugin_id, intent, data["result"])
                return data["result"]  # type: ignore[return-value]
        return None

    def on_conductor_response(self, response: str, context: Dict[str, Any]) -> Optional[str]:
        """Fire on_conductor_response hook. First non-None result wins.

        This allows plugins to transform the conductor's response before
        it's returned to the user.
        """
        results = self._execute_hook("on_conductor_response", response, context)
        for plugin_id, data in results.items():
            if data["result"] is not None and data["error"] is None:
                return data["result"]  # type: ignore[return-value]
        return None

    def get_agent_specs(self) -> List[Dict[str, Any]]:
        """Collect agent specs from all agent-type plugins.

        Returns a list of AgentSpec dicts that can be registered with
        the conductor's agent registry.
        """
        specs: List[Dict[str, Any]] = []
        results = self._execute_hook("get_agent_spec")
        for plugin_id, data in results.items():
            if data["result"] is not None and data["error"] is None:
                if isinstance(data["result"], dict):
                    specs.append(data["result"])
                elif isinstance(data["result"], list):
                    specs.extend(data["result"])
        return specs

    def get_sync_rule_packs(self) -> List[Dict[str, Any]]:
        """Collect sync rule packs from all sync_rule-type plugins."""
        packs: List[Dict[str, Any]] = []
        results = self._execute_hook("get_sync_rules")
        for plugin_id, data in results.items():
            if data["result"] is not None and data["error"] is None:
                if isinstance(data["result"], dict):
                    packs.append(data["result"])
                elif isinstance(data["result"], list):
                    packs.extend(data["result"])
        return packs


# --- Singleton runtime -------------------------------------------------------

_runtime: Optional[PluginRuntime] = None


def get_runtime() -> PluginRuntime:
    """Get the singleton plugin runtime instance."""
    global _runtime
    if _runtime is None:
        _runtime = PluginRuntime()
    return _runtime
