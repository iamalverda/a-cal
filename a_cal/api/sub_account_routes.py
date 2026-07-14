"""Sub-account, provider, sync, and sync-rule routes for standalone A-Cal.

Split from ``standalone_data.py``. These endpoints manage the sub-account
hierarchy, provider connections, sync triggers, and sync rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, UTC
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from a_cal.api._helpers import _fire_plugin_hook
from a_cal.api.store import _store
from a_cal.auth.session import get_current_user_id as _get_uid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a-cal-data"])


# --- request/response models -----------------------------------------------

class SubAccountCreate(BaseModel):
    """Payload for creating a sub-account."""
    name: str
    kind: str = "unified"
    sync_mode: str = "mirror_filter"
    is_main: bool = False
    parent_sub_account_id: str | None = None
    agent_enabled: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class SubAccountOut(BaseModel):
    """Serialized sub-account returned to the frontend."""
    id: str
    name: str
    kind: str
    is_main: bool
    sync_mode: str
    agent_enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)


class ProviderConnectionCreate(BaseModel):
    """Payload for creating a provider connection."""
    sub_account_id: str
    provider_type: str
    provider_account_id: str
    display_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list)


class ProviderConnectionOut(BaseModel):
    """Serialized provider connection."""
    id: str
    sub_account_id: str
    provider_type: str
    provider_account_id: str
    display_name: str | None = None
    status: str
    last_sync_at: datetime | None = None


class SyncRuleCreate(BaseModel):
    """Payload for creating a sync rule."""
    sub_account_id: str
    rule_type: str
    field: str = "title"
    pattern: str = "*"
    action: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class SyncTriggerRequest(BaseModel):
    """Payload for triggering a provider sync."""
    sub_account_id: str


# --- sub-account endpoints -------------------------------------------------

@router.post("/sub-accounts", response_model=SubAccountOut)
def create_sub_account(body: SubAccountCreate) -> SubAccountOut:
    """Create a new sub-account in the persistent store."""
    data = _store.create_sub_account({
        "name": body.name,
        "kind": body.kind,
        "is_main": body.is_main,
        "sync_mode": body.sync_mode,
        "agent_enabled": body.agent_enabled,
        "settings": body.settings,
    })
    logger.info("created sub-account: %s (%s)", data["id"], body.name)
    return SubAccountOut(
        id=data["id"], name=data["name"], kind=data["kind"], is_main=data["is_main"],
        sync_mode=data["sync_mode"], agent_enabled=data["agent_enabled"], settings=data.get("settings", {}),
    )


@router.get("/sub-accounts", response_model=list[SubAccountOut])
def list_sub_accounts() -> list[SubAccountOut]:
    """List all sub-accounts for the current user."""
    return [
        SubAccountOut(
            id=s["id"], name=s["name"], kind=s["kind"], is_main=s["is_main"],
            sync_mode=s["sync_mode"], agent_enabled=s["agent_enabled"], settings=s.get("settings", {}),
        )
        for s in _store.list_sub_accounts()
    ]


@router.patch("/sub-accounts/{sub_id}", response_model=SubAccountOut)
def update_sub_account(sub_id: str, body: dict[str, Any]) -> SubAccountOut:
    """Update a sub-account's settings (sync mode, agent_enabled, etc.)."""
    result = _store.update_sub_account(sub_id, body)
    if not result:
        raise HTTPException(status_code=404, detail="Sub-account not found")
    return SubAccountOut(
        id=result["id"], name=result["name"], kind=result["kind"], is_main=result["is_main"],
        sync_mode=result["sync_mode"], agent_enabled=result["agent_enabled"], settings=result.get("settings", {}),
    )


@router.delete("/sub-accounts/{sub_id}")
def delete_sub_account(sub_id: str) -> dict[str, str]:
    """Delete a sub-account and its associated providers."""
    if not _store.delete_sub_account(sub_id):
        raise HTTPException(status_code=404, detail="Sub-account not found")
    return {"status": "deleted", "id": sub_id}


# --- provider connection endpoints -----------------------------------------

@router.post("/providers", response_model=ProviderConnectionOut)
def create_provider(body: ProviderConnectionCreate) -> ProviderConnectionOut:
    """Create a new provider connection."""
    data = _store.create_provider({
        "sub_account_id": body.sub_account_id,
        "provider_type": body.provider_type,
        "provider_account_id": body.provider_account_id,
        "display_name": body.display_name,
        "config": body.config,
        "scopes": body.scopes,
    })
    logger.info("created provider connection: %s (%s)", data["id"], body.provider_type)
    return ProviderConnectionOut(
        id=data["id"], sub_account_id=data["sub_account_id"], provider_type=data["provider_type"],
        provider_account_id=data["provider_account_id"], display_name=data.get("display_name"),
        status=data["status"], last_sync_at=None,
    )


@router.get("/providers", response_model=list[ProviderConnectionOut])
def list_providers(sub_account_id: str = Query(...)) -> list[ProviderConnectionOut]:
    """List provider connections for a specific sub-account."""
    return [
        ProviderConnectionOut(
            id=p["id"], sub_account_id=p["sub_account_id"], provider_type=p["provider_type"],
            provider_account_id=p["provider_account_id"], display_name=p.get("display_name"),
            status=p["status"], last_sync_at=p.get("last_sync_at"),
        )
        for p in _store.list_providers(sub_account_id)
    ]


