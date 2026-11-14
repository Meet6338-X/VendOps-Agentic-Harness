import sqlite3
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from vendops.contracts.state import VendOpsState
from vendops.graph.llm import BaseLLMAdapter
from vendops.graph.nodes.decide import decide_node
from vendops.graph.nodes.execute import execute_node
from vendops.graph.nodes.hitl_gate import hitl_gate_node
from vendops.graph.nodes.ingest import ingest_node
from vendops.graph.nodes.normalize import normalize_node
from vendops.graph.nodes.respond import respond_node
from vendops.graph.nodes.triage import triage_node
from vendops.graph.nodes.verify import verify_node


def build_vendops_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    llm_adapter: BaseLLMAdapter | None = None,
    erp_client: Any = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Construct and compile the VendOps StateGraph pipeline with SQLite checkpointing."""
    builder = StateGraph(VendOpsState)

    # Bind node callbacks with injected adapters / clients
    def _ingest(state: VendOpsState) -> dict[str, Any]:
        return ingest_node(state)

    def _normalize(state: VendOpsState) -> dict[str, Any]:
        return normalize_node(state)

    def _triage(state: VendOpsState) -> dict[str, Any]:
        return triage_node(state, llm=llm_adapter)

    def _verify(state: VendOpsState) -> dict[str, Any]:
        return verify_node(state, erp_client=erp_client)

    def _decide(state: VendOpsState) -> dict[str, Any]:
        return decide_node(state, llm=llm_adapter)

    def _hitl_gate(state: VendOpsState) -> dict[str, Any]:
        return hitl_gate_node(state)

    def _execute(state: VendOpsState) -> dict[str, Any]:
        return execute_node(state, erp_client=erp_client)

    def _respond(state: VendOpsState) -> dict[str, Any]:
        return respond_node(state, llm=llm_adapter)

    # Register nodes
    builder.add_node("ingest", _ingest)
    builder.add_node("normalize", _normalize)
    builder.add_node("triage", _triage)
    builder.add_node("verify", _verify)
    builder.add_node("decide", _decide)
    builder.add_node("hitl_gate", _hitl_gate)
    builder.add_node("execute", _execute)
    builder.add_node("respond", _respond)

    # Register edges
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "normalize")
    builder.add_edge("normalize", "triage")
    builder.add_edge("triage", "verify")
    builder.add_edge("verify", "decide")
    builder.add_edge("decide", "hitl_gate")
    builder.add_edge("hitl_gate", "execute")
    builder.add_edge("execute", "respond")
    builder.add_edge("respond", END)

    # Default to in-memory SQLite checkpointer if none supplied
    if checkpointer is None:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    return builder.compile(checkpointer=checkpointer)
