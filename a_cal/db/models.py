"""SQLAlchemy models for A-Cal's persistent storage.

Uses SQLite for standalone mode. When running with atom, these tables are
additive to atom's database (same engine, same Base metadata).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, UTC
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    create_engine,
    event as sa_event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


class Base(DeclarativeBase):
    """Shared declarative base for A-Cal tables."""
    pass


class JSONType(TypeDecorator):
    """Platform-independent JSON column.

    Stores JSON as TEXT in SQLite. Uses native JSONB in PostgreSQL for
    indexing and query performance.
    """
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Use JSONB on PostgreSQL, TEXT on everything else."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                __import__("sqlalchemy").dialects.postgresql.JSONB()
            )
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: object) -> str | None:
        if value is None:
            return None
        # On PostgreSQL with JSONB, SQLAlchemy handles serialization.
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value: str | None, dialect: object) -> Any:
        if value is None or value == "":
            return None
        # On PostgreSQL, psycopg2 returns Python objects from JSONB.
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)


def _utcnow() -> datetime:
    """UTC timestamp for default column values."""
    return datetime.now(UTC)


def _new_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())



class User(Base):
    """A registered A-Cal user.

    Each user has one or more sub-accounts linked to provider connections.
    In standalone mode, the first registered user becomes the default.
    """
    __tablename__ = "a_cal_users"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    email = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    password_hash = Column(String(512), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class SubAccount(Base):
    """A sub-account grouping one or more provider connections."""
    __tablename__ = "a_cal_sub_accounts"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    name = Column(String(255), nullable=False)
    kind = Column(String(50), nullable=False, default="unified")
    is_main = Column(Boolean, nullable=False, default=False)
    sync_mode = Column(String(50), nullable=False, default="mirror_filter")
    agent_enabled = Column(Boolean, nullable=False, default=False)
    settings = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class ProviderConnection(Base):
    """A connection to an external calendar or email provider."""
    __tablename__ = "a_cal_provider_connections"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    sub_account_id = Column(String(36), ForeignKey("a_cal_sub_accounts.id"), nullable=False, index=True)
    provider_type = Column(String(50), nullable=False)
    provider_account_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    last_sync_at = Column(DateTime, nullable=True)
    config = Column(JSONType, nullable=False, default=dict)
    scopes = Column(JSONType, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class SyncRule(Base):
    """A sync rule controlling what flows between sub and main calendars."""
    __tablename__ = "a_cal_sync_rules"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    sub_account_id = Column(String(36), ForeignKey("a_cal_sub_accounts.id"), nullable=False, index=True)
    rule_type = Column(String(50), nullable=False)
    field = Column(String(50), nullable=False, default="title")
    pattern = Column(String(255), nullable=False, default="*")
    action = Column(JSONType, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class CalendarEvent(Base):
    """A calendar event from a provider, stored for offline access."""
    __tablename__ = "a_cal_events"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    provider_event_id = Column(String(255), nullable=False)
    provider_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)
    source_sub_account_id = Column(String(36), ForeignKey("a_cal_sub_accounts.id"), nullable=True)
    event_metadata = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class Setting(Base):
    """A key-value setting for a user (mode, model routing, etc.)."""
    __tablename__ = "a_cal_settings"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    key = Column(String(100), nullable=False)
    value = Column(JSONType, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class SelfModelFact(Base):
    """A fact learned about the user, stored persistently."""
    __tablename__ = "a_cal_self_model_facts"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    category = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    depth = Column(String(50), nullable=False, default="pattern_memory")
    privacy_tier = Column(String(50), nullable=False, default="standard")
    confidence = Column(String(20), nullable=False, default="0.5")
    provenance = Column(String(255), nullable=True)
    source_event_ids = Column(JSONType, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class Negotiation(Base):
    """A swarm negotiation between sub-accounts, stored for auditability."""
    __tablename__ = "a_cal_negotiations"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    state = Column(String(50), nullable=False, default="initiated")
    claims = Column(JSONType, nullable=False, default=list)
    messages = Column(JSONType, nullable=False, default=list)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class MarketplaceItemDB(Base):
    """A marketplace item published by a user or built-in."""
    __tablename__ = "a_cal_marketplace_items"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(255), nullable=False)
    item_type = Column(String(50), nullable=False)
    author = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    provenance = Column(JSONType, nullable=False, default=dict)
    config = Column(JSONType, nullable=False, default=dict)
    tags = Column(JSONType, nullable=False, default=list)
    remixed_from = Column(String(36), nullable=True)
    install_count = Column(Integer, nullable=False, default=0)
    rating = Column(String(10), nullable=False, default="0.0")
    rating_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=_utcnow)


class InstallRecordDB(Base):
    """A record of a user installing a marketplace item."""
    __tablename__ = "a_cal_marketplace_installs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    item_id = Column(String(36), ForeignKey("a_cal_marketplace_items.id"), nullable=False)
    installed_config = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class PluginDB(Base):
    """A registered plugin in the developer layer."""
    __tablename__ = "a_cal_plugins"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(255), nullable=False)
    plugin_type = Column(String(50), nullable=False)
    version = Column(String(50), nullable=False, default="0.1.0")
    author = Column(String(255), nullable=False, default="local-dev-user")
    description = Column(Text, nullable=False, default="")
    config_schema = Column(JSONType, nullable=False, default=dict)
    default_config = Column(JSONType, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class EventTypeDB(Base):
    """A bookable event type (cal.com-style booking page definition).

    Persisted version of the EventType dataclass from calcom_bridge.
    Survives server restarts so users don't lose their event type
    configurations.
    """
    __tablename__ = "a_cal_event_types"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="local-dev-user")
    title = Column(String(255), nullable=False, default="30 Minute Meeting")
    slug = Column(String(255), nullable=False, default="30-min")
    duration_minutes = Column(Integer, nullable=False, default=30)
    description = Column(Text, nullable=False, default="")
    scheduling_type = Column(String(50), nullable=False, default="collective")
    availability = Column(JSONType, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="active")
    color = Column(String(20), nullable=False, default="#3B82F6")
    event_metadata = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


def get_database_url() -> str | None:
    """Get the database URL from the environment.

    Checks ``DATABASE_URL`` first (standard convention, works with PostgreSQL
    and any SQLAlchemy-compatible URL). Returns None if not set, in which case
    the caller falls back to SQLite.

    Examples:
        postgresql://user:pass@localhost:5432/acal
        postgresql+psycopg2://user:pass@localhost:5432/acal
    """
    return os.getenv("DATABASE_URL")


def get_db_path() -> str:
    """Get the SQLite database file path.

    Defaults to ``~/.a-cal/a-cal.db``. Override with ``A_CAL_DB_PATH`` env var.
    Only used when ``DATABASE_URL`` is not set.
    """
    env_path = os.getenv("A_CAL_DB_PATH")
    if env_path:
        return env_path
    home = os.path.expanduser("~")
    db_dir = os.path.join(home, ".a-cal")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "a-cal.db")


def create_engine_and_session(db_path: str | None = None):
    """Create a SQLAlchemy engine and session factory.

    Supports both SQLite (standalone mode) and PostgreSQL (production / atom
    deployment). Connection selection priority:

    1. Explicit ``db_path`` argument (used by tests for ``:memory:``).
    2. ``DATABASE_URL`` env var (PostgreSQL or any SQLAlchemy URL).
    3. Default SQLite path from ``get_db_path()``.

    Args:
        db_path: Path to the SQLite database file, or ``:memory:`` for tests.
            If None, checks ``DATABASE_URL`` then falls back to SQLite.

    Returns:
        Tuple of (engine, SessionLocal) for database operations.
    """
    # Resolve the effective db_path: explicit arg > env var > default path
    if db_path is None:
        env_url = get_database_url()
        if env_url:
            # External database (PostgreSQL, etc.) — use the URL directly
            url = env_url
            is_sqlite = False
            is_in_memory = False
        else:
            db_path = get_db_path()
            url = f"sqlite:///{db_path}"
            is_sqlite = True
            is_in_memory = db_path == ":memory:"
    elif db_path == ":memory:":
        url = "sqlite://"
        is_sqlite = True
        is_in_memory = True
    else:
        url = f"sqlite:///{db_path}"
        is_sqlite = True
        is_in_memory = False

    # Build engine with appropriate connection settings
    if is_in_memory:
        from sqlalchemy.pool import StaticPool
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    elif is_sqlite:
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL or other external database
        engine = create_engine(url, pool_pre_ping=True)

    # SQLite-specific optimizations (WAL mode for concurrent reads)
    if is_sqlite:
        @sa_event.listens_for(engine, "connect")
        def set_wal_mode(dbapi_conn, conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    Base.metadata.create_all(engine)

    # Handle incremental schema changes on existing databases.
    # create_all only creates missing tables, not missing columns.
    from a_cal.db.schema_upgrade import upgrade_schema
    upgrade_schema(engine)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, SessionLocal


# Module-level engine and session (lazy-initialized)
_engine = None
_SessionLocal = None


def _get_engine_and_session():
    """Get or create the module-level engine and session factory."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine, _SessionLocal = create_engine_and_session()
    return _engine, _SessionLocal


def get_session() -> Session:
    """Get a new database session."""
    _, session_local = _get_engine_and_session()
    return session_local()
