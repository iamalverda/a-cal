"""A-Cal agent and settings API routes.

These endpoints wire the frontend to the conductor, agent registry, and
settings modules. They share the ``/api/a-cal`` prefix with ``routes.py``.

In the full atom deployment, settings are persisted in atom's database.
In standalone mode, an in-memory per-user store is used (suitable for
development and single-user self-hosted).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from a_cal.agents.conductor import ACalConductor
from a_cal.agents.registry import AgentRegistry
from a_cal.agents.llm_service import StandaloneLLMService
from a_cal.integrations.atom_bridge import get_atom_adapters, get_atom_status
from a_cal.db.store import PersistentStore as _DBStore
from a_cal.agents.llm_service import check_ollama_available, list_ollama_models
from a_cal.settings.modes import get_mode_config, SkillMode
from a_cal.settings.model_routing import ModelRoutingConfig
from a_cal.settings.autonomy import AutonomyConfig, AutonomyLevel
from a_cal.self_model.settings import SelfModelSettings
from a_cal.self_model.model import SelfModel
from a_cal.self_model.store import SelfModelStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-agents"])


# --- in-memory settings store (standalone mode) ---------------------------

class _SettingsStore:
    """Per-user settings store backed by SQLite.

    Settings (mode, model routing, LLM enabled, API keys, self-model)
    are persisted to the database and survive server restarts.
    Conductor instances are cached in-memory and invalidated on config changes.
    """

    def __init__(self) -> None:
        self._db = _DBStore()
        self._conductors: Dict[str, ACalConductor] = {}
        self._registries: Dict[str, AgentRegistry] = {}

    def get_mode(self, user_id: str) -> str:
        return self._db.get_setting("skill_mode", SkillMode.PRO.value)

    def set_mode(self, user_id: str, mode: str) -> str:
        self._db.set_setting("skill_mode", mode)
        return mode

    def get_routing(self, user_id: str) -> ModelRoutingConfig:
        data = self._db.get_setting("model_routing")
        if data:
            return ModelRoutingConfig(**data)
        return ModelRoutingConfig()

    def set_routing(self, user_id: str, config: ModelRoutingConfig) -> ModelRoutingConfig:
        self._db.set_setting("model_routing", config.to_dict())
        # Invalidate cached conductor so it picks up new routing.
        self._conductors.pop(user_id, None)
        return config

    def get_self_model_settings(self, user_id: str) -> SelfModelSettings:
        data = self._db.get_setting("self_model_settings")
        if data:
            return SelfModelSettings(**data)
        return SelfModelSettings()

    def set_self_model_settings(self, user_id: str, settings: SelfModelSettings) -> SelfModelSettings:
        self._db.set_setting("self_model_settings", settings.to_dict())
        return settings

    def get_conductor(self, user_id: str) -> ACalConductor:
        if user_id not in self._conductors:
            llm_service = None
            if self.get_llm_enabled(user_id):
                backend_mode = self.get_backend_mode(user_id)
                if backend_mode == "atom":
                    # Atom mode: use atom's LLM service (BYOK, cognitive
                    # tier routing, governance). Falls back to standalone
                    # if atom adapters fail to initialize.
                    _, atom_llm, _ = get_atom_adapters(workspace_id=user_id)
                    if atom_llm:
                        llm_service = atom_llm
                    else:
                        logger.warning(
                            "backend_mode=atom but atom adapters unavailable, "
                            "falling back to standalone"
                        )
                        routing = self.get_routing(user_id)
                        api_keys = self._db.get_raw_api_keys()
                        llm_service = StandaloneLLMService(
                            routing=routing, api_keys=api_keys,
                        )
                else:
                    # Standalone mode (default): use StandaloneLLMService
                    # with user-configured model routing and API keys.
                    routing = self.get_routing(user_id)
                    api_keys = self._db.get_raw_api_keys()
                    llm_service = StandaloneLLMService(
                        routing=routing, api_keys=api_keys,
                    )
            autonomy = self.get_autonomy(user_id)
            self._conductors[user_id] = ACalConductor(
                user_id=user_id,
                llm_service=llm_service,
                nervous_system=_get_nervous_system(),
                event_store=self._db,
                provider_store=self._db,
                autonomy_config=autonomy,
            )
        return self._conductors[user_id]

    def get_llm_enabled(self, user_id: str) -> bool:
        return self._db.get_setting("llm_enabled", False)

    def set_llm_enabled(self, user_id: str, enabled: bool) -> bool:
        self._db.set_setting("llm_enabled", enabled)
        # Invalidate cached conductor so it picks up the change.
        self._conductors.pop(user_id, None)
        return enabled

    def get_registry(self, user_id: str) -> AgentRegistry:
        if user_id not in self._registries:
           self._registries[user_id] = AgentRegistry()
        return self._registries[user_id]

    def get_api_keys(self, user_id: str) -> Dict[str, str]:
        return self._db.get_api_keys()

    def set_api_keys(self, user_id: str, keys: Dict[str, str]) -> Dict[str, str]:
        result = self._db.set_api_keys(keys)
        # Invalidate cached conductor so it picks up new keys.
        self._conductors.pop(user_id, None)
        return result

    def get_backend_mode(self, user_id: str) -> str:
        """Get the backend mode: 'standalone' or 'atom'."""
        return self._db.get_setting("backend_mode", "standalone")

    def set_backend_mode(self, user_id: str, mode: str) -> str:
        """Set the backend mode and invalidate cached conductor."""
        self._db.set_setting("backend_mode", mode)
        self._conductors.pop(user_id, None)
        return mode

    def get_autonomy(self, user_id: str) -> AutonomyConfig:
        """Get the user's agent autonomy configuration."""
        data = self._db.get_setting("autonomy_config")
        if data:
            return AutonomyConfig.from_dict(data)
        return AutonomyConfig()

    def set_autonomy(self, user_id: str, config: AutonomyConfig) -> AutonomyConfig:
        """Set autonomy config and invalidate cached conductor."""
        self._db.set_setting("autonomy_config", config.to_dict())
        self._conductors.pop(user_id, None)
        return config

    def get_timezone(self, user_id: str) -> str:
        """Get the user's IANA timezone (e.g. America/Chicago).

        Defaults to the system local timezone if not explicitly set.
        """
        tz = self._db.get_setting("timezone")
        if tz:
            return tz
        # Fall back to system local timezone
        try:
            import zoneinfo
            local = datetime.now().astimezone()
            return str(local.tzinfo)
        except Exception:
            return "UTC"

    def set_timezone(self, user_id: str, tz: str) -> str:
        """Set the user's timezone and invalidate cached conductor."""
        self._db.set_setting("timezone", tz)
        self._conductors.pop(user_id, None)
        return tz


