"""a-cal: sub-accounts, provider connections, sync rules

Creates the three additive A-Cal tables on atom's database. These are
independent of atom's existing migrations (separate Alembic root) so they can
be added via alembic ``version_locations`` without disturbing atom's line.

Revision ID: acal0001
Revises:
Create Date: 2026-07-12

To deploy with atom's alembic, add to ``alembic.ini``::

    version_locations = %(here)s/versions /path/to/a-cal/alembic/versions

then ``alembic upgrade acal0001`` (or merge heads).
"""
from alembic import op
import sqlalchemy as sa

revision = "acal0001"
down_revision = None
branch_labels = ("a_cal",)
depends_on = None


def upgrade() -> None:
    op.create_table(
        "a_cal_sub_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="unified"),
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("sync_mode", sa.String(), nullable=False, server_default="mirror_filter"),
        sa.Column("parent_sub_account_id", sa.String(length=36), sa.ForeignKey("a_cal_sub_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("settings", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "is_main", name="uq_a_cal_one_main_per_user_partial"),
    )
    op.create_table(
        "a_cal_provider_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sub_account_id", sa.String(length=36), sa.ForeignKey("a_cal_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider_type", sa.String(), nullable=False),
        sa.Column("provider_account_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("credentials_ref", sa.String(), nullable=True),
        sa.Column("scopes", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(), nullable=False, server_default="pending", index=True),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("sub_account_id", "provider_type", "provider_account_id", name="uq_a_cal_provider_conn"),
    )
    op.create_table(
        "a_cal_sync_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sub_account_id", sa.String(length=36), sa.ForeignKey("a_cal_sub_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("action", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("a_cal_sync_rules")
    op.drop_table("a_cal_provider_connections")
    op.drop_table("a_cal_sub_accounts")
