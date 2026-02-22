"""add trace_id and span_id fields for correlation

Revision ID: 20260222_0004
Revises: 20260221_0003
Create Date: 2026-02-22 12:20:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260222_0004"
down_revision = "20260221_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("trace_id", sa.String(length=64), nullable=True))
    op.add_column("task_steps", sa.Column("span_id", sa.String(length=64), nullable=True))
    op.add_column("tool_calls", sa.Column("span_id", sa.String(length=64), nullable=True))

    op.execute("UPDATE tasks SET trace_id = md5(random()::text || clock_timestamp()::text)")
    op.execute("UPDATE task_steps SET span_id = md5(random()::text || clock_timestamp()::text)")
    op.execute("UPDATE tool_calls SET span_id = md5(random()::text || clock_timestamp()::text)")

    op.alter_column("tasks", "trace_id", nullable=False)
    op.alter_column("task_steps", "span_id", nullable=False)
    op.alter_column("tool_calls", "span_id", nullable=False)
    op.create_unique_constraint("uq_tasks_trace_id", "tasks", ["trace_id"])


def downgrade() -> None:
    op.drop_constraint("uq_tasks_trace_id", "tasks", type_="unique")
    op.drop_column("tool_calls", "span_id")
    op.drop_column("task_steps", "span_id")
    op.drop_column("tasks", "trace_id")
