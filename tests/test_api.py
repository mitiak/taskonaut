from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from taskrunner.api import app
from taskrunner.db import get_db
from taskrunner.models import Task, TaskStatus
from taskrunner.service import TaskRunnerService


def test_list_tasks_returns_all_tasks(monkeypatch) -> None:
    now = datetime.now(UTC)
    first_task = Task(
        id=uuid4(),
        status=TaskStatus.succeeded,
        flow_name="predefined_echo_add",
        current_step=3,
        input_payload={"text": "hello", "a": 2, "b": 3},
        output_payload={"echo": {"text": "hello"}, "add": {"sum": 5}},
        step_history=[],
        created_at=now,
        updated_at=now,
    )
    second_task = Task(
        id=uuid4(),
        status=TaskStatus.failed,
        flow_name="predefined_echo_add",
        current_step=1,
        input_payload={"text": "oops", "a": 1, "b": 1},
        output_payload=None,
        step_history=[],
        created_at=now,
        updated_at=now,
    )

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
