from __future__ import annotations

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
