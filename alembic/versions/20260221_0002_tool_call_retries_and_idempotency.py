"""add tool call retries, idempotency, and timing fields

Revision ID: 20260221_0002
Revises: 20260220_0001
Create Date: 2026-02-21 18:45:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0002"
down_revision = "20260220_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_calls", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column(
        "tool_calls",
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("tool_calls", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("tool_calls", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tool_calls", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE tool_calls
        SET idempotency_key = task_id::text || ':' || task_step_id::text || ':' || tool_name,
            last_error = COALESCE(last_error, error_message)
        """
    )

    op.alter_column("tool_calls", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_tool_calls_idempotency_key",
        "tool_calls",
        ["idempotency_key"],
    )
    op.alter_column("tool_calls", "retry_count", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_tool_calls_idempotency_key", "tool_calls", type_="unique")
    op.drop_column("tool_calls", "finished_at")
    op.drop_column("tool_calls", "started_at")
    op.drop_column("tool_calls", "last_error")
    op.drop_column("tool_calls", "retry_count")
    op.drop_column("tool_calls", "idempotency_key")
