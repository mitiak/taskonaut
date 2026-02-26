from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, cast

from logster.config import load_config  # type: ignore[import-untyped]
from logster.format import format_record  # type: ignore[import-untyped]

_BASE_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


class _HealthFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /health" not in record.getMessage()


def _json_default(value: Any) -> str:
    return str(value)


def _payload_from_record(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "file": record.filename,
        "function": record.funcName,
        "line": record.lineno,
        "message": record.getMessage(),
    }
    if record.exc_info:
        payload["exception"] = logging.Formatter().formatException(record.exc_info)

    for key, value in record.__dict__.items():
        if key in _BASE_LOG_RECORD_FIELDS or key.startswith("_"):
            continue
        payload[key] = value
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_payload_from_record(record), default=_json_default)


class LogsterFormatter(logging.Formatter):
    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self.config = load_config(config_path=config_path)

    def format(self, record: logging.LogRecord) -> str:
        payload = _payload_from_record(record)
        rendered = format_record(
            payload,
            use_color=not self.config.no_color,
            output_style=self.config.output_style,
            time_color=self.config.time_color,
            level_color=self.config.level_color,
            file_color=self.config.file_color,
            origin_color=self.config.origin_color,
            metadata_color=self.config.metadata_color,
            message_color=self.config.message_color,
            verbose_metadata_key_color=self.config.verbose_metadata_key_color,
            verbose_metadata_value_color=self.config.verbose_metadata_value_color,
            verbose_metadata_punctuation_color=self.config.verbose_metadata_punctuation_color,
            fields=self.config.fields,
        )
        return cast(str, rendered)


def configure_logging(
    level: str | None = None,
    *,
    log_style: str | None = None,
    logster_config_path: str | None = None,
) -> None:
    logger = logging.getLogger("taskrunner")
    configured_style = log_style or os.getenv("LOG_STYLE", "json") or "json"
    style = configured_style.lower()
    existing_styles = [
        getattr(handler, "_taskrunner_logging_style", None)
        for handler in logger.handlers
        if getattr(handler, "_taskrunner_logging_style", None) is not None
    ]

    # If logging is already configured and no explicit style was requested,
    # keep the existing style instead of resetting to default json.
    if log_style is None and existing_styles:
        return

    if any(
        getattr(handler, "_taskrunner_logging_style", None) == style for handler in logger.handlers
    ):
        return

    for handler in list(logger.handlers):
        if getattr(handler, "_taskrunner_logging_style", None) is not None:
            logger.removeHandler(handler)

    handler = logging.StreamHandler()
    if style == "logster":
        handler.setFormatter(LogsterFormatter(config_path=logster_config_path))
    else:
        handler.setFormatter(JsonFormatter())
        style = "json"
    handler._taskrunner_logging_style = style  # type: ignore[attr-defined]

    logger.addHandler(handler)
    level_name: str = cast(str, level or os.getenv("LOG_LEVEL", "INFO") or "INFO")
    logger.setLevel(level_name)
    logger.propagate = False
    logging.getLogger("uvicorn.access").addFilter(_HealthFilter())
