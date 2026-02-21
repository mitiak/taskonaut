from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload
from tenacity import Retrying, stop_after_attempt, wait_exponential

from taskrunner.models import Task, TaskStatus, TaskStep, TaskStepStatus, ToolCall, ToolCallStatus
from taskrunner.schemas import TaskCreateRequest
from taskrunner.tools import AddInput, EchoInput, add, echo

logger = logging.getLogger(__name__)

FLOW_STEPS: tuple[str, ...] = ("echo", "add")
TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})
TOOL_MAX_ATTEMPTS = 3
TOOL_WAIT_MULTIPLIER_SECONDS = 0.1
TOOL_WAIT_MIN_SECONDS = 0.1
TOOL_WAIT_MAX_SECONDS = 1.0


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
        try:
            self._acquire_task_lock(task_id)
            task = self._get_task_for_update(task_id)
            logger.info(
                "task.advance.started",
                extra={"task_id": str(task.id), "status": task.status.value},
            )

            if task.status in TERMINAL_TASK_STATUSES:
                logger.info(
                    "task.advance.terminal",
                    extra={"task_id": str(task.id), "status": task.status.value},
                )
                self.db.commit()
                return self.get_task(task.id)

            if task.status == TaskStatus.PLANNED:
                task.status = TaskStatus.RUNNING
                logger.info(
                    "task.advance.transition",
                    extra={"task_id": str(task.id), "to": task.status.value},
                )
                self.db.commit()
                return self.get_task(task.id)

            if task.status == TaskStatus.RUNNING:
                next_step = self._get_next_planned_step(task.id)
                if next_step is None:
                    task.status = TaskStatus.FAILED
                    logger.error("task.advance.no_step", extra={"task_id": str(task.id)})
                    self.db.commit()
                    return self.get_task(task.id)

                self._execute_step(task, next_step)
                logger.info(
                    "task.advance.executed",
                    extra={"task_id": str(task.id), "step": next_step.step_name},
                )
                self.db.commit()
                return self.get_task(task.id)

            if task.status == TaskStatus.WAITING_OBSERVATION:
                if self._get_next_planned_step(task.id) is None:
                    task.status = TaskStatus.COMPLETED
                    task.output_payload = self._build_output_payload(task.id)
                else:
                    task.status = TaskStatus.RUNNING
                logger.info(
                    "task.advance.transition",
                    extra={"task_id": str(task.id), "to": task.status.value},
                )
                self.db.commit()
                return self.get_task(task.id)

            previous_status = task.status.value
            task.status = TaskStatus.FAILED
            logger.error(
                "task.advance.invalid_state",
                extra={"task_id": str(task.id), "status": previous_status},
            )
            self.db.commit()
            return self.get_task(task.id)
        except Exception:
            self.db.rollback()
            raise

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

    def _get_task_for_update(self, task_id: UUID) -> Task:
        stmt = select(Task).where(Task.id == task_id).with_for_update()
        task = self.db.scalar(stmt)
        if task is None:
            logger.warning("task.not_found", extra={"task_id": str(task_id)})
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    def _acquire_task_lock(self, task_id: UUID) -> None:
        # Advisory lock key must fit signed bigint.
        lock_key = task_id.int % ((2**63) - 1)
        self.db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})

    def _build_tool_call_idempotency_key(self, task_id: UUID, step_id: UUID, tool_name: str) -> str:
        return f"{task_id}:{step_id}:{tool_name}"

    def _invoke_tool(self, tool_name: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "echo":
            return echo(EchoInput.model_validate(request_payload)).model_dump()
        if tool_name == "add":
            return add(AddInput.model_validate(request_payload)).model_dump()
        raise ValueError(f"Unknown step tool: {tool_name}")

    def _run_tool_with_retry(
        self,
        *,
        task_id: UUID,
        step_id: UUID,
        tool_name: str,
        request_payload: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None, int, datetime, datetime]:
        started_at = datetime.now(UTC)
        attempts = 0
        last_error: str | None = None
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(TOOL_MAX_ATTEMPTS),
                wait=wait_exponential(
                    multiplier=TOOL_WAIT_MULTIPLIER_SECONDS,
                    min=TOOL_WAIT_MIN_SECONDS,
                    max=TOOL_WAIT_MAX_SECONDS,
                ),
                reraise=True,
            ):
                with attempt:
                    attempts = attempt.retry_state.attempt_number
                    return (
                        self._invoke_tool(tool_name=tool_name, request_payload=request_payload),
                        None,
                        max(0, attempts - 1),
                        started_at,
                        datetime.now(UTC),
                    )
        except Exception as exc:
            attempts = max(1, attempts)
            last_error = str(exc)
            logger.warning(
                "tool.execute.failed",
                extra={
                    "task_id": str(task_id),
                    "step_id": str(step_id),
                    "tool_name": tool_name,
                    "attempts": attempts,
                    "error": last_error,
                },
            )
            return None, last_error, max(0, attempts - 1), started_at, datetime.now(UTC)
        raise RuntimeError("unreachable: retry loop exited without returning")

    def _execute_step(self, task: Task, step: TaskStep) -> None:
        step.status = TaskStepStatus.RUNNING

        tool_name = step.step_name
        request_payload = step.input_payload
        idempotency_key = self._build_tool_call_idempotency_key(task.id, step.id, tool_name)
        existing_call = self.db.scalar(
            select(ToolCall).where(ToolCall.idempotency_key == idempotency_key).limit(1)
        )
        if existing_call is not None:
            if existing_call.status == ToolCallStatus.COMPLETED:
                step.status = TaskStepStatus.COMPLETED
                step.output_payload = existing_call.response_payload
                step.error_message = None
                task.current_step = step.step_index
                task.status = TaskStatus.WAITING_OBSERVATION
            else:
                existing_error = (
                    existing_call.last_error or existing_call.error_message or "Tool call failed"
                )
                step.status = TaskStepStatus.FAILED
                step.error_message = existing_error
                task.status = TaskStatus.FAILED
                task.current_step = step.step_index
            logger.info(
                "tool.execute.idempotent_reuse",
                extra={
                    "task_id": str(task.id),
                    "step_id": str(step.id),
                    "tool_name": tool_name,
                    "idempotency_key": idempotency_key,
                },
            )
            return

        result, last_error, retry_count, started_at, finished_at = self._run_tool_with_retry(
            task_id=task.id,
            step_id=step.id,
            tool_name=tool_name,
            request_payload=request_payload,
        )
        if result is None:
            step.status = TaskStepStatus.FAILED
            step.error_message = last_error
            task.status = TaskStatus.FAILED
            task.current_step = step.step_index
            self.db.add(
                ToolCall(
                    task_id=task.id,
                    task_step_id=step.id,
                    idempotency_key=idempotency_key,
                    tool_name=tool_name,
                    status=ToolCallStatus.FAILED,
                    retry_count=retry_count,
                    last_error=last_error,
                    started_at=started_at,
                    finished_at=finished_at,
                    request_payload=request_payload,
                    response_payload=None,
                    error_message=last_error,
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
                idempotency_key=idempotency_key,
                tool_name=tool_name,
                status=ToolCallStatus.COMPLETED,
                retry_count=retry_count,
                last_error=None,
                started_at=started_at,
                finished_at=finished_at,
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
