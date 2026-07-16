"""Add user_id column to a_cal_events.

Revision ID: acal0003
Revises: acal0002
Create Date: 2026-07-12

The user_id column was added to the CalendarEvent model for multi-user
isolation (commit 29ccd53). This migration adds it to existing databases.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "acal0003"
down_revision = "acal0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add user_id column to a_cal_events."""
    op.add_column(
        "a_cal_events",
        sa.Column(
            "user_id",
            sa.String(length=36),
            nullable=False,
            server_default="local-dev-user",
        ),
    )
    op.create_index("ix_a_cal_events_user_id", "a_cal_events", ["user_id"])


def downgrade() -> None:
    """Remove user_id column from a_cal_events."""
    op.drop_index("ix_a_cal_events_user_id", table_name="a_cal_events")
    with op.batch_alter_table("a_cal_events") as batch_op:
        batch_op.drop_column("user_id")
