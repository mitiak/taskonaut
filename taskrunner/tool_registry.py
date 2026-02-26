from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from taskrunner.policy import PolicyViolationError
from taskrunner.tools import (
    SocAgentInput,
    SocAgentOutput,
    incident_reporter_call,
    log_summarizer_call,
    threat_classifier_call,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    executor: Callable[[Any], Any]


_TOOL_REGISTRY: dict[str, ToolSpec] = {
    "log_summarizer": ToolSpec(
        name="log_summarizer",
        input_model=SocAgentInput,
        output_model=SocAgentOutput,
        executor=log_summarizer_call,
    ),
    "threat_classifier": ToolSpec(
        name="threat_classifier",
        input_model=SocAgentInput,
        output_model=SocAgentOutput,
        executor=threat_classifier_call,
    ),
    "incident_reporter": ToolSpec(
        name="incident_reporter",
        input_model=SocAgentInput,
        output_model=SocAgentOutput,
        executor=incident_reporter_call,
    ),
}


def list_allowlisted_tools() -> tuple[str, ...]:
    return tuple(sorted(_TOOL_REGISTRY.keys()))


def get_tool_spec(tool_name: str) -> ToolSpec:
    try:
        return _TOOL_REGISTRY[tool_name]
    except KeyError as exc:
        allowlist = ", ".join(list_allowlisted_tools())
        raise PolicyViolationError(
            code="UNKNOWN_TOOL",
            message=f"Tool '{tool_name}' is not allowlisted. Allowed tools: {allowlist}",
        ) from exc


def validate_tool_input(tool_name: str, payload: dict[str, Any]) -> BaseModel:
    spec = get_tool_spec(tool_name)
    try:
        return spec.input_model.model_validate(payload)
    except ValidationError as exc:
        raise PolicyViolationError(
            code="INVALID_TOOL_INPUT",
            message=f"Tool '{tool_name}' input validation failed: {exc.errors()}",
        ) from exc


def validate_tool_output(tool_name: str, payload: Any) -> BaseModel:
    spec = get_tool_spec(tool_name)
    candidate = payload.model_dump() if isinstance(payload, BaseModel) else payload
    try:
        return spec.output_model.model_validate(candidate, strict=True)
    except ValidationError as exc:
        raise PolicyViolationError(
            code="INVALID_TOOL_OUTPUT",
            message=f"Tool '{tool_name}' output validation failed: {exc.errors()}",
        ) from exc


def execute_tool(tool_name: str, payload: dict[str, Any], timeout_secs: float) -> dict[str, Any]:
    spec = get_tool_spec(tool_name)
    validated_input = validate_tool_input(tool_name, payload)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(spec.executor, validated_input)
        try:
            output = future.result(timeout=timeout_secs)
        except FutureTimeoutError as exc:
            future.cancel()
            raise PolicyViolationError(
                code="TOOL_TIMEOUT",
                message=f"Tool '{tool_name}' exceeded timeout of {timeout_secs:.2f}s",
            ) from exc
    validated_output = validate_tool_output(tool_name, output)
    return validated_output.model_dump()
