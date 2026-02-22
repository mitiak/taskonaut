from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from taskrunner.flows import FlowDefinition
from taskrunner.policy import PolicyViolationError
from taskrunner.service import TaskRunnerService


class FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1


def test_invalid_schema_rejected_before_tool_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDB()
    service = TaskRunnerService(db=db)  # type: ignore[arg-type]

    def should_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("tool input validation should not run for invalid task schema")

    monkeypatch.setattr("taskrunner.service.validate_tool_input", should_not_run)

    with pytest.raises(PolicyViolationError) as exc_info:
        service.validate_request_payload(
            flow_name="demo",
            raw_input='{"text":123,"a":"x","b":3}',
        )

    assert exc_info.value.code == "INVALID_TASK_INPUT_SCHEMA"
    assert db.commits == 1
    assert db.added


def test_unknown_tool_rejected_and_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDB()
    service = TaskRunnerService(db=db)  # type: ignore[arg-type]

    unknown_flow = FlowDefinition(
        name="malicious",
        node_sequence=("evil_tool",),
        node_handlers={},
        graph=SimpleNamespace(),
    )
    monkeypatch.setattr("taskrunner.service.get_flow_definition", lambda _: unknown_flow)

    with pytest.raises(PolicyViolationError) as exc_info:
        service.validate_request_payload(
            flow_name="malicious",
            raw_input='{"text":"ok","a":2,"b":3}',
        )

    assert exc_info.value.code == "UNKNOWN_TOOL"
    assert db.commits == 1
    assert db.added


def test_max_input_bytes_limit_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDB()
    service = TaskRunnerService(db=db)  # type: ignore[arg-type]
    monkeypatch.setenv("TASKRUNNER_MAX_INPUT_BYTES", "16")

    with pytest.raises(PolicyViolationError) as exc_info:
        service.validate_request_payload(
            flow_name="demo",
            raw_input='{"text":"hello there","a":2,"b":3}',
        )

    assert exc_info.value.code == "MAX_INPUT_BYTES_EXCEEDED"
    assert db.commits == 1
    assert db.added


def test_run_task_respects_policy_max_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDB()
    service = TaskRunnerService(db=db)  # type: ignore[arg-type]
    monkeypatch.setenv("TASKRUNNER_MAX_STEPS", "1")

    with pytest.raises(PolicyViolationError) as exc_info:
        service.run_task(uuid4(), max_steps=2)

    assert exc_info.value.code == "MAX_STEPS_EXCEEDED"
    assert db.commits == 1
