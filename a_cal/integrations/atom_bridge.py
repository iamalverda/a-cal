"""Atom integration bridge — upgrades A-Cal when atom is available.

A-Cal runs in two modes:

  **Standalone** (default): SQLite storage, StandaloneLLMService for model
  dispatch, keyword-based intent classification. No external dependencies.

  **Atom-backed** (when atom is detected): encrypted OAuth token storage
  via atom's ConnectionService, LLM inference via atom's LLMService with
  BYOKHandler and cognitive tier routing, and LLM-powered intent
  classification via atom's IntentClassifier.

The bridge auto-detects atom by searching known locations for atom's
``backend/`` directory and adding it to ``sys.path``. Callers don't need
to know which mode is active — they call the same methods.

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
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Directories to search for atom's backend/ folder, relative to common
# locations. The first match that contains core/llm_service.py wins.
_ATOM_SEARCH_PATHS: list[str] = [
    # Sibling directory (A-Cal and atom in the same parent folder)
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "atom", "backend"),
    # A-Cal project root / atom
    os.path.join(os.path.dirname(__file__), "..", "..", "atom", "backend"),
    # Environment variable override
    os.environ.get("ATOM_BACKEND_PATH", ""),
]


def _find_atom_backend() -> str | None:
    """Search known locations for atom's backend directory.

    Returns the absolute path to atom's ``backend/`` folder if found,
    or None if atom is not installed locally.
    """
    for candidate in _ATOM_SEARCH_PATHS:
        if not candidate:
            continue
        path = os.path.abspath(candidate)
        if os.path.isfile(os.path.join(path, "core", "llm_service.py")):
            return path
    return None


def _ensure_atom_on_path() -> str | None:
    """Add atom's backend to sys.path if found and not already present.

    Returns the path that was added (or was already present), or None
    if atom's backend could not be located.
    """
    # Check if atom is already importable (someone added it manually).
    try:
        import core.llm_service  # type: ignore  # noqa: F401
        import core.connection_service  # type: ignore  # noqa: F401
        return "<already on sys.path>"
    except ImportError:
        pass

    backend_path = _find_atom_backend()
    if backend_path is None:
        return None

    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
        logger.info("atom backend added to sys.path: %s", backend_path)

    return backend_path


def is_atom_available() -> bool:
    """Check whether atom's backend is importable.

    Auto-detects atom's ``backend/`` directory by searching known locations
    and adding it to ``sys.path`` if found. Returns True if atom's
    ``core.connection_service`` and ``core.llm_service`` can be imported.

    Set the ``A_CAL_DISABLE_ATOM`` environment variable to force atom off
    (useful for testing standalone mode even when atom is installed).
    """
    if os.environ.get("A_CAL_DISABLE_ATOM", "").lower() in ("1", "true", "yes"):
        return False

    path = _ensure_atom_on_path()
    if path is None:
        return False

    try:
        import core.connection_service  # type: ignore  # noqa: F401
        import core.llm_service  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _init_atom_db() -> None:
    """Create atom's database tables if they don't exist.

    Atom's ConnectionService expects a ``user_connections`` table. When
    atom is first detected, we ensure its tables exist so OAuth token
    storage works without requiring atom's full migration system.
    """
    try:
        from core.database import Base, engine  # type: ignore
        from core.models import UserConnection  # type: ignore  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.debug("atom DB init skipped: %s", exc)


def get_atom_status() -> dict[str, Any]:
    """Return a status dict describing atom availability for the frontend.

    Returns:
        Dict with keys:
        - available: bool
        - backend_path: str or None
        - adapters: dict of adapter name -> bool (which are ready)
    """
    if os.environ.get("A_CAL_DISABLE_ATOM", "").lower() in ("1", "true", "yes"):
        return {
            "available": False,
            "backend_path": None,
            "adapters": {"token_storage": False, "llm": False, "intent": False},
        }

    path = _ensure_atom_on_path()
    if path is None:
        return {
            "available": False,
            "backend_path": None,
            "adapters": {"token_storage": False, "llm": False, "intent": False},
        }

    token_ok = llm_ok = intent_ok = False
    try:
        import core.connection_service  # type: ignore  # noqa: F401
        token_ok = True
    except ImportError:
        pass
    try:
        import core.llm_service  # type: ignore  # noqa: F401
        llm_ok = True
    except ImportError:
        pass
    try:
        import core.intent_classifier  # type: ignore  # noqa: F401
        intent_ok = True
    except ImportError:
        pass

    return {
        "available": token_ok or llm_ok or intent_ok,
        "backend_path": path,
        "adapters": {
            "token_storage": token_ok,
            "llm": llm_ok,
            "intent": intent_ok,
        },
    }


# ---------------------------------------------------------------------------
# Token storage adapter
# ---------------------------------------------------------------------------

class AtomTokenStorage:
    """Adapter around atom's ConnectionService for encrypted OAuth token storage.

    In standalone mode, OAuth tokens are stored in the provider connection's
    ``config`` JSON column (plaintext in SQLite). When atom is available,
    tokens are encrypted via atom's ConnectionService and stored in atom's
    ``UserConnection`` table with Fernet encryption at rest.

    Atom's ConnectionService uses a different API than the bridge's original
    design: ``save_connection`` takes ``integration_id`` and ``name``
    (not ``connection_id`` and ``provider``), ``get_connection_credentials``
    is async and takes ``(connection_id, user_id)``, and ``delete_connection``
    takes ``(connection_id, user_id)``. This adapter translates between the
    two interfaces.
    """

    def __init__(self) -> None:
        """Initialize the adapter, importing atom's ConnectionService.

        Raises:
            ImportError: If atom is not available (caller should check
                ``is_atom_available()`` first).
        """
        if not is_atom_available():
            raise ImportError("atom is not available")
        from core.connection_service import ConnectionService  # type: ignore

        self._svc = ConnectionService()
        logger.info("AtomTokenStorage initialized with atom ConnectionService")

    @staticmethod
    def _integration_id(provider_type: str) -> str:
        """Build a stable integration_id for A-Cal provider types."""
        return f"a_cal_{provider_type}"

    def save_oauth_tokens(
        self, user_id: str, provider_type: str, tokens: dict[str, Any],
    ) -> str:
        """Store encrypted OAuth tokens for a provider connection.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type (google_calendar, outlook_calendar, gmail).
            tokens: Token dict (access_token, refresh_token, etc.).

        Returns:
            The connection ID (UUID) in atom's UserConnection table.
        """
        integration_id = self._integration_id(provider_type)
        conn = self._svc.save_connection(
            user_id=user_id,
            integration_id=integration_id,
            name=provider_type,
            credentials=tokens,
        )
        logger.info("Stored encrypted OAuth tokens for %s/%s (conn_id=%s)",
                     user_id, provider_type, conn.id)
        return conn.id

    async def get_oauth_tokens(
        self, user_id: str, provider_type: str,
    ) -> dict[str, Any] | None:
        """Retrieve and decrypt OAuth tokens for a provider.

        Looks up the connection by integration_id, then fetches credentials.
        Atom's ``get_connection_credentials`` is async and may refresh
        expired tokens automatically.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type.

        Returns:
            Decrypted token dict, or None if not found.
        """
        integration_id = self._integration_id(provider_type)
        connections = self._svc.get_connections(user_id, integration_id)
        if not connections:
            return None

        # Use the first matching connection (there should be only one per integration_id).
        conn_id = connections[0]["id"]
        return await self._svc.get_connection_credentials(conn_id, user_id)

    def delete_oauth_tokens(self, user_id: str, provider_type: str) -> bool:
        """Delete stored OAuth tokens for a provider.

        Args:
            user_id: The atom user/workspace ID.
            provider_type: The provider type.

        Returns:
            True if deleted, False if not found.
        """
        integration_id = self._integration_id(provider_type)
        connections = self._svc.get_connections(user_id, integration_id)
        if not connections:
            return False

        conn_id = connections[0]["id"]
        return self._svc.delete_connection(conn_id, user_id)


# ---------------------------------------------------------------------------
# LLM service adapter
# ---------------------------------------------------------------------------

class AtomLLMAdapter:
    """Adapter around atom's LLMService that matches StandaloneLLMService's interface.

    The conductor calls ``generate_response(prompt, system_prompt, task,
    tenant_id)``. This adapter translates that call into atom's
    ``LLMService.generate(prompt, system_instruction, model, workspace_id)``
    and returns the text.

    Atom's LLMService uses a BYOKHandler with cognitive tier routing,
    governance de-escalation, and continuous learning personalization.
    API keys must be configured in atom's BYOK system (separate from
    A-Cal's standalone settings).
    """

    def __init__(self, workspace_id: str = "default") -> None:
        """Initialize the adapter.

        Args:
            workspace_id: atom workspace ID for multi-tenant key resolution.

        Raises:
            ImportError: If atom is not available.
        """
        if not is_atom_available():
            raise ImportError("atom is not available")
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
        if not is_atom_available():
            raise ImportError("atom is not available")
        from core.intent_classifier import IntentClassifier  # type: ignore

        self._classifier = IntentClassifier(workspace_id=workspace_id)
        logger.info("AtomIntentClassifier initialized with atom IntentClassifier")

    async def classify(self, message: str) -> dict[str, Any] | None:
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
) -> tuple[AtomTokenStorage | None, Any | None, AtomIntentClassifier | None]:
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

    # Ensure atom's database tables exist (needed for ConnectionService).
    _init_atom_db()

    token_storage: AtomTokenStorage | None = None
    llm_service: Any | None = None
    intent_classifier: AtomIntentClassifier | None = None

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


def get_atom_token_storage() -> AtomTokenStorage | None:
    """Convenience: return just the token storage adapter, or None.

    Used by oauth_routes.py to avoid initializing the LLM service
    (which is heavier) when only token storage is needed.
    """
    if not is_atom_available():
        return None
    _init_atom_db()
    try:
        return AtomTokenStorage()
    except Exception as exc:
        logger.warning("AtomTokenStorage init failed: %s", exc)
        return None