_store = _SettingsStore()


def _current_user_id() -> str:
    """Placeholder — wired to atom's auth in production."""
    return "local-dev-user"


# Module-level override for self-model store data dir (used by tests).
_sm_data_dir: Optional[str] = None


def _get_sm_store() -> SelfModelStore:
    """Get the self-model store for the current user.

    Uses _sm_data_dir if set (for testing); otherwise defaults to
    ~/.a-cal/self_model.
    """
    return SelfModelStore(user_id=_current_user_id(), data_dir=_sm_data_dir)


# --- request/response models -----------------------------------------------

class ConductorChatRequest(BaseModel):
    message: str


class ModeRequest(BaseModel):
    mode: str


class ModelRoutingRequest(BaseModel):
    global_provider: str = "ollama"
    global_model: str = "llama3.2"
    per_task_overrides: Dict[str, str] = Field(default_factory=dict)
    privacy_force_local: bool = True


class SelfModelSettingsRequest(BaseModel):
    depth: str = "pattern_memory"
    enabled_categories: Dict[str, bool] = Field(default_factory=dict)
    cloud_sync_enabled: bool = False
    proactive_suggestions_enabled: bool = False
    feed_into_calendar_view: bool = True
    feed_into_agents: bool = True
    feed_into_proactive: bool = False


class AutonomyRequest(BaseModel):
    """Payload for updating agent autonomy settings."""
    default_level: str = "confirm"
    per_sub_account: Dict[str, str] = Field(default_factory=dict)


# --- conductor chat --------------------------------------------------------

