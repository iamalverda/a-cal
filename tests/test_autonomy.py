"""Tests for agent autonomy levels (Q4).

Three levels: suggest_only, confirm, full_auto.
Global default with per-sub-account overrides.
The conductor gates action execution based on the effective level.
"""

from __future__ import annotations

import pytest

from a_cal.settings.autonomy import AutonomyConfig, AutonomyLevel


class TestAutonomyConfig:
    """Unit tests for AutonomyConfig resolution logic."""

    def test_default_is_confirm(self):
        """Default autonomy level is CONFIRM (agentic but secure)."""
        cfg = AutonomyConfig()
        assert cfg.default_level == AutonomyLevel.CONFIRM.value
        assert cfg.resolve(None) == AutonomyLevel.CONFIRM

    def test_resolve_uses_global_default(self):
        """resolve() returns the global default when no override exists."""
        cfg = AutonomyConfig(default_level=AutonomyLevel.FULL_AUTO.value)
        assert cfg.resolve(None) == AutonomyLevel.FULL_AUTO
        assert cfg.resolve("some_sub_id") == AutonomyLevel.FULL_AUTO

    def test_resolve_uses_per_sub_account_override(self):
        """Per-sub-account override takes precedence over global default."""
        cfg = AutonomyConfig(
            default_level=AutonomyLevel.CONFIRM.value,
            per_sub_account={"sub1": AutonomyLevel.SUGGEST_ONLY.value},
        )
        assert cfg.resolve("sub1") == AutonomyLevel.SUGGEST_ONLY
        assert cfg.resolve("sub2") == AutonomyLevel.CONFIRM
        assert cfg.resolve(None) == AutonomyLevel.CONFIRM

    def test_resolve_falls_back_on_invalid_override(self):
        """Invalid per-sub-account level falls back to global default."""
        cfg = AutonomyConfig(
            default_level=AutonomyLevel.CONFIRM.value,
            per_sub_account={"sub1": "bogus_level"},
        )
        assert cfg.resolve("sub1") == AutonomyLevel.CONFIRM

    def test_resolve_falls_back_on_invalid_default(self):
        """Invalid global default falls back to CONFIRM."""
        cfg = AutonomyConfig(default_level="nonsense")
        assert cfg.resolve(None) == AutonomyLevel.CONFIRM

    def test_should_execute_only_full_auto(self):
        """should_execute() is True only for FULL_AUTO."""
        for level in AutonomyLevel:
            cfg = AutonomyConfig(default_level=level.value)
            assert cfg.should_execute(None) == (level == AutonomyLevel.FULL_AUTO)

    def test_should_confirm_only_confirm(self):
        """should_confirm() is True only for CONFIRM."""
        for level in AutonomyLevel:
            cfg = AutonomyConfig(default_level=level.value)
            assert cfg.should_confirm(None) == (level == AutonomyLevel.CONFIRM)

    def test_to_dict_roundtrip(self):
        """to_dict / from_dict preserves all fields."""
        cfg = AutonomyConfig(
            default_level=AutonomyLevel.FULL_AUTO.value,
            per_sub_account={"a": "suggest_only", "b": "confirm"},
        )
        d = cfg.to_dict()
        restored = AutonomyConfig.from_dict(d)
        assert restored.default_level == AutonomyLevel.FULL_AUTO.value
        assert restored.per_sub_account == {"a": "suggest_only", "b": "confirm"}
        assert restored.resolve("a") == AutonomyLevel.SUGGEST_ONLY
        assert restored.resolve("b") == AutonomyLevel.CONFIRM
        assert restored.resolve("c") == AutonomyLevel.FULL_AUTO

    def test_from_dict_defaults(self):
        """from_dict with empty data returns sensible defaults."""
        cfg = AutonomyConfig.from_dict({})
        assert cfg.default_level == AutonomyLevel.CONFIRM.value
        assert cfg.per_sub_account == {}

    def test_per_sub_account_override_for_should_execute(self):
        """should_execute respects per-sub-account overrides."""
        cfg = AutonomyConfig(
            default_level=AutonomyLevel.FULL_AUTO.value,
            per_sub_account={"safe_sub": AutonomyLevel.SUGGEST_ONLY.value},
        )
        assert cfg.should_execute("safe_sub") is False
        assert cfg.should_execute("other_sub") is True
        assert cfg.should_execute(None) is True
