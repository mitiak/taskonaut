from __future__ import annotations

import json
import logging

from taskrunner.log_config import JsonFormatter


def test_json_formatter_includes_core_and_extra_fields() -> None:
    record = logging.makeLogRecord(
        {
            "name": "taskrunner.test",
            "levelname": "INFO",
            "levelno": logging.INFO,
            "msg": "event happened",
            "args": (),
            "task_id": "abc-123",
            "step": "echo",
        }
    )

    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "taskrunner.test"
    assert payload["message"] == "event happened"
    assert payload["task_id"] == "abc-123"
    assert payload["step"] == "echo"
    assert isinstance(payload["timestamp"], str)
