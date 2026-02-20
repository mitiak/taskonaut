from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

_BASE_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


def _json_default(value: Any) -> str:
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _BASE_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, default=_json_default)


def configure_logging(level: str | None = None) -> None:
    logger = logging.getLogger("taskrunner")
    if any(getattr(handler, "_taskrunner_json_logging", False) for handler in logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._taskrunner_json_logging = True  # type: ignore[attr-defined]

    logger.addHandler(handler)
    logger.setLevel(level or os.getenv("LOG_LEVEL", "INFO"))
    logger.propagate = False
