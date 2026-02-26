from __future__ import annotations

from taskrunner.tools import SocAgentInput, SocAgentOutput


def test_soc_agent_input_model() -> None:
    payload = SocAgentInput(
        raw_logs=["log line 1", "log line 2"],
        context={"actor_id": "analyst-001", "actor_role": "analyst"},
        session_id="test-session",
    )
    assert payload.raw_logs == ["log line 1", "log line 2"]
    assert payload.session_id == "test-session"


def test_soc_agent_output_model() -> None:
    output = SocAgentOutput(
        result={"risk_score": 8.5},
        reasoning_step="log_summarizer",
    )
    assert output.result["risk_score"] == 8.5
    assert output.reasoning_step == "log_summarizer"
