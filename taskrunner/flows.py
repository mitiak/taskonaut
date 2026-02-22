from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from taskrunner.policy import get_policy_limits
from taskrunner.schemas import TaskCreateRequest
from taskrunner.tool_registry import execute_tool


class GraphExecutionState(TypedDict, total=False):
    text: str
    a: int
    b: int
    echo_result: dict[str, Any]
    add_result: dict[str, Any]


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


def _echo_node(state: GraphExecutionState) -> dict[str, Any]:
    limits = get_policy_limits()
    output = execute_tool("echo", {"text": state["text"]}, timeout_secs=limits.tool_timeout_secs)
    return {"echo_result": output}


def _add_node(state: GraphExecutionState) -> dict[str, Any]:
    limits = get_policy_limits()
    output = execute_tool(
        "add",
        {"a": state["a"], "b": state["b"]},
        timeout_secs=limits.tool_timeout_secs,
    )
    return {"add_result": output}


def _build_linear_graph(node_handlers: dict[str, Any], node_sequence: tuple[str, ...]) -> Any:
    builder = StateGraph(GraphExecutionState)
    for node_name, node_handler in node_handlers.items():
        builder.add_node(node_name, node_handler)
    if node_sequence:
        builder.add_edge(START, node_sequence[0])
        for i in range(len(node_sequence) - 1):
            builder.add_edge(node_sequence[i], node_sequence[i + 1])
        builder.add_edge(node_sequence[-1], END)
    return builder.compile()


_FLOW_NODE_HANDLERS: dict[str, dict[str, Any]] = {
    "echo_add": {
        "echo": _echo_node,
        "add": _add_node,
    },
    "demo": {
        "echo": _echo_node,
        "add": _add_node,
    },
    "add_echo": {
        "add": _add_node,
        "echo": _echo_node,
    },
}

_FLOW_NODE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "echo_add": ("echo", "add"),
    "demo": ("echo", "add"),
    "add_echo": ("add", "echo"),
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
    return {"text": request.text, "a": request.a, "b": request.b}


def build_step_input_payload(request: TaskCreateRequest, node_name: str) -> dict[str, Any]:
    if node_name == "echo":
        return {"text": request.text}
    if node_name == "add":
        return {"a": request.a, "b": request.b}
    raise ValueError(f"Unsupported node '{node_name}'")


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

    if node_name == "echo":
        return merged_state["echo_result"], dict(merged_state)
    if node_name == "add":
        return merged_state["add_result"], dict(merged_state)
    raise ValueError(f"Unsupported node '{node_name}'")
