from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from taskrunner.schemas import TaskCreateRequest
from taskrunner.tool_registry import execute_tool


class GraphExecutionState(TypedDict, total=False):
    raw_logs: list[str]
    session_id: str
    actor_id: str
    actor_role: str
    log_summary: dict[str, Any]
    threat_indicators: dict[str, Any]
    mitre_tactics: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]
    risk_score: float
    incident_report: dict[str, Any]
    log_summarizer_result: dict[str, Any]
    threat_classifier_result: dict[str, Any]
    incident_reporter_result: dict[str, Any]


@dataclass(frozen=True)
class FlowDefinition:
    name: str
    node_sequence: tuple[str, ...]
    node_handlers: dict[str, Any]
    graph: Any

    def first_node(self) -> str | None:
        return self.node_sequence[0] if self.node_sequence else None

    def next_node(self, current_node: str) -> str | None:
        if current_node not in self.node_sequence:
            return None
        idx = self.node_sequence.index(current_node)
        if idx + 1 >= len(self.node_sequence):
            return None
        return self.node_sequence[idx + 1]


def _summarize_node(state: GraphExecutionState) -> dict[str, Any]:
    payload = {
        "raw_logs": state.get("raw_logs", []),
        "context": {
            "actor_id": state.get("actor_id", ""),
            "actor_role": state.get("actor_role", ""),
        },
        "session_id": state.get("session_id", ""),
    }
    output = execute_tool("log_summarizer", payload, timeout_secs=120.0)
    return {"log_summarizer_result": output}


def _classify_node(state: GraphExecutionState) -> dict[str, Any]:
    summary_result = state.get("log_summarizer_result") or {}
    payload = {
        "raw_logs": state.get("raw_logs", []),
        "context": {
            "actor_id": state.get("actor_id", ""),
            "actor_role": state.get("actor_role", ""),
            "log_summary": summary_result.get("result", {}),
        },
        "session_id": state.get("session_id", ""),
    }
    output = execute_tool("threat_classifier", payload, timeout_secs=120.0)
    return {"threat_classifier_result": output}


def _report_node(state: GraphExecutionState) -> dict[str, Any]:
    summary_result = state.get("log_summarizer_result") or {}
    classify_result = state.get("threat_classifier_result") or {}
    payload = {
        "raw_logs": state.get("raw_logs", []),
        "context": {
            "actor_id": state.get("actor_id", ""),
            "actor_role": state.get("actor_role", ""),
            "log_summary": summary_result.get("result", {}),
            "classification": classify_result.get("result", {}),
        },
        "session_id": state.get("session_id", ""),
    }
    output = execute_tool("incident_reporter", payload, timeout_secs=120.0)
    return {"incident_reporter_result": output}


def _build_linear_graph(node_handlers: dict[str, Any], node_sequence: tuple[str, ...]) -> Any:
    builder: StateGraph = StateGraph(GraphExecutionState)
    for node_name, node_handler in node_handlers.items():
        builder.add_node(node_name, node_handler)
    if node_sequence:
        builder.add_edge(START, node_sequence[0])
        for i in range(len(node_sequence) - 1):
            builder.add_edge(node_sequence[i], node_sequence[i + 1])
        builder.add_edge(node_sequence[-1], END)
    return builder.compile()


_FLOW_NODE_HANDLERS: dict[str, dict[str, Any]] = {
    "soc_pipeline": {
        "log_summarizer": _summarize_node,
        "threat_classifier": _classify_node,
        "incident_reporter": _report_node,
    },
}

_FLOW_NODE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "soc_pipeline": ("log_summarizer", "threat_classifier", "incident_reporter"),
}

FLOW_REGISTRY: dict[str, FlowDefinition] = {
    flow_name: FlowDefinition(
        name=flow_name,
        node_sequence=_FLOW_NODE_SEQUENCES[flow_name],
        node_handlers=_FLOW_NODE_HANDLERS[flow_name],
        graph=_build_linear_graph(_FLOW_NODE_HANDLERS[flow_name], _FLOW_NODE_SEQUENCES[flow_name]),
    )
    for flow_name in _FLOW_NODE_HANDLERS
}


def list_flows() -> tuple[str, ...]:
    return tuple(sorted(FLOW_REGISTRY.keys()))


def get_flow_definition(flow_name: str) -> FlowDefinition:
    try:
        return FLOW_REGISTRY[flow_name]
    except KeyError as exc:
        supported = ", ".join(list_flows())
        raise ValueError(f"Unsupported flow '{flow_name}'. Available flows: {supported}") from exc


def build_initial_graph_state(request: TaskCreateRequest) -> GraphExecutionState:
    state: GraphExecutionState = {}
    if request.raw_logs is not None:
        state["raw_logs"] = request.raw_logs
    if request.session_id is not None:
        state["session_id"] = request.session_id
    if request.actor_id is not None:
        state["actor_id"] = request.actor_id
    if request.actor_role is not None:
        state["actor_role"] = request.actor_role
    return state


def build_step_input_payload(request: TaskCreateRequest, node_name: str) -> dict[str, Any]:
    if node_name in ("log_summarizer", "threat_classifier", "incident_reporter"):
        return {
            "raw_logs": request.raw_logs or [],
            "session_id": request.session_id or "",
            "context": {
                "actor_id": request.actor_id or "",
                "actor_role": request.actor_role or "",
            },
        }
    raise ValueError(f"Unsupported node '{node_name}'")


_SOC_RESULT_FIELDS: dict[str, str] = {
    "log_summarizer": "log_summarizer_result",
    "threat_classifier": "threat_classifier_result",
    "incident_reporter": "incident_reporter_result",
}


def execute_graph_node(
    *,
    flow_name: str,
    node_name: str,
    graph_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    flow = get_flow_definition(flow_name)
    handler = flow.node_handlers[node_name]
    state_input = cast(GraphExecutionState, dict(graph_state))
    updates = handler(state_input)
    if not isinstance(updates, dict):
        raise ValueError(f"Flow node '{node_name}' returned non-dict updates")
    merged_state = cast(GraphExecutionState, {**state_input, **updates})

    if node_name in _SOC_RESULT_FIELDS:
        result_field = _SOC_RESULT_FIELDS[node_name]
        return merged_state.get(result_field, {}), dict(merged_state)
    raise ValueError(f"Unsupported node '{node_name}'")