@router.get("/providers/all", response_model=list[ProviderConnectionOut])
def list_all_providers() -> list[ProviderConnectionOut]:
    """List all provider connections (used by the sidebar to group by sub-account)."""
    return [
        ProviderConnectionOut(
            id=p["id"], sub_account_id=p["sub_account_id"], provider_type=p["provider_type"],
            provider_account_id=p["provider_account_id"], display_name=p.get("display_name"),
            status=p["status"], last_sync_at=p.get("last_sync_at"),
        )
        for p in _store.list_providers()
    ]


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict[str, str]:
    """Delete a provider connection by ID."""
    if not _store.delete_provider(provider_id):
        raise HTTPException(status_code=404, detail="Provider connection not found")
    return {"status": "deleted", "provider_id": provider_id}


@router.patch("/providers/{provider_id}")
def update_provider_status(provider_id: str, body: dict[str, Any]) -> ProviderConnectionOut:
    """Update a provider connection status (e.g., mark as connected after OAuth)."""
    result = _store.update_provider_status(provider_id, body.get("status", "connected"))
    if not result:
        raise HTTPException(status_code=404, detail="Provider connection not found")
    return ProviderConnectionOut(
        id=result["id"], sub_account_id=result["sub_account_id"], provider_type=result["provider_type"],
        provider_account_id=result["provider_account_id"], display_name=result.get("display_name"),
        status=result["status"], last_sync_at=result.get("last_sync_at"),
    )


# --- sync trigger ----------------------------------------------------------

@router.post("/sync/trigger")
async def trigger_sync(body: SyncTriggerRequest) -> dict[str, Any]:
    """Trigger a sync for a sub-account's providers.

    Attempts to pull real events from connected providers via the sync engine.
    Falls back to marking providers as connected and returning the current
    event count when providers are unreachable (e.g., no library installed,
    no server configured, or standalone demo mode).

    After pulling events, feeds them to the self-model extractor so it can
    learn patterns (busy times, meeting cadence, preferences). Extraction is
    fire-and-forget — failures don't affect the sync result.
    """
    from datetime import datetime

    from a_cal.providers.factory import build_calendar_provider
    from a_cal.providers.base import CalendarEventDTO
    from a_cal.self_model.model import SelfModel
    from a_cal.self_model.settings import SelfModelSettings

    providers = _store.list_providers(body.sub_account_id)
    now = datetime.now(UTC)
    sync_end = now + timedelta(days=30)

    pulled_count = 0
    errors: list[dict[str, str]] = []
    all_events: list[CalendarEventDTO] = []

    for p in providers:
        provider_type = p["provider_type"]
        # Only attempt real sync for calendar providers
        calendar_types = {"google_calendar", "outlook_calendar", "caldav"}
        if provider_type not in calendar_types:
            _store.update_provider_status(p["id"], "connected")
            continue

        try:
            provider = build_calendar_provider(p)
            events = await provider.list_events(now, sync_end)
            for ev in events:
                ev.source_sub_account_id = body.sub_account_id
                all_events.append(ev)
                existing = _store.find_event_by_title(ev.title)
                if not existing:
                    _store.create_event(ev.to_storage_dict())
                    pulled_count += 1
            _store.update_provider_status(p["id"], "connected")
        except Exception as exc:
            logger.warning("provider sync failed for %s: %s", p["id"], exc)
            _store.update_provider_status(p["id"], "error")
            errors.append({"provider_id": p["id"], "error": str(exc)})

    # Feed synced events to the self-model extractor (fire-and-forget).
    facts_learned = 0
    if all_events:
        try:
            sm_settings_data = _store.get_setting("self_model_settings")
            if sm_settings_data:
                sm_settings = SelfModelSettings.from_dict(sm_settings_data)
            else:
                sm_settings = SelfModelSettings.default_for_depth(
                    __import__("a_cal.self_model.types", fromlist=["SelfModelDepth"]).SelfModelDepth.PATTERN_MEMORY
                )
            sm = SelfModel(user_id=_get_uid(), settings=sm_settings)
            provenance = f"sync:{body.sub_account_id}"
            facts = await sm.observe_events(all_events, provenance)
            facts_learned = len(facts)
        except Exception as exc:
            logger.warning("self-model extraction after sync failed: %s", exc)

    # Fire on_sync_complete plugin hook (fire-and-forget).
    sync_events_data = [ev.to_storage_dict() for ev in all_events]
    _fire_plugin_hook("on_sync_complete", body.sub_account_id, sync_events_data)

    event_count = len(_store.get_unified_calendar(30))
    return {
        "sub_account_id": body.sub_account_id,
        "providers_synced": len(providers),
        "events_pulled": pulled_count,
        "events_in_store": event_count,
        "facts_learned": facts_learned,
        "errors": errors,
        "status": "synced" if not errors else "partial",
    }


# --- sync rule endpoints ---------------------------------------------------

@router.post("/sync-rules")
def create_sync_rule(body: SyncRuleCreate) -> dict[str, str]:
    """Create a sync rule for a sub-account."""
    data = _store.create_sync_rule({
        "sub_account_id": body.sub_account_id,
        "rule_type": body.rule_type,
        "field": body.field,
        "pattern": body.pattern,
        "action": body.action,
        "priority": body.priority,
    })
    return {"id": data["id"], "sub_account_id": body.sub_account_id}


@router.get("/sync-rules")
def list_sync_rules(sub_account_id: str = Query(...)) -> list[dict[str, Any]]:
    """List sync rules for a sub-account."""
    return [
        {
            "id": r["id"],
            "sub_account_id": r["sub_account_id"],
            "rule_type": r["rule_type"],
            "field": r["field"],
            "pattern": r["pattern"],
            "action": r["action"],
            "priority": r["priority"],
            "is_active": True,
        }
        for r in _store.list_sync_rules(sub_account_id)
    ]


@router.delete("/sync-rules/{rule_id}")
def delete_sync_rule(rule_id: str) -> dict[str, str]:
    """Delete a sync rule."""
    deleted = _store.delete_sync_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sync rule not found")
    return {"status": "deleted", "id": rule_id}
