from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from taskrunner.models import TaskStatus, TaskStepStatus, ToolCallStatus


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_name: str = Field(default="soc_pipeline")
    raw_logs: list[str] | None = Field(default=None)
    session_id: str | None = Field(default=None)
    actor_id: str | None = Field(default=None)
    actor_role: str | None = Field(default=None)


class RunTaskRequest(StrictBaseModel):
    max_steps: int = Field(default=12, ge=1, le=1000)


class ToolCallResponse(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    task_id: UUID
    task_step_id: UUID
    span_id: str
    idempotency_key: str
    tool_name: str
    status: ToolCallStatus
    retry_count: int
    last_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None
    error_message: str | None
    created_at: datetime


class TaskStepResponse(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    task_id: UUID
    step_index: int
    step_name: str
    span_id: str
    status: TaskStepStatus
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    tool_calls: list[ToolCallResponse]


class TaskResponse(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    trace_id: str
    status: TaskStatus
    flow_name: str
    current_step: int
    current_node: str | None
    next_node: str | None
    graph_state_summary: dict[str, Any]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    steps: list[TaskStepResponse]
    tool_calls: list[ToolCallResponse]
