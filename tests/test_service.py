from taskrunner.service import TaskRunnerService


def test_step_record_is_deterministic_shape() -> None:
    payload = TaskRunnerService._step_record(
        step="echo",
        status="succeeded",
        tool_input={"text": "hello"},
        tool_output={"text": "hello"},
    )

    assert payload["step"] == "echo"
    assert payload["status"] == "succeeded"
    assert payload["input"] == {"text": "hello"}
    assert payload["output"] == {"text": "hello"}
    assert isinstance(payload["timestamp"], str)