@router.post("/conductor/chat")
async def conductor_chat(body: ConductorChatRequest):
    """Send a message to the A-Cal conductor.

    The conductor classifies intent, routes through the nervous system
    (thalamus gate -> RAS -> basal ganglia -> conductor -> CAS modules),
    and returns a real response. In standalone mode (no LLM), responses
    are rule-based but interact with real calendar data. When an LLM is
    connected, responses are model-generated.

    The response includes:
    - routing: which specialist was chosen and at what cognitive tier
    - response: the human-readable response text
    - actions: structured actions the agent identified
    - routing_trace: full nervous system trace (when available)
    - cas_modules_engaged: which bio-mimetic modules were activated
    """
    user_id = _current_user_id()
    conductor = _store.get_conductor(user_id)
    result = await conductor.handle(body.message)
    return result


# --- email-to-schedule ----------------------------------------------------

@router.post("/email/scan-schedule")
async def scan_emails_for_schedule():
    """Scan connected email providers for scheduling-related content.

    Runs the email-to-schedule pipeline: reads recent emails, detects meeting
    proposals, extracts proposed times, and cross-references with the user's
    calendar to find conflicts. Returns actionable suggestions.

    Privacy: email content is processed locally. No email body text is sent
    to external services. When an LLM is used for richer analysis, privacy-
    tiered routing forces email processing to local models.
    """
    from a_cal.agents.email_scheduler import scan_emails_for_scheduling
    from a_cal.providers.factory import build_email_provider

    user_id = _current_user_id()

    # Get email providers
    from a_cal.api.standalone_data import _store as data_store
    all_providers = data_store.list_providers()
    email_types = {"imap_smtp", "gmail"}
    email_providers = [
        p for p in all_providers
        if p["provider_type"] in email_types and p.get("status") == "connected"
    ]

    # Fetch recent emails
    emails: list[dict[str, Any]] = []
    for p in email_providers:
        try:
            provider = build_email_provider(p)
            messages, _ = await provider.list_messages(since_cursor=None, limit=50)
            for msg in messages:
                emails.append({
                    "subject": msg.subject,
                    "from_address": msg.from_address,
                    "snippet": msg.snippet or "",
                    "body_text": msg.body_text or "",
                    "has_calendar_invite": False,
                    "received_at": msg.received_at.isoformat() if msg.received_at else None,
                })
        except Exception as exc:
            logger.warning("email fetch failed for %s: %s", p["id"], exc)

    # Get calendar events
    events = data_store.get_unified_calendar(days=14)

    # Run the pipeline
    result = scan_emails_for_scheduling(emails, events)
    return result


# --- agents ----------------------------------------------------------------

@router.get("/agents")
def list_agents():
    """List all registered A-Cal agents (built-in + custom)."""
    user_id = _current_user_id()
    registry = _store.get_registry(user_id)
    return registry.to_dict_list()


# --- settings: skill mode --------------------------------------------------

@router.get("/settings/mode")
def get_mode():
    """Get the current skill mode config (Simple / Pro / Developer)."""
    user_id = _current_user_id()
    mode = _store.get_mode(user_id)
    return get_mode_config(mode).to_dict()


@router.post("/settings/mode")
def set_mode(body: ModeRequest):
    """Switch the skill mode. Returns the new mode config."""
    user_id = _current_user_id()
    mode = _store.set_mode(user_id, body.mode)
    return get_mode_config(mode).to_dict()


# --- settings: model routing -----------------------------------------------

@router.get("/settings/model-routing")
def get_model_routing():
    """Get the user's model routing configuration."""
    user_id = _current_user_id()
    return _store.get_routing(user_id).to_dict()


@router.post("/settings/model-routing")
def set_model_routing(body: ModelRoutingRequest):
    """Update model routing (global provider, per-task overrides, privacy)."""
    user_id = _current_user_id()
    config = ModelRoutingConfig(
        global_provider=body.global_provider,
        global_model=body.global_model,
        per_task_overrides=body.per_task_overrides,
        privacy_force_local=body.privacy_force_local,
    )
    return _store.set_routing(user_id, config).to_dict()


# --- settings: agent autonomy ---------------------------------------------

@router.get("/settings/autonomy")
def get_autonomy():
    """Get the user's agent autonomy configuration.

    Returns the global default autonomy level and any per-sub-account
    overrides. The conductor uses this to decide whether to execute
    actions automatically, ask for confirmation, or only suggest.
    """
    user_id = _current_user_id()
    return _store.get_autonomy(user_id).to_dict()


