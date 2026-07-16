"""sync remaining tables and columns with current models

Creates the 13 tables missing from the original migrations (users, teams,
team_members, webhooks, webhook_deliveries, bookings, auth_attempts, and the
email-related tables) and adds columns added to event_types since the original
migrations were written. This brings the Alembic chain in sync with what
``create_all`` + ``upgrade_schema`` produce, so a fresh Postgres deploy via
``alembic upgrade head`` matches the SQLite dev path.

Revision ID: acal0004
Revises: acal0003
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "acal0004"
down_revision = "acal0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Users ---
    op.create_table(
        "a_cal_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_users_email", "a_cal_users", ["email"], unique=True)

    # --- Teams ---
    op.create_table(
        "a_cal_teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("settings", sa.Text, nullable=True),
    )
    op.create_index("ix_a_cal_teams_user_id", "a_cal_teams", ["user_id"], unique=False)

    # --- Team members ---
    op.create_table(
        "a_cal_team_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("invited_by", sa.String(36), nullable=True),
        sa.Column("joined_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_team_members_team_id", "a_cal_team_members", ["team_id"], unique=False)

    # --- Webhooks ---
    op.create_table(
        "a_cal_webhooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("events", sa.Text, nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
    )
    op.create_index("ix_a_cal_webhooks_user_id", "a_cal_webhooks", ["user_id"], unique=False)

    # --- Webhook deliveries ---
    op.create_table(
        "a_cal_webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("webhook_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.Text, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_a_cal_webhook_deliveries_webhook_id",
        "a_cal_webhook_deliveries",
        ["webhook_id"],
        unique=False,
    )

    # --- Bookings ---
    op.create_table(
        "a_cal_bookings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("start_time", sa.DateTime, nullable=False),
        sa.Column("end_time", sa.DateTime, nullable=False),
        sa.Column("attendee_name", sa.String(255), nullable=False),
        sa.Column("attendee_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="confirmed"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("cancelled_at", sa.DateTime, nullable=True),
        sa.Column("timezone", sa.String(50), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("price_cents", sa.Integer, nullable=True),
        sa.Column("payment_status", sa.String(50), nullable=True),
        sa.Column("calendar_event_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_a_cal_bookings_event_type_id", "a_cal_bookings", ["event_type_id"], unique=False)
    op.create_index("ix_a_cal_bookings_user_id", "a_cal_bookings", ["user_id"], unique=False)

    # --- Auth attempts (rate limiting / lockout) ---
    op.create_table(
        "a_cal_auth_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("fail_count", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime, nullable=True),
        sa.Column("last_attempt_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_auth_attempts_key", "a_cal_auth_attempts", ["key"], unique=True)

    # --- Email filters ---
    op.create_table(
        "a_cal_email_filters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("action_value", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_email_filters_user_id", "a_cal_email_filters", ["user_id"], unique=False)

    # --- Email labels ---
    op.create_table(
        "a_cal_email_labels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_email_labels_user_id", "a_cal_email_labels", ["user_id"], unique=False)

    # --- Email snoozes ---
    op.create_table(
        "a_cal_email_snoozes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider_connection_id", sa.String(36), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("snooze_until", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_email_snoozes_user_id", "a_cal_email_snoozes", ["user_id"], unique=False)

    # --- Email templates ---
    op.create_table(
        "a_cal_email_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_email_templates_user_id", "a_cal_email_templates", ["user_id"], unique=False)

    # --- Routing forms ---
    op.create_table(
        "a_cal_routing_forms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("questions", sa.Text, nullable=False),
        sa.Column("routing_rules", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_routing_forms_user_id", "a_cal_routing_forms", ["user_id"], unique=False)

    # --- Scheduled emails ---
    op.create_table(
        "a_cal_scheduled_emails",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider_connection_id", sa.String(36), nullable=False),
        sa.Column("to_addresses", sa.Text, nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("attachments", sa.Text, nullable=True),
        sa.Column("scheduled_for", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_a_cal_scheduled_emails_user_id", "a_cal_scheduled_emails", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("a_cal_scheduled_emails")
    op.drop_table("a_cal_routing_forms")
    op.drop_table("a_cal_email_templates")
    op.drop_table("a_cal_email_snoozes")
    op.drop_table("a_cal_email_labels")
    op.drop_table("a_cal_email_filters")
    op.drop_table("a_cal_auth_attempts")
    op.drop_table("a_cal_bookings")
    op.drop_table("a_cal_webhook_deliveries")
    op.drop_table("a_cal_webhooks")
    op.drop_table("a_cal_team_members")
    op.drop_table("a_cal_teams")
    op.drop_table("a_cal_users")
