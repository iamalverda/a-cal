"""Tests for the developer layer — plugins, config-as-code, agent spec CRUD."""

from __future__ import annotations

import pytest

from a_cal.developer.plugins import PluginBase, PluginRegistry, PluginType
from a_cal.developer.config_io import ConfigExporter, ConfigImporter, CONFIG_SCHEMA_VERSION
from a_cal.developer.agent_crud import AgentSpecStore
from a_cal.agents.specs import AgentSpec, CognitiveTier, A_CAL_AGENTS


# --- Plugin system tests ----------------------------------------------------

class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        plugin = PluginBase(name="Test Plugin", plugin_type=PluginType.AGENT.value)
        reg.register(plugin)
        assert reg.get(plugin.id) is plugin

    def test_unregister(self):
        reg = PluginRegistry()
        plugin = PluginBase(name="Test", plugin_type=PluginType.AGENT.value)
        reg.register(plugin)
        assert reg.unregister(plugin.id) is True
        assert reg.get(plugin.id) is None

    def test_unregister_nonexistent(self):
        reg = PluginRegistry()
        assert reg.unregister("nonexistent") is False

    def test_list_filtered_by_type(self):
        reg = PluginRegistry()
        reg.register(PluginBase(name="Agent Plugin", plugin_type=PluginType.AGENT.value))
        reg.register(PluginBase(name="Provider Plugin", plugin_type=PluginType.PROVIDER.value))

        agents = reg.list_plugins(plugin_type=PluginType.AGENT.value)
        assert len(agents) == 1
        assert agents[0].name == "Agent Plugin"

    def test_list_enabled_only(self):
        reg = PluginRegistry()
        reg.register(PluginBase(name="Enabled", plugin_type=PluginType.AGENT.value, enabled=True))
        reg.register(PluginBase(name="Disabled", plugin_type=PluginType.AGENT.value, enabled=False))

        enabled = reg.list_plugins(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "Enabled"

    def test_enable_disable(self):
        reg = PluginRegistry()
        plugin = PluginBase(name="Test", plugin_type=PluginType.AGENT.value, enabled=False)
        reg.register(plugin)

        reg.enable(plugin.id)
        assert plugin.enabled is True

        reg.disable(plugin.id)
        assert plugin.enabled is False

    def test_update_config(self):
        reg = PluginRegistry()
        plugin = PluginBase(name="Test", plugin_type=PluginType.AGENT.value, default_config={"key": "old"})
        reg.register(plugin)

        reg.update_config(plugin.id, {"key": "new", "extra": "added"})
        assert plugin.default_config["key"] == "new"
        assert plugin.default_config["extra"] == "added"

    def test_to_dict_list(self):
        reg = PluginRegistry()
        reg.register(PluginBase(name="Test", plugin_type=PluginType.AGENT.value))
        dicts = reg.to_dict_list()
        assert len(dicts) == 1
        assert dicts[0]["name"] == "Test"

    def test_plugin_roundtrip(self):
        plugin = PluginBase(name="Roundtrip", plugin_type=PluginType.AGENT.value, description="Test")
        data = plugin.to_dict()
        restored = PluginBase.from_dict(data)
        assert restored.name == plugin.name
        assert restored.plugin_type == plugin.plugin_type


# --- Config-as-code tests ---------------------------------------------------

class TestConfigExport:
    def test_export_contains_required_keys(self):
        exporter = ConfigExporter()
        config = exporter.export()

        assert config["schema_version"] == CONFIG_SCHEMA_VERSION
        assert "mode" in config
        assert "model_routing" in config
        assert "self_model" in config
        assert "custom_agent_specs" in config
        assert "plugins" in config
        assert "sub_accounts" in config

    def test_export_to_json(self):
        exporter = ConfigExporter()
        json_str = exporter.to_json()
        assert '"schema_version"' in json_str
        assert isinstance(json_str, str)

    def test_export_includes_custom_agents(self):
        exporter = ConfigExporter(
            custom_agent_specs=[{"name": "custom_agent", "display_name": "Custom"}]
        )
        config = exporter.export()
        assert len(config["custom_agent_specs"]) == 1

    def test_export_includes_built_in_count(self):
        exporter = ConfigExporter()
        config = exporter.export()
        assert config["built_in_agent_count"] == len(A_CAL_AGENTS)


class TestConfigImport:
    def test_import_roundtrip(self):
        exporter = ConfigExporter(mode="pro")
        exported = exporter.export()

        importer = ConfigImporter()
        result = importer.import_config(exported)

        assert result["mode"] == "pro"
        assert len(importer.errors) == 0

    def test_import_json_string(self):
        exporter = ConfigExporter()
        json_str = exporter.to_json()

        importer = ConfigImporter()
        result = importer.import_json(json_str)

        assert "model_routing" in result
        assert "self_model" in result

    def test_import_warns_on_version_mismatch(self):
        importer = ConfigImporter()
        result = importer.import_config({
            "schema_version": "0.0.0",
            "mode": {"mode": "simple"},
        })
        assert len(importer.warnings) > 0
        assert "version mismatch" in importer.warnings[0]

    def test_import_defaults_on_missing_mode(self):
        importer = ConfigImporter()
        result = importer.import_config({})
        assert result["mode"] == "simple"
        assert any("mode" in w for w in importer.warnings)

    def test_import_handles_bad_routing_gracefully(self):
        importer = ConfigImporter()
        result = importer.import_config({
            "schema_version": CONFIG_SCHEMA_VERSION,
            "model_routing": {"not_valid": True},
        })
        # Should fall back to defaults without crashing.
        assert result["model_routing"].global_provider  # has a default value


# --- Agent spec CRUD tests --------------------------------------------------

class TestAgentSpecStore:
    def test_list_all_includes_builtins(self):
        store = AgentSpecStore()
        specs = store.list_all()
        assert len(specs) >= 6  # 6 built-in agents

    def test_list_custom_empty_by_default(self):
        store = AgentSpecStore()
        assert len(store.list_custom()) == 0

    def test_create_custom_spec(self):
        store = AgentSpecStore()
        spec = AgentSpec(
            name="my_custom_agent",
            display_name="My Custom Agent",
            description="A custom agent",
            system_prompt="You are a custom agent.",
        )
        created = store.create(spec)
        assert created.name == "my_custom_agent"
        assert store.get("my_custom_agent") is spec

    def test_create_conflicts_with_builtin(self):
        store = AgentSpecStore()
        spec = AgentSpec(name="a_cal_conductor", display_name="Fake Conductor", description="Fake", system_prompt="Fake")
        with pytest.raises(ValueError, match="conflicts with a built-in"):
            store.create(spec)

    def test_create_duplicate_custom(self):
        store = AgentSpecStore()
        spec = AgentSpec(name="custom_1", display_name="Custom 1", description="A custom agent", system_prompt="You are a custom agent.")
        store.create(spec)
        with pytest.raises(ValueError, match="already exists"):
            store.create(AgentSpec(name="custom_1", display_name="Dup", description="Dup", system_prompt="Dup"))

    def test_update_custom_spec(self):
        store = AgentSpecStore()
        store.create(AgentSpec(name="custom_1", display_name="Original", description="Original", system_prompt="Original prompt"))
        updated = store.update("custom_1", {"display_name": "Updated", "system_prompt": "New prompt"})

        assert updated.display_name == "Updated"
        assert updated.system_prompt == "New prompt"

    def test_update_builtin_raises(self):
        store = AgentSpecStore()
        with pytest.raises(ValueError, match="cannot modify built-in"):
            store.update("a_cal_conductor", {"display_name": "Hacked"})

    def test_update_nonexistent_raises(self):
        store = AgentSpecStore()
        with pytest.raises(KeyError):
            store.update("nonexistent", {"display_name": "Test"})

    def test_delete_custom_spec(self):
        store = AgentSpecStore()
        store.create(AgentSpec(name="custom_1", display_name="Custom 1", description="A custom agent", system_prompt="You are a custom agent."))
        assert store.delete("custom_1") is True
        assert store.get("custom_1") is None

    def test_delete_builtin_raises(self):
        store = AgentSpecStore()
        with pytest.raises(ValueError, match="cannot delete built-in"):
            store.delete("a_cal_conductor")

    def test_delete_nonexistent_returns_false(self):
        store = AgentSpecStore()
        assert store.delete("nonexistent") is False

    def test_to_dict_list(self):
        store = AgentSpecStore()
        store.create(AgentSpec(name="custom_1", display_name="Custom 1", description="A custom agent", system_prompt="You are a custom agent."))
        dicts = store.to_dict_list()
        # 6 built-ins + 1 custom
        assert len(dicts) >= 7
        names = [d["name"] for d in dicts]
        assert "custom_1" in names
        assert "a_cal_conductor" in names
