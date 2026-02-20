from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from taskrunner.api import app
from taskrunner.db import get_db
from taskrunner.models import Task, TaskStatus
from taskrunner.service import MaxStepsExceededError, TaskRunnerService


def _task(task_id: UUID, status: TaskStatus) -> Task:
    now = datetime.now(UTC)
    task = Task(
        id=task_id,
        status=status,
        flow_name="predefined_echo_add",
        current_step=0,
        input_payload={"text": "hello", "a": 2, "b": 3},
        output_payload=None,
        created_at=now,
        updated_at=now,
    )
    task.steps = []
    task.tool_calls = []
    return task


def test_create_task_returns_201(monkeypatch) -> None:
    task_id = uuid4()

    def fake_create_task(self: TaskRunnerService, request) -> Task:
        return _task(task_id, TaskStatus.PLANNED)

    monkeypatch.setattr(TaskRunnerService, "create_task", fake_create_task)
    app.dependency_overrides[get_db] = lambda: object()

    try:
        client = TestClient(app)
        response = client.post("/tasks", json={"text": "hello", "a": 2, "b": 3})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == str(task_id)
    assert response.json()["status"] == TaskStatus.PLANNED.value


def test_advance_task_returns_200(monkeypatch) -> None:
    task_id = uuid4()

    def fake_advance_task(self: TaskRunnerService, task_id_arg: UUID) -> Task:
        assert task_id_arg == task_id
        return _task(task_id, TaskStatus.RUNNING)

    monkeypatch.setattr(TaskRunnerService, "advance_task", fake_advance_task)
    app.dependency_overrides[get_db] = lambda: object()

    try:
        client = TestClient(app)
        response = client.post(f"/tasks/{task_id}/advance")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == TaskStatus.RUNNING.value


def test_run_task_max_steps_returns_409(monkeypatch) -> None:
    task_id = uuid4()

    def fake_run_task(self: TaskRunnerService, task_id_arg: UUID, max_steps: int) -> Task:
        assert task_id_arg == task_id
        assert max_steps == 2
        raise MaxStepsExceededError("too many steps")

    monkeypatch.setattr(TaskRunnerService, "run_task", fake_run_task)
    app.dependency_overrides[get_db] = lambda: object()

    try:
        client = TestClient(app)
        response = client.post(f"/tasks/{task_id}/run", json={"max_steps": 2})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "too many steps"


def test_list_tasks_returns_all_tasks(monkeypatch) -> None:
    first_task = _task(uuid4(), TaskStatus.COMPLETED)
    second_task = _task(uuid4(), TaskStatus.FAILED)

    def fake_list_tasks(self: TaskRunnerService) -> list[Task]:
        return [first_task, second_task]

    monkeypatch.setattr(TaskRunnerService, "list_tasks", fake_list_tasks)
    app.dependency_overrides[get_db] = lambda: object()

    try:
        client = TestClient(app)
        response = client.get("/tasks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["id"] == str(first_task.id)
    assert payload[1]["id"] == str(second_task.id)
