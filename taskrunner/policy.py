from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyLimits:
    max_input_bytes: int
    max_steps: int
    tool_timeout_secs: float


class PolicyViolationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_policy_limits() -> PolicyLimits:
    return PolicyLimits(
        max_input_bytes=int(os.getenv("TASKRUNNER_MAX_INPUT_BYTES", "65536")),
        max_steps=int(os.getenv("TASKRUNNER_MAX_STEPS", "64")),
        tool_timeout_secs=float(os.getenv("TASKRUNNER_TOOL_TIMEOUT_SECS", "2.0")),
    )
