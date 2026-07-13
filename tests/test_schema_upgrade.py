"""Tests for incremental schema upgrades on existing databases."""

import os
import sqlite3
import tempfile

import pytest
from sqlalchemy import create_engine, text

from a_cal.db.schema_upgrade import upgrade_schema, _column_exists


@pytest.fixture()
def old_db_path():
    """Create a database with the old a_cal_events schema (no user_id)."""
    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE a_cal_events (
        id VARCHAR(36) PRIMARY KEY,
        provider_event_id VARCHAR(255) NOT NULL,
        provider_type VARCHAR(50) NOT NULL,
        title VARCHAR(500) NOT NULL,
        start DATETIME NOT NULL,
        end DATETIME NOT NULL,
        description TEXT,
        location VARCHAR(500),
        source_sub_account_id VARCHAR(36),
        event_metadata JSON DEFAULT '{}',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    conn.commit()
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestSchemaUpgrade:
    """Incremental schema upgrade for standalone mode."""

    def test_column_missing_before_upgrade(self, old_db_path):
        """user_id should not exist on a database with the old schema."""
        engine = create_engine(f"sqlite:///{old_db_path}")
        with engine.connect() as conn:
            assert not _column_exists(conn, "a_cal_events", "user_id")

    def test_upgrade_adds_user_id(self, old_db_path):
        """upgrade_schema adds the user_id column to a_cal_events."""
        engine = create_engine(f"sqlite:///{old_db_path}")
        upgrade_schema(engine)
        with engine.connect() as conn:
            assert _column_exists(conn, "a_cal_events", "user_id")

    def test_upgrade_is_idempotent(self, old_db_path):
        """Running upgrade_schema twice doesn't error."""
        engine = create_engine(f"sqlite:///{old_db_path}")
        upgrade_schema(engine)
        upgrade_schema(engine)  # should not raise
        with engine.connect() as conn:
            assert _column_exists(conn, "a_cal_events", "user_id")

    def test_fresh_database_has_user_id(self):
        """A fresh database created by create_all already has user_id."""
        from a_cal.db.models import Base, CalendarEvent, _get_engine_and_session

        engine, _ = _get_engine_and_session()
        with engine.connect() as conn:
            assert _column_exists(conn, "a_cal_events", "user_id")
