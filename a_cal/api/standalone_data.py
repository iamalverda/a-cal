"""In-memory data/sync routes for standalone A-Cal server.

Provides the sub-account, provider-connection, sync-rule, and unified-calendar
endpoints without requiring atom's SQLAlchemy database. Uses an in-memory store
seeded with demo data so the frontend works fully in standalone mode.

When atom is available, these routes are replaced by ``a_cal.api.routes``
which uses the real database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal-data"])

from a_cal.auth.session import get_current_user_id as _get_uid

USER_ID = "local-dev-user"  # Legacy fallback; use _uid() for runtime


def _fire_plugin_hook(hook_name: str, *args) -> None:
    """Fire a plugin runtime hook, swallowing all errors.

    Plugin hook failures must never crash event operations. This helper
    isolates plugin code from the core data path.

    Args:
        hook_name: Name of the hook to fire (e.g. "on_event_created").
        *args: Positional arguments to pass to the hook.
    """
    try:
        from a_cal.developer.plugin_runtime import get_runtime
        runtime = get_runtime()
        getattr(runtime, hook_name)(*args)
    except Exception as exc:
        logger.debug("plugin hook %s failed: %s", hook_name, exc)


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


class AttachmentOut(BaseModel):
    """Metadata for an email attachment shown in the UI."""
    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0
    content_id: str | None = None


class EmailMessageOut(BaseModel):
    """Serialized email message returned to the frontend.

    Includes account-level metadata so the frontend can show which account
    each message belongs to in the unified inbox view.
    """
    provider_message_id: str
    provider_type: str
    provider_connection_id: str
    subject: str
    from_address: str
    to_addresses: list[str] = Field(default_factory=list)
    received_at: datetime | None = None
    snippet: str | None = None
    has_calendar_invite: bool = False
    labels: list[str] = Field(default_factory=list)
    account_display_name: str | None = None
    account_email: str | None = None
    sub_account_id: str | None = None
    sub_account_name: str | None = None
    is_unread: bool = False
    is_starred: bool = False
    body_text: str | None = None
    thread_id: str | None = None
    attachments: list[AttachmentOut] = Field(default_factory=list)


class EmailAccountOut(BaseModel):
    """A connected email account in the unified inbox."""
    provider_connection_id: str
    provider_type: str
    display_name: str
    email: str | None = None
    sub_account_id: str
    sub_account_name: str
    status: str
    unread_count: int = 0
    total_count: int = 0


class UnifiedEvent(BaseModel):
    """A calendar event in the unified timeline."""
    provider_event_id: str
    provider_type: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    source_sub_account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)



from a_cal.db.store import PersistentStore

# Persistent store — uses SQLite by default, in-memory for tests.
# Data survives server restarts in standalone mode.
_store = PersistentStore()

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

class SyncTriggerRequest(BaseModel):
    """Payload for triggering a provider sync."""
    sub_account_id: str


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


# --- unified main-calendar view --------------------------------------------

@router.get("/calendar/unified", response_model=list[UnifiedEvent])
async def unified_calendar(days: int = Query(7, ge=1, le=90)) -> list[UnifiedEvent]:
    """Return the unified calendar timeline for the next N days.

    In standalone mode, this returns the seeded demo events. In production
    with atom, this pulls from real providers via the sync engine.
    """
    events = _store.get_unified_calendar(days)
    result: list[UnifiedEvent] = []
    for evt in events:
        evt_start = evt["start"]
        if isinstance(evt_start, str):
            evt_start = datetime.fromisoformat(evt_start)
        if evt_start.tzinfo is None:
            evt_start = evt_start.replace(tzinfo=UTC)
        evt_end = evt["end"]
        if isinstance(evt_end, str):
            evt_end = datetime.fromisoformat(evt_end)
        result.append(UnifiedEvent(
            provider_event_id=evt["provider_event_id"],
            provider_type=evt["provider_type"],
            title=evt["title"],
            start=evt_start,
            end=evt_end,
            description=evt.get("description"),
            location=evt.get("location"),
            source_sub_account_id=evt.get("source_sub_account_id"),
            metadata=evt.get("metadata", {}),
        ))
    return result


# --- event CRUD endpoints --------------------------------------------------

class EventCreate(BaseModel):
    """Payload for creating a calendar event."""
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    source_sub_account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventUpdate(BaseModel):
    """Payload for updating a calendar event."""
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/calendar/events", response_model=UnifiedEvent)
def create_event(body: EventCreate) -> UnifiedEvent:
    """Create a new calendar event.

    In standalone mode, this creates the event in the local SQLite store.
    In production with atom, this would also push to the connected provider
    via the sync engine.
    """
    evt = _store.create_event({
        "title": body.title,
        "start": body.start,
        "end": body.end,
        "description": body.description,
        "location": body.location,
        "source_sub_account_id": body.source_sub_account_id,
        "metadata": body.metadata,
    })
    _fire_plugin_hook("on_event_created", evt)
    return _event_to_response(evt)


@router.patch("/calendar/events/{event_id}", response_model=UnifiedEvent)
def update_event(event_id: str, body: EventUpdate) -> UnifiedEvent:
    """Update an existing calendar event by provider_event_id."""
    patch: dict[str, Any] = {}
    if body.title is not None:
        patch["title"] = body.title
    if body.start is not None:
        patch["start"] = body.start
    if body.end is not None:
        patch["end"] = body.end
    if body.description is not None:
        patch["description"] = body.description
    if body.location is not None:
        patch["location"] = body.location
    if body.metadata is not None:
        patch["metadata"] = body.metadata

    evt = _store.update_event(event_id, patch)
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")
    _fire_plugin_hook("on_event_updated", evt)
    return _event_to_response(evt)


@router.delete("/calendar/events/{event_id}")
def delete_event(event_id: str) -> dict[str, str]:
    """Delete a calendar event by provider_event_id."""
    if not _store.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    _fire_plugin_hook("on_event_deleted", event_id)
    return {"status": "deleted", "event_id": event_id}


@router.get("/calendar/events", response_model=list[UnifiedEvent])
def list_events(days: int = Query(30, ge=1, le=365)) -> list[UnifiedEvent]:
    """List all events within the next N days (wider window for agents)."""
    events = _store.get_all_events(days)
    return [_event_to_response(evt) for evt in events]


def _event_to_response(evt: dict[str, Any]) -> UnifiedEvent:
    """Convert a store event dict to a UnifiedEvent response."""
    evt_start = evt["start"]
    if isinstance(evt_start, str):
        evt_start = datetime.fromisoformat(evt_start)
    if evt_start.tzinfo is None:
        evt_start = evt_start.replace(tzinfo=UTC)
    evt_end = evt["end"]
    if isinstance(evt_end, str):
        evt_end = datetime.fromisoformat(evt_end)
    return UnifiedEvent(
        provider_event_id=evt["provider_event_id"],
        provider_type=evt.get("provider_type", "local"),
        title=evt["title"],
        start=evt_start,
        end=evt_end,
        description=evt.get("description"),
        location=evt.get("location"),
        source_sub_account_id=evt.get("source_sub_account_id"),
        metadata=evt.get("metadata", {}),
    )


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


# --- email messages --------------------------------------------------------

@router.get("/email/messages", response_model=list[EmailMessageOut])
async def list_email_messages(
    sub_account_id: str | None = Query(None),
    provider_connection_id: str | None = Query(None),
    folder: str = Query("INBOX"),
    limit: int = Query(50, ge=1, le=200),
) -> list[EmailMessageOut]:
    """List email messages from connected email providers.

    When no ``sub_account_id`` or ``provider_connection_id`` is given, returns
    a unified inbox — messages from ALL connected email accounts, merged and
    sorted newest-first. When a filter is provided, only that account's
    messages are returned.

    Args:
        sub_account_id: Filter to a specific sub-account.
        provider_connection_id: Filter to a specific provider connection.
        folder: IMAP folder or Gmail label (INBOX, STARRED, SENT, DRAFT, TRASH, ALL).
        limit: Maximum number of messages to return.

    Returns:
        List of email messages with account metadata for the unified inbox.
    """
    from a_cal.providers.factory import build_email_provider

    all_providers = _store.list_providers()
    email_types = {"imap_smtp", "gmail"}
    email_providers = [
        p for p in all_providers
        if p["provider_type"] in email_types
        and p.get("status") == "connected"
    ]
    if sub_account_id:
        email_providers = [p for p in email_providers if p["sub_account_id"] == sub_account_id]
    if provider_connection_id:
        email_providers = [p for p in email_providers if p["id"] == provider_connection_id]

    # Build sub-account name lookup
    all_subs = _store.list_sub_accounts()
    sub_map = {s["id"]: s for s in all_subs}

    results: list[EmailMessageOut] = []
    for p in email_providers:
        try:
            provider = build_email_provider(p)
            # Map folder names: "ALL" -> INBOX for IMAP (no All Mail concept)
            imap_folder = "INBOX" if folder in ("ALL", "INBOX") else folder
            gmail_label = folder  # Gmail uses label names directly
            actual_folder = gmail_label if p["provider_type"] == "gmail" else imap_folder

            messages, _cursor = await provider.list_messages(
                since_cursor=None, folder=actual_folder, limit=limit,
            )
            account_name = p.get("display_name") or p.get("provider_account_id", "Email Account")
            account_email = p.get("config", {}).get("email") or p.get("config", {}).get("username")
            sub = sub_map.get(p.get("sub_account_id", ""), {})
            for msg in messages:
                # Detect calendar invites by checking common headers/labels
                invite_headers = {"text/calendar", "method=request"}
                has_invite = bool(
                    invite_headers.intersection(
                        {v.lower() for v in msg.headers.get("Content-Type", "").split(";")}
                    )
                    or "calendar" in " ".join(msg.labels).lower()
                    or any("invite" in lbl.lower() for lbl in msg.labels)
                )
                labels = msg.labels or []
                is_unread = "UNREAD" in labels
                is_starred = "STARRED" in labels
                results.append(EmailMessageOut(
                    provider_message_id=msg.provider_message_id,
                    provider_type=msg.provider_type,
                    provider_connection_id=p["id"],
                    subject=msg.subject,
                    from_address=msg.from_address,
                    to_addresses=msg.to_addresses,
                    received_at=msg.received_at,
                    snippet=msg.snippet,
                    has_calendar_invite=has_invite,
                    labels=labels,
                    account_display_name=account_name,
                    account_email=account_email,
                    sub_account_id=p.get("sub_account_id"),
                    sub_account_name=sub.get("name"),
                    is_unread=is_unread,
                    is_starred=is_starred,
                    body_text=msg.body_text,
                    thread_id=msg.thread_id,
                    attachments=[
                        AttachmentOut(
                            filename=a.filename,
                            content_type=a.content_type,
                            size=a.size,
                            content_id=a.content_id,
                        )
                        for a in (msg.attachments or [])
                    ],
                ))
        except Exception as exc:
            logger.warning("email listing failed for %s: %s", p["id"], exc)

    # Sort: starred emails first, then newest first (stable sort).
    results.sort(
        key=lambda m: m.received_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    results.sort(key=lambda m: not m.is_starred)
    return results[:limit]


@router.get("/email/accounts", response_model=list[EmailAccountOut])
async def list_email_accounts() -> list[EmailAccountOut]:
    """List all connected email accounts for the unified inbox sidebar.

    Returns one entry per connected email provider (Gmail or IMAP/SMTP),
    with display name, email address, sub-account info, and unread count.
    """
    all_providers = _store.list_providers()
    email_types = {"imap_smtp", "gmail"}
    email_providers = [
        p for p in all_providers
        if p["provider_type"] in email_types
    ]

    all_subs = _store.list_sub_accounts()
    sub_map = {s["id"]: s for s in all_subs}

    accounts: list[EmailAccountOut] = []
    for p in email_providers:
        account_name = p.get("display_name") or p.get("provider_account_id", "Email Account")
        account_email = p.get("config", {}).get("email") or p.get("config", {}).get("username")
        sub = sub_map.get(p.get("sub_account_id", ""), {})
        unread = 0
        total = 0
        if p.get("status") == "connected":
            try:
                from a_cal.providers.factory import build_email_provider
                provider = build_email_provider(p)
                messages, _ = await provider.list_messages(
                    since_cursor=None, folder="INBOX", limit=50,
                )
                total = len(messages)
                unread = sum(1 for m in messages if "UNREAD" in (m.labels or []))
            except Exception:
                pass
        accounts.append(EmailAccountOut(
            provider_connection_id=p["id"],
            provider_type=p["provider_type"],
            display_name=account_name,
            email=account_email,
            sub_account_id=p.get("sub_account_id", ""),
            sub_account_name=sub.get("name", ""),
            status=p.get("status", "pending"),
            unread_count=unread,
            total_count=total,
        ))
    return accounts


@router.post("/email/star")
async def star_email(body: dict[str, Any]) -> dict[str, Any]:
    """Star or unstar an email message.

    Body fields: provider_connection_id, provider_message_id, starred (bool).
    """
    from a_cal.providers.factory import build_email_provider

    conn_id = body.get("provider_connection_id")
    msg_id = body.get("provider_message_id")
    starred = body.get("starred", True)
    if not conn_id or not msg_id:
        raise HTTPException(status_code=400, detail="provider_connection_id and provider_message_id required")

    all_providers = _store.list_providers()
    conn = next((p for p in all_providers if p["id"] == conn_id), None)
    if not conn:
        raise HTTPException(status_code=404, detail="Provider connection not found")

    try:
        provider = build_email_provider(conn)
        ok = await provider.star_message(msg_id, starred)
        return {"status": "ok" if ok else "failed", "starred": starred}
    except Exception as exc:
        logger.warning("email star failed for %s: %s", conn_id, exc)
        raise HTTPException(status_code=502, detail=f"Star failed: {exc}")


@router.post("/email/mark-read")
async def mark_email_read(body: dict[str, Any]) -> dict[str, Any]:
    """Mark an email message as read or unread.

    Body fields: provider_connection_id, provider_message_id, read (bool).
    """
    from a_cal.providers.factory import build_email_provider

    conn_id = body.get("provider_connection_id")
    msg_id = body.get("provider_message_id")
    read = body.get("read", True)
    if not conn_id or not msg_id:
        raise HTTPException(status_code=400, detail="provider_connection_id and provider_message_id required")

    all_providers = _store.list_providers()
    conn = next((p for p in all_providers if p["id"] == conn_id), None)
    if not conn:
        raise HTTPException(status_code=404, detail="Provider connection not found")

    try:
        provider = build_email_provider(conn)
        ok = await provider.mark_read(msg_id, read)
        return {"status": "ok" if ok else "failed", "read": read}
    except Exception as exc:
        logger.warning("email mark_read failed for %s: %s", conn_id, exc)
        raise HTTPException(status_code=502, detail=f"Mark read failed: {exc}")


@router.post("/email/delete")
async def delete_email(body: dict[str, Any]) -> dict[str, Any]:
    """Delete or trash an email message.

    Body fields: provider_connection_id, provider_message_id.
    """
    from a_cal.providers.factory import build_email_provider

    conn_id = body.get("provider_connection_id")
    msg_id = body.get("provider_message_id")
    if not conn_id or not msg_id:
        raise HTTPException(status_code=400, detail="provider_connection_id and provider_message_id required")

    all_providers = _store.list_providers()
    conn = next((p for p in all_providers if p["id"] == conn_id), None)
    if not conn:
        raise HTTPException(status_code=404, detail="Provider connection not found")

    try:
        provider = build_email_provider(conn)
        ok = await provider.delete_message(msg_id)
        return {"status": "ok" if ok else "failed", "deleted": True}
    except Exception as exc:
        logger.warning("email delete failed for %s: %s", conn_id, exc)
        raise HTTPException(status_code=502, detail=f"Delete failed: {exc}")


@router.get("/email/search", response_model=list[EmailMessageOut])
async def search_email(
    q: str = Query(..., min_length=1),
    sub_account_id: str | None = Query(None),
    provider_connection_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[EmailMessageOut]:
    """Search email messages across all connected accounts.

    When no filter is given, searches ALL connected email accounts and merges
    results. Uses provider-native search (Gmail search syntax or IMAP SEARCH).

    Args:
        q: Search query string.
        sub_account_id: Filter to a specific sub-account.
        provider_connection_id: Filter to a specific provider connection.
        limit: Maximum number of results.

    Returns:
        List of matching email messages from all searched accounts.
    """
    from a_cal.providers.factory import build_email_provider

    all_providers = _store.list_providers()
    email_types = {"imap_smtp", "gmail"}
    email_providers = [
        p for p in all_providers
        if p["provider_type"] in email_types
        and p.get("status") == "connected"
    ]
    if sub_account_id:
        email_providers = [p for p in email_providers if p["sub_account_id"] == sub_account_id]
    if provider_connection_id:
        email_providers = [p for p in email_providers if p["id"] == provider_connection_id]

    all_subs = _store.list_sub_accounts()
    sub_map = {s["id"]: s for s in all_subs}

    results: list[EmailMessageOut] = []
    for p in email_providers:
        try:
            provider = build_email_provider(p)
            messages = await provider.search_messages(query=q, folder="INBOX", limit=limit)
            account_name = p.get("display_name") or p.get("provider_account_id", "Email Account")
            account_email = p.get("config", {}).get("email") or p.get("config", {}).get("username")
            sub = sub_map.get(p.get("sub_account_id", ""), {})
            for msg in messages:
                labels = msg.labels or []
                results.append(EmailMessageOut(
                    provider_message_id=msg.provider_message_id,
                    provider_type=msg.provider_type,
                    provider_connection_id=p["id"],
                    subject=msg.subject,
                    from_address=msg.from_address,
                    to_addresses=msg.to_addresses,
                    received_at=msg.received_at,
                    snippet=msg.snippet,
                    has_calendar_invite=any("invite" in lbl.lower() for lbl in labels),
                    labels=labels,
                    account_display_name=account_name,
                    account_email=account_email,
                    sub_account_id=p.get("sub_account_id"),
                    sub_account_name=sub.get("name"),
                    is_unread="UNREAD" in labels,
                    is_starred="STARRED" in labels,
                    body_text=msg.body_text,
                    thread_id=msg.thread_id,
                    attachments=[
                        AttachmentOut(
                            filename=a.filename,
                            content_type=a.content_type,
                            size=a.size,
                            content_id=a.content_id,
                        )
                        for a in (msg.attachments or [])
                    ],
                ))
        except Exception as exc:
            logger.warning("email search failed for %s: %s", p["id"], exc)

    results.sort(
        key=lambda m: m.received_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return results[:limit]


@router.get("/email/folders")
async def list_email_folders(
    provider_connection_id: str | None = Query(None),
) -> dict[str, list[str]]:
    """List available email folders/labels per connected email account.

    Args:
        provider_connection_id: If given, only list folders for that account.

    Returns:
        Dict mapping provider_connection_id to list of folder names.
    """
    from a_cal.providers.factory import build_email_provider

    all_providers = _store.list_providers()
    email_types = {"imap_smtp", "gmail"}
    email_providers = [
        p for p in all_providers
        if p["provider_type"] in email_types
        and p.get("status") == "connected"
    ]
    if provider_connection_id:
        email_providers = [p for p in email_providers if p["id"] == provider_connection_id]

    result: dict[str, list[str]] = {}
    for p in email_providers:
        try:
            provider = build_email_provider(p)
            folders = await provider.list_folders()
            result[p["id"]] = folders
        except Exception as exc:
            logger.warning("folder listing failed for %s: %s", p["id"], exc)
            result[p["id"]] = ["INBOX"]
    return result


@router.post("/email/send")
async def send_email(body: dict[str, Any]) -> dict[str, Any]:
    """Send an email through a connected email provider.

    Body fields: provider_connection_id, to (list), subject, body_text,
    attachments (optional list of {filename, content_type, content} where
    content is base64-encoded).
    """
    from a_cal.providers.factory import build_email_provider

    provider_id = body.get("provider_connection_id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_connection_id required")

    all_providers = _store.list_providers()
    conn = next((p for p in all_providers if p["id"] == provider_id), None)
    if not conn:
        raise HTTPException(status_code=404, detail="Provider connection not found")
    if conn["provider_type"] not in ("imap_smtp", "gmail"):
        raise HTTPException(status_code=400, detail="Provider is not an email provider")

    try:
        provider = build_email_provider(conn)
        kwargs: dict[str, Any] = {
            "to": body.get("to", []),
            "subject": body.get("subject", ""),
            "body_text": body.get("body_text", ""),
        }
        attachments = body.get("attachments")
        if attachments:
            kwargs["attachments"] = attachments
        msg_id = await provider.send_message(**kwargs)
        return {"status": "sent", "provider_message_id": msg_id}
    except Exception as exc:
        logger.warning("email send failed for %s: %s", provider_id, exc)
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")
