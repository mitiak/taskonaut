from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskStatus(enum.StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_OBSERVATION = "WAITING_OBSERVATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStepStatus(enum.StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ToolCallStatus(enum.StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False),
        nullable=False,
        default=TaskStatus.PLANNED,
    )
    flow_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="soc_pipeline",
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    graph_state_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    steps: Mapped[list[TaskStep]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskStep.step_index",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ToolCall.created_at",
    )
    graph_state_snapshots: Mapped[list[GraphStateSnapshot]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="GraphStateSnapshot.step_index",
    )


class TaskStep(Base):
    __tablename__ = "task_steps"
    __table_args__ = (
        UniqueConstraint("task_id", "step_index", name="uq_task_steps_task_id_step_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    span_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TaskStepStatus] = mapped_column(
        Enum(TaskStepStatus, name="task_step_status", native_enum=False),
        nullable=False,
        default=TaskStepStatus.PLANNED,
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    task: Mapped[Task] = relationship(back_populates="steps")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ToolCall.created_at",
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tool_calls_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    span_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ToolCallStatus] = mapped_column(
        Enum(ToolCallStatus, name="tool_call_status", native_enum=False),
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped[Task] = relationship(back_populates="tool_calls")
    step: Mapped[TaskStep] = relationship(back_populates="tool_calls")


class GraphStateSnapshot(Base):
    __tablename__ = "graph_state_snapshots"
    __table_args__ = (
        UniqueConstraint("task_id", "step_index", name="uq_graph_state_snapshots_task_step"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_node: Mapped[str | None] = mapped_column(String(100), nullable=True)
    graph_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped[Task] = relationship(back_populates="graph_state_snapshots")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    violation_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
