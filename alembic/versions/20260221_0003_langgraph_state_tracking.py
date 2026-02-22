"""add langgraph task tracking and snapshots

Revision ID: 20260221_0003
Revises: 20260221_0002
Create Date: 2026-02-21 21:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0003"
down_revision = "20260221_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("current_node", sa.String(length=100), nullable=True))
    op.add_column("tasks", sa.Column("next_node", sa.String(length=100), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "graph_state_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.execute("UPDATE tasks SET flow_name = 'echo_add' WHERE flow_name = 'predefined_echo_add'")

    op.create_table(
        "graph_state_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("current_node", sa.String(length=100), nullable=True),
        sa.Column("next_node", sa.String(length=100), nullable=True),
        sa.Column("graph_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "step_index", name="uq_graph_state_snapshots_task_step"),
    )

    op.alter_column("tasks", "graph_state_summary", server_default=None)


def downgrade() -> None:
    op.drop_table("graph_state_snapshots")
    op.drop_column("tasks", "graph_state_summary")
    op.drop_column("tasks", "next_node")
    op.drop_column("tasks", "current_node")
