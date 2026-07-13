"""Schema upgrade utilities for standalone mode.

Handles incremental schema changes that ``create_all`` misses on existing
databases (``create_all`` only creates missing tables, not missing columns).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Each entry: (table, column, SQL to add the column if missing)
_COLUMN_ADDITIONS: list[tuple[str, str, str]] = [
    (
        "a_cal_events",
        "user_id",
        "ALTER TABLE a_cal_events ADD COLUMN user_id VARCHAR(36) "
        "NOT NULL DEFAULT 'local-dev-user'",
    ),
    (
        "a_cal_marketplace_items",
        "content_hash",
        "ALTER TABLE a_cal_marketplace_items ADD COLUMN content_hash VARCHAR(16) "
        "NOT NULL DEFAULT ''",
    ),
    (
        "a_cal_marketplace_items",
        "verification_status",
        "ALTER TABLE a_cal_marketplace_items ADD COLUMN verification_status VARCHAR(30) "
        "NOT NULL DEFAULT 'unverified'",
    ),
    (
        "a_cal_marketplace_items",
        "flag_count",
        "ALTER TABLE a_cal_marketplace_items ADD COLUMN flag_count INTEGER "
        "NOT NULL DEFAULT 0",
    ),
    # EventTypeDB scheduling extensions (Phase 2)
    (
        "a_cal_event_types",
        "buffer_before_minutes",
        "ALTER TABLE a_cal_event_types ADD COLUMN buffer_before_minutes INTEGER "
        "NOT NULL DEFAULT 0",
    ),
    (
        "a_cal_event_types",
        "buffer_after_minutes",
        "ALTER TABLE a_cal_event_types ADD COLUMN buffer_after_minutes INTEGER "
        "NOT NULL DEFAULT 0",
    ),
    (
        "a_cal_event_types",
        "min_notice_hours",
        "ALTER TABLE a_cal_event_types ADD COLUMN min_notice_hours INTEGER "
        "NOT NULL DEFAULT 24",
    ),
    (
        "a_cal_event_types",
        "max_booking_days",
        "ALTER TABLE a_cal_event_types ADD COLUMN max_booking_days INTEGER "
        "NOT NULL DEFAULT 60",
    ),
    (
        "a_cal_event_types",
        "recurring_pattern",
        "ALTER TABLE a_cal_event_types ADD COLUMN recurring_pattern VARCHAR(50) "
        "NOT NULL DEFAULT 'none'",
    ),
    (
        "a_cal_event_types",
        "recurring_interval",
        "ALTER TABLE a_cal_event_types ADD COLUMN recurring_interval INTEGER "
        "NOT NULL DEFAULT 1",
    ),
    (
        "a_cal_event_types",
        "custom_questions",
        "ALTER TABLE a_cal_event_types ADD COLUMN custom_questions TEXT "
        "NOT NULL DEFAULT '[]'",
    ),
    (
        "a_cal_event_types",
        "video_provider",
        "ALTER TABLE a_cal_event_types ADD COLUMN video_provider VARCHAR(50) "
        "NOT NULL DEFAULT ''",
    ),
    (
        "a_cal_event_types",
        "reminder_enabled",
        "ALTER TABLE a_cal_event_types ADD COLUMN reminder_enabled BOOLEAN "
        "NOT NULL DEFAULT 1",
    ),
    (
        "a_cal_event_types",
        "reminder_minutes_before",
        "ALTER TABLE a_cal_event_types ADD COLUMN reminder_minutes_before INTEGER "
        "NOT NULL DEFAULT 60",
    ),
    (
        "a_cal_event_types",
        "confirmation_email_enabled",
        "ALTER TABLE a_cal_event_types ADD COLUMN confirmation_email_enabled BOOLEAN "
        "NOT NULL DEFAULT 1",
    ),
    (
        "a_cal_event_types",
        "confirmation_template",
        "ALTER TABLE a_cal_event_types ADD COLUMN confirmation_template TEXT "
        "NULL",
    ),
    # CalendarEvent Phase 3 extensions
    (
        "a_cal_events",
        "is_all_day",
        "ALTER TABLE a_cal_events ADD COLUMN is_all_day BOOLEAN "
        "NOT NULL DEFAULT 0",
    ),
    (
        "a_cal_events",
        "recurrence_rule",
        "ALTER TABLE a_cal_events ADD COLUMN recurrence_rule TEXT NULL",
    ),
    (
        "a_cal_events",
        "attendees",
        "ALTER TABLE a_cal_events ADD COLUMN attendees TEXT NULL",
    ),
    (
        "a_cal_events",
        "color",
        "ALTER TABLE a_cal_events ADD COLUMN color VARCHAR(20) NULL",
    ),
]


def _column_exists(conn: Any, table: str, column: str) -> bool:
    """Check if a column exists in a table (SQLite/PostgreSQL compatible)."""
    # PRAGMA doesn't support parameterized table names, but `table` is
    # always a hardcoded internal constant (never user input).
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade_schema(engine: Any) -> None:
    """Add missing columns to existing tables.

    Call this after ``create_all`` to handle incremental schema changes
    on databases that were created with an older schema.
    """
    with engine.connect() as conn:
        for table, column, sql in _COLUMN_ADDITIONS:
            try:
                if not _column_exists(conn, table, column):
                    logger.info("Adding column %s.%s (schema upgrade)", table, column)
                    conn.execute(text(sql))
                    conn.commit()
            except Exception as exc:
                # Column might already exist or ALTER not supported
                logger.warning("Schema upgrade for %s.%s skipped: %s", table, column, exc)
