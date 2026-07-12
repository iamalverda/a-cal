"""Tests for the settings module — skill progression modes and model routing."""

import pytest

from a_cal.settings import (
    SkillMode,
    SIMPLE_MODE,
    PRO_MODE,
    DEVELOPER_MODE,
    get_mode_config,
    ModelRoutingConfig,
    ModelProvider,
)
from a_cal.settings.model_routing import FORCE_LOCAL_TASKS


class TestSkillModes:
    def test_simple_mode_defaults(self):
        assert SIMPLE_MODE.mode == SkillMode.SIMPLE
        assert SIMPLE_MODE.developer_studio is False
        assert SIMPLE_MODE.api_sdk is False
        assert SIMPLE_MODE.plugin_system is False
        assert SIMPLE_MODE.visual_builder is True

    def test_pro_mode_adds_plugins_and_config(self):
        assert PRO_MODE.plugin_system is True
        assert PRO_MODE.config_as_code is True
        assert PRO_MODE.per_task_model_routing is True
        assert PRO_MODE.developer_studio is False
        assert PRO_MODE.api_sdk is False

    def test_developer_mode_adds_studio_and_api(self):
        assert DEVELOPER_MODE.developer_studio is True
        assert DEVELOPER_MODE.api_sdk is True
        assert DEVELOPER_MODE.plugin_system is True

    def test_modes_are_additive(self):
        # Core panels (calendar, command_bar, sub_accounts) should be shared
        core = {"calendar", "command_bar", "sub_accounts"}
        assert core.issubset(set(SIMPLE_MODE.visible_panels))
        assert core.issubset(set(PRO_MODE.visible_panels))
        assert core.issubset(set(DEVELOPER_MODE.visible_panels))
        # Each mode should have at least as many panels as the one below
        assert len(PRO_MODE.visible_panels) >= len(SIMPLE_MODE.visible_panels)
        assert len(DEVELOPER_MODE.visible_panels) >= len(PRO_MODE.visible_panels)

    def test_get_mode_config_fallback(self):
        config = get_mode_config("nonexistent")
        assert config.mode == SkillMode.SIMPLE

    def test_simple_default_sync_mode(self):
        assert SIMPLE_MODE.default_sync_mode == "mirror_filter"

    def test_developer_default_self_model_depth(self):
        assert DEVELOPER_MODE.default_self_model_depth == "attention_intent"


class TestModelRouting:
    def test_default_is_local(self):
        config = ModelRoutingConfig()
        result = config.resolve_model("sync")
        assert result["provider"] == ModelProvider.OLLAMA.value

    def test_email_forced_local(self):
        config = ModelRoutingConfig(global_provider=ModelProvider.OPENAI.value)
        result = config.resolve_model("email")
        assert result["forced_local"] == "true"
        assert result["provider"] == ModelProvider.OLLAMA.value

    def test_self_model_forced_local(self):
        config = ModelRoutingConfig(global_provider=ModelProvider.ANTHROPIC.value)
        result = config.resolve_model("self_model")
        assert result["forced_local"] == "true"

    def test_negotiate_forced_local(self):
        config = ModelRoutingConfig(global_provider=ModelProvider.OPENAI.value)
        result = config.resolve_model("negotiate")
        assert result["forced_local"] == "true"

    def test_per_task_override(self):
        config = ModelRoutingConfig(
            global_provider=ModelProvider.OLLAMA.value,
            per_task_overrides={"schedule": "openai:gpt-4o"},
        )
        result = config.resolve_model("schedule")
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"
        assert result["forced_local"] == "false"

    def test_sync_not_forced_local(self):
        config = ModelRoutingConfig(global_provider=ModelProvider.OPENAI.value)
        result = config.resolve_model("sync")
        assert result["forced_local"] == "false"
        assert result["provider"] == "openai"

    def test_roundtrip(self):
        config = ModelRoutingConfig(
            global_provider="openai",
            global_model="gpt-4o",
            per_task_overrides={"sync": "ollama:llama3.2"},
        )
        data = config.to_dict()
        restored = ModelRoutingConfig.from_dict(data)
        assert restored.global_provider == "openai"
        assert restored.global_model == "gpt-4o"
        assert restored.per_task_overrides["sync"] == "ollama:llama3.2"

    def test_all_providers_present(self):
        """Ensure mainstream and open-source providers are all listed."""
        values = {p.value for p in ModelProvider}
        # Mainstream
        assert "openai" in values
        assert "anthropic" in values
        assert "google" in values
        # Open-source friendly
        assert "deepseek" in values
        assert "groq" in values
        assert "openrouter" in values
        assert "together" in values
        # Local
        assert "ollama" in values
        assert "llama_cpp" in values
        assert "lm_studio" in values