@router.post("/settings/autonomy")
def set_autonomy(body: AutonomyRequest):
    """Update agent autonomy settings.

    Valid levels: 'suggest_only' (propose only), 'confirm' (execute with
    confirmation), 'full_auto' (execute without asking).
    """
    valid_levels = {lvl.value for lvl in AutonomyLevel}
    if body.default_level not in valid_levels:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"default_level must be one of: {', '.join(sorted(valid_levels))}",
        )
    for sa_id, level in body.per_sub_account.items():
        if level not in valid_levels:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level '{level}' for sub-account '{sa_id}'",
            )
    user_id = _current_user_id()
    config = AutonomyConfig(
        default_level=body.default_level,
        per_sub_account=body.per_sub_account,
    )
    return _store.set_autonomy(user_id, config).to_dict()


# --- settings: timezone ---------------------------------------------------

@router.get("/settings/timezone")
def get_timezone():
    """Get the user's IANA timezone (e.g. America/Chicago)."""
    user_id = _current_user_id()
    return {"timezone": _store.get_timezone(user_id)}


class TimezoneRequest(BaseModel):
    timezone: str


@router.post("/settings/timezone")
def set_timezone(body: TimezoneRequest):
    """Set the user's timezone. Accepts any IANA timezone name."""
    user_id = _current_user_id()
    # Validate that the timezone is recognized
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(body.timezone)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {body.timezone}")
    return {"timezone": _store.set_timezone(user_id, body.timezone)}


# --- settings: self-model --------------------------------------------------

@router.get("/settings/self-model")
def get_self_model_settings():
    """Get the user's self-model settings (depth, toggles, privacy)."""
    user_id = _current_user_id()
    settings = _store.get_self_model_settings(user_id)
    return settings.to_dict()


@router.post("/settings/self-model")
def set_self_model_settings(body: SelfModelSettingsRequest):
    """Update self-model settings (depth, category toggles, privacy)."""
    user_id = _current_user_id()
    settings = SelfModelSettings(
        depth=body.depth,
        enabled_categories=body.enabled_categories,
        cloud_sync_enabled=body.cloud_sync_enabled,
        proactive_suggestions_enabled=body.proactive_suggestions_enabled,
        feed_into_calendar_view=body.feed_into_calendar_view,
        feed_into_agents=body.feed_into_agents,
        feed_into_proactive=body.feed_into_proactive,
    )
    return _store.set_self_model_settings(user_id, settings).to_dict()
 

 
# --- self-model facts (transparency view) ----------------------------------

class FactEditRequest(BaseModel):
    """Payload for editing a fact's content (user correction)."""
    content: str


@router.get("/self-model/facts")
def list_self_model_facts(category: Optional[str] = None):
    """List all active self-model facts, optionally filtered by category.

    Facts are sorted by confidence (highest first). This is the transparency
    view — the user can see everything the self-model has learned about them.
    """
    store = _get_sm_store()
    if category:
        facts = store.by_category(category)
    else:
        facts = store.all_active()
    return [f.to_dict() for f in facts]


@router.get("/self-model/facts/search")
def search_self_model_facts(q: str, limit: int = 10):
    """Search self-model facts by keyword (case-insensitive substring match)."""
    store = _get_sm_store()
    facts = store.search(q, limit=limit)
    return [f.to_dict() for f in facts]


