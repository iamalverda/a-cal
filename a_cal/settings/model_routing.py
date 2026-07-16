"""Model routing configuration (Q4).

Beginner default: one global model setting (pick local or cloud, done).
Underlying rule: anything touching personal, identity, or email content is
forced local regardless of the global choice.
Advanced settings expose per-task model assignment.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ModelProvider(str, enum.Enum):
    """Supported model providers — mainstream and open-source (BYOK)."""

    # Local
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    LM_STUDIO = "lm_studio"

    # Cloud — mainstream
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"

    # Cloud — open-source friendly
    DEEPSEEK = "deepseek"
    TOGETHER = "together"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    MISTRAL = "mistral"


# Tasks that are always forced local (privacy-tiered routing, Q4).
FORCE_LOCAL_TASKS = {"email", "self_model", "negotiate"}


@dataclass
class ModelRoutingConfig:
    """The user's model routing configuration.

    In Simple mode, only ``global_provider`` and ``global_model`` are visible.
    In Pro/Developer mode, ``per_task_overrides`` allows assigning different
    models to different agent tasks (cheap model for sync, smart model for
    reasoning).
    """

    global_provider: str = ModelProvider.OLLAMA.value
    global_model: str = "llama3.2"  # sensible default local model
    per_task_overrides: dict[str, str] = field(default_factory=dict)
    # API keys are stored as refs into atom's encrypted token storage.
    api_key_refs: dict[str, str] = field(default_factory=dict)
    # Informational only: surfaced in settings so users can SEE that privacy-
    # sensitive tasks run locally. It does NOT gate the enforcement — the force
    # in resolve_model is unconditional (charter: "privacy is structural, not a
    # setting … cannot accidentally disable it"). Kept for backward-compatible
    # serialization; setting it False has no effect on routing.
    privacy_force_local: bool = True

    def resolve_model(self, task: str) -> dict[str, str]:
        """Resolve which provider + model to use for a given task.

        Privacy-sensitive tasks (email, self_model, negotiate) are ALWAYS
        forced to local — unconditionally, regardless of the global setting,
        per-task overrides, or the ``privacy_force_local`` flag. This makes the
        privacy guarantee structural rather than a toggle the user (or an API
        caller) could flip off.
        """
        if task in FORCE_LOCAL_TASKS:
            return {"provider": ModelProvider.OLLAMA.value, "model": "local-private", "forced_local": "true"}

        override = self.per_task_overrides.get(task)
        if override:
            # Override format: "provider:model"
            if ":" in override:
                provider, model = override.split(":", 1)
                return {"provider": provider, "model": model, "forced_local": "false"}
            return {"provider": self.global_provider, "model": override, "forced_local": "false"}

        return {"provider": self.global_provider, "model": self.global_model, "forced_local": "false"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_provider": self.global_provider,
            "global_model": self.global_model,
            "per_task_overrides": dict(self.per_task_overrides),
            "api_key_refs": dict(self.api_key_refs),
            "privacy_force_local": self.privacy_force_local,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRoutingConfig:
        return cls(
            global_provider=data.get("global_provider", ModelProvider.OLLAMA.value),
            global_model=data.get("global_model", "llama3.2"),
            per_task_overrides=dict(data.get("per_task_overrides", {})),
            api_key_refs=dict(data.get("api_key_refs", {})),
            privacy_force_local=data.get("privacy_force_local", True),
        )
