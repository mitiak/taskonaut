from __future__ import annotations

from taskrunner.flows import execute_graph_node, get_flow_definition, list_flows


def test_registry_has_at_least_two_flows() -> None:
    flows = list_flows()
    assert "echo_add" in flows
    assert "add_echo" in flows


def test_echo_node_executes_with_pydantic_tool_contract() -> None:
    result, state = execute_graph_node(
        flow_name="echo_add",
        node_name="echo",
        graph_state={"text": "hello", "a": 1, "b": 2},
    )
    assert result == {"text": "hello"}
    assert state["echo_result"] == {"text": "hello"}


def test_add_echo_flow_orders_nodes_deterministically() -> None:
    flow = get_flow_definition("add_echo")
    assert flow.node_sequence == ("add", "echo")
