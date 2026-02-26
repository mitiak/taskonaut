from __future__ import annotations

import logging
from datetime import UTC, datetime
from json import dumps
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload
from tenacity import Retrying, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from taskrunner.flows import (
    build_initial_graph_state,
    build_step_input_payload,
    execute_graph_node,
    get_flow_definition,
)
from taskrunner.models import (
    AuditLog,
    GraphStateSnapshot,
    Task,
    TaskStatus,
    TaskStep,
    TaskStepStatus,
    ToolCall,
    ToolCallStatus,
)
from taskrunner.policy import PolicyViolationError, get_policy_limits
from taskrunner.schemas import TaskCreateRequest
from taskrunner.tool_registry import get_tool_spec, validate_tool_input
from taskrunner.tracing import format_span_id, format_trace_id, get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})
TOOL_MAX_ATTEMPTS = 3
TOOL_WAIT_MULTIPLIER_SECONDS = 0.1
TOOL_WAIT_MIN_SECONDS = 0.1
TOOL_WAIT_MAX_SECONDS = 1.0


class TaskNotFoundError(Exception):
    pass


class MaxStepsExceededError(Exception):
    pass


class InvalidFlowError(Exception):
    pass


class TaskRunnerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _audit_policy_violation(
        self,
        *,
        code: str,
        message: str,
        task_id: UUID | None = None,
        step_id: UUID | None = None,
        tool_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                task_id=task_id,
                task_step_id=step_id,
                tool_name=tool_name,
                violation_code=code,
                message=message,
                payload=payload or {},
            )
        )

    def validate_request_payload(
        self,
        *,
        flow_name: str,
        raw_input: str,
    ) -> TaskCreateRequest:
        limits = get_policy_limits()
        input_bytes = len(raw_input.encode("utf-8"))
        if input_bytes > limits.max_input_bytes:
            message = (
                "Input payload is "
                f"{input_bytes} bytes, exceeds max_input_bytes={limits.max_input_bytes}"
            )
            self._audit_policy_violation(
                code="MAX_INPUT_BYTES_EXCEEDED",
                message=message,
                payload={"input_bytes": input_bytes, "max_input_bytes": limits.max_input_bytes},
            )
            self.db.commit()
            raise PolicyViolationError("MAX_INPUT_BYTES_EXCEEDED", message)

        try:
            request = TaskCreateRequest.model_validate_json(raw_input, strict=True)
        except Exception as exc:
            message = f"Task input schema validation failed: {exc}"
            self._audit_policy_violation(
                code="INVALID_TASK_INPUT_SCHEMA",
                message=message,
                payload={"flow_name": flow_name},
            )
            self.db.commit()
            raise PolicyViolationError("INVALID_TASK_INPUT_SCHEMA", message) from exc

        if request.flow_name != flow_name:
            request = request.model_copy(update={"flow_name": flow_name})

        self._validate_tool_plan(request=request, raw_input_bytes=input_bytes)
        return request

    def _validate_tool_plan(self, *, request: TaskCreateRequest, raw_input_bytes: int) -> None:
        try:
            flow = get_flow_definition(request.flow_name)
        except ValueError as exc:
            message = str(exc)
            self._audit_policy_violation(
                code="INVALID_FLOW",
                message=message,
                payload={"flow_name": request.flow_name},
            )
            self.db.commit()
            raise PolicyViolationError("INVALID_FLOW", message) from exc

        limits = get_policy_limits()
        if raw_input_bytes > limits.max_input_bytes:
            message = (
                "Input payload is "
                f"{raw_input_bytes} bytes, exceeds max_input_bytes={limits.max_input_bytes}"
            )
            self._audit_policy_violation(
                code="MAX_INPUT_BYTES_EXCEEDED",
                message=message,
                payload={"input_bytes": raw_input_bytes, "max_input_bytes": limits.max_input_bytes},
            )
            self.db.commit()
            raise PolicyViolationError("MAX_INPUT_BYTES_EXCEEDED", message)

        for node_name in flow.node_sequence:
            try:
                step_payload = build_step_input_payload(request=request, node_name=node_name)
            except ValueError as exc:
                message = str(exc)
                self._audit_policy_violation(
                    code="UNKNOWN_TOOL",
                    message=message,
                    tool_name=node_name,
                    payload={"flow_name": request.flow_name},
                )
                self.db.commit()
                raise PolicyViolationError("UNKNOWN_TOOL", message) from exc
            try:
                get_tool_spec(node_name)
                validate_tool_input(node_name, step_payload)
            except PolicyViolationError as exc:
                self._audit_policy_violation(
                    code=exc.code,
                    message=exc.message,
                    tool_name=node_name,
                    payload={"flow_name": request.flow_name, "step_payload": step_payload},
                )
                self.db.commit()
                raise

    def create_task(self, request: TaskCreateRequest) -> Task:
        with tracer.start_as_current_span("task.create") as span:
            request_json = dumps(request.model_dump(), separators=(",", ":"))
            raw_input_bytes = len(request_json.encode("utf-8"))
            self._validate_tool_plan(request=request, raw_input_bytes=raw_input_bytes)
            flow = get_flow_definition(request.flow_name)

            initial_graph_state = dict(build_initial_graph_state(request))
            first_node = flow.first_node()
            trace_id = format_trace_id(span.get_span_context().trace_id) or str(uuid4())
            logger.info(
                "task.create.started",
                extra={
                    "flow_name": flow.name,
                    "trace_id": trace_id,
                    "session_id": request.session_id,
                    "actor_id": request.actor_id,
                },
            )
            task = Task(
                trace_id=trace_id,
                status=TaskStatus.PLANNED,
                flow_name=flow.name,
                current_step=0,
                current_node=first_node,
                next_node=first_node,
                graph_state_summary=self._build_graph_state_summary(
                    flow_name=flow.name,
                    current_node=first_node,
                    next_node=first_node,
                    graph_state=initial_graph_state,
                ),
                input_payload=request.model_dump(),
                output_payload=None,
            )
            self.db.add(task)
            self.db.flush()

            steps = [
                TaskStep(
                    task_id=task.id,
                    step_index=index,
                    step_name=node_name,
                    span_id=str(uuid4()),
                    status=TaskStepStatus.PLANNED,
                    input_payload=build_step_input_payload(request=request, node_name=node_name),
                )
                for index, node_name in enumerate(flow.node_sequence, start=1)
            ]
            self.db.add_all(steps)
            self._upsert_graph_snapshot(
                task_id=task.id,
                step_index=0,
                current_node=task.current_node,
                next_node=task.next_node,
                graph_state=initial_graph_state,
            )
            self.db.commit()
            logger.info(
                "task.create.succeeded",
                extra={"task_id": str(task.id), "trace_id": task.trace_id},
            )
            return self.get_task(task.id)

    def advance_task(self, task_id: UUID) -> Task:
        try:
            self._acquire_task_lock(task_id)
            task = self._get_task_for_update(task_id)
            with tracer.start_as_current_span(
                "task.advance",
                attributes={
                    "task.id": str(task.id),
                    "task.trace_id": task.trace_id,
                    "task.status": task.status.value,
                },
            ):
                logger.info(
                    "task.advance.started",
                    extra={
                        "task_id": str(task.id),
                        "status": task.status.value,
                        "trace_id": task.trace_id,
                    },
                )

                if task.status in TERMINAL_TASK_STATUSES:
                    logger.info(
                        "task.advance.terminal",
                        extra={
                            "task_id": str(task.id),
                            "status": task.status.value,
                            "trace_id": task.trace_id,
                        },
                    )
                    self.db.commit()
                    return self.get_task(task.id)

                if task.status == TaskStatus.PLANNED:
                    task.status = TaskStatus.RUNNING
                    task.current_node = task.next_node
                    task.graph_state_summary = self._build_graph_state_summary(
                        flow_name=task.flow_name,
                        current_node=task.current_node,
                        next_node=task.next_node,
                        graph_state=self._get_latest_graph_state(task.id),
                    )
                    logger.info(
                        "task.advance.transition",
                        extra={
                            "task_id": str(task.id),
                            "to": task.status.value,
                            "trace_id": task.trace_id,
                        },
                    )
                    self.db.commit()
                    return self.get_task(task.id)

                if task.status == TaskStatus.RUNNING:
                    next_step = self._get_next_planned_step(task.id)
                    if next_step is None:
                        task.status = TaskStatus.FAILED
                        task.next_node = None
                        task.graph_state_summary = self._build_graph_state_summary(
                            flow_name=task.flow_name,
                            current_node=task.current_node,
                            next_node=task.next_node,
                            graph_state=self._get_latest_graph_state(task.id),
                        )
                        logger.error(
                            "task.advance.no_step",
                            extra={"task_id": str(task.id), "trace_id": task.trace_id},
                        )
                        self.db.commit()
                        return self.get_task(task.id)

                    self._execute_step(task, next_step)
                    logger.info(
                        "task.advance.executed",
                        extra={
                            "task_id": str(task.id),
                            "step": next_step.step_name,
                            "trace_id": task.trace_id,
                        },
                    )
                    self.db.commit()
                    return self.get_task(task.id)

                if task.status == TaskStatus.WAITING_OBSERVATION:
                    if self._get_next_planned_step(task.id) is None:
                        task.status = TaskStatus.COMPLETED
                        task.next_node = None
                        task.output_payload = self._build_output_payload(task.id)
                    else:
                        task.status = TaskStatus.RUNNING
                        task.current_node = task.next_node
                    task.graph_state_summary = self._build_graph_state_summary(
                        flow_name=task.flow_name,
                        current_node=task.current_node,
                        next_node=task.next_node,
                        graph_state=self._get_latest_graph_state(task.id),
                    )
                    logger.info(
                        "task.advance.transition",
                        extra={
                            "task_id": str(task.id),
                            "to": task.status.value,
                            "trace_id": task.trace_id,
                        },
                    )
                    self.db.commit()
                    return self.get_task(task.id)

                previous_status = task.status.value
                task.status = TaskStatus.FAILED
                task.next_node = None
                task.graph_state_summary = self._build_graph_state_summary(
                    flow_name=task.flow_name,
                    current_node=task.current_node,
                    next_node=task.next_node,
                    graph_state=self._get_latest_graph_state(task.id),
                )
                logger.error(
                    "task.advance.invalid_state",
                    extra={
                        "task_id": str(task.id),
                        "status": previous_status,
                        "trace_id": task.trace_id,
                    },
                )
                self.db.commit()
                return self.get_task(task.id)
        except Exception:
            self.db.rollback()
            raise

    def run_task(self, task_id: UUID, max_steps: int) -> Task:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        limits = get_policy_limits()
        if max_steps > limits.max_steps:
            message = f"max_steps={max_steps} exceeds policy max_steps={limits.max_steps}"
            self._audit_policy_violation(
                code="MAX_STEPS_EXCEEDED",
                message=message,
                task_id=task_id,
                payload={"max_steps": max_steps, "policy_max_steps": limits.max_steps},
            )
            self.db.commit()
            raise PolicyViolationError("MAX_STEPS_EXCEEDED", message)

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

    def _run_tool_with_retry(
        self,
        *,
        task_id: UUID,
        step_id: UUID,
        flow_name: str,
        node_name: str,
        graph_state: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, int, datetime, datetime]:
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
                retry=retry_if_not_exception_type(PolicyViolationError),
                reraise=True,
            ):
                with attempt:
                    attempts = attempt.retry_state.attempt_number
                    output_payload, updated_graph_state = execute_graph_node(
                        flow_name=flow_name,
                        node_name=node_name,
                        graph_state=graph_state,
                    )
                    return (
                        output_payload,
                        updated_graph_state,
                        None,
                        max(0, attempts - 1),
                        started_at,
                        datetime.now(UTC),
                    )
        except PolicyViolationError:
            raise
        except Exception as exc:
            attempts = max(1, attempts)
            last_error = str(exc)
            logger.warning(
                "tool.execute.failed",
                extra={
                    "task_id": str(task_id),
                    "step_id": str(step_id),
                    "tool_name": node_name,
                    "attempts": attempts,
                    "error": last_error,
                },
            )
            return None, None, last_error, max(0, attempts - 1), started_at, datetime.now(UTC)
        raise RuntimeError("unreachable: retry loop exited without returning")

    def _fail_step_with_policy_violation(
        self,
        *,
        task: Task,
        step: TaskStep,
        tool_name: str,
        code: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        step.status = TaskStepStatus.FAILED
        step.error_message = message
        task.status = TaskStatus.FAILED
        task.current_step = step.step_index
        task.current_node = step.step_name
        task.next_node = None
        task.graph_state_summary = self._build_graph_state_summary(
            flow_name=task.flow_name,
            current_node=task.current_node,
            next_node=task.next_node,
            graph_state=self._get_latest_graph_state(task.id),
        )
        self._audit_policy_violation(
            code=code,
            message=message,
            task_id=task.id,
            step_id=step.id,
            tool_name=tool_name,
            payload=payload,
        )
        logger.error(
            "policy.violation",
            extra={
                "task_id": str(task.id),
                "trace_id": task.trace_id,
                "step_id": str(step.id),
                "span_id": step.span_id,
                "tool_name": tool_name,
                "violation_code": code,
                "error": message,
            },
        )

    def _execute_step(self, task: Task, step: TaskStep) -> None:
        with tracer.start_as_current_span(
            "task.step.execute",
            attributes={
                "task.id": str(task.id),
                "task.trace_id": task.trace_id,
                "step.id": str(step.id),
                "step.name": step.step_name,
                "step.index": step.step_index,
            },
        ) as step_span:
            step.status = TaskStepStatus.RUNNING
            step.span_id = format_span_id(step_span.get_span_context().span_id) or step.span_id

            tool_name = step.step_name
            request_payload = step.input_payload
            try:
                get_tool_spec(tool_name)
                validate_tool_input(tool_name, request_payload)
            except PolicyViolationError as exc:
                self._fail_step_with_policy_violation(
                    task=task,
                    step=step,
                    tool_name=tool_name,
                    code=exc.code,
                    message=exc.message,
                    payload={"step_input": request_payload},
                )
                return

            flow = get_flow_definition(task.flow_name)
            idempotency_key = self._build_tool_call_idempotency_key(task.id, step.id, tool_name)
            existing_call = self.db.scalar(
                select(ToolCall).where(ToolCall.idempotency_key == idempotency_key).limit(1)
            )
            if existing_call is not None:
                existing_snapshot = self.db.scalar(
                    select(GraphStateSnapshot)
                    .where(
                        GraphStateSnapshot.task_id == task.id,
                        GraphStateSnapshot.step_index == step.step_index,
                    )
                    .limit(1)
                )
                if existing_call.status == ToolCallStatus.COMPLETED:
                    step.status = TaskStepStatus.COMPLETED
                    step.output_payload = existing_call.response_payload
                    step.error_message = None
                    task.current_step = step.step_index
                    task.status = TaskStatus.WAITING_OBSERVATION
                    task.current_node = step.step_name
                    task.next_node = flow.next_node(step.step_name)
                    summary_graph_state = (
                        existing_snapshot.graph_state
                        if existing_snapshot is not None
                        else self._get_latest_graph_state(task.id)
                    )
                    task.graph_state_summary = self._build_graph_state_summary(
                        flow_name=task.flow_name,
                        current_node=task.current_node,
                        next_node=task.next_node,
                        graph_state=summary_graph_state,
                    )
                else:
                    existing_error = existing_call.last_error or existing_call.error_message
                    if existing_error is None:
                        existing_error = "Tool call failed"
                    step.status = TaskStepStatus.FAILED
                    step.error_message = existing_error
                    task.status = TaskStatus.FAILED
                    task.current_step = step.step_index
                    task.current_node = step.step_name
                    task.next_node = None
                    task.graph_state_summary = self._build_graph_state_summary(
                        flow_name=task.flow_name,
                        current_node=task.current_node,
                        next_node=task.next_node,
                        graph_state=self._get_latest_graph_state(task.id),
                    )
                logger.info(
                    "tool.execute.idempotent_reuse",
                    extra={
                        "task_id": str(task.id),
                        "trace_id": task.trace_id,
                        "step_id": str(step.id),
                        "tool_name": tool_name,
                        "idempotency_key": idempotency_key,
                        "span_id": existing_call.span_id,
                        "tool_call_id": str(existing_call.id),
                    },
                )
                logger.info(
                    "tool_call.reused",
                    extra={
                        "task_id": str(task.id),
                        "trace_id": task.trace_id,
                        "step_id": str(step.id),
                        "span_id": existing_call.span_id,
                        "tool_call_id": str(existing_call.id),
                        "tool_name": tool_name,
                        "status": existing_call.status.value,
                    },
                )
                return

            latest_graph_state = self._get_latest_graph_state(task_id=task.id)
            try:
                result, updated_graph_state, last_error, retry_count, started_at, finished_at = (
                    self._run_tool_with_retry(
                        task_id=task.id,
                        step_id=step.id,
                        flow_name=task.flow_name,
                        node_name=tool_name,
                        graph_state=latest_graph_state,
                    )
                )
            except PolicyViolationError as exc:
                self._fail_step_with_policy_violation(
                    task=task,
                    step=step,
                    tool_name=step.step_name,
                    code=exc.code,
                    message=exc.message,
                    payload={"step_input": step.input_payload},
                )
                return

            if result is None:
                step.status = TaskStepStatus.FAILED
                step.error_message = last_error
                task.status = TaskStatus.FAILED
                task.current_step = step.step_index
                task.current_node = step.step_name
                task.next_node = None
                task.graph_state_summary = self._build_graph_state_summary(
                    flow_name=task.flow_name,
                    current_node=task.current_node,
                    next_node=task.next_node,
                    graph_state=latest_graph_state,
                )
                failed_tool_call = ToolCall(
                    id=uuid4(),
                    task_id=task.id,
                    task_step_id=step.id,
                    span_id=step.span_id,
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
                self.db.add(failed_tool_call)
                logger.error(
                    "tool_call.failed",
                    extra={
                        "task_id": str(task.id),
                        "trace_id": task.trace_id,
                        "step_id": str(step.id),
                        "span_id": failed_tool_call.span_id,
                        "tool_call_id": str(failed_tool_call.id),
                        "tool_name": tool_name,
                        "error": last_error,
                    },
                )
                return

            step.status = TaskStepStatus.COMPLETED
            step.output_payload = result
            step.error_message = None
            task.current_step = step.step_index
            task.current_node = step.step_name
            task.next_node = flow.next_node(step.step_name)
            task.status = TaskStatus.WAITING_OBSERVATION
            if updated_graph_state is None:
                updated_graph_state = latest_graph_state
            self._upsert_graph_snapshot(
                task_id=task.id,
                step_index=step.step_index,
                current_node=task.current_node,
                next_node=task.next_node,
                graph_state=updated_graph_state,
            )
            task.graph_state_summary = self._build_graph_state_summary(
                flow_name=task.flow_name,
                current_node=task.current_node,
                next_node=task.next_node,
                graph_state=updated_graph_state,
            )
            completed_tool_call = ToolCall(
                id=uuid4(),
                task_id=task.id,
                task_step_id=step.id,
                span_id=step.span_id,
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
            self.db.add(completed_tool_call)
            logger.info(
                "tool_call.completed",
                extra={
                    "task_id": str(task.id),
                    "trace_id": task.trace_id,
                    "step_id": str(step.id),
                    "span_id": completed_tool_call.span_id,
                    "tool_call_id": str(completed_tool_call.id),
                    "tool_name": tool_name,
                    "retry_count": retry_count,
                },
            )

    def _get_latest_graph_state(self, task_id: UUID) -> dict[str, Any]:
        stmt = (
            select(GraphStateSnapshot)
            .where(GraphStateSnapshot.task_id == task_id)
            .order_by(GraphStateSnapshot.step_index.desc())
            .limit(1)
        )
        snapshot = self.db.scalar(stmt)
        if snapshot is None:
            return {}
        return snapshot.graph_state

    def _upsert_graph_snapshot(
        self,
        *,
        task_id: UUID,
        step_index: int,
        current_node: str | None,
        next_node: str | None,
        graph_state: dict[str, Any],
    ) -> None:
        snapshot = self.db.scalar(
            select(GraphStateSnapshot)
            .where(
                GraphStateSnapshot.task_id == task_id,
                GraphStateSnapshot.step_index == step_index,
            )
            .limit(1)
        )
        if snapshot is None:
            self.db.add(
                GraphStateSnapshot(
                    task_id=task_id,
                    step_index=step_index,
                    current_node=current_node,
                    next_node=next_node,
                    graph_state=graph_state,
                )
            )
            return
        snapshot.current_node = current_node
        snapshot.next_node = next_node
        snapshot.graph_state = graph_state

    def _build_graph_state_summary(
        self,
        *,
        flow_name: str,
        current_node: str | None,
        next_node: str | None,
        graph_state: dict[str, Any],
    ) -> dict[str, Any]:
        flow = get_flow_definition(flow_name)
        state_field_by_node = {
            "summarize": "summarize_result",
            "classify": "classify_result",
            "report": "report_result",
        }
        completed_nodes = [
            node_name
            for node_name in flow.node_sequence
            if graph_state.get(state_field_by_node.get(node_name, node_name)) is not None
        ]
        return {
            "flow": flow_name,
            "total_nodes": len(flow.node_sequence),
            "completed_nodes": completed_nodes,
            "remaining_nodes": len(flow.node_sequence) - len(completed_nodes),
            "current_node": current_node,
            "next_node": next_node,
        }

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
