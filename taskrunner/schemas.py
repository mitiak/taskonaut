from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from taskrunner.models import TaskStatus


class TaskCreateRequest(BaseModel):
    text: str = Field(default="hello")
    a: int = Field(default=1)
    b: int = Field(default=2)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: TaskStatus
    flow_name: str
    current_step: int
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    step_history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
