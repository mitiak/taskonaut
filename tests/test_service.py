from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from taskrunner.models import TaskStatus
from taskrunner.service import MaxStepsExceededError, TaskRunnerService


def test_run_task_raises_after_max_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TaskRunnerService(db=object())  # type: ignore[arg-type]
    task_id = uuid4()
    running = SimpleNamespace(status=TaskStatus.RUNNING)

    monkeypatch.setattr(service, "get_task", lambda task_id_arg: running)
    monkeypatch.setattr(service, "advance_task", lambda task_id_arg: running)

    with pytest.raises(MaxStepsExceededError):
        service.run_task(task_id, max_steps=2)


def test_run_task_returns_when_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TaskRunnerService(db=object())  # type: ignore[arg-type]
    task_id = uuid4()
    running = SimpleNamespace(status=TaskStatus.RUNNING)
    completed = SimpleNamespace(status=TaskStatus.COMPLETED)
    state = {"count": 0}

    def fake_get_task(task_id_arg):
        return running

    def fake_advance_task(task_id_arg):
        state["count"] += 1
        return completed if state["count"] == 1 else running

    monkeypatch.setattr(service, "get_task", fake_get_task)
    monkeypatch.setattr(service, "advance_task", fake_advance_task)

    result = service.run_task(task_id, max_steps=2)
    assert result.status == TaskStatus.COMPLETED


def test_build_tool_call_idempotency_key_uses_task_step_and_tool() -> None:
    service = TaskRunnerService(db=object())  # type: ignore[arg-type]
    task_id = uuid4()
    step_id = uuid4()

    key = service._build_tool_call_idempotency_key(task_id, step_id, "log_summarizer")

    assert key == f"{task_id}:{step_id}:log_summarizer"


def test_run_tool_with_retry_returns_retry_count_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskRunnerService(db=object())  # type: ignore[arg-type]
    task_id = uuid4()
    step_id = uuid4()
    state = {"calls": 0}

    def fake_execute_graph_node(
        *,
        flow_name: str,
        node_name: str,
        graph_state: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        state["calls"] += 1
        if state["calls"] < 2:
            raise RuntimeError("temporary failure")
        return {"ok": True, "tool": node_name, "flow": flow_name}, {**graph_state, "ok": True}

    monkeypatch.setattr("taskrunner.service.execute_graph_node", fake_execute_graph_node)

    result, graph_state, last_error, retry_count, started_at, finished_at = (
        service._run_tool_with_retry(
            task_id=task_id,
            step_id=step_id,
            flow_name="soc_pipeline",
            node_name="summarize",
            graph_state={"raw_logs": ["log1"], "session_id": "s1"},
        )
    )

    assert result == {"ok": True, "tool": "summarize", "flow": "soc_pipeline"}
    assert graph_state == {"raw_logs": ["log1"], "session_id": "s1", "ok": True}
    assert last_error is None
    assert retry_count == 1
    assert isinstance(started_at, datetime)
    assert isinstance(finished_at, datetime)
