from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from taskrunner.models import Task, TaskStatus
from taskrunner.schemas import TaskCreateRequest
from taskrunner.tools import AddInput, EchoInput, add, echo

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    pass


class TaskRunnerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run_predefined_flow(self, request: TaskCreateRequest) -> Task:
        logger.info(
            "task_flow.started",
            extra={"text": request.text, "a": request.a, "b": request.b},
        )
        task = Task(
            status=TaskStatus.pending,
            current_step=0,
            input_payload=request.model_dump(),
            step_history=[],
        )
        self.db.add(task)
        self.db.flush()
        logger.info("task_flow.created", extra={"task_id": str(task.id)})

        task.status = TaskStatus.running
        task.current_step = 1

        echo_output = echo(EchoInput(text=request.text)).model_dump()
        logger.info("task_flow.step_succeeded", extra={"task_id": str(task.id), "step": "echo"})
        task.step_history = [
            self._step_record(
                step="echo",
                status="succeeded",
                tool_input={"text": request.text},
                tool_output=echo_output,
            )
        ]

        task.current_step = 2
        add_output = add(AddInput(a=request.a, b=request.b)).model_dump()
        logger.info("task_flow.step_succeeded", extra={"task_id": str(task.id), "step": "add"})
        task.step_history = [
            *task.step_history,
            self._step_record(
                step="add",
                status="succeeded",
                tool_input={"a": request.a, "b": request.b},
                tool_output=add_output,
            ),
        ]

        task.current_step = 3
        task.status = TaskStatus.succeeded
        task.output_payload = {
            "echo": echo_output,
            "add": add_output,
        }
        self.db.commit()
        self.db.refresh(task)
        logger.info("task_flow.completed", extra={"task_id": str(task.id), "status": task.status.value})
        return task

    def get_task(self, task_id: UUID) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            logger.warning("task.not_found", extra={"task_id": str(task_id)})
            raise TaskNotFoundError(f"Task {task_id} not found")
        logger.info("task.found", extra={"task_id": str(task_id), "status": task.status.value})
        return task

    @staticmethod
    def _step_record(
        step: str,
        status: str,
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "step": step,
            "status": status,
            "input": tool_input,
            "output": tool_output,
            "timestamp": datetime.now(UTC).isoformat(),
        }
