"""A-Cal API routes.

Sub-account CRUD, provider-connection management, and the unified main-calendar
view. Designed to mount into atom's FastAPI app (``app.include_router(a_cal_router)``)
or run as a standalone service. Auth is delegated to atom's existing session
middleware — these routes assume an authenticated ``user_id``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a-cal", tags=["a-cal"])


# --- request/response models -----------------------------------------------

class SubAccountCreate(BaseModel):
    name: str
    kind: str = "unified"  # calendar | email | unified
    sync_mode: str = "mirror_filter"
    is_main: bool = False
    parent_sub_account_id: Optional[str] = None
    agent_enabled: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)


class SubAccountOut(BaseModel):
    id: str
    name: str
    kind: str
    is_main: bool
    sync_mode: str
    agent_enabled: bool
    settings: Dict[str, Any] = Field(default_factory=dict)


class ProviderConnectionCreate(BaseModel):
    sub_account_id: str
    provider_type: str
    provider_account_id: str
    display_name: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    scopes: List[str] = Field(default_factory=list)


class ProviderConnectionOut(BaseModel):
    id: str
    sub_account_id: str
    provider_type: str
    provider_account_id: str
    display_name: Optional[str] = None
    status: str
    last_sync_at: Optional[datetime] = None


class SyncRuleCreate(BaseModel):
    sub_account_id: str
    rule_type: str  # include | exclude | transform | agent
    field: str = "title"
    pattern: str = "*"
    action: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class UnifiedEvent(BaseModel):
    provider_event_id: str
    provider_type: str
    title: str
    start: datetime
    end: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    source_sub_account_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- DB session dependency (bridges to atom's SessionLocal) -----------------

def get_db():
    """Yield a SQLAlchemy session from atom's SessionLocal."""
    from core.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_user_id() -> str:
    """Placeholder — in production this reads atom's auth session/header.

    Wired to atom's X-User-ID middleware during integration.
    """
    return "local-dev-user"


# --- sub-account endpoints -------------------------------------------------

@router.post("/sub-accounts", response_model=SubAccountOut)
def create_sub_account(body: SubAccountCreate, db=Depends(get_db)):
    from a_cal.models import SubAccount

    sub = SubAccount(
        user_id=_current_user_id(),
        name=body.name,
        kind=body.kind,
        is_main=body.is_main,
        sync_mode=body.sync_mode,
        parent_sub_account_id=body.parent_sub_account_id,
        agent_enabled=body.agent_enabled,
        settings=body.settings,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return SubAccountOut(
        id=sub.id, name=sub.name, kind=sub.kind, is_main=sub.is_main,
        sync_mode=sub.sync_mode, agent_enabled=sub.agent_enabled, settings=sub.settings or {},
    )


@router.get("/sub-accounts", response_model=List[SubAccountOut])
def list_sub_accounts(db=Depends(get_db)):
    from a_cal.models import SubAccount

    rows = db.query(SubAccount).filter(SubAccount.user_id == _current_user_id()).all()
    return [
        SubAccountOut(
            id=r.id, name=r.name, kind=r.kind, is_main=r.is_main,
            sync_mode=r.sync_mode, agent_enabled=r.agent_enabled, settings=r.settings or {},
        )
        for r in rows
    ]


# --- provider connection endpoints -----------------------------------------

@router.post("/providers", response_model=ProviderConnectionOut)
def create_provider(body: ProviderConnectionCreate, db=Depends(get_db)):
    from a_cal.models import ProviderConnection

    conn = ProviderConnection(
        sub_account_id=body.sub_account_id,
        user_id=_current_user_id(),
        provider_type=body.provider_type,
        provider_account_id=body.provider_account_id,
        display_name=body.display_name,
        config=body.config,
        scopes=body.scopes,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return ProviderConnectionOut(
        id=conn.id, sub_account_id=conn.sub_account_id, provider_type=conn.provider_type,
        provider_account_id=conn.provider_account_id, display_name=conn.display_name,
        status=conn.status, last_sync_at=conn.last_sync_at,
    )


@router.get("/providers", response_model=List[ProviderConnectionOut])
def list_providers(sub_account_id: str = Query(...), db=Depends(get_db)):
    from a_cal.models import ProviderConnection

    rows = db.query(ProviderConnection).filter(ProviderConnection.sub_account_id == sub_account_id).all()
    return [
        ProviderConnectionOut(
            id=r.id, sub_account_id=r.sub_account_id, provider_type=r.provider_type,
            provider_account_id=r.provider_account_id, display_name=r.display_name,
            status=r.status, last_sync_at=r.last_sync_at,
        )
        for r in rows
    ]


# --- unified main-calendar view --------------------------------------------

@router.get("/calendar/unified", response_model=List[UnifiedEvent])
async def unified_calendar(
    days: int = Query(7, ge=1, le=90),
    db=Depends(get_db),
):
    """The composite main-calendar view — all sub-accounts rolled up.

    Pulls each sub-account's events via the sync engine and merges them into
    one timeline. This is the endpoint the A-Cal calendar UI renders.
    """
    from a_cal.models import ProviderConnection, SubAccount
    from a_cal.providers.factory import build_calendar_provider
    from a_cal.sync.engine import SubAccountSyncEngine

    user_id = _current_user_id()
    subs = db.query(SubAccount).filter(SubAccount.user_id == user_id).all()
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=days)

    unified: List[Dict[str, Any]] = []
    for sub in subs:
        conns = db.query(ProviderConnection).filter(ProviderConnection.sub_account_id == sub.id).all()
        providers = []
        for c in conns:
            try:
                providers.append(build_calendar_provider(_conn_to_dict(c)))
            except Exception as exc:
                logger.warning("could not build provider %s: %s", c.provider_type, exc)
        if not providers:
            continue
        rules = [r for r in (sub.sync_rules or [])]
        engine = SubAccountSyncEngine(_sub_to_dict(sub, rules), providers)
        events = await engine.pull_window(now, window_end)
        unified.extend([e.to_storage_dict() for e in events])

    return unified


def _conn_to_dict(c: Any) -> Dict[str, Any]:
    return {
        "provider_type": c.provider_type,
        "config": c.config or {},
        "credentials_ref": c.credentials_ref,
    }


def _sub_to_dict(sub: Any, rules: list) -> Dict[str, Any]:
    return {
        "id": sub.id,
        "sync_mode": sub.sync_mode,
        "sync_rules": [
            {
                "rule_type": r.rule_type, "field": r.field, "pattern": r.pattern,
                "action": r.action or {}, "priority": r.priority, "is_active": r.is_active,
            }
            for r in rules
        ],
    }


# --- sync rule endpoints ---------------------------------------------------

@router.post("/sync-rules")
def create_sync_rule(body: SyncRuleCreate, db=Depends(get_db)):
    from a_cal.models import SubCalendarSyncRule

    rule = SubCalendarSyncRule(
        sub_account_id=body.sub_account_id,
        rule_type=body.rule_type,
        field=body.field,
        pattern=body.pattern,
        action=body.action,
        priority=body.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "sub_account_id": rule.sub_account_id}
