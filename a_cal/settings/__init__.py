"""A-Cal settings — skill progression modes and feature gates.

Three named modes (Q9) switch the UI surface and capability set:
  - SIMPLE:     Beginners, non-technical. Visual builder, one-model dropdown.
  - PRO:        Power users. Plugins, per-task model overrides, config-as-code.
  - DEVELOPER:  Developers. API/SDK, Developer Studio for building plugins.

Plus the developer on-ramps (Q7) and model routing config (Q4).
"""

from a_cal.settings.modes import (
    SkillMode,
    ModeConfig,
    SIMPLE_MODE,
    PRO_MODE,
    DEVELOPER_MODE,
    ALL_MODES,
    get_mode_config,
)
from a_cal.settings.model_routing import ModelRoutingConfig, ModelProvider

__all__ = [
    "SkillMode",
    "ModeConfig",
    "SIMPLE_MODE",
    "PRO_MODE",
    "DEVELOPER_MODE",
    "ALL_MODES",
    "get_mode_config",
    "ModelRoutingConfig",
    "ModelProvider",
]
