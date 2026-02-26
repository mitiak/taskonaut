from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict

from taskrunner.config import get_cdrmind_url


class SocAgentInput(BaseModel):
    model_config = ConfigDict(strict=False)
    raw_logs: list[str]
    context: dict
    session_id: str


class SocAgentOutput(BaseModel):
    model_config = ConfigDict(strict=False)
    result: dict
    reasoning_step: str


def _call_cdrmind(path: str, payload: SocAgentInput) -> SocAgentOutput:
    url = f"{get_cdrmind_url()}{path}"
    response = httpx.post(url, json=payload.model_dump(), timeout=120.0)
    response.raise_for_status()
    data = response.json()
    return SocAgentOutput(result=data.get("result", data), reasoning_step=data.get("reasoning_step", path))


def log_summarizer_call(payload: SocAgentInput) -> SocAgentOutput:
    return _call_cdrmind("/agents/summarize", payload)


def threat_classifier_call(payload: SocAgentInput) -> SocAgentOutput:
    return _call_cdrmind("/agents/classify", payload)


def incident_reporter_call(payload: SocAgentInput) -> SocAgentOutput:
    return _call_cdrmind("/agents/report", payload)
