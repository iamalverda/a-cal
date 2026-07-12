"""Atom integration bridge — upgrades A-Cal when atom is available.

A-Cal runs in two modes:

  **Standalone** (default): SQLite storage, StandaloneLLMService for model
  dispatch, keyword-based intent classification. No external dependencies.

  **Atom-backed** (when atom is on PYTHONPATH): encrypted OAuth token storage
  via atom's ConnectionService, LLM inference via atom's LLMService with
  BYOKHandler and cognitive tier routing, and LLM-powered intent
  classification via atom's IntentClassifier.

The bridge detects atom at import time and provides adapter objects that
implement the same interfaces as their standalone counterparts. Callers
don't need to know which mode is active — they call the same methods.

Usage::

    from a_cal.integrations.atom_bridge import get_atom_adapters

    token_storage, llm_service, intent_classifier = get_atom_adapters()
    if token_storage:
        # atom is available — use encrypted storage
        token_storage.save_oauth_tokens(provider_id, tokens)
    else:
        # standalone — use SQLite config column
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def is_atom_available() -> bool:
    """Check whether atom's backend is importable.

    Returns True if ``core.connection_service`` and ``core.llm_service``
    can be imported (atom is on PYTHONPATH), False otherwise.
    """
    try:
        import core.connection_service  # type: ignore  # noqa: F401
        import core.llm_service  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Token storage adapter
# ---------------------------------------------------------------------------

class AtomTokenStorage:
    """Adapter around atom's ConnectionService for encrypted OAuth token storage.

    In standalone mode, OAuth tokens are stored in the provider connection's
    ``config`` JSON column (plaintext in SQLite). When atom is available,
    tokens are encrypted via atom's CredentialVault/ConnectionService and
    stored in atom's ``UserConnection`` table with Fernet encryption at rest.
    """

    def __init__(self) -> None:
        """Initialize the adapter, importing atom's ConnectionService.

        Raises:
            ImportError: If atom is not available (caller should check
                ``is_atom_available()`` first).
        """
        from core.connection_service import ConnectionService  # type: ignore

        self._svc = ConnectionService()
        logger.info("AtomTokenStorage initialized with atom ConnectionService")

    def save_oauth_tokens(
        self, user_id: str, provider_type: str, tokens: Dict[str, Any],
    ) -> str:
        """Store encrypted OAuth tokens for a provider connection.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type (google_calendar, outlook_calendar, gmail).
            tokens: Token dict (access_token, refresh_token, etc.).

        Returns:
            The connection ID in atom's UserConnection table.
        """
        connection_id = f"a_cal_{provider_type}_{user_id}"
        self._svc.save_connection(
            user_id=user_id,
            connection_id=connection_id,
            provider=provider_type,
            credentials=tokens,
        )
        logger.info("Stored encrypted OAuth tokens for %s/%s", user_id, provider_type)
        return connection_id

    def get_oauth_tokens(
        self, user_id: str, provider_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt OAuth tokens for a provider.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type.

        Returns:
            Decrypted token dict, or None if not found.
        """
        connection_id = f"a_cal_{provider_type}_{user_id}"
        return self._svc.get_connection_credentials(user_id, connection_id)

    def delete_oauth_tokens(self, user_id: str, provider_type: str) -> bool:
        """Delete stored OAuth tokens for a provider.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type.

        Returns:
            True if deleted, False if not found.
        """
        connection_id = f"a_cal_{provider_type}_{user_id}"
        return self._svc.delete_connection(user_id, connection_id)


# ---------------------------------------------------------------------------
# LLM service adapter
# ---------------------------------------------------------------------------

