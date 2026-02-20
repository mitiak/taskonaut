from __future__ import annotations

import json
import logging

from taskrunner.log_config import JsonFormatter, LogsterFormatter


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


def test_logster_formatter_uses_toml_config(tmp_path) -> None:
    config_path = tmp_path / "logster.toml"
    config_path.write_text(
        'output_style = "compact"\n'
        "no_color = true\n"
        '[fields]\n'
        'message_fields = ["message"]\n'
        'main_line_fields = ["timestamp", "level", "logger", "message"]\n'
    )
    record = logging.makeLogRecord(
        {
            "name": "taskrunner.test",
            "levelname": "INFO",
            "levelno": logging.INFO,
            "msg": "event happened",
            "args": (),
        }
    )

    formatted = LogsterFormatter(config_path=str(config_path)).format(record)

    assert "[INFO]" in formatted
    assert "event happened" in formatted
    assert "\u001b[" not in formatted
