from __future__ import annotations

import pytest

from taskrunner.flows import get_flow_definition, list_flows


def test_registry_has_soc_pipeline() -> None:
    flows = list_flows()
    assert "soc_pipeline" in flows
    assert len(flows) == 1


def test_soc_pipeline_node_sequence() -> None:
    flow = get_flow_definition("soc_pipeline")
    assert flow.node_sequence == ("summarize", "classify", "report")


def test_soc_pipeline_next_node() -> None:
    flow = get_flow_definition("soc_pipeline")
    assert flow.next_node("summarize") == "classify"
    assert flow.next_node("classify") == "report"
    assert flow.next_node("report") is None


def test_get_unknown_flow_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported flow"):
        get_flow_definition("echo_add")
