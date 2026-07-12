"""SQLAlchemy models for A-Cal's persistent storage.

Uses SQLite for standalone mode. When running with atom, these tables are
additive to atom's database (same engine, same Base metadata).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
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

    Stores JSON as TEXT in SQLite. Uses native JSON in PostgreSQL.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: object) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: Optional[str], dialect: object) -> Any:
        if value is None or value == "":
            return None
        return json.loads(value)


def _utcnow() -> datetime:
    """UTC timestamp for default column values."""
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())


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


def get_db_path() -> str:
    """Get the SQLite database file path.

    Defaults to ``~/.a-cal/a-cal.db``. Override with ``A_CAL_DB_PATH`` env var.
    """
    env_path = os.getenv("A_CAL_DB_PATH")
    if env_path:
        return env_path
    home = os.path.expanduser("~")
    db_dir = os.path.join(home, ".a-cal")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "a-cal.db")


def create_engine_and_session(db_path: Optional[str] = None):
    """Create a SQLAlchemy engine and session factory.

    Args:
        db_path: Path to the SQLite database file. If None, uses default.

    Returns:
        Tuple of (engine, SessionLocal) for database operations.
    """
    if db_path is None:
        db_path = get_db_path()

    # Use check_same_thread=False for FastAPI's async/threaded request handling
    # Use StaticPool for in-memory databases so all sessions share one connection
    if db_path == ":memory:":
        from sqlalchemy.pool import StaticPool
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

    # Enable WAL mode for better concurrent read performance
    @sa_event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(engine)
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
