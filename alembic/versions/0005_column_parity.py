"""Bring every migration-created table to column parity with the ORM models.

Revision 0004 achieved *table* parity (all 24 tables exist after
``alembic upgrade head``) but not *column* parity: several tables were
created from stale column lists, and the columns added to older tables by
``a_cal.db.schema_upgrade`` were never mirrored into the chain. On the
Postgres deploy path (``scripts/migrate-and-start.sh`` runs alembic, then
the app starts) ``create_all`` cannot alter the pre-existing tables, so
every ORM operation on event types, bookings, teams, team members, and
webhooks failed with "no such column".

This revision adds each model column missing from the chain, with server
defaults matching the model defaults so it applies cleanly even if rows
exist. Legacy extra columns from 0001/0004 that the models don't define
are kept (dropping them is riskier than ignoring them), EXCEPT that the
four which were NOT NULL without a server default are relaxed to nullable
— the ORM never writes them, so every insert into those tables violated
the constraint.

Foreign keys for ``a_cal_event_types.team_id`` / ``routing_form_id`` are
intentionally omitted: SQLite cannot add FK constraints via ALTER TABLE,
and the ORM does not rely on DB-level enforcement for these.

Revision ID: acal0005
Revises: acal0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "acal0005"
down_revision = "acal0004"
branch_labels = None
depends_on = None

# (table, column) pairs in creation order; downgrade drops them in reverse.
_ADDED: list[tuple[str, sa.Column]] = [
    # --- a_cal_events: Phase 3 calendar extensions -------------------------
    ("a_cal_events", sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
    ("a_cal_events", sa.Column("recurrence_rule", sa.Text(), nullable=True)),
    ("a_cal_events", sa.Column("attendees", sa.JSON(), nullable=True)),
    ("a_cal_events", sa.Column("color", sa.String(20), nullable=True)),
    # --- a_cal_marketplace_items: trust & moderation ------------------------
    ("a_cal_marketplace_items", sa.Column("content_hash", sa.String(16), nullable=False, server_default="")),
    ("a_cal_marketplace_items", sa.Column("verification_status", sa.String(30), nullable=False, server_default="unverified")),
    ("a_cal_marketplace_items", sa.Column("flag_count", sa.Integer(), nullable=False, server_default=sa.text("0"))),
    # --- a_cal_event_types: multi-user + scheduling + payments --------------
    ("a_cal_event_types", sa.Column("user_id", sa.String(36), nullable=False, server_default="local-dev-user")),
    ("a_cal_event_types", sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default=sa.text("0"))),
    ("a_cal_event_types", sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default=sa.text("0"))),
    ("a_cal_event_types", sa.Column("min_notice_hours", sa.Integer(), nullable=False, server_default=sa.text("24"))),
    ("a_cal_event_types", sa.Column("max_booking_days", sa.Integer(), nullable=False, server_default=sa.text("60"))),
    ("a_cal_event_types", sa.Column("recurring_pattern", sa.String(50), nullable=False, server_default="none")),
    ("a_cal_event_types", sa.Column("recurring_interval", sa.Integer(), nullable=False, server_default=sa.text("1"))),
    ("a_cal_event_types", sa.Column("custom_questions", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))),
    ("a_cal_event_types", sa.Column("video_provider", sa.String(50), nullable=False, server_default="")),
    ("a_cal_event_types", sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"))),
    ("a_cal_event_types", sa.Column("reminder_minutes_before", sa.Integer(), nullable=False, server_default=sa.text("60"))),
    ("a_cal_event_types", sa.Column("confirmation_email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"))),
    ("a_cal_event_types", sa.Column("confirmation_template", sa.Text(), nullable=True)),
    ("a_cal_event_types", sa.Column("team_id", sa.String(36), nullable=True)),
    ("a_cal_event_types", sa.Column("assignment_strategy", sa.String(50), nullable=False, server_default="collective")),
    ("a_cal_event_types", sa.Column("routing_form_id", sa.String(36), nullable=True)),
    ("a_cal_event_types", sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false"))),
    ("a_cal_event_types", sa.Column("price_cents", sa.Integer(), nullable=False, server_default=sa.text("0"))),
    ("a_cal_event_types", sa.Column("currency", sa.String(3), nullable=False, server_default="USD")),
    ("a_cal_event_types", sa.Column("stripe_product_id", sa.String(255), nullable=True)),
    # --- a_cal_bookings: attendee details + payments ------------------------
    ("a_cal_bookings", sa.Column("attendee_timezone", sa.String(100), nullable=False, server_default="UTC")),
    ("a_cal_bookings", sa.Column("answers", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
    ("a_cal_bookings", sa.Column("video_link", sa.String(500), nullable=True)),
    ("a_cal_bookings", sa.Column("booking_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
    ("a_cal_bookings", sa.Column("payment_intent_id", sa.String(255), nullable=True)),
    ("a_cal_bookings", sa.Column("assigned_member_id", sa.String(36), nullable=True)),
    # --- a_cal_teams ---------------------------------------------------------
    ("a_cal_teams", sa.Column("logo_url", sa.String(500), nullable=True)),
    ("a_cal_teams", sa.Column("branding", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
    # --- a_cal_team_members --------------------------------------------------
    ("a_cal_team_members", sa.Column("email", sa.String(255), nullable=False, server_default="")),
    ("a_cal_team_members", sa.Column("display_name", sa.String(255), nullable=False, server_default="")),
    ("a_cal_team_members", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))),
    ("a_cal_team_members", sa.Column("provider_connection_id", sa.String(36), nullable=True)),
    # --- a_cal_webhooks: delivery bookkeeping --------------------------------
    ("a_cal_webhooks", sa.Column("last_delivery_at", sa.DateTime(), nullable=True)),
    ("a_cal_webhooks", sa.Column("last_status", sa.Integer(), nullable=True)),
]


# Legacy columns (not in any model) created NOT NULL without a server
# default; the ORM never sets them, so inserts failed. Relaxed to nullable.
# batch_alter_table rebuilds the table on SQLite and emits plain
# ALTER COLUMN ... DROP NOT NULL on PostgreSQL.
_RELAXED: list[tuple[str, str, object]] = [
    ("a_cal_provider_connections", "user_id", sa.String()),
    ("a_cal_team_members", "user_id", sa.String(36)),
    ("a_cal_team_members", "updated_at", sa.DateTime()),
    ("a_cal_webhooks", "updated_at", sa.DateTime()),
]


def upgrade() -> None:
    """Add missing model columns; relax blocking legacy NOT NULLs."""
    for table, column in _ADDED:
        op.add_column(table, column)
    op.create_index(
        "ix_a_cal_event_types_user_id", "a_cal_event_types", ["user_id"], unique=False
    )
    for table, column, coltype in _RELAXED:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=coltype, nullable=True)


def downgrade() -> None:
    """Revert this revision (reverse order; NULLs in relaxed columns block)."""
    for table, column, coltype in reversed(_RELAXED):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=coltype, nullable=False)
    op.drop_index("ix_a_cal_event_types_user_id", table_name="a_cal_event_types")
    for table, column in reversed(_ADDED):
        op.drop_column(table, column.name)
