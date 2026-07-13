"""A-Cal data model — sub-accounts, provider connections, and sync rules.

These tables extend atom's existing schema (``core.database.Base``) so they
live in the same database as ``users`` / ``tenants`` / ``agent_jobs``. They are
additive: no existing atom table is altered, which keeps upstream atom updates
mergeable.

Design notes:
  * A *SubAccount* is a labeled collection of provider connections under one
    A-Cal user. A "main" sub-account is the composite/conductor view; non-main
    sub-accounts are the linked provider groupings (e.g. "Work Google",
    "Personal Fastmail").
  * A *ProviderConnection* is one linked external account (one Google cal, one
    Outlook cal, one CalDAV server, one IMAP mailbox). Credentials are NOT
    stored inline — ``credentials_ref`` points at atom's encrypted
    ``token_storage`` / ``secrets.enc`` layer.
  * *SubCalendarSyncRule* drives the per-sub-account model the user picked in
    settings (mirror+filter / intelligent merge / layered federation /
    per-sub-agent). The sync engine reads these rules to decide what flows to
    the main calendar and what stays local.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone, UTC
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

# atom's declarative base + platform-portable column types.
from core.database import Base
from core.models import JSONColumn, UUID


class SubAccountKind(str, enum.Enum):
    """Whether a sub-account groups calendar providers, email providers, or both."""

    CALENDAR = "calendar"
    EMAIL = "email"
    UNIFIED = "unified"  # the main composite account


class SyncMode(str, enum.Enum):
    """The four sub-account models the user can choose per sub-account (Q3).

    MIRROR_FILTER is the default; the others are opt-in escalations.
    """

    MIRROR_FILTER = "mirror_filter"
    INTELLIGENT_MERGE = "intelligent_merge"
    LAYERED_FEDERATION = "layered_federation"
    PER_SUB_AGENT = "per_sub_agent"


class ProviderType(str, enum.Enum):
    """Every external account A-Cal can link (calendar + email)."""

    GOOGLE_CALENDAR = "google_calendar"
    OUTLOOK_CALENDAR = "outlook_calendar"
    CALDAV = "caldav"  # any CalDAV server (Radicale, Nextcloud, Fastmail, ...)
    GMAIL = "gmail"
    IMAP_SMTP = "imap_smtp"  # any email provider via IMAP/SMTP gateway


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    REVOKED = "revoked"


class SubAccount(Base):
    """A labeled group of provider connections under one A-Cal user identity.

    Exactly one sub-account per user is ``is_main=True``; it is the composite
    "conductor" calendar/email view. All others roll up into it according to
    their ``sync_mode`` and their ``SubCalendarSyncRule`` rows.
    """

    __tablename__ = "a_cal_sub_accounts"

    id = Column(UUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String, nullable=False)  # "Work Google", "Personal", "Main"
    kind = Column(String, nullable=False, default=SubAccountKind.UNIFIED.value)
    is_main = Column(Boolean, nullable=False, default=False, index=True)

    # The user-selected sub-account model for this sub.
    sync_mode = Column(String, nullable=False, default=SyncMode.MIRROR_FILTER.value)

    # Optional nesting: a sub can roll up into a parent sub before reaching main.
    parent_sub_account_id = Column(UUID(), ForeignKey("a_cal_sub_accounts.id", ondelete="SET NULL"), nullable=True)

    # Whether this sub gets its own dedicated agent (PER_SUB_AGENT mode).
    agent_enabled = Column(Boolean, nullable=False, default=False)

    # Free-form settings: color, visibility, display order, notification prefs.
    settings = Column(JSONColumn, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    provider_connections = relationship(
        "ProviderConnection", back_populates="sub_account", cascade="all, delete-orphan"
    )
    sync_rules = relationship(
        "SubCalendarSyncRule", back_populates="sub_account", cascade="all, delete-orphan"
    )
    parent = relationship("SubAccount", remote_side="SubAccount.id", backref="children")

    __table_args__ = (
        UniqueConstraint("user_id", "is_main", name="uq_a_cal_one_main_per_user_partial"),
    )


class ProviderConnection(Base):
    """One linked external account (one Google calendar, one IMAP mailbox, ...).

    Credentials are never stored here. ``credentials_ref`` is a handle into
    atom's encrypted token storage (Fernet / ``secrets.enc``), so a connection
    can be revoked without touching raw secrets.
    """

    __tablename__ = "a_cal_provider_connections"

    id = Column(UUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    sub_account_id = Column(UUID(), ForeignKey("a_cal_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    provider_type = Column(String, nullable=False)  # ProviderType value
    # The external account's own identifier (email address, CalDAV principal URL, ...).
    provider_account_id = Column(String, nullable=False)
    display_name = Column(String, nullable=True)  # "christopher@work.com"

    # Opaque handle into atom's encrypted token_storage; never raw secrets.
    credentials_ref = Column(String, nullable=True)
    scopes = Column(JSONColumn, default=list)  # OAuth scopes granted

    status = Column(String, nullable=False, default=ConnectionStatus.PENDING.value, index=True)

    # Incremental sync state — opaque to the model, meaningful to the provider.
    sync_cursor = Column(Text, nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Provider-specific config (CalDAV server URL, IMAP host/port, etc.).
    config = Column(JSONColumn, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    sub_account = relationship("SubAccount", back_populates="provider_connections")

    __table_args__ = (
        UniqueConstraint("sub_account_id", "provider_type", "provider_account_id", name="uq_a_cal_provider_conn"),
    )


class SubCalendarSyncRule(Base):
    """Per-sub-account rules deciding what flows to the main calendar/email view.

    Evaluated by the sync engine. Rule types:
      * INCLUDE / EXCLUDE — filter by a field match (calendar_id, keyword,
        attendee domain, event category).
      * TRANSFORM — rewrite a field on the way up (rename, recolor, tag).
      * AGENT — delegate the decision to this sub's agent (PER_SUB_AGENT).
    """

    __tablename__ = "a_cal_sync_rules"

    id = Column(UUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    sub_account_id = Column(UUID(), ForeignKey("a_cal_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    rule_type = Column(String, nullable=False)  # include | exclude | transform | agent
    field = Column(String, nullable=False)  # calendar_id | keyword | attendee | category | title
    pattern = Column(String, nullable=False)  # glob/substring/regex evaluated by the engine
    action = Column(JSONColumn, default=dict)  # what to do on match (e.g. {"tag": "work"})
    priority = Column(Integer, nullable=False, default=0)  # lower runs first

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    sub_account = relationship("SubAccount", back_populates="sync_rules")
