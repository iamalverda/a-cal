"""Persistent store backed by SQLite.

Wraps the database models with a clean API that mirrors the in-memory stores
used by the standalone server. Falls back to in-memory when testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import (
    Base,
    CalendarEvent,
    Negotiation,
    ProviderConnection,
    SelfModelFact,
    Setting,
    SubAccount,
    SyncRule,
    get_session,
    create_engine_and_session,
)

logger = logging.getLogger(__name__)

USER_ID = "local-dev-user"


def _serialize_sub_account(sa: SubAccount) -> Dict[str, Any]:
    """Convert a SubAccount ORM object to a dict."""
    return {
        "id": sa.id,
        "user_id": sa.user_id,
        "name": sa.name,
        "kind": sa.kind,
        "is_main": sa.is_main,
        "sync_mode": sa.sync_mode,
        "agent_enabled": sa.agent_enabled,
        "settings": sa.settings or {},
    }


def _serialize_provider(p: ProviderConnection) -> Dict[str, Any]:
    """Convert a ProviderConnection ORM object to a dict."""
    return {
        "id": p.id,
        "sub_account_id": p.sub_account_id,
        "provider_type": p.provider_type,
        "provider_account_id": p.provider_account_id,
        "display_name": p.display_name,
        "status": p.status,
        "last_sync_at": p.last_sync_at.isoformat() if p.last_sync_at else None,
        "config": p.config or {},
        "scopes": p.scopes or [],
    }


def _serialize_sync_rule(r: SyncRule) -> Dict[str, Any]:
    """Convert a SyncRule ORM object to a dict."""
    return {
        "id": r.id,
        "sub_account_id": r.sub_account_id,
        "rule_type": r.rule_type,
        "field": r.field,
        "pattern": r.pattern,
        "action": r.action or {},
        "priority": r.priority,
    }


def _serialize_event(e: CalendarEvent) -> Dict[str, Any]:
    """Convert a CalendarEvent ORM object to a dict."""
    return {
        "provider_event_id": e.provider_event_id,
        "provider_type": e.provider_type,
        "title": e.title,
        "start": e.start.isoformat() if e.start else None,
        "end": e.end.isoformat() if e.end else None,
        "description": e.description,
        "location": e.location,
        "source_sub_account_id": e.source_sub_account_id,
        "metadata": e.event_metadata or {},
    }


class PersistentStore:
    """SQLite-backed store for A-Cal data.

    Replaces the in-memory _STORE and _SettingsStore with persistent storage.
    Data survives server restarts.
    """

    def __init__(self, in_memory: bool = False) -> None:
        """Initialize the store.

        Args:
            in_memory: If True, use an in-memory SQLite database (for tests).
        """
        if in_memory:
            self._engine, self._SessionLocal = create_engine_and_session(":memory:")
        else:
            from .models import _get_engine_and_session
            self._engine, self._SessionLocal = _get_engine_and_session()

        self._seed_if_empty()

    def _seed_if_empty(self) -> None:
        """Seed demo data on first run when the database is empty."""
        with self._session() as db:
            if db.query(SubAccount).count() > 0:
                return

            logger.info("Seeding initial demo data into database")

            # Main account
            main = SubAccount(
                id="sa-main",
                user_id=USER_ID,
                name="Main Calendar",
                kind="unified",
                is_main=True,
                sync_mode="mirror_filter",
                agent_enabled=True,
                settings={"color": "#6366f1", "visible": True},
            )
            # Work Google
            work = SubAccount(
                id="sa-work-google",
                user_id=USER_ID,
                name="Work Google",
                kind="calendar",
                is_main=False,
                sync_mode="mirror_filter",
                agent_enabled=False,
                settings={"color": "#3b82f6", "visible": True},
            )
            # Personal
            personal = SubAccount(
                id="sa-personal",
                user_id=USER_ID,
                name="Personal",
                kind="calendar",
                is_main=False,
                sync_mode="mirror_filter",
                agent_enabled=False,
                settings={"color": "#10b981", "visible": True},
            )
            # Side Project
            side = SubAccount(
                id="sa-side-project",
                user_id=USER_ID,
                name="Side Project",
                kind="calendar",
                is_main=False,
                sync_mode="intelligent_merge",
                agent_enabled=True,
                settings={"color": "#f59e0b", "visible": True},
            )
            db.add_all([main, work, personal, side])

            # Providers
            providers = [
                ProviderConnection(
                    id="pc-1",
                    sub_account_id="sa-work-google",
                    provider_type="google_calendar",
                    provider_account_id="user@gmail.com",
                    display_name="Work Calendar",
                    status="connected",
                    config={},
                    scopes=[],
                ),
                ProviderConnection(
                    id="pc-2",
                    sub_account_id="sa-personal",
                    provider_type="outlook_calendar",
                    provider_account_id="user@outlook.com",
                    display_name="Personal Outlook",
                    status="connected",
                    config={},
                    scopes=[],
                ),
                ProviderConnection(
                    id="pc-3",
                    sub_account_id="sa-side-project",
                    provider_type="caldav",
                    provider_account_id="user@radicale.local",
                    display_name="Project CalDAV",
                    status="pending",
                    config={},
                    scopes=[],
                ),
                ProviderConnection(
                    id="pc-4",
                    sub_account_id="sa-personal",
                    provider_type="imap_smtp",
                    provider_account_id="user@outlook.com",
                    display_name="Personal Email",
                    status="connected",
                    config={},
                    scopes=[],
                ),
            ]
            db.add_all(providers)

            # Sync rules
            rules = [
                SyncRule(
                    id="sr-1",
                    sub_account_id="sa-work-google",
                    rule_type="include",
                    field="title",
                    pattern="*",
                    action={"mirror_to_main": True},
                    priority=1,
                ),
                SyncRule(
                    id="sr-2",
                    sub_account_id="sa-personal",
                    rule_type="exclude",
                    field="title",
                    pattern="*private*",
                    action={"mirror_to_main": False},
                    priority=2,
                ),
                SyncRule(
                    id="sr-3",
                    sub_account_id="sa-side-project",
                    rule_type="include",
                    field="title",
                    pattern="*deadline*|*sprint*|*review*",
                    action={"mirror_to_main": True},
                    priority=1,
                ),
            ]
            db.add_all(rules)

            # Demo events — all in the future relative to now
            now = datetime.now(timezone.utc)
            events = [
                CalendarEvent(
                    id="evt-1",
                    provider_event_id="gcal-1",
                    provider_type="google_calendar",
                    title="Team Standup",
                    start=now + timedelta(hours=2),
                    end=now + timedelta(hours=2, minutes=30),
                    description="Daily sync",
                    location="Zoom",
                    source_sub_account_id="sa-work-google",
                    event_metadata={},
                ),
                CalendarEvent(
                    id="evt-2",
                    provider_event_id="gcal-2",
                    provider_type="google_calendar",
                    title="1:1 with Manager",
                    start=now + timedelta(hours=3),
                    end=now + timedelta(hours=3, minutes=30),
                    description="Weekly check-in",
                    location="Office",
                    source_sub_account_id="sa-work-google",
                    event_metadata={},
                ),
                CalendarEvent(
                    id="evt-3",
                    provider_type="outlook_calendar",
                    provider_event_id="olk-1",
                    title="Dentist Appointment",
                    start=now + timedelta(days=1),
                    end=now + timedelta(days=1, hours=1),
                    description="Annual checkup",
                    location="Dr. Smith Office",
                    source_sub_account_id="sa-personal",
                    event_metadata={},
                ),
                CalendarEvent(
                    id="evt-4",
                    provider_type="caldav",
                    provider_event_id="caldav-1",
                    title="Sprint Review",
                    start=now + timedelta(hours=5),
                    end=now + timedelta(hours=6),
                    description="End of sprint demo",
                    location="Discord",
                    source_sub_account_id="sa-side-project",
                    event_metadata={},
                ),
                CalendarEvent(
                    id="evt-5",
                    provider_event_id="gcal-3",
                    provider_type="google_calendar",
                    title="Design Review",
                    start=now + timedelta(days=2),
                    end=now + timedelta(days=2, hours=1),
                    description="Review new UI mockups",
                    location="Figma",
                    source_sub_account_id="sa-work-google",
                    event_metadata={},
                ),
            ]
            db.add_all(events)

            db.commit()
            logger.info("Demo data seeded successfully")

    def _session(self) -> Session:
        """Get a new database session."""
        return self._SessionLocal()

    # --- Sub-accounts -------------------------------------------------------

    def list_sub_accounts(self) -> List[Dict[str, Any]]:
        """List all sub accounts."""
        with self._session() as db:
            rows = db.query(SubAccount).all()
            return [_serialize_sub_account(r) for r in rows]

    def create_sub_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sub-account."""
        with self._session() as db:
            import uuid as _uuid
            sa = SubAccount(
                id=f"sa-{_uuid.uuid4().hex[:8]}",
                user_id=USER_ID,
                name=data["name"],
                kind=data.get("kind", "unified"),
                is_main=data.get("is_main", False),
                sync_mode=data.get("sync_mode", "mirror_filter"),
                agent_enabled=data.get("agent_enabled", False),
                settings=data.get("settings", {}),
            )
            db.add(sa)
            db.commit()
            db.refresh(sa)
            return _serialize_sub_account(sa)

    def update_sub_account(self, sub_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a sub-account by ID."""
        with self._session() as db:
            sa = db.query(SubAccount).filter(SubAccount.id == sub_id).first()
            if not sa:
                return None
            for key, val in patch.items():
                if hasattr(sa, key) and key != "id":
                    setattr(sa, key, val)
            db.commit()
            db.refresh(sa)
            return _serialize_sub_account(sa)

    def delete_sub_account(self, sub_id: str) -> bool:
        """Delete a sub-account and its associated providers and rules."""
        with self._session() as db:
            sa = db.query(SubAccount).filter(SubAccount.id == sub_id).first()
            if not sa:
                return False
            db.query(ProviderConnection).filter(ProviderConnection.sub_account_id == sub_id).delete()
            db.query(SyncRule).filter(SyncRule.sub_account_id == sub_id).delete()
            db.delete(sa)
            db.commit()
            return True

    # --- Providers ----------------------------------------------------------

    def list_providers(self, sub_account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List provider connections, optionally filtered by sub-account."""
        with self._session() as db:
            q = db.query(ProviderConnection)
            if sub_account_id:
                q = q.filter(ProviderConnection.sub_account_id == sub_account_id)
            rows = q.all()
            return [_serialize_provider(r) for r in rows]

    def create_provider(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new provider connection."""
        with self._session() as db:
            import uuid as _uuid
            p = ProviderConnection(
                id=f"pc-{_uuid.uuid4().hex[:8]}",
                sub_account_id=data["sub_account_id"],
                provider_type=data["provider_type"],
                provider_account_id=data["provider_account_id"],
                display_name=data.get("display_name"),
                status="pending",
                config=data.get("config", {}),
                scopes=data.get("scopes", []),
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            return _serialize_provider(p)

    def delete_provider(self, provider_id: str) -> bool:
        """Delete a provider connection by ID.

        Args:
            provider_id: The ID of the provider connection to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._session() as db:
            p = db.query(ProviderConnection).filter(
                ProviderConnection.id == provider_id,
            ).first()
            if not p:
                return False
            db.delete(p)
            db.commit()
            logger.info("deleted provider connection: %s", provider_id)
            return True

    def update_provider_status(self, provider_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Update a provider connection status.

        Args:
            provider_id: The provider connection ID.
            status: New status (pending, connected, error, revoked).

        Returns:
            Updated provider dict, or None if not found.
        """
        with self._session() as db:
            p = db.query(ProviderConnection).filter(
                ProviderConnection.id == provider_id,
            ).first()
            if not p:
                return None
            p.status = status
            if status == "connected":
                p.last_sync_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(p)
            return _serialize_provider(p)

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single provider connection by ID.

        Args:
            provider_id: The provider connection ID.

        Returns:
            Provider dict (including config and scopes) or None if not found.
        """
        with self._session() as db:
            p = db.query(ProviderConnection).filter(
                ProviderConnection.id == provider_id,
            ).first()
            if not p:
                return None
            return _serialize_provider(p)

    def update_provider_config(
        self, provider_id: str, config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a provider connection's config (e.g., store OAuth tokens).

        Merges the given config into the existing config dict so partial
        updates (adding tokens without wiping other fields) are safe.

        Args:
            provider_id: The provider connection ID.
            config: Config fields to merge into the stored config.

        Returns:
            Updated provider dict, or None if not found.
        """
        with self._session() as db:
            p = db.query(ProviderConnection).filter(
                ProviderConnection.id == provider_id,
            ).first()
            if not p:
                return None
            merged = dict(p.config or {})
            merged.update(config)
            p.config = merged
            db.commit()
            db.refresh(p)
            return _serialize_provider(p)

    # --- Calendar events ----------------------------------------------------

    def get_unified_calendar(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get events from all sub-accounts within the next N days."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        with self._session() as db:
            rows = db.query(CalendarEvent).filter(
                CalendarEvent.start >= now,
                CalendarEvent.start <= end,
            ).order_by(CalendarEvent.start).all()
            return [_serialize_event(r) for r in rows]

    def get_all_events(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get all events within the next N days (wider window for agent queries)."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        with self._session() as db:
            rows = db.query(CalendarEvent).filter(
                CalendarEvent.start >= now,
                CalendarEvent.start <= end,
            ).order_by(CalendarEvent.start).all()
            return [_serialize_event(r) for r in rows]

    def create_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new calendar event in the store.

        Args:
            data: Dict with title, start, end, and optional fields.

        Returns:
            The created event as a dict.
        """
        import uuid as _uuid
        start_val = data["start"]
        end_val = data["end"]
        if isinstance(start_val, str):
            start_val = datetime.fromisoformat(start_val.replace("Z", "+00:00"))
        if isinstance(end_val, str):
            end_val = datetime.fromisoformat(end_val.replace("Z", "+00:00"))
        if start_val.tzinfo is None:
            start_val = start_val.replace(tzinfo=timezone.utc)
        if end_val.tzinfo is None:
            end_val = end_val.replace(tzinfo=timezone.utc)

        with self._session() as db:
            evt = CalendarEvent(
                provider_event_id=data.get("provider_event_id", str(_uuid.uuid4())),
                provider_type=data.get("provider_type", "local"),
                title=data["title"],
                start=start_val,
                end=end_val,
                description=data.get("description"),
                location=data.get("location"),
                source_sub_account_id=data.get("source_sub_account_id"),
                event_metadata=data.get("metadata", {}),
            )
            db.add(evt)
            db.commit()
            db.refresh(evt)
            logger.info("created event: %s (%s)", evt.id, evt.title)
            return _serialize_event(evt)

    def update_event(self, event_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing calendar event.

        Args:
            event_id: The provider_event_id of the event to update.
            patch: Dict of fields to update (title, start, end, etc.).

        Returns:
            The updated event as a dict, or None if not found.
        """
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.provider_event_id == event_id,
            ).first()
            if not evt:
                return None
            for key, value in patch.items():
                if key in ("start", "end") and isinstance(value, str):
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=timezone.utc)
                if key == "title":
                    evt.title = value
                elif key == "start":
                    evt.start = value
                elif key == "end":
                    evt.end = value
                elif key == "description":
                    evt.description = value
                elif key == "location":
                    evt.location = value
                elif key == "metadata":
                    evt.event_metadata = value
            db.commit()
            db.refresh(evt)
            logger.info("updated event: %s (%s)", evt.provider_event_id, evt.title)
            return _serialize_event(evt)

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event by provider_event_id.

        Args:
            event_id: The provider_event_id of the event to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.provider_event_id == event_id,
            ).first()
            if not evt:
                return False
            db.delete(evt)
            db.commit()
            logger.info("deleted event: %s", event_id)
            return True

    def find_event_by_title(self, title_fragment: str) -> Optional[Dict[str, Any]]:
        """Find an event by partial title match (for agent rescheduling)."""
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.title.ilike(f"%{title_fragment}%"),
            ).order_by(CalendarEvent.start).first()
            return _serialize_event(evt) if evt else None

    # --- Sync rules ---------------------------------------------------------

    def list_sync_rules(self, sub_account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List sync rules, optionally filtered by sub-account."""
        with self._session() as db:
            q = db.query(SyncRule)
            if sub_account_id:
                q = q.filter(SyncRule.sub_account_id == sub_account_id)
            rows = q.all()
            return [_serialize_sync_rule(r) for r in rows]

    def create_sync_rule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sync rule."""
        with self._session() as db:
            r = SyncRule(
                sub_account_id=data["sub_account_id"],
                rule_type=data["rule_type"],
                field=data.get("field", "title"),
                pattern=data.get("pattern", "*"),
                action=data.get("action", {}),
                priority=data.get("priority", 0),
            )
            db.add(r)
            db.commit()
            db.refresh(r)
            return _serialize_sync_rule(r)

    def delete_sync_rule(self, rule_id: str) -> bool:
        """Delete a sync rule by ID. Returns True if deleted."""
        with self._session() as db:
            r = db.query(SyncRule).filter(SyncRule.id == rule_id).first()
            if not r:
                return False
            db.delete(r)
            db.commit()
            return True

    # --- Settings -----------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key."""
        with self._session() as db:
            s = db.query(Setting).filter(
                Setting.user_id == USER_ID,
                Setting.key == key,
            ).first()
            if not s:
                return default
            return s.value

    def set_setting(self, key: str, value: Any) -> Any:
        """Set a setting value by key."""
        with self._session() as db:
            s = db.query(Setting).filter(
                Setting.user_id == USER_ID,
                Setting.key == key,
            ).first()
            if s:
                s.value = value
            else:
                s = Setting(user_id=USER_ID, key=key, value=value)
                db.add(s)
            db.commit()
            return value

    # --- API keys (stored as settings, masked on retrieval) -----------------

    def get_api_keys(self) -> Dict[str, str]:
        """Get API keys, masked for display."""
        keys = self.get_setting("api_keys", {})
        return {k: "***" if v else "" for k, v in keys.items()} if keys else {}

    def get_raw_api_keys(self) -> Dict[str, str]:
        """Get raw API keys for internal use (never exposed to API responses)."""
        return self.get_setting("api_keys", {}) or {}

    def set_api_keys(self, keys: Dict[str, str]) -> Dict[str, str]:
        """Set API keys. Merges with existing keys."""
        existing = self.get_setting("api_keys", {}) or {}
        # Only update keys that have non-empty values (skip masked ones)
        for k, v in keys.items():
            if v and v != "***":
                existing[k] = v
        self.set_setting("api_keys", existing)
        return {k: "***" if v else "" for k, v in existing.items()}

    # --- Self-model facts ---------------------------------------------------

    def list_self_model_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List self-model facts, optionally filtered by category."""
        with self._session() as db:
            q = db.query(SelfModelFact).filter(SelfModelFact.status == "active")
            if category:
                q = q.filter(SelfModelFact.category == category)
            rows = q.all()
            return [
                {
                    "id": r.id,
                    "category": r.category,
                    "content": r.content,
                    "depth": r.depth,
                    "privacy_tier": r.privacy_tier,
                    "confidence": float(r.confidence),
                    "provenance": r.provenance,
                    "status": r.status,
                }
                for r in rows
            ]

    def add_self_model_fact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a self-model fact."""
        with self._session() as db:
            f = SelfModelFact(
                user_id=USER_ID,
                category=data["category"],
                content=data["content"],
                depth=data.get("depth", "pattern_memory"),
                privacy_tier=data.get("privacy_tier", "standard"),
                confidence=str(data.get("confidence", 0.5)),
                provenance=data.get("provenance"),
                source_event_ids=data.get("source_event_ids"),
            )
            db.add(f)
            db.commit()
            db.refresh(f)
            return {
                "id": f.id,
                "category": f.category,
                "content": f.content,
                "depth": f.depth,
                "confidence": float(f.confidence),
            }

    def delete_self_model_fact(self, fact_id: str) -> bool:
        """Delete (soft-delete) a self-model fact."""
        with self._session() as db:
            f = db.query(SelfModelFact).filter(SelfModelFact.id == fact_id).first()
            if not f:
                return False
            f.status = "deleted"
            db.commit()
            return True

    # --- Negotiations -------------------------------------------------------

    def list_negotiations(self) -> List[Dict[str, Any]]:
        """List all negotiations."""
        with self._session() as db:
            rows = db.query(Negotiation).order_by(Negotiation.created_at.desc()).all()
            return [
                {
                    "id": r.id,
                    "state": r.state,
                    "claims": r.claims,
                    "messages": r.messages,
                    "resolution": r.resolution,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    def save_negotiation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a negotiation."""
        with self._session() as db:
            n = Negotiation(
                user_id=USER_ID,
                state=data.get("state", "initiated"),
                claims=data.get("claims", []),
                messages=data.get("messages", []),
                resolution=data.get("resolution"),
            )
            db.add(n)
            db.commit()
            db.refresh(n)
            return {"id": n.id, "state": n.state}
