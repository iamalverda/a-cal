"""Tests for the plugin execution runtime.

Tests cover:
  - Plugin loading from a temp directory (valid plugins, no hooks, syntax errors)
  - Hook execution (on_event_created, on_conductor_response, etc.)
  - Enable / disable / reload
  - Agent spec and sync rule collection from plugins
  - Error isolation (one plugin's error doesn't crash others)
"""

from __future__ import annotations

import os
import textwrap
from typing import Any, Dict, List

import pytest

from a_cal.developer.plugin_runtime import (
    DEFAULT_PLUGIN_DIR,
    LoadedPlugin,
    PluginRuntime,
    SUPPORTED_HOOKS,
    get_runtime,
    _runtime as runtime_singleton_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plugin_dir(tmp_path):
    """Return a temp directory that the runtime will scan."""
    d = tmp_path / "plugins"
    d.mkdir()
    return str(d)


@pytest.fixture
def runtime(plugin_dir, monkeypatch):
    """Return a fresh PluginRuntime pointed at the temp plugin dir.

    Also resets the singleton so tests don't leak state.
    """
    import a_cal.developer.plugin_runtime as pr
    monkeypatch.setattr(pr, "_runtime", None)
    rt = PluginRuntime(plugin_dir=plugin_dir)
    return rt


def _write_plugin(directory: str, filename: str, code: str) -> str:
    """Write a .py plugin file into *directory* and return its path."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        f.write(textwrap.dedent(code))
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestPluginLoading:
    """Tests for scan_and_load and _load_plugin_file."""

    def test_scan_empty_dir(self, runtime, plugin_dir):
        """Scanning an empty directory returns [] and still works."""
        results = runtime.scan_and_load()
        assert results == []
        assert runtime._scanned is True

    def test_scan_creates_missing_dir(self, runtime, tmp_path):
        """scan_and_load creates the plugin directory if it doesn't exist."""
        missing = str(tmp_path / "does_not_exist_yet")
        rt = PluginRuntime(plugin_dir=missing)
        results = rt.scan_and_load()
        assert os.path.isdir(missing)
        assert results == []

    def test_load_valid_plugin_with_hooks(self, runtime, plugin_dir):
        """A valid plugin with hooks loads successfully."""
        _write_plugin(plugin_dir, "test_agent.py", '''
            class Plugin:
                name = "Test Agent"
                plugin_type = "agent"

                def on_event_created(self, event):
                    return {"modified": True}

                def get_agent_spec(self):
                    return {"name": "test_agent", "display_name": "Test Agent"}
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 1
        p = results[0]
        assert p.id == "test_agent"
        assert p.name == "Test Agent"
        assert p.plugin_type == "agent"
        assert p.load_error is None
        assert p.instance is not None
        assert "on_event_created" in p.hooks
        assert "get_agent_spec" in p.hooks
        assert p.enabled is True

    def test_load_plugin_no_hooks(self, runtime, plugin_dir):
        """A plugin with no supported hooks reports a load error."""
        _write_plugin(plugin_dir, "no_hooks.py", '''
            class Plugin:
                name = "No Hooks Plugin"
                plugin_type = "agent"

                def some_other_method(self):
                    pass
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 1
        p = results[0]
        assert p.load_error is not None
        assert "No supported hooks" in p.load_error
        assert p.instance is None

    def test_load_plugin_no_class(self, runtime, plugin_dir):
        """A plugin file without a Plugin class reports a load error."""
        _write_plugin(plugin_dir, "no_class.py", '''
            def some_function():
                pass
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 1
        p = results[0]
        assert p.load_error is not None
        assert "Plugin" in p.load_error

    def test_load_plugin_syntax_error(self, runtime, plugin_dir):
        """A plugin file with a syntax error is caught, not raised."""
        _write_plugin(plugin_dir, "bad_syntax.py", '''
            class Plugin(
                pass
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 1
        p = results[0]
        assert p.load_error is not None
        assert "SyntaxError" in p.load_error or "syntax" in p.load_error.lower()

    def test_load_plugin_runtime_error(self, runtime, plugin_dir):
        """A plugin that raises during __init__ is caught."""
        _write_plugin(plugin_dir, "bad_init.py", '''
            class Plugin:
                def __init__(self):
                    raise ValueError("boom")
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 1
        p = results[0]
        assert p.load_error is not None
        assert "ValueError" in p.load_error

    def test_underscore_files_skipped(self, runtime, plugin_dir):
        """Files starting with _ are skipped."""
        _write_plugin(plugin_dir, "_hidden.py", '''
            class Plugin:
                def on_event_created(self, event):
                    return event
        ''')
        results = runtime.scan_and_load()
        assert results == []

    def test_non_py_files_skipped(self, runtime, plugin_dir):
        """Non-.py files are skipped."""
        with open(os.path.join(plugin_dir, "readme.md"), "w") as f:
            f.write("# Plugins")
        results = runtime.scan_and_load()
        assert results == []

    def test_multiple_plugins_loaded(self, runtime, plugin_dir):
        """Multiple valid plugins all load."""
        _write_plugin(plugin_dir, "plugin_a.py", '''
            class Plugin:
                name = "A"
                def on_event_created(self, event):
                    return event
        ''')
        _write_plugin(plugin_dir, "plugin_b.py", '''
            class Plugin:
                name = "B"
                def on_event_updated(self, event):
                    return event
        ''')
        results = runtime.scan_and_load()
        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"plugin_a", "plugin_b"}

    def test_get_plugin_after_load(self, runtime, plugin_dir):
        """get_plugin returns the loaded plugin by id."""
        _write_plugin(plugin_dir, "my_plugin.py", '''
            class Plugin:
                name = "My Plugin"
                def on_event_created(self, event):
                    return event
        ''')
        runtime.scan_and_load()
        p = runtime.get_plugin("my_plugin")
        assert p is not None
        assert p.name == "My Plugin"

    def test_get_plugin_not_found(self, runtime):
        """get_plugin returns None for unknown id."""
        assert runtime.get_plugin("nonexistent") is None

    def test_list_loaded(self, runtime, plugin_dir):
        """list_loaded returns all loaded plugins."""
        _write_plugin(plugin_dir, "p1.py", '''
            class Plugin:
                def on_event_created(self, e): return e
        ''')
        runtime.scan_and_load()
        loaded = runtime.list_loaded()
        assert len(loaded) == 1
        assert loaded[0].id == "p1"


# ---------------------------------------------------------------------------
# Hook execution
# ---------------------------------------------------------------------------

class TestHookExecution:
    """Tests for hook execution on loaded plugins."""

    def test_on_event_created_hook(self, runtime, plugin_dir):
        """on_event_created fires and returns results."""
        _write_plugin(plugin_dir, "logger.py", '''
            class Plugin:
                name = "Logger"
                plugin_type = "agent"
                def on_event_created(self, event):
                    return {"logged": True, "event_title": event.get("title")}
        ''')
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Meeting"})
        assert "logger" in results
        assert results["logger"]["error"] is None
        assert results["logger"]["result"]["event_title"] == "Meeting"

    def test_disabled_plugin_not_executed(self, runtime, plugin_dir):
        """A disabled plugin's hooks are not called."""
        _write_plugin(plugin_dir, "disabled.py", '''
            class Plugin:
                name = "Disabled"
                def on_event_created(self, event):
                    return {"should_not_fire": True}
        ''')
        runtime.scan_and_load()
        runtime.disable("disabled")
        results = runtime.on_event_created({"title": "Test"})
        assert results == {}

    def test_hook_error_isolated(self, runtime, plugin_dir):
        """A plugin that raises in a hook doesn't crash other plugins."""
        _write_plugin(plugin_dir, "crasher.py", '''
            class Plugin:
                name = "Crasher"
                def on_event_created(self, event):
                    raise RuntimeError("plugin crashed")
        ''')
        _write_plugin(plugin_dir, "healthy.py", '''
            class Plugin:
                name = "Healthy"
                def on_event_created(self, event):
                    return {"ok": True}
        ''')
        runtime.scan_and_load()
        results = runtime.on_event_created({"title": "Test"})
        assert "crasher" in results
        assert results["crasher"]["error"] is not None
        assert "RuntimeError" in results["crasher"]["error"]
        assert "healthy" in results
        assert results["healthy"]["result"] == {"ok": True}
        assert results["healthy"]["error"] is None

    def test_on_event_updated_hook(self, runtime, plugin_dir):
        """on_event_updated fires correctly."""
        _write_plugin(plugin_dir, "tracker.py", '''
            class Plugin:
                name = "Tracker"
                def on_event_updated(self, event):
                    return {"tracked": True}
        ''')
        runtime.scan_and_load()
        results = runtime.on_event_updated({"title": "Updated"})
        assert "tracker" in results
        assert results["tracker"]["result"] == {"tracked": True}

    def test_on_event_deleted_hook(self, runtime, plugin_dir):
        """on_event_deleted fires correctly."""
        _write_plugin(plugin_dir, "cleanup.py", '''
            class Plugin:
                name = "Cleanup"
                def on_event_deleted(self, event_id):
                    return None
        ''')
        runtime.scan_and_load()
        results = runtime.on_event_deleted("evt-123")
        assert "cleanup" in results
        assert results["cleanup"]["error"] is None

    def test_on_sync_complete_hook(self, runtime, plugin_dir):
        """on_sync_complete fires correctly."""
        _write_plugin(plugin_dir, "sync_hook.py", '''
            class Plugin:
                name = "SyncHook"
                def on_sync_complete(self, sub_account_id, events):
                    return {"synced_count": len(events)}
        ''')
        runtime.scan_and_load()
        results = runtime.on_sync_complete("sub-1", [{"title": "A"}, {"title": "B"}])
        assert "sync_hook" in results
        assert results["sync_hook"]["result"]["synced_count"] == 2

    def test_on_intent_classified_override(self, runtime, plugin_dir):
        """on_intent_classified returns first non-None override."""
        _write_plugin(plugin_dir, "intent_override.py", '''
            class Plugin:
                name = "IntentOverride"
                def on_intent_classified(self, message, intent):
                    if "meeting" in message.lower():
                        return "schedule"
                    return None
        ''')
        runtime.scan_and_load()
        result = runtime.on_intent_classified("schedule a meeting", "chat")
        assert result == "schedule"

    def test_on_intent_classified_no_override(self, runtime, plugin_dir):
        """on_intent_classified returns None when no plugin overrides."""
        _write_plugin(plugin_dir, "no_op.py", '''
            class Plugin:
                name = "NoOp"
                def on_intent_classified(self, message, intent):
                    return None
        ''')
        runtime.scan_and_load()
        result = runtime.on_intent_classified("hello", "chat")
        assert result is None

    def test_on_conductor_response_transform(self, runtime, plugin_dir):
        """on_conductor_response returns first non-None transform."""
        _write_plugin(plugin_dir, "responder.py", '''
            class Plugin:
                name = "Responder"
                def on_conductor_response(self, response, context):
                    return response.upper()
        ''')
        runtime.scan_and_load()
        result = runtime.on_conductor_response("hello world", {})
        assert result == "HELLO WORLD"

    def test_on_conductor_response_no_transform(self, runtime, plugin_dir):
        """on_conductor_response returns None when no plugin transforms."""
        _write_plugin(plugin_dir, "pass_through.py", '''
            class Plugin:
                name = "PassThrough"
                def on_conductor_response(self, response, context):
                    return None
        ''')
        runtime.scan_and_load()
        result = runtime.on_conductor_response("hello", {})
        assert result is None


# ---------------------------------------------------------------------------
# Enable / disable / reload
# ---------------------------------------------------------------------------

class TestEnableDisableReload:
    """Tests for enable, disable, and reload operations."""

    def test_enable_plugin(self, runtime, plugin_dir):
        """enable sets enabled=True and returns True."""
        _write_plugin(plugin_dir, "toggle.py", '''
            class Plugin:
                name = "Toggle"
                def on_event_created(self, e): return e
        ''')
        runtime.scan_and_load()
        runtime.disable("toggle")
        assert runtime.get_plugin("toggle").enabled is False
        assert runtime.enable("toggle") is True
        assert runtime.get_plugin("toggle").enabled is True

    def test_disable_plugin(self, runtime, plugin_dir):
        """disable sets enabled=False and returns True."""
        _write_plugin(plugin_dir, "toggle.py", '''
            class Plugin:
                name = "Toggle"
                def on_event_created(self, e): return e
        ''')
        runtime.scan_and_load()
        assert runtime.disable("toggle") is True
        assert runtime.get_plugin("toggle").enabled is False

    def test_enable_unknown_plugin(self, runtime):
        """enable returns False for unknown plugin."""
        assert runtime.enable("nonexistent") is False

    def test_disable_unknown_plugin(self, runtime):
        """disable returns False for unknown plugin."""
        assert runtime.disable("nonexistent") is False

    def test_reload_plugin(self, runtime, plugin_dir):
        """reload re-reads the file from disk and updates the instance."""
        _write_plugin(plugin_dir, "reloadable.py", '''
            class Plugin:
                name = "V1"
                def on_event_created(self, e):
                    return {"version": 1}
        ''')
        runtime.scan_and_load()
        assert runtime.get_plugin("reloadable").name == "V1"

        # Overwrite the file with a new version
        _write_plugin(plugin_dir, "reloadable.py", '''
            class Plugin:
                name = "V2"
                def on_event_created(self, e):
                    return {"version": 2}
        ''')
        result = runtime.reload("reloadable")
        assert result is not None
        assert result.name == "V2"

        # Verify hook execution uses new code
        hook_results = runtime.on_event_created({})
        assert hook_results["reloadable"]["result"]["version"] == 2

    def test_reload_unknown_plugin(self, runtime):
        """reload returns None for unknown plugin."""
        assert runtime.reload("nonexistent") is None


# ---------------------------------------------------------------------------
# Agent specs and sync rules from plugins
# ---------------------------------------------------------------------------

class TestAgentSpecsAndSyncRules:
    """Tests for get_agent_specs and get_sync_rule_packs."""

    def test_get_agent_specs_single(self, runtime, plugin_dir):
        """get_agent_specs collects a single agent spec dict."""
        _write_plugin(plugin_dir, "custom_agent.py", '''
            class Plugin:
                name = "CustomAgent"
                def get_agent_spec(self):
                    return {"name": "custom", "display_name": "Custom Agent"}
        ''')
        runtime.scan_and_load()
        specs = runtime.get_agent_specs()
        assert len(specs) == 1
        assert specs[0]["name"] == "custom"

    def test_get_agent_specs_list(self, runtime, plugin_dir):
        """get_agent_specs handles a plugin that returns a list of specs."""
        _write_plugin(plugin_dir, "multi_agent.py", '''
            class Plugin:
                name = "MultiAgent"
                def get_agent_spec(self):
                    return [
                        {"name": "agent1"},
                        {"name": "agent2"},
                    ]
        ''')
        runtime.scan_and_load()
        specs = runtime.get_agent_specs()
        assert len(specs) == 2

    def test_get_sync_rule_packs(self, runtime, plugin_dir):
        """get_sync_rule_packs collects sync rule dicts."""
        _write_plugin(plugin_dir, "sync_rules.py", '''
            class Plugin:
                name = "SyncRules"
                def get_sync_rules(self):
                    return [{"mode": "mirror", "filters": ["work"]}]
        ''')
        runtime.scan_and_load()
        packs = runtime.get_sync_rule_packs()
        assert len(packs) == 1
        assert packs[0]["mode"] == "mirror"

    def test_get_agent_specs_empty_when_no_plugins(self, runtime, plugin_dir):
        """get_agent_specs returns [] when no agent plugins are loaded."""
        runtime.scan_and_load()
        assert runtime.get_agent_specs() == []


# ---------------------------------------------------------------------------
# LoadedPlugin dataclass
# ---------------------------------------------------------------------------

class TestLoadedPluginDataclass:
    """Tests for the LoadedPlugin dataclass."""

    def test_to_dict(self):
        """to_dict serializes all fields correctly."""
        p = LoadedPlugin(
            id="test",
            name="Test",
            plugin_type="agent",
            file_path="/tmp/test.py",
            instance=None,
            hooks=["on_event_created"],
            enabled=True,
            load_error=None,
        )
        d = p.to_dict()
        assert d["id"] == "test"
        assert d["name"] == "Test"
        assert d["plugin_type"] == "agent"
        assert d["hooks"] == ["on_event_created"]
        assert d["enabled"] is True
        assert d["load_error"] is None
        assert "loaded_at" in d

    def test_to_dict_with_error(self):
        """to_dict includes load_error when set."""
        p = LoadedPlugin(
            id="bad",
            name="bad",
            plugin_type="unknown",
            file_path="/tmp/bad.py",
            instance=None,
            load_error="SyntaxError: oops",
        )
        d = p.to_dict()
        assert d["load_error"] == "SyntaxError: oops"


# ---------------------------------------------------------------------------
# Constants and singleton
# ---------------------------------------------------------------------------

class TestConstantsAndSingleton:
    """Tests for module constants and singleton behavior."""

    def test_supported_hooks_list(self):
        """SUPPORTED_HOOKS contains the expected hooks."""
        expected = {
            "on_event_created",
            "on_event_updated",
            "on_event_deleted",
            "on_sync_complete",
            "on_intent_classified",
            "on_conductor_response",
            "get_agent_spec",
            "get_sync_rules",
        }
        assert set(SUPPORTED_HOOKS) == expected

    def test_default_plugin_dir(self):
        """DEFAULT_PLUGIN_DIR points to ~/.a-cal/plugins/."""
        assert DEFAULT_PLUGIN_DIR.endswith(".a-cal/plugins")

    def test_get_runtime_singleton(self, monkeypatch, tmp_path):
        """get_runtime returns the same instance on repeated calls."""
        import a_cal.developer.plugin_runtime as pr
        monkeypatch.setattr(pr, "_runtime", None)
        monkeypatch.setenv("A_CAL_PLUGIN_DIR", str(tmp_path))
        r1 = pr.get_runtime()
        r2 = pr.get_runtime()
        assert r1 is r2
        monkeypatch.setattr(pr, "_runtime", None)

    def test_get_runtime_uses_env_var(self, monkeypatch, tmp_path):
        """get_runtime picks up A_CAL_PLUGIN_DIR from the environment."""
        import a_cal.developer.plugin_runtime as pr
        monkeypatch.setattr(pr, "_runtime", None)
        custom = str(tmp_path / "custom_plugins")
        monkeypatch.setenv("A_CAL_PLUGIN_DIR", custom)
        rt = pr.get_runtime()
        assert rt._plugin_dir == custom
        monkeypatch.setattr(pr, "_runtime", None)
