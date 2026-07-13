"""Standalone LLM service — talks to Ollama and cloud providers without atom.

This module provides the ``StandaloneLLMService`` that the conductor uses to
generate real LLM responses in standalone mode. In the full atom deployment,
this is replaced by atom's model service (which handles the same routing but
with atom's encrypted key storage and multi-tenant support).

Supported providers:
  - Ollama (local) — HTTP to localhost:11434, no API key needed
  - OpenAI — chat completions API
  - Anthropic — messages API
  - Groq — OpenAI-compatible
  - OpenRouter — OpenAI-compatible
  - Together — OpenAI-compatible
  - DeepSeek — OpenAI-compatible
  - Google Gemini — generateContent API
  - Mistral — OpenAI-compatible

All HTTP calls use ``httpx.AsyncClient``. If the provider is unreachable or
the API key is missing, the service returns an error string instead of
raising so the conductor can still return routing info.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from a_cal.settings.model_routing import ModelProvider, ModelRoutingConfig

logger = logging.getLogger(__name__)

# HTTP timeout for LLM calls (models can be slow, especially local ones).
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
# Shorter timeout for Ollama model listing (just a metadata fetch).
_OLLAMA_LIST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    text: str
    provider: str
    model: str
    forced_local: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "forced_local": self.forced_local,
            "error": self.error,
        }


class StandaloneLLMService:
    """Async LLM service that routes to local or cloud models.

    Constructed with the user's ModelRoutingConfig and optional API keys.
    The conductor passes user messages + system prompts; this service resolves
    the right provider/model, makes the call, and returns the text.

    If the configured provider is unreachable, returns an error response
    instead of raising — the conductor can still return routing info.
    """

    # Ollama default endpoint (configurable via constructor).
    _ollama_url: str = "http://localhost:11434"

    # Cloud provider base URLs.
    _CLOUD_URLS: dict[str, str] = {
        ModelProvider.OPENAI.value: "https://api.openai.com/v1",
        ModelProvider.GROQ.value: "https://api.groq.com/openai/v1",
        ModelProvider.OPENROUTER.value: "https://openrouter.ai/api/v1",
        ModelProvider.TOGETHER.value: "https://api.together.xyz/v1",
        ModelProvider.DEEPSEEK.value: "https://api.deepseek.com/v1",
        ModelProvider.MISTRAL.value: "https://api.mistral.ai/v1",
    }

    # Providers that use the OpenAI-compatible chat completions format.
    _OPENAI_COMPATIBLE = {
        ModelProvider.OPENAI.value,
        ModelProvider.GROQ.value,
        ModelProvider.OPENROUTER.value,
        ModelProvider.TOGETHER.value,
        ModelProvider.DEEPSEEK.value,
        ModelProvider.MISTRAL.value,
    }

    def __init__(
        self,
        routing: ModelRoutingConfig | None = None,
        api_keys: dict[str, str] | None = None,
        ollama_url: str | None = None,
    ) -> None:
        """Initialize with routing config and API keys.

        Args:
            routing: The user's model routing config. Falls back to defaults.
            api_keys: Map of provider name → API key for cloud providers.
            ollama_url: Override for the Ollama endpoint.
        """
        self.routing = routing or ModelRoutingConfig()
        self.api_keys = api_keys or {}
        if ollama_url:
            self._ollama_url = ollama_url

    async def warmup(self) -> None:
        """Preload the configured model into memory with a tiny prompt.

        Local models (Ollama) need to be loaded into RAM before the first
        real request, which can add 10-60 seconds of latency. Calling this
        on startup or when the user enables the LLM makes the first chat
        message feel instant. Safe to call multiple times — Ollama keeps
        the model loaded based on its ``keep_alive`` setting.
        """
        resolved = self.routing.resolve_model("chat")
        provider = resolved["provider"]
        if provider != ModelProvider.OLLAMA.value:
            return  # Only Ollama benefits from warmup
        try:
            await self._call_ollama(
                prompt="Ready.",
                system_prompt="You are a calendar assistant.",
                model=resolved["model"],
            )
            logger.info("Ollama model warmed up successfully")
        except Exception as exc:
            logger.debug("Ollama warmup skipped: %r", exc)

    async def generate_response(
        self,
        prompt: str,
        system_prompt: str = "",
        task: str = "chat",
        tenant_id: str = "local-dev-user",
    ) -> str:
        """Generate a response from the appropriate LLM.

        Args:
            prompt: The user's message or instruction.
            system_prompt: The agent's system prompt (role, constraints).
            task: The task type (chat, sync, schedule, email, negotiate,
                  self_model). Used for model routing and privacy enforcement.
            tenant_id: User identifier (for future multi-tenant support).

        Returns:
            The LLM's response text. If the provider is unreachable, returns
            an error message string (never raises).
        """
        resolved = self.routing.resolve_model(task)
        provider = resolved["provider"]
        model = resolved["model"]

        try:
            if provider in (ModelProvider.OLLAMA.value, ModelProvider.LLAMA_CPP.value, ModelProvider.LM_STUDIO.value):
                response = await self._call_ollama(prompt, system_prompt, model)
            elif provider in self._OPENAI_COMPATIBLE:
                response = await self._call_openai_compatible(
                    prompt, system_prompt, model, provider,
                )
            elif provider == ModelProvider.ANTHROPIC.value:
                response = await self._call_anthropic(prompt, system_prompt, model)
            elif provider == ModelProvider.GOOGLE.value:
                response = await self._call_gemini(prompt, system_prompt, model)
            elif provider == ModelProvider.AZURE.value:
                response = await self._call_azure(prompt, system_prompt, model)
            else:
                logger.warning("unknown provider %s, falling back to ollama", provider)
                response = await self._call_ollama(prompt, system_prompt, model)

            return response.text

        except httpx.TimeoutException as exc:
            logger.error(
                "LLM call timed out (provider=%s, model=%s): %r",
                provider, model, exc,
            )
            return (
                f"The {provider} model took too long to respond (timed out after "
                f"the configured wait). Local models can be slow on first load — "
                f"try again, or switch to a smaller model in Settings."
            )
        except Exception as exc:
            logger.error(
                "LLM call failed (provider=%s, model=%s): %r",
                provider, model, exc,
            )
            err_msg = str(exc) or repr(exc)
            return (
                f"I couldn't reach the {provider} service right now. "
                f"Error: {err_msg}. You can check your model settings or try again."
            )

    async def _call_ollama(
        self, prompt: str, system_prompt: str, model: str,
    ) -> LLMResponse:
        """Call Ollama's /api/chat endpoint (local, no API key)."""
        # If the requested model isn't available, fall back to the first
        # installed model rather than failing hard.
        actual_model = await self._resolve_ollama_model(model)
        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            # Keep the model loaded in memory for 5 minutes after the call
            # so subsequent messages are fast (no model reload overhead).
            "keep_alive": "5m",
            # Limit context window and response length for speed. Ollama's
            # default context is 128K tokens, which causes huge memory
            # allocation and slow inference even for short prompts. 8K is
            # plenty for calendar chat. num_predict caps the response at
            # ~300 words so the model doesn't ramble.
            "options": {
                "num_ctx": 8192,
                "num_predict": 256,
                # Low temperature for factual calendar responses — prevents
                # the model from inventing events or times that don't exist.
                "temperature": 0.3,
            },
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/chat",
                json=payload,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            return LLMResponse(
                text=text,
                provider=ModelProvider.OLLAMA.value,
                model=actual_model,
            )

    async def _resolve_ollama_model(self, requested: str) -> str:
        """Return the requested model if available, else the first installed model.

        This handles the case where the user's configured model name doesn't
        match any installed Ollama model (e.g. default 'llama3.2' when only
        'gemma3:4b' is installed). Falls back gracefully instead of erroring.
        """
        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_LIST_TIMEOUT) as client:
                resp = await client.get(f"{self._ollama_url}/api/tags")
                if resp.status_code != 200:
                    return requested
                models = [m["name"] for m in resp.json().get("models", [])]
                if requested in models:
                    return requested
                if models:
                    logger.info(
                        "model %r not found in Ollama, falling back to %r",
                        requested, models[0],
                    )
                    return models[0]
                return requested
        except Exception:
            return requested

    async def _call_openai_compatible(
        self, prompt: str, system_prompt: str, model: str, provider: str,
    ) -> LLMResponse:
        """Call an OpenAI-compatible chat completions endpoint."""
        api_key = self.api_keys.get(provider, "")
        if not api_key:
            raise RuntimeError(
                f"No API key set for {provider}. Add it in Settings → Model Routing."
            )

        base_url = self._CLOUD_URLS.get(provider, "https://api.openai.com/v1")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"{provider} returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return LLMResponse(text=text, provider=provider, model=model)

    async def _call_anthropic(
        self, prompt: str, system_prompt: str, model: str,
    ) -> LLMResponse:
        """Call Anthropic's messages API."""
        api_key = self.api_keys.get(ModelProvider.ANTHROPIC.value, "")
        if not api_key:
            raise RuntimeError("No API key set for Anthropic.")

        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Anthropic returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            text = data["content"][0]["text"]
            return LLMResponse(
                text=text,
                provider=ModelProvider.ANTHROPIC.value,
                model=model,
            )

    async def _call_gemini(
        self, prompt: str, system_prompt: str, model: str,
    ) -> LLMResponse:
        """Call Google Gemini's generateContent API."""
        api_key = self.api_keys.get(ModelProvider.GOOGLE.value, "")
        if not api_key:
            raise RuntimeError("No API key set for Google Gemini.")

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                json=payload,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return LLMResponse(
                text=text,
                provider=ModelProvider.GOOGLE.value,
                model=model,
            )

    async def _call_azure(
        self, prompt: str, system_prompt: str, model: str,
    ) -> LLMResponse:
        """Call Azure OpenAI (requires endpoint + API key in config)."""
        api_key = self.api_keys.get(ModelProvider.AZURE.value, "")
        endpoint = self.api_keys.get("azure_endpoint", "")
        if not api_key or not endpoint:
            raise RuntimeError("Azure requires both an API key and endpoint URL.")

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"api-key": api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{endpoint}/openai/deployments/{model}/chat/completions?api-version=2024-02-15-preview",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Azure returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return LLMResponse(
                text=text,
                provider=ModelProvider.AZURE.value,
                model=model,
            )


async def check_ollama_available(ollama_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is running and reachable.

    Returns True if the Ollama API responds, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_LIST_TIMEOUT) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def list_ollama_models(ollama_url: str = "http://localhost:11434") -> list[str]:
    """List available models from the local Ollama instance.

    Returns a list of model names. Empty list if Ollama is not running.
    """
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_LIST_TIMEOUT) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []
