"""additional tables: events, settings, self_model_facts, negotiations, marketplace, plugins, event_types

Adds the remaining A-Cal tables beyond the initial three (sub_accounts,
provider_connections, sync_rules) created in 0001.

Revision ID: acal0002
Revises: acal0001
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "acal0002"
down_revision = "acal0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Calendar events (offline cache from providers)
    op.create_table(
        "a_cal_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("source_sub_account_id", sa.String(length=36),
                  sa.ForeignKey("a_cal_sub_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_metadata", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Key-value settings
    op.create_table(
        "a_cal_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Self-model facts
    op.create_table(
        "a_cal_self_model_facts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("depth", sa.String(length=50), nullable=False, server_default="pattern_memory"),
        sa.Column("privacy_tier", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="0.5"),
        sa.Column("provenance", sa.Text(), nullable=True),
        sa.Column("source_event_ids", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Swarm negotiations
    op.create_table(
        "a_cal_negotiations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="initiated"),
        sa.Column("claims", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("messages", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Marketplace items
    op.create_table(
        "a_cal_marketplace_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("item_type", sa.String(length=50), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("provenance", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("config", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("tags", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("remixed_from", sa.String(length=36), nullable=True),
        sa.Column("install_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.String(length=10), nullable=False, server_default="0.0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Marketplace install records
    op.create_table(
        "a_cal_marketplace_installs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("item_id", sa.String(length=36),
                  sa.ForeignKey("a_cal_marketplace_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installed_config", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Plugins
    op.create_table(
        "a_cal_plugins",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plugin_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="0.1.0"),
        sa.Column("author", sa.String(length=255), nullable=False, server_default="local-dev-user"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("config_schema", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("default_config", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Event types (cal.com-style booking pages)
    op.create_table(
        "a_cal_event_types",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="30 Minute Meeting"),
        sa.Column("slug", sa.String(length=255), nullable=False, server_default="30-min"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("scheduling_type", sa.String(length=50), nullable=False, server_default="collective"),
        sa.Column("availability", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("color", sa.String(length=20), nullable=False, server_default="#3B82F6"),
        sa.Column("event_metadata", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("a_cal_event_types")
    op.drop_table("a_cal_plugins")
    op.drop_table("a_cal_marketplace_installs")
    op.drop_table("a_cal_marketplace_items")
    op.drop_table("a_cal_negotiations")
    op.drop_table("a_cal_self_model_facts")
    op.drop_table("a_cal_settings")
    op.drop_table("a_cal_events")