@router.delete("/self-model/facts/{fact_id}")
def delete_self_model_fact(fact_id: str):
    """Soft-delete a single self-model fact (user-initiated)."""
    store = _get_sm_store()
    if not store.get(fact_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Fact not found")
    store.delete(fact_id)
    return {"status": "deleted", "fact_id": fact_id}


@router.delete("/self-model/facts")
def clear_all_self_model_facts():
    """Delete all self-model facts for the current user."""
    store = _get_sm_store()
    count = store.clear_all()
    return {"facts_removed": count}


@router.patch("/self-model/facts/{fact_id}")
def edit_self_model_fact(fact_id: str, body: FactEditRequest):
    """Edit a fact's content (user correction).

    Sets confidence to 1.0 and marks provenance as user-corrected.
    """
    store = _get_sm_store()
    if not store.get(fact_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Fact not found")
    fact = store.update(fact_id, body.content)
    return fact.to_dict() if fact else {"error": "update failed"}


@router.get("/self-model/export")
def export_self_model_facts():
    """Export all self-model facts as a JSON blob (for backup / transfer)."""
    store = _get_sm_store()
    return store.export()


@router.get("/self-model/suggestions")
def get_proactive_suggestions(limit: int = 5):
    """Get proactive suggestions ranked by priority tier.

    Returns self-model facts that are most relevant for proactive nudges,
    using the tiered priority system from the meta-cognition protocol.
    Only returns suggestions if the user has opted into proactive suggestions
    via their self-model settings.

    Args:
        limit: Maximum number of suggestions to return (default 5).

    Returns:
        List of suggestion dicts with fact_id, content, category, priority,
        and confidence. Empty list if proactive suggestions are disabled.
    """
    user_id = _current_user_id()
    settings = _store.get_self_model_settings(user_id)
    store = _get_sm_store()
    model = SelfModel(
        user_id=user_id,
        settings=settings,
        store=store,
    )
    return model.get_proactive_suggestions(limit=limit)


# --- settings: API keys & model availability -------------------------------

class ApiKeysRequest(BaseModel):
    """Payload for setting provider API keys."""
    keys: Dict[str, str] = Field(default_factory=dict)


@router.get("/settings/api-keys")
def get_api_keys():
    """Get configured API key provider names (values are masked)."""
    user_id = _current_user_id()
    keys = _store.get_api_keys(user_id)
    # Never return actual key values — just which providers have keys.
    return {provider: "***" for provider in keys}


@router.post("/settings/api-keys")
def set_api_keys(body: ApiKeysRequest):
    """Set API keys for cloud providers. Keys are stored in-memory (standalone).

     In the full atom deployment, keys are stored in atom's encrypted
     ``secrets.enc`` / ``token_storage`` — never in plain memory.
    """
    user_id = _current_user_id()
    _store.set_api_keys(user_id, body.keys)
    return {provider: "***" for provider in body.keys}


@router.get("/settings/ollama-status")
async def ollama_status():
    """Check if Ollama is running and list available local models."""
    available = await check_ollama_available()
    models = await list_ollama_models() if available else []
    return {"available": available, "models": models}


# --- settings: backend mode (standalone vs atom) ---------------------------

class BackendModeRequest(BaseModel):
    """Payload for switching backend mode."""
    mode: str  # "standalone" or "atom"


@router.get("/settings/backend-mode")
def get_backend_mode():
    """Get the current backend mode (standalone or atom)."""
    user_id = _current_user_id()
    mode = _store.get_backend_mode(user_id)
    return {"mode": mode}


@router.post("/settings/backend-mode")
def set_backend_mode(body: BackendModeRequest):
    """Switch the backend mode.

    In standalone mode (default), A-Cal uses its own LLM service with
    user-configured model routing. In atom mode, A-Cal uses atom's
    LLMService with BYOKHandler, cognitive tier routing, and governance.
    Atom mode requires atom to be installed locally.
    """
    user_id = _current_user_id()
    if body.mode not in ("standalone", "atom"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="mode must be 'standalone' or 'atom'",
        )
    mode = _store.set_backend_mode(user_id, body.mode)
    return {"mode": mode}


@router.get("/settings/atom-status")
def atom_status():
    """Check whether atom is available and which adapters are ready.

    The frontend uses this to show the user whether atom mode is available
    and to enable/disable the backend mode toggle accordingly.
    """
    return get_atom_status()


class LLMEnabledRequest(BaseModel):
    """Payload for toggling LLM mode."""
    enabled: bool


@router.get("/settings/llm-enabled")
def get_llm_enabled():
    """Check whether real LLM responses are enabled (vs routing-only)."""
    user_id = _current_user_id()
    return {"enabled": _store.get_llm_enabled(user_id)}


@router.post("/settings/llm-enabled")
def set_llm_enabled(body: LLMEnabledRequest):
    """Enable or disable real LLM responses.

    When enabled, the conductor dispatches to the configured model provider
    (Ollama by default). When disabled, the conductor returns routing-only
    responses — useful for testing or when no model is available.
    """
    user_id = _current_user_id()
    enabled = _store.set_llm_enabled(user_id, body.enabled)
    return {"enabled": enabled}


@router.post("/settings/preload-model")
async def preload_model():
    """Preload the configured LLM model into memory (Ollama warmup).

    Local models need to be loaded into RAM before the first real request,
    which can add 30-90 seconds of latency. The frontend should call this
    endpoint when the page loads (or when the user enables the LLM) so the
    first chat message is fast. Returns immediately — warmup runs in the
    background.

    Only works for Ollama (local) providers. Cloud providers don't need
    warmup.
    """
    import asyncio

    from a_cal.agents.llm_service import StandaloneLLMService

    user_id = _current_user_id()
    if not _store.get_llm_enabled(user_id):
        return {"status": "skipped", "reason": "LLM not enabled"}

    routing = _store.get_routing(user_id)
    api_keys = _store._db.get_raw_api_keys()
    svc = StandaloneLLMService(routing=routing, api_keys=api_keys)

    async def _do_warmup() -> None:
        try:
            await svc.warmup()
        except Exception:
            logger.debug("model preload failed (not critical)")

    asyncio.create_task(_do_warmup())
    return {"status": "warming_up"}


# ---------------------------------------------------------------------------
# Nervous System — CAS bio-mimetic agent architecture
# ---------------------------------------------------------------------------

from a_cal.agents.nervous_system import NervousSystemCoordinator, SystemState
from a_cal.agents.cas_specs import CAS_AGENTS, CAS_AGENTS_BY_NAME

# Singleton nervous system coordinator (per-server instance)
_nervous_system: Optional[NervousSystemCoordinator] = None


def _get_nervous_system() -> NervousSystemCoordinator:
    """Get or create the singleton nervous system coordinator."""
    global _nervous_system
    if _nervous_system is None:
        _nervous_system = NervousSystemCoordinator()
    return _nervous_system


class NSRouteRequest(BaseModel):
    """Request to route a signal through the nervous system."""
    signal: str


class NSUserStateRequest(BaseModel):
    """Request to assess user state from events."""
    events: list[Dict[str, Any]] = Field(default_factory=list)


class NSBindingRequest(BaseModel):
    """Request to verify calendar binding."""
    events: list[Dict[str, Any]] = Field(default_factory=list)
    sub_accounts: list[Dict[str, Any]] = Field(default_factory=list)


@router.get("/nervous-system/overview")
def ns_overview():
    """Get a complete overview of the nervous system state and CAS agents."""
    ns = _get_nervous_system()
    return ns.get_system_overview()


@router.get("/nervous-system/agents")
def ns_agents():
    """Get all agents — original 6 specialists + 10 CAS bio-mimetic modules."""
    ns = _get_nervous_system()
    return ns.get_all_agents_combined()


@router.get("/nervous-system/state")
def ns_state():
    """Get the current nervous system state (activation, autonomic, spotlight)."""
    ns = _get_nervous_system()
    return ns.state.to_dict()


@router.post("/nervous-system/route")
def ns_route(body: NSRouteRequest):
    """Route a signal through the complete nervous system and return a trace.

    The trace shows how the signal flowed through:
    thalamus gate → RAS → basal ganglia → conductor → CAS modules → hippocampus.
    """
    ns = _get_nervous_system()
    trace = ns.route_through_nervous_system(body.signal)
    return trace.to_dict()


@router.get("/nervous-system/memories")
def ns_memories(limit: int = 10):
    """Get recent episodic memories from the hippocampus module."""
    ns = _get_nervous_system()
    return ns._memory_store[-limit:]


@router.post("/nervous-system/assess-user-state")
def ns_assess_user_state(body: NSUserStateRequest):
    """Assess the user's state from calendar events (insula module)."""
    ns = _get_nervous_system()
    return ns.assess_user_state(body.events)


@router.post("/nervous-system/verify-binding")
def ns_verify_binding(body: NSBindingRequest):
    """Verify the unified calendar view is coherent (claustrum module)."""
    ns = _get_nervous_system()
    return ns.verify_binding(body.events, body.sub_accounts)


@router.get("/nervous-system/cas-agents")
def ns_cas_agents():
    """Get only the CAS bio-mimetic agents with their brain-module metadata."""
    return [a.to_dict() for a in CAS_AGENTS]
