"""Persistent store backed by SQLite.

Wraps the database models with a clean API that mirrors the in-memory stores
used by the standalone server. Falls back to in-memory when testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import (
    Base,
    BookingDB,
    CalendarEvent,
    EmailLabel,
    EmailFilter,
    EmailSnooze,
    ScheduledEmail,
    EmailTemplate,
    EventTypeDB,
    Team,
    TeamMember,
    RoutingForm,
    WebhookConfig,
    WebhookDelivery,
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

USER_ID = "local-dev-user"  # Fallback for seeding; runtime uses _uid()


def _uid() -> str:
    """Return the current user ID from auth context.

    Falls back to USER_ID ("local-dev-user") when no session is active,
    preserving backward compatibility with standalone/demo mode.
    """
    try:
        from a_cal.auth.session import get_current_user_id
        return get_current_user_id()
    except Exception:
        return USER_ID


def _serialize_sub_account(sa: SubAccount) -> dict[str, Any]:
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


def _serialize_provider(p: ProviderConnection) -> dict[str, Any]:
    """Convert a ProviderConnection ORM object to a dict.

    Note: OAuth tokens are stored in config["oauth_tokens"] but are never
    exposed through API responses because ProviderConnectionOut does not
    include the config field.
    """
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


def _serialize_sync_rule(r: SyncRule) -> dict[str, Any]:
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


def _serialize_event(e: CalendarEvent) -> dict[str, Any]:
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
        "is_all_day": getattr(e, "is_all_day", False) or False,
        "recurrence_rule": getattr(e, "recurrence_rule", None),
        "attendees": getattr(e, "attendees", None),
        "color": getattr(e, "color", None),
    }


def _serialize_event_type(et: EventTypeDB) -> dict[str, Any]:
    """Convert an EventTypeDB ORM object to a dict matching EventType.to_dict."""
    return {
        "id": et.id,
        "title": et.title,
        "slug": et.slug,
        "duration_minutes": et.duration_minutes,
        "description": et.description,
        "scheduling_type": et.scheduling_type,
        "availability": et.availability or {},
        "status": et.status,
        "color": et.color,
        "metadata": et.event_metadata or {},
        "buffer_before_minutes": et.buffer_before_minutes,
        "buffer_after_minutes": et.buffer_after_minutes,
        "min_notice_hours": et.min_notice_hours,
        "max_booking_days": et.max_booking_days,
        "recurring_pattern": et.recurring_pattern,
        "recurring_interval": et.recurring_interval,
        "custom_questions": et.custom_questions or [],
        "video_provider": et.video_provider,
        "reminder_enabled": et.reminder_enabled,
        "reminder_minutes_before": et.reminder_minutes_before,
        "confirmation_email_enabled": et.confirmation_email_enabled,
        "confirmation_template": et.confirmation_template,
        "team_id": et.team_id,
        "assignment_strategy": et.assignment_strategy,
        "routing_form_id": et.routing_form_id,
        "is_paid": et.is_paid,
        "price_cents": et.price_cents,
        "currency": et.currency,
        "stripe_product_id": et.stripe_product_id,
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
            now = datetime.now(UTC)
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

    def list_sub_accounts(self) -> list[dict[str, Any]]:
        """List all sub-accounts for the current user."""
        with self._session() as db:
            rows = db.query(SubAccount).filter(
                SubAccount.user_id == _uid()
            ).all()
            return [_serialize_sub_account(r) for r in rows]

    def create_sub_account(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new sub-account."""
        with self._session() as db:
            import uuid as _uuid
            sa = SubAccount(
                id=f"sa-{_uuid.uuid4().hex[:8]}",
                user_id=_uid(),
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

    def update_sub_account(self, sub_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a sub-account by ID (must belong to current user)."""
        with self._session() as db:
            sa = db.query(SubAccount).filter(
                SubAccount.id == sub_id,
                SubAccount.user_id == _uid(),
            ).first()
            if not sa:
                return None
            for key, val in patch.items():
                if hasattr(sa, key) and key != "id":
                    setattr(sa, key, val)
            db.commit()
            db.refresh(sa)
            return _serialize_sub_account(sa)

    def delete_sub_account(self, sub_id: str) -> bool:
        """Delete a sub-account and its associated providers and rules.

        Only deletes if the sub-account belongs to the current user.
        """
        with self._session() as db:
            sa = db.query(SubAccount).filter(
                SubAccount.id == sub_id,
                SubAccount.user_id == _uid(),
            ).first()
            if not sa:
                return False
            db.query(ProviderConnection).filter(ProviderConnection.sub_account_id == sub_id).delete()
            db.query(SyncRule).filter(SyncRule.sub_account_id == sub_id).delete()
            db.delete(sa)
            db.commit()
            return True

    # --- Providers ----------------------------------------------------------

    def list_providers(self, sub_account_id: str | None = None) -> list[dict[str, Any]]:
        """List provider connections for the current user.

        Filters through the SubAccount join to ensure only the current
        user's providers are returned. Optionally narrowed by sub-account.
        """
        with self._session() as db:
            user_sub_ids = [s.id for s in db.query(SubAccount.id).filter(
                SubAccount.user_id == _uid()
            ).all()]
            q = db.query(ProviderConnection).filter(
                ProviderConnection.sub_account_id.in_(user_sub_ids)
            )
            if sub_account_id:
                q = q.filter(ProviderConnection.sub_account_id == sub_account_id)
            rows = q.all()
            return [_serialize_provider(r) for r in rows]

    def _provider_if_owned(self, db: Session, provider_id: str) -> ProviderConnection | None:
        """Return the provider row only if it belongs to the current user.

        Provider connections have no ``user_id`` of their own — ownership is
        derived from the parent sub-account. This joins through
        ``SubAccount`` so a user can never read or mutate another user's
        provider connection by guessing its ID.
        """
        return (
            db.query(ProviderConnection)
            .join(SubAccount, ProviderConnection.sub_account_id == SubAccount.id)
            .filter(
                ProviderConnection.id == provider_id,
                SubAccount.user_id == _uid(),
            )
            .first()
        )

    def create_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new provider connection.

        The target sub-account must belong to the current user; otherwise a
        ``ValueError`` is raised so a user cannot attach a provider to
        someone else's sub-account.
        """
        with self._session() as db:
            owns_sub = db.query(SubAccount).filter(
                SubAccount.id == data["sub_account_id"],
                SubAccount.user_id == _uid(),
            ).first()
            if owns_sub is None:
                raise ValueError("Sub-account not found")
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
            True if deleted, False if not found or not owned.
        """
        with self._session() as db:
            p = self._provider_if_owned(db, provider_id)
            if not p:
                return False
            db.delete(p)
            db.commit()
            logger.info("deleted provider connection: %s", provider_id)
            return True

    def update_provider_status(self, provider_id: str, status: str) -> dict[str, Any] | None:
        """Update a provider connection status.

        Args:
            provider_id: The provider connection ID.
            status: New status (pending, connected, error, revoked).

        Returns:
            Updated provider dict, or None if not found or not owned.
        """
        with self._session() as db:
            p = self._provider_if_owned(db, provider_id)
            if not p:
                return None
            p.status = status
            if status == "connected":
                p.last_sync_at = datetime.now(UTC)
            db.commit()
            db.refresh(p)
            return _serialize_provider(p)

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Fetch a single provider connection by ID.

        Args:
            provider_id: The provider connection ID.

        Returns:
            Provider dict (including config and scopes) or None if not found
            or not owned by the current user.
        """
        with self._session() as db:
            p = self._provider_if_owned(db, provider_id)
            if not p:
                return None
            return _serialize_provider(p)

    def update_provider_config(
        self, provider_id: str, config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a provider connection's config (e.g., store OAuth tokens).

        Merges the given config into the existing config dict so partial
        updates (adding tokens without wiping other fields) are safe.

        Args:
            provider_id: The provider connection ID.
            config: Config fields to merge into the stored config.

        Returns:
            Updated provider dict, or None if not found or not owned.
        """
        with self._session() as db:
            p = self._provider_if_owned(db, provider_id)
            if not p:
                return None
            merged = dict(p.config or {})
            merged.update(config)
            p.config = merged
            db.commit()
            db.refresh(p)
            return _serialize_provider(p)

    # --- Calendar events ----------------------------------------------------

    def get_unified_calendar(self, days: int = 7) -> list[dict[str, Any]]:
        """Get events for the current user within the next N days."""
        now = datetime.now(UTC)
        end = now + timedelta(days=days)
        with self._session() as db:
            rows = db.query(CalendarEvent).filter(
                CalendarEvent.user_id == _uid(),
                CalendarEvent.start >= now,
                CalendarEvent.start <= end,
            ).order_by(CalendarEvent.start).all()
            return [_serialize_event(r) for r in rows]

    def get_all_events(self, days: int = 30) -> list[dict[str, Any]]:
        """Get all events for the current user within the next N days."""
        now = datetime.now(UTC)
        end = now + timedelta(days=days)
        with self._session() as db:
            rows = db.query(CalendarEvent).filter(
                CalendarEvent.user_id == _uid(),
                CalendarEvent.start >= now,
                CalendarEvent.start <= end,
            ).order_by(CalendarEvent.start).all()
            return [_serialize_event(r) for r in rows]

    def create_event(self, data: dict[str, Any]) -> dict[str, Any]:
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
            start_val = start_val.replace(tzinfo=UTC)
        if end_val.tzinfo is None:
            end_val = end_val.replace(tzinfo=UTC)
        # Normalize to UTC before storing — SQLite DateTime strips timezone
        # info, so we must store in UTC to keep all events comparable.
        start_val = start_val.astimezone(UTC)
        end_val = end_val.astimezone(UTC)

        with self._session() as db:
            evt = CalendarEvent(
                user_id=_uid(),
                provider_event_id=data.get("provider_event_id", str(_uuid.uuid4())),
                provider_type=data.get("provider_type", "local"),
                title=data["title"],
                start=start_val,
                end=end_val,
                description=data.get("description"),
                location=data.get("location"),
                source_sub_account_id=data.get("source_sub_account_id"),
                event_metadata=data.get("metadata", {}),
                is_all_day=data.get("is_all_day", False),
                recurrence_rule=data.get("recurrence_rule"),
                attendees=data.get("attendees"),
                color=data.get("color"),
            )
            db.add(evt)
            db.commit()
            db.refresh(evt)
            logger.info("created event: %s (%s)", evt.id, evt.title)
            return _serialize_event(evt)

    def update_event(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing calendar event (must belong to current user).

        Args:
            event_id: The provider_event_id of the event to update.
            patch: Dict of fields to update (title, start, end, etc.).

        Returns:
            The updated event as a dict, or None if not found or not owned.
        """
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.provider_event_id == event_id,
                CalendarEvent.user_id == _uid(),
            ).first()
            if not evt:
                return None
            for key, value in patch.items():
                if key in ("start", "end") and isinstance(value, str):
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=UTC)
                    # Normalize to UTC before storing (SQLite strips tz info)
                    value = value.astimezone(UTC)
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
                elif key == "is_all_day":
                    evt.is_all_day = value
                elif key == "recurrence_rule":
                    evt.recurrence_rule = value
                elif key == "attendees":
                    evt.attendees = value
                elif key == "color":
                    evt.color = value
            db.commit()
            db.refresh(evt)
            logger.info("updated event: %s (%s)", evt.provider_event_id, evt.title)
            return _serialize_event(evt)

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event by provider_event_id (must belong to current user).

        Args:
            event_id: The provider_event_id of the event to delete.

        Returns:
            True if deleted, False if not found or not owned.
        """
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.provider_event_id == event_id,
                CalendarEvent.user_id == _uid(),
            ).first()
            if not evt:
                return False
            db.delete(evt)
            db.commit()
            logger.info("deleted event: %s", event_id)
            return True

    def find_event_by_title(self, title_fragment: str) -> dict[str, Any] | None:
        """Find an event by partial title match for the current user."""
        with self._session() as db:
            evt = db.query(CalendarEvent).filter(
                CalendarEvent.title.ilike(f"%{title_fragment}%"),
                CalendarEvent.user_id == _uid(),
            ).order_by(CalendarEvent.start).first()
            return _serialize_event(evt) if evt else None

    # --- Sync rules ---------------------------------------------------------

    def list_sync_rules(self, sub_account_id: str | None = None) -> list[dict[str, Any]]:
        """List sync rules for the current user, optionally by sub-account."""
        with self._session() as db:
            user_sub_ids = [s.id for s in db.query(SubAccount.id).filter(
                SubAccount.user_id == _uid()
            ).all()]
            q = db.query(SyncRule).filter(
                SyncRule.sub_account_id.in_(user_sub_ids)
            )
            if sub_account_id:
                q = q.filter(SyncRule.sub_account_id == sub_account_id)
            rows = q.all()
            return [_serialize_sync_rule(r) for r in rows]

    def create_sync_rule(self, data: dict[str, Any]) -> dict[str, Any]:
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
                Setting.user_id == _uid(),
                Setting.key == key,
            ).first()
            if not s:
                return default
            return s.value

    def set_setting(self, key: str, value: Any) -> Any:
        """Set a setting value by key."""
        with self._session() as db:
            s = db.query(Setting).filter(
                Setting.user_id == _uid(),
                Setting.key == key,
            ).first()
            if s:
                s.value = value
            else:
                s = Setting(user_id=_uid(), key=key, value=value)
                db.add(s)
            db.commit()
            return value

    # --- API keys (stored as settings, masked on retrieval) -----------------

    def get_api_keys(self) -> dict[str, str]:
        """Get API keys, masked for display."""
        keys = self.get_setting("api_keys", {})
        return {k: "***" if v else "" for k, v in keys.items()} if keys else {}

    def get_raw_api_keys(self) -> dict[str, str]:
        """Get raw API keys for internal use (never exposed to API responses)."""
        return self.get_setting("api_keys", {}) or {}

    def set_api_keys(self, keys: dict[str, str]) -> dict[str, str]:
        """Set API keys. Merges with existing keys."""
        existing = self.get_setting("api_keys", {}) or {}
        # Only update keys that have non-empty values (skip masked ones)
        for k, v in keys.items():
            if v and v != "***":
                existing[k] = v
        self.set_setting("api_keys", existing)
        return {k: "***" if v else "" for k, v in existing.items()}

    # --- Self-model facts ---------------------------------------------------

    def list_self_model_facts(self, category: str | None = None) -> list[dict[str, Any]]:
        """List self-model facts for the current user, optionally by category."""
        with self._session() as db:
            q = db.query(SelfModelFact).filter(
                SelfModelFact.status == "active",
                SelfModelFact.user_id == _uid(),
            )
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

    def add_self_model_fact(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add a self-model fact."""
        with self._session() as db:
            f = SelfModelFact(
                user_id=_uid(),
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

    def list_negotiations(self) -> list[dict[str, Any]]:
        """List all negotiations for the current user."""
        with self._session() as db:
            rows = db.query(Negotiation).filter(
                Negotiation.user_id == _uid()
            ).order_by(Negotiation.created_at.desc()).all()
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

    def save_negotiation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Save a negotiation."""
        with self._session() as db:
            n = Negotiation(
                user_id=_uid(),
                state=data.get("state", "initiated"),
                claims=data.get("claims", []),
                messages=data.get("messages", []),
                resolution=data.get("resolution"),
            )
            db.add(n)
            db.commit()
            db.refresh(n)
            return {"id": n.id, "state": n.state}

    # --- Event types (cal.com integration) ---------------------------------

    def list_event_types(self) -> list[dict[str, Any]]:
        """List all event types for the current user.

        Returns:
            List of event type dicts (serialized via EventType.to_dict).
        """
        with self._session() as db:
            rows = db.query(EventTypeDB).filter(
                EventTypeDB.user_id == _uid()
            ).order_by(EventTypeDB.created_at).all()
            return [_serialize_event_type(r) for r in rows]

    def _ensure_unique_slug(
        self, db: Session, desired: str, exclude_id: str | None = None,
    ) -> str:
        """Return a globally-unique event-type slug.

        Slugs address public booking pages (``/booking/{slug}``) and
        ``get_event_type_by_slug`` matches on slug alone, so a slug must be
        unique across all users — otherwise a booking could resolve to the
        wrong owner. Collisions are suffixed ``-2``, ``-3``, ….
        """
        base = (desired or "event").strip().lower() or "event"
        candidate = base
        n = 1
        while True:
            q = db.query(EventTypeDB).filter(EventTypeDB.slug == candidate)
            if exclude_id:
                q = q.filter(EventTypeDB.id != exclude_id)
            if q.first() is None:
                return candidate
            n += 1
            candidate = f"{base}-{n}"

    def create_event_type(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new event type and persist it to the database.

        Args:
            data: Event type fields including scheduling constraints, recurring
                pattern, custom questions, video provider, and reminders.

        Returns:
            The created event type as a dict.
        """
        with self._session() as db:
            slug = self._ensure_unique_slug(db, data.get("slug") or data.get("title", "30-min"))
            et = EventTypeDB(
                user_id=_uid(),
                title=data.get("title", "30 Minute Meeting"),
                slug=slug,
                duration_minutes=data.get("duration_minutes", 30),
                description=data.get("description", ""),
                scheduling_type=data.get("scheduling_type", "collective"),
                availability=data.get("availability", {}),
                status=data.get("status", "active"),
                color=data.get("color", "#3B82F6"),
                event_metadata=data.get("metadata", {}),
                buffer_before_minutes=data.get("buffer_before_minutes", 0),
                buffer_after_minutes=data.get("buffer_after_minutes", 0),
                min_notice_hours=data.get("min_notice_hours", 24),
                max_booking_days=data.get("max_booking_days", 60),
                recurring_pattern=data.get("recurring_pattern", "none"),
                recurring_interval=data.get("recurring_interval", 1),
                custom_questions=data.get("custom_questions", []),
                video_provider=data.get("video_provider", ""),
                reminder_enabled=data.get("reminder_enabled", True),
                reminder_minutes_before=data.get("reminder_minutes_before", 60),
                confirmation_email_enabled=data.get("confirmation_email_enabled", True),
                confirmation_template=data.get("confirmation_template"),
                team_id=data.get("team_id"),
                assignment_strategy=data.get("assignment_strategy", "collective"),
                routing_form_id=data.get("routing_form_id"),
                is_paid=data.get("is_paid", False),
                price_cents=data.get("price_cents", 0),
                currency=data.get("currency", "USD"),
                stripe_product_id=data.get("stripe_product_id"),
            )
            db.add(et)
            db.commit()
            db.refresh(et)
            return _serialize_event_type(et)

    def get_event_type(self, et_id: str) -> dict[str, Any] | None:
        """Get a single event type by ID (must belong to current user).

        Args:
            et_id: The event type UUID.

        Returns:
            Event type dict or None if not found or not owned.
        """
        with self._session() as db:
            row = db.query(EventTypeDB).filter(
                EventTypeDB.id == et_id,
                EventTypeDB.user_id == _uid(),
            ).first()
            if row is None:
                return None
            return _serialize_event_type(row)

    def delete_event_type(self, et_id: str) -> bool:
        """Delete an event type by ID (must belong to current user).

        Args:
            et_id: The event type UUID.

        Returns:
            True if deleted, False if not found or not owned.
        """
        with self._session() as db:
            row = db.query(EventTypeDB).filter(
                EventTypeDB.id == et_id,
                EventTypeDB.user_id == _uid(),
            ).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def clear_event_types(self) -> None:
        """Delete all event types. Used in tests to reset state between runs."""
        with self._session() as db:
            db.query(EventTypeDB).delete()
            db.commit()

    def update_event_type(self, et_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update an event type's fields.

        Args:
            et_id: The event type UUID.
            patch: Dict of fields to update.

        Returns:
            Updated event type dict, or None if not found.
        """
        with self._session() as db:
            row = db.query(EventTypeDB).filter(
                EventTypeDB.id == et_id,
                EventTypeDB.user_id == _uid(),
            ).first()
            if row is None:
                return None
            if "slug" in patch and patch["slug"]:
                patch = dict(patch)
                patch["slug"] = self._ensure_unique_slug(db, patch["slug"], exclude_id=et_id)
            for key, val in patch.items():
                if key == "metadata":
                    row.event_metadata = val
                elif hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return _serialize_event_type(row)

    def get_event_type_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Get an event type by its slug (for public booking pages).

        Does not filter by user_id since the booking page is public.

        Args:
            slug: The URL slug of the event type.

        Returns:
            Event type dict or None if not found.
        """
        with self._session() as db:
            row = db.query(EventTypeDB).filter(
                EventTypeDB.slug == slug,
                EventTypeDB.status == "active",
            ).first()
            if row is None:
                return None
            return _serialize_event_type(row)

    # --- Bookings ---

    def create_booking(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new booking.

        Args:
            data: Booking fields (event_type_id, attendee_name, attendee_email,
                start_time, end_time, answers, video_link, etc.).

        Returns:
            The created booking as a dict.
        """
        with self._session() as db:
            # Look up the event type to get the owner's user_id.
            et = db.query(EventTypeDB).filter(
                EventTypeDB.id == data["event_type_id"]
            ).first()
            if et is None:
                raise ValueError("Event type not found")

            booking = BookingDB(
                event_type_id=data["event_type_id"],
                user_id=et.user_id,
                attendee_name=data.get("attendee_name", ""),
                attendee_email=data.get("attendee_email", ""),
                attendee_timezone=data.get("attendee_timezone", "UTC"),
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                status=data.get("status", "confirmed"),
                answers=data.get("answers", {}),
                video_link=data.get("video_link"),
                notes=data.get("notes"),
                booking_metadata=data.get("metadata", {}),
                payment_status=data.get("payment_status", "free"),
                payment_intent_id=data.get("payment_intent_id"),
                assigned_member_id=data.get("assigned_member_id"),
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)
            return self._serialize_booking(booking)

    def list_bookings(self, event_type_id: str | None = None) -> list[dict[str, Any]]:
        """List bookings for the current user.

        Args:
            event_type_id: If given, filter to bookings for that event type.

        Returns:
            List of booking dicts.
        """
        with self._session() as db:
            q = db.query(BookingDB).filter(BookingDB.user_id == _uid())
            if event_type_id:
                q = q.filter(BookingDB.event_type_id == event_type_id)
            rows = q.order_by(BookingDB.start_time.desc()).all()
            return [self._serialize_booking(r) for r in rows]

    def get_booking(self, booking_id: str) -> dict[str, Any] | None:
        """Get a single booking by ID.

        Args:
            booking_id: The booking UUID.

        Returns:
            Booking dict or None if not found.
        """
        with self._session() as db:
            row = db.query(BookingDB).filter(
                BookingDB.id == booking_id,
                BookingDB.user_id == _uid(),
            ).first()
            if row is None:
                return None
            return self._serialize_booking(row)

    def update_booking(self, booking_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a booking (e.g. cancel, add notes).

        Args:
            booking_id: The booking UUID.
            patch: Dict of fields to update.

        Returns:
            Updated booking dict, or None if not found.
        """
        with self._session() as db:
            row = db.query(BookingDB).filter(
                BookingDB.id == booking_id,
                BookingDB.user_id == _uid(),
            ).first()
            if row is None:
                return None
            for key, val in patch.items():
                if key == "metadata":
                    row.booking_metadata = val
                elif hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return self._serialize_booking(row)

    def delete_booking(self, booking_id: str) -> bool:
        """Delete a booking by ID.

        Args:
            booking_id: The booking UUID.

        Returns:
            True if deleted, False if not found.
        """
        with self._session() as db:
            row = db.query(BookingDB).filter(
                BookingDB.id == booking_id,
                BookingDB.user_id == _uid(),
            ).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True


    # --- Email Labels (Phase 4) ---

    def list_email_labels(self) -> list[dict[str, Any]]:
        """List all custom email labels for the current user."""
        with self._session() as db:
            rows = db.query(EmailLabel).filter(
                EmailLabel.user_id == _uid(),
            ).order_by(EmailLabel.name).all()
            return [{"id": r.id, "name": r.name, "color": r.color} for r in rows]

    def create_email_label(self, name: str, color: str = "#6366f1") -> dict[str, Any]:
        """Create a new custom email label."""
        with self._session() as db:
            lbl = EmailLabel(user_id=_uid(), name=name, color=color)
            db.add(lbl)
            db.commit()
            db.refresh(lbl)
            return {"id": lbl.id, "name": lbl.name, "color": lbl.color}

    def delete_email_label(self, label_id: str) -> bool:
        """Delete a custom email label."""
        with self._session() as db:
            lbl = db.query(EmailLabel).filter(
                EmailLabel.id == label_id,
                EmailLabel.user_id == _uid(),
            ).first()
            if not lbl:
                return False
            db.delete(lbl)
            db.commit()
            return True

    # --- Email Filters (Phase 4) ---

    def list_email_filters(self) -> list[dict[str, Any]]:
        """List all email filter rules for the current user."""
        with self._session() as db:
            rows = db.query(EmailFilter).filter(
                EmailFilter.user_id == _uid(),
            ).order_by(EmailFilter.created_at).all()
            return [{
                "id": r.id, "name": r.name, "field": r.field,
                "pattern": r.pattern, "action": r.action,
                "action_value": r.action_value, "is_active": r.is_active,
            } for r in rows]

    def create_email_filter(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new email filter rule."""
        with self._session() as db:
            flt = EmailFilter(
                user_id=_uid(),
                name=data["name"],
                field=data.get("field", "from"),
                pattern=data["pattern"],
                action=data.get("action", "label"),
                action_value=data.get("action_value"),
                is_active=data.get("is_active", True),
            )
            db.add(flt)
            db.commit()
            db.refresh(flt)
            return {
                "id": flt.id, "name": flt.name, "field": flt.field,
                "pattern": flt.pattern, "action": flt.action,
                "action_value": flt.action_value, "is_active": flt.is_active,
            }

    def delete_email_filter(self, filter_id: str) -> bool:
        """Delete an email filter rule."""
        with self._session() as db:
            flt = db.query(EmailFilter).filter(
                EmailFilter.id == filter_id,
                EmailFilter.user_id == _uid(),
            ).first()
            if not flt:
                return False
            db.delete(flt)
            db.commit()
            return True

    # --- Email Snooze (Phase 4) ---

    def snooze_email(self, provider_connection_id: str, provider_message_id: str,
                     snooze_until: datetime) -> dict[str, Any]:
        """Snooze an email until a future time."""
        with self._session() as db:
            sz = EmailSnooze(
                user_id=_uid(),
                provider_connection_id=provider_connection_id,
                provider_message_id=provider_message_id,
                snooze_until=snooze_until,
            )
            db.add(sz)
            db.commit()
            db.refresh(sz)
            return {
                "id": sz.id,
                "provider_connection_id": sz.provider_connection_id,
                "provider_message_id": sz.provider_message_id,
                "snooze_until": sz.snooze_until.isoformat(),
            }

    def list_snoozed_emails(self) -> list[dict[str, Any]]:
        """List all snoozed emails for the current user."""
        with self._session() as db:
            rows = db.query(EmailSnooze).filter(
                EmailSnooze.user_id == _uid(),
            ).order_by(EmailSnooze.snooze_until).all()
            return [{
                "id": r.id,
                "provider_connection_id": r.provider_connection_id,
                "provider_message_id": r.provider_message_id,
                "snooze_until": r.snooze_until.isoformat(),
            } for r in rows]

    def unsnooze_email(self, snooze_id: str) -> bool:
        """Remove a snooze record (return email to inbox)."""
        with self._session() as db:
            sz = db.query(EmailSnooze).filter(
                EmailSnooze.id == snooze_id,
                EmailSnooze.user_id == _uid(),
            ).first()
            if not sz:
                return False
            db.delete(sz)
            db.commit()
            return True

    # --- Scheduled Emails (Phase 4) ---

    def schedule_email(self, data: dict[str, Any]) -> dict[str, Any]:
        """Schedule an email to be sent at a future time."""
        with self._session() as db:
            scheduled_for = data["scheduled_for"]
            if isinstance(scheduled_for, str):
                scheduled_for = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
                if scheduled_for.tzinfo is None:
                    scheduled_for = scheduled_for.replace(tzinfo=UTC)
                scheduled_for = scheduled_for.astimezone(UTC)

            se = ScheduledEmail(
                user_id=_uid(),
                provider_connection_id=data["provider_connection_id"],
                to_addresses=data["to_addresses"],
                subject=data["subject"],
                body_text=data["body_text"],
                attachments=data.get("attachments"),
                scheduled_for=scheduled_for,
                status="pending",
            )
            db.add(se)
            db.commit()
            db.refresh(se)
            return {
                "id": se.id,
                "provider_connection_id": se.provider_connection_id,
                "to_addresses": se.to_addresses,
                "subject": se.subject,
                "body_text": se.body_text,
                "scheduled_for": se.scheduled_for.isoformat(),
                "status": se.status,
            }

    def list_scheduled_emails(self) -> list[dict[str, Any]]:
        """List all scheduled emails for the current user."""
        with self._session() as db:
            rows = db.query(ScheduledEmail).filter(
                ScheduledEmail.user_id == _uid(),
                ScheduledEmail.status == "pending",
            ).order_by(ScheduledEmail.scheduled_for).all()
            return [{
                "id": r.id,
                "provider_connection_id": r.provider_connection_id,
                "to_addresses": r.to_addresses,
                "subject": r.subject,
                "body_text": r.body_text,
                "scheduled_for": r.scheduled_for.isoformat(),
                "status": r.status,
            } for r in rows]

    def cancel_scheduled_email(self, sched_id: str) -> bool:
        """Cancel a scheduled email."""
        with self._session() as db:
            se = db.query(ScheduledEmail).filter(
                ScheduledEmail.id == sched_id,
                ScheduledEmail.user_id == _uid(),
            ).first()
            if not se:
                return False
            db.delete(se)
            db.commit()
            return True

    # --- Email Templates (Phase 4) ---

    def list_email_templates(self) -> list[dict[str, Any]]:
        """List all email templates for the current user."""
        with self._session() as db:
            rows = db.query(EmailTemplate).filter(
                EmailTemplate.user_id == _uid(),
            ).order_by(EmailTemplate.name).all()
            return [{
                "id": r.id, "name": r.name,
                "subject": r.subject, "body_text": r.body_text,
            } for r in rows]

    def create_email_template(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new email template."""
        with self._session() as db:
            tpl = EmailTemplate(
                user_id=_uid(),
                name=data["name"],
                subject=data.get("subject"),
                body_text=data["body_text"],
            )
            db.add(tpl)
            db.commit()
            db.refresh(tpl)
            return {
                "id": tpl.id, "name": tpl.name,
                "subject": tpl.subject, "body_text": tpl.body_text,
            }

    def update_email_template(self, tpl_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing email template."""
        with self._session() as db:
            tpl = db.query(EmailTemplate).filter(
                EmailTemplate.id == tpl_id,
                EmailTemplate.user_id == _uid(),
            ).first()
            if not tpl:
                return None
            if "name" in patch:
                tpl.name = patch["name"]
            if "subject" in patch:
                tpl.subject = patch["subject"]
            if "body_text" in patch:
                tpl.body_text = patch["body_text"]
            db.commit()
            db.refresh(tpl)
            return {
                "id": tpl.id, "name": tpl.name,
                "subject": tpl.subject, "body_text": tpl.body_text,
            }

    def delete_email_template(self, tpl_id: str) -> bool:
        """Delete an email template."""
        with self._session() as db:
            tpl = db.query(EmailTemplate).filter(
                EmailTemplate.id == tpl_id,
                EmailTemplate.user_id == _uid(),
            ).first()
            if not tpl:
                return False
            db.delete(tpl)
            db.commit()
            return True

    def check_slot_available(self, event_type_id: str, start_time: datetime, end_time: datetime) -> bool:
        """Check if a time slot is available (no overlapping bookings).

        Args:
            event_type_id: The event type UUID.
            start_time: Proposed booking start.
            end_time: Proposed booking end.

        Returns:
            True if the slot is available, False if there's a conflict.
        """
        with self._session() as db:
            existing = db.query(BookingDB).filter(
                BookingDB.event_type_id == event_type_id,
                BookingDB.status != "cancelled",
                BookingDB.start_time < end_time,
                BookingDB.end_time > start_time,
            ).first()
            return existing is None

    # --- Teams (Phase 5) ---

    def list_teams(self) -> list[dict[str, Any]]:
        """List all teams for the current user."""
        with self._session() as db:
            rows = db.query(Team).filter(Team.user_id == _uid()).order_by(Team.created_at.desc()).all()
            return [self._serialize_team(r) for r in rows]

    def create_team(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new scheduling team."""
        with self._session() as db:
            team = Team(
                user_id=_uid(),
                name=data.get("name", "My Team"),
                slug=data.get("slug", ""),
                description=data.get("description", ""),
                logo_url=data.get("logo_url"),
                branding=data.get("branding", {}),
            )
            db.add(team)
            db.commit()
            db.refresh(team)
            return self._serialize_team(team)

    def get_team(self, team_id: str) -> dict[str, Any] | None:
        """Get a single team by ID."""
        with self._session() as db:
            row = db.query(Team).filter(Team.id == team_id, Team.user_id == _uid()).first()
            if row is None:
                return None
            return self._serialize_team(row)

    def update_team(self, team_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a team's fields."""
        with self._session() as db:
            row = db.query(Team).filter(Team.id == team_id, Team.user_id == _uid()).first()
            if row is None:
                return None
            for key, val in patch.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return self._serialize_team(row)

    def delete_team(self, team_id: str) -> bool:
        """Delete a team and all its members."""
        with self._session() as db:
            row = db.query(Team).filter(Team.id == team_id, Team.user_id == _uid()).first()
            if row is None:
                return False
            db.query(TeamMember).filter(TeamMember.team_id == team_id).delete()
            db.delete(row)
            db.commit()
            return True

    @staticmethod
    def _serialize_team(t: Team) -> dict[str, Any]:
        """Convert a Team ORM object to a dict."""
        return {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "description": t.description,
            "logo_url": t.logo_url,
            "branding": t.branding or {},
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }

    # --- Team Members ---

    def list_team_members(self, team_id: str) -> list[dict[str, Any]]:
        """List all members of a team the current user owns.

        Returns an empty list if the team does not belong to the current
        user, so members cannot be enumerated cross-tenant by team ID.
        """
        with self._session() as db:
            owns = db.query(Team).filter(
                Team.id == team_id, Team.user_id == _uid(),
            ).first()
            if owns is None:
                return []
            rows = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
            return [self._serialize_team_member(r) for r in rows]

    def _member_if_owned(self, db: Session, member_id: str) -> TeamMember | None:
        """Return a team member only if its team belongs to the current user."""
        return (
            db.query(TeamMember)
            .join(Team, TeamMember.team_id == Team.id)
            .filter(TeamMember.id == member_id, Team.user_id == _uid())
            .first()
        )

    def add_team_member(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add a member to a team."""
        with self._session() as db:
            member = TeamMember(
                team_id=data["team_id"],
                email=data.get("email", ""),
                display_name=data.get("display_name", ""),
                role=data.get("role", "member"),
                provider_connection_id=data.get("provider_connection_id"),
                is_active=data.get("is_active", True),
            )
            db.add(member)
            db.commit()
            db.refresh(member)
            return self._serialize_team_member(member)

    def update_team_member(self, member_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a team member's fields (only if the team is owned)."""
        with self._session() as db:
            row = self._member_if_owned(db, member_id)
            if row is None:
                return None
            for key, val in patch.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return self._serialize_team_member(row)

    def remove_team_member(self, member_id: str) -> bool:
        """Remove a member from a team (only if the team is owned)."""
        with self._session() as db:
            row = self._member_if_owned(db, member_id)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def get_next_round_robin_member(self, team_id: str) -> dict[str, Any] | None:
        """Get the next active member for round-robin assignment.

        Picks the member with the fewest confirmed bookings, breaking ties
        by creation order (oldest first).

        Args:
            team_id: The team UUID.

        Returns:
            Team member dict or None if no active members.
        """
        with self._session() as db:
            members = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.is_active == True,
            ).order_by(TeamMember.created_at).all()
            if not members:
                return None
            # Count bookings per member
            counts: dict[str, int] = {}
            for m in members:
                count = db.query(BookingDB).filter(
                    BookingDB.assigned_member_id == m.id,
                    BookingDB.status == "confirmed",
                ).count()
                counts[m.id] = count
            # Pick the member with fewest bookings
            chosen = min(members, key=lambda m: (counts[m.id], m.created_at))
            return self._serialize_team_member(chosen)

    @staticmethod
    def _serialize_team_member(m: TeamMember) -> dict[str, Any]:
        """Convert a TeamMember ORM object to a dict."""
        return {
            "id": m.id,
            "team_id": m.team_id,
            "email": m.email,
            "display_name": m.display_name,
            "role": m.role,
            "provider_connection_id": m.provider_connection_id,
            "is_active": m.is_active,
        }

    # --- Routing Forms ---

    def list_routing_forms(self) -> list[dict[str, Any]]:
        """List all routing forms for the current user."""
        with self._session() as db:
            rows = db.query(RoutingForm).filter(RoutingForm.user_id == _uid()).all()
            return [self._serialize_routing_form(r) for r in rows]

    def create_routing_form(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new routing form."""
        with self._session() as db:
            form = RoutingForm(
                user_id=_uid(),
                name=data.get("name", ""),
                description=data.get("description", ""),
                questions=data.get("questions", []),
                routing_rules=data.get("routing_rules", []),
                is_active=data.get("is_active", True),
            )
            db.add(form)
            db.commit()
            db.refresh(form)
            return self._serialize_routing_form(form)

    def get_routing_form(self, form_id: str) -> dict[str, Any] | None:
        """Get a routing form by ID."""
        with self._session() as db:
            row = db.query(RoutingForm).filter(RoutingForm.id == form_id, RoutingForm.user_id == _uid()).first()
            if row is None:
                return None
            return self._serialize_routing_form(row)

    def update_routing_form(self, form_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a routing form."""
        with self._session() as db:
            row = db.query(RoutingForm).filter(RoutingForm.id == form_id, RoutingForm.user_id == _uid()).first()
            if row is None:
                return None
            for key, val in patch.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return self._serialize_routing_form(row)

    def delete_routing_form(self, form_id: str) -> bool:
        """Delete a routing form."""
        with self._session() as db:
            row = db.query(RoutingForm).filter(RoutingForm.id == form_id, RoutingForm.user_id == _uid()).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    @staticmethod
    def _serialize_routing_form(f: RoutingForm) -> dict[str, Any]:
        """Convert a RoutingForm ORM object to a dict."""
        return {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "questions": f.questions or [],
            "routing_rules": f.routing_rules or [],
            "is_active": f.is_active,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }

    # --- Webhooks ---

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List all webhook configs for the current user."""
        with self._session() as db:
            rows = db.query(WebhookConfig).filter(WebhookConfig.user_id == _uid()).all()
            return [self._serialize_webhook(r) for r in rows]

    def create_webhook(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new webhook endpoint config."""
        with self._session() as db:
            hook = WebhookConfig(
                user_id=_uid(),
                url=data.get("url", ""),
                events=data.get("events", []),
                secret=data.get("secret"),
                is_active=data.get("is_active", True),
            )
            db.add(hook)
            db.commit()
            db.refresh(hook)
            # Return the secret once, at creation time, so the owner can copy
            # it for signature verification. List responses omit it.
            return self._serialize_webhook(hook, include_secret=True)

    def update_webhook(self, webhook_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update a webhook config."""
        with self._session() as db:
            row = db.query(WebhookConfig).filter(WebhookConfig.id == webhook_id, WebhookConfig.user_id == _uid()).first()
            if row is None:
                return None
            for key, val in patch.items():
                if hasattr(row, key):
                    setattr(row, key, val)
            db.commit()
            db.refresh(row)
            return self._serialize_webhook(row)

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook config."""
        with self._session() as db:
            row = db.query(WebhookConfig).filter(WebhookConfig.id == webhook_id, WebhookConfig.user_id == _uid()).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def list_active_webhooks_for_event(
        self, event_type_name: str, user_id: str,
    ) -> list[dict[str, Any]]:
        """List a single user's active webhooks subscribed to an event type.

        ``user_id`` is required and scopes the lookup to one owner. Event
        dispatch (e.g. from a public, unauthenticated booking page) must pass
        the event-type owner's ``user_id`` so a booking never fans out to
        another tenant's webhook endpoints.
        """
        with self._session() as db:
            rows = db.query(WebhookConfig).filter(
                WebhookConfig.user_id == user_id,
                WebhookConfig.is_active == True,
            ).all()
            result = []
            for r in rows:
                events = r.events or []
                if event_type_name in events or "*" in events:
                    result.append(self._serialize_webhook(r, include_secret=True))
            return result

    def mark_webhook_delivered(self, webhook_id: str, last_status: int | None) -> None:
        """Record delivery bookkeeping (last status + time) on a webhook.

        Intentionally not user-scoped: the caller has already authorized the
        webhook via ``list_active_webhooks_for_event`` (which is owner-scoped),
        and dispatch runs in a public request context where the contextvar
        user would not match the webhook's owner.
        """
        with self._session() as db:
            hook = db.query(WebhookConfig).filter(
                WebhookConfig.id == webhook_id,
            ).first()
            if hook is None:
                return
            hook.last_delivery_at = datetime.now(UTC)
            hook.last_status = last_status
            db.commit()

    def list_webhook_deliveries(self, webhook_id: str) -> list[dict[str, Any]]:
        """List delivery history for a specific webhook owned by the user."""
        with self._session() as db:
            owns = db.query(WebhookConfig).filter(
                WebhookConfig.id == webhook_id,
                WebhookConfig.user_id == _uid(),
            ).first()
            if owns is None:
                return []
            rows = db.query(WebhookDelivery).filter(
                WebhookDelivery.webhook_id == webhook_id,
            ).order_by(WebhookDelivery.delivered_at.desc()).limit(50).all()
            return [
                {
                    "id": r.id,
                    "webhook_id": r.webhook_id,
                    "event_type": r.event_type,
                    "status_code": r.status_code,
                    "response_body": r.response_body,
                    "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
                }
                for r in rows
            ]

    def record_webhook_delivery(self, data: dict[str, Any]) -> dict[str, Any]:
        """Record a webhook delivery attempt."""
        with self._session() as db:
            delivery = WebhookDelivery(
                webhook_id=data["webhook_id"],
                event_type=data.get("event_type", ""),
                payload=data.get("payload", {}),
                status_code=data.get("status_code"),
                response_body=data.get("response_body"),
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)
            return {
                "id": delivery.id,
                "webhook_id": delivery.webhook_id,
                "event_type": delivery.event_type,
                "status_code": delivery.status_code,
                "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            }

    @staticmethod
    def _serialize_webhook(w: WebhookConfig, include_secret: bool = False) -> dict[str, Any]:
        """Convert a WebhookConfig ORM object to a dict.

        The signing ``secret`` is omitted by default so it is not echoed in
        list responses. Callers that genuinely need it — the one-time create
        response and the dispatcher that signs payloads — pass
        ``include_secret=True``. ``has_secret`` always indicates presence.
        """
        data: dict[str, Any] = {
            "id": w.id,
            "url": w.url,
            "events": w.events or [],
            "has_secret": bool(w.secret),
            "is_active": w.is_active,
            "last_delivery_at": w.last_delivery_at.isoformat() if w.last_delivery_at else None,
            "last_status": w.last_status,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        if include_secret:
            data["secret"] = w.secret
        return data

    @staticmethod
    def _serialize_booking(b: BookingDB) -> dict[str, Any]:
        """Convert a BookingDB ORM object to a dict."""
        return {
            "id": b.id,
            "event_type_id": b.event_type_id,
            "user_id": b.user_id,
            "attendee_name": b.attendee_name,
            "attendee_email": b.attendee_email,
            "attendee_timezone": b.attendee_timezone,
            "start_time": b.start_time.isoformat() if b.start_time else None,
            "end_time": b.end_time.isoformat() if b.end_time else None,
            "status": b.status,
            "answers": b.answers or {},
            "video_link": b.video_link,
            "notes": b.notes,
            "metadata": b.booking_metadata or {},
            "payment_status": b.payment_status,
            "payment_intent_id": b.payment_intent_id,
            "assigned_member_id": b.assigned_member_id,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