class AtomLLMAdapter:
    """Adapter around atom's LLMService that matches StandaloneLLMService's interface.

    The conductor calls ``generate_response(prompt, system_prompt, task,
    tenant_id)``. This adapter translates that call into atom's
    ``LLMService.generate(prompt, system_instruction, ...)`` and returns
    a normalized LLMResponse-compatible dict.

    atom's LLMService handles BYOK key resolution, cognitive tier routing,
    and governance de-escalation — so A-Cal gets all of that for free.
    """

    def __init__(self, workspace_id: str = "default") -> None:
        """Initialize the adapter.

        Args:
            workspace_id: atom workspace ID for multi-tenant key resolution.

        Raises:
            ImportError: If atom is not available.
        """
        from core.llm_service import get_llm_service  # type: ignore

        self._llm = get_llm_service(workspace_id=workspace_id)
        self._workspace_id = workspace_id
        logger.info("AtomLLMAdapter initialized with atom LLMService")

    async def generate_response(
        self,
        prompt: str,
        system_prompt: str = "",
        task: str = "chat",
        tenant_id: str = "local-dev-user",
    ) -> str:
        """Generate a response via atom's LLM service.

        Args:
            prompt: The user's message or instruction.
            system_prompt: The agent's system prompt.
            task: The task type (used for logging; atom handles tier routing).
            tenant_id: User identifier.

        Returns:
            The LLM's response text.
        """
        text = await self._llm.generate(
            prompt=prompt,
            system_instruction=system_prompt or "You are a helpful calendar assistant.",
            model="auto",
            workspace_id=tenant_id or self._workspace_id,
        )
        return text


# ---------------------------------------------------------------------------
# Intent classifier adapter
# ---------------------------------------------------------------------------

class AtomIntentClassifier:
    """Adapter around atom's IntentClassifier for LLM-powered intent routing.

    The conductor's keyword-based ``classify_intent`` works without an LLM
    but can misclassify ambiguous requests. When atom is available, this
    adapter uses atom's IntentClassifier (which calls an LLM) to get
    more accurate routing. The result is mapped back to A-Cal's IntentType.
    """

    def __init__(self, workspace_id: str = "default") -> None:
        """Initialize the adapter.

        Raises:
            ImportError: If atom is not available.
        """
        from core.intent_classifier import IntentClassifier  # type: ignore

        self._classifier = IntentClassifier(workspace_id=workspace_id)
        logger.info("AtomIntentClassifier initialized with atom IntentClassifier")

    async def classify(self, message: str) -> Optional[Dict[str, Any]]:
        """Classify a user message using atom's LLM-powered classifier.

        Args:
            message: The user's message.

        Returns:
            Dict with 'category', 'confidence', 'reasoning', or None if
            classification fails (caller should fall back to keywords).
        """
        try:
            result = await self._classifier.classify_intent(message)
            return {
                "category": result.category.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "requires_execution": result.requires_execution,
            }
        except Exception as exc:
            logger.warning("atom intent classification failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_atom_adapters(
    workspace_id: str = "default",
) -> Tuple[Optional[AtomTokenStorage], Optional[Any], Optional[AtomIntentClassifier]]:
    """Get atom-backed adapters, or (None, None, None) if atom isn't available.

    This is the main entry point. Callers check whether the returned values
    are non-None to decide whether to use atom or fall back to standalone.

    Args:
        workspace_id: atom workspace ID for multi-tenant resolution.

    Returns:
        Tuple of (token_storage, llm_service, intent_classifier). Any or all
        may be None if atom is not available or a specific adapter fails.
    """
    if not is_atom_available():
        return None, None, None

    token_storage: Optional[AtomTokenStorage] = None
    llm_service: Optional[Any] = None
    intent_classifier: Optional[AtomIntentClassifier] = None

    try:
        token_storage = AtomTokenStorage()
    except Exception as exc:
        logger.warning("AtomTokenStorage init failed: %s", exc)

    try:
        llm_service = AtomLLMAdapter(workspace_id=workspace_id)
    except Exception as exc:
        logger.warning("AtomLLMAdapter init failed: %s", exc)

    try:
        intent_classifier = AtomIntentClassifier(workspace_id=workspace_id)
    except Exception as exc:
        logger.warning("AtomIntentClassifier init failed: %s", exc)

    if token_storage or llm_service or intent_classifier:
        logger.info(
            "atom adapters ready: token_storage=%s, llm=%s, intent=%s",
            bool(token_storage), bool(llm_service), bool(intent_classifier),
        )

    return token_storage, llm_service, intent_classifier
