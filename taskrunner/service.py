from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from taskrunner.models import Task, TaskStatus, TaskStep, TaskStepStatus, ToolCall, ToolCallStatus
from taskrunner.schemas import TaskCreateRequest
from taskrunner.tools import AddInput, EchoInput, add, echo

logger = logging.getLogger(__name__)

FLOW_STEPS: tuple[str, ...] = ("echo", "add")
TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})


class TaskNotFoundError(Exception):
    pass


class MaxStepsExceededError(Exception):
    pass


class TaskRunnerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, request: TaskCreateRequest) -> Task:
        logger.info(
            "task.create.started",
            extra={"text": request.text, "a": request.a, "b": request.b},
        )
        task = Task(
            status=TaskStatus.PLANNED,
            current_step=0,
            input_payload=request.model_dump(),
            output_payload=None,
        )
        self.db.add(task)
        self.db.flush()

        steps = [
            TaskStep(
                task_id=task.id,
                step_index=1,
                step_name="echo",
                status=TaskStepStatus.PLANNED,
                input_payload={"text": request.text},
            ),
            TaskStep(
                task_id=task.id,
                step_index=2,
                step_name="add",
                status=TaskStepStatus.PLANNED,
                input_payload={"a": request.a, "b": request.b},
            ),
        ]
        self.db.add_all(steps)
        self.db.commit()
        logger.info("task.create.succeeded", extra={"task_id": str(task.id)})
        return self.get_task(task.id)

    def advance_task(self, task_id: UUID) -> Task:
        task = self.get_task(task_id)
        logger.info(
            "task.advance.started",
            extra={"task_id": str(task.id), "status": task.status.value},
        )

        if task.status in TERMINAL_TASK_STATUSES:
            logger.info(
                "task.advance.terminal",
                extra={"task_id": str(task.id), "status": task.status.value},
            )
            return task

        if task.status == TaskStatus.PLANNED:
            task.status = TaskStatus.RUNNING
            self.db.commit()
            logger.info(
                "task.advance.transition",
                extra={"task_id": str(task.id), "to": task.status.value},
            )
            return self.get_task(task.id)

        if task.status == TaskStatus.RUNNING:
            next_step = self._get_next_planned_step(task.id)
            if next_step is None:
                task.status = TaskStatus.FAILED
                self.db.commit()
                logger.error("task.advance.no_step", extra={"task_id": str(task.id)})
                return self.get_task(task.id)

            self._execute_step(task, next_step)
            self.db.commit()
            logger.info(
                "task.advance.executed",
                extra={"task_id": str(task.id), "step": next_step.step_name},
            )
            return self.get_task(task.id)

        if task.status == TaskStatus.WAITING_OBSERVATION:
            if self._get_next_planned_step(task.id) is None:
                task.status = TaskStatus.COMPLETED
                task.output_payload = self._build_output_payload(task.id)
            else:
                task.status = TaskStatus.RUNNING
            self.db.commit()
            logger.info(
                "task.advance.transition",
                extra={"task_id": str(task.id), "to": task.status.value},
            )
            return self.get_task(task.id)

        task.status = TaskStatus.FAILED
        self.db.commit()
        logger.error(
            "task.advance.invalid_state",
            extra={"task_id": str(task.id), "status": task.status.value},
        )
        return self.get_task(task.id)

    def run_task(self, task_id: UUID, max_steps: int) -> Task:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")

        task = self.get_task(task_id)
        for _ in range(max_steps):
            if task.status in TERMINAL_TASK_STATUSES:
                return task
            task = self.advance_task(task_id)

        if task.status in TERMINAL_TASK_STATUSES:
            return task
        raise MaxStepsExceededError(
            f"Task {task_id} did not reach terminal state within {max_steps} steps"
        )

    def get_task(self, task_id: UUID) -> Task:
        stmt = (
            select(Task)
            .options(
                selectinload(Task.steps).selectinload(TaskStep.tool_calls),
                selectinload(Task.tool_calls),
            )
            .where(Task.id == task_id)
        )
        task = self.db.scalar(stmt)
        if task is None:
            logger.warning("task.not_found", extra={"task_id": str(task_id)})
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    def list_tasks(self) -> list[Task]:
        stmt = (
            select(Task)
            .options(
                selectinload(Task.steps).selectinload(TaskStep.tool_calls),
                selectinload(Task.tool_calls),
            )
            .order_by(Task.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def _get_next_planned_step(self, task_id: UUID) -> TaskStep | None:
        stmt = (
            select(TaskStep)
            .where(
                TaskStep.task_id == task_id,
                TaskStep.status == TaskStepStatus.PLANNED,
            )
            .order_by(TaskStep.step_index.asc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def _execute_step(self, task: Task, step: TaskStep) -> None:
        step.status = TaskStepStatus.RUNNING

        tool_name = step.step_name
        request_payload = step.input_payload
        try:
            if tool_name == "echo":
                result = echo(EchoInput.model_validate(request_payload)).model_dump()
            elif tool_name == "add":
                result = add(AddInput.model_validate(request_payload)).model_dump()
            else:
                raise ValueError(f"Unknown step tool: {tool_name}")
        except Exception as exc:
            step.status = TaskStepStatus.FAILED
            step.error_message = str(exc)
            task.status = TaskStatus.FAILED
            task.current_step = step.step_index
            self.db.add(
                ToolCall(
                    task_id=task.id,
                    task_step_id=step.id,
                    tool_name=tool_name,
                    status=ToolCallStatus.FAILED,
                    request_payload=request_payload,
                    response_payload=None,
                    error_message=str(exc),
                )
            )
            return

        step.status = TaskStepStatus.COMPLETED
        step.output_payload = result
        step.error_message = None
        task.current_step = step.step_index
        task.status = TaskStatus.WAITING_OBSERVATION
        self.db.add(
            ToolCall(
                task_id=task.id,
                task_step_id=step.id,
                tool_name=tool_name,
                status=ToolCallStatus.COMPLETED,
                request_payload=request_payload,
                response_payload=result,
                error_message=None,
            )
        )

    def _build_output_payload(self, task_id: UUID) -> dict[str, object]:
        stmt = (
            select(TaskStep)
            .where(
                TaskStep.task_id == task_id,
                TaskStep.status == TaskStepStatus.COMPLETED,
            )
            .order_by(TaskStep.step_index.asc())
        )
        steps = self.db.scalars(stmt).all()
        return {
            step.step_name: step.output_payload
            for step in steps
            if step.output_payload is not None
        }
