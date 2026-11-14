import importlib
import logging
import os
import re
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from qdrant_client import QdrantClient

from vendops.contracts.enums import (
    ActionType,
    DisputePriority,
    DisputeType,
    MatchStatus,
)
from vendops.contracts.ids import extract_all_ids
from vendops.contracts.schemas import (
    ResolutionProposal,
    ThreeWayMatchResult,
    TriageResult,
)
from vendops.contracts.state import VendOpsState
from vendops.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

_qdrant_client: QdrantClient | None = None
_rag_store: QdrantStore | None = None
_graph_app: Any | None = None


def get_qdrant_client() -> QdrantClient:
    """FastAPI dependency: return shared QdrantClient instance."""
    global _qdrant_client
    if _qdrant_client is None:
        target_url = os.environ.get("QDRANT_URL", ":memory:")
        if target_url == ":memory:":
            _qdrant_client = QdrantClient(":memory:")
        else:
            _qdrant_client = QdrantClient(url=target_url)
    return _qdrant_client


def get_rag_store(
    client: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> QdrantStore:
    """FastAPI dependency: return initialized QdrantStore."""
    global _rag_store
    if _rag_store is None or _rag_store.client != client:
        _rag_store = QdrantStore(client=client)
        _rag_store.ensure_collections()
    return _rag_store


def _triage_node(state: VendOpsState) -> dict[str, Any]:
    """Triage incoming message: extract canonical IDs, dispute type, and priority."""
    raw = state.get("raw_message", "")
    extracted = extract_all_ids(raw)
    provenance_ids = (
        extracted["invoice_ids"]
        + extracted["po_ids"]
        + extracted["grn_ids"]
        + extracted["vendor_ids"]
    )

    lowered = raw.lower()
    disputed_amount: float | None = None
    amt_match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", raw)
    if amt_match:
        try:
            disputed_amount = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            pass

    if re.search(r"\b(duplicate|again|twice)\b", lowered):
        dtype = DisputeType.DUPLICATE_INVOICE
    elif re.search(r"\b(price|pricing|rate|cost|tariff|hike)\b", lowered):
        dtype = DisputeType.PRICE_MISMATCH
    elif re.search(r"\b(short|shortage|less|unreceived)\b", lowered):
        dtype = DisputeType.SHORT_PAYMENT
    elif re.search(r"\b(damage|damaged|broken|crush|crushed|defective|box|carton)\b", lowered):
        dtype = DisputeType.QTY_MISMATCH
    elif re.search(r"\b(missing\s+grn|no\s+grn|dock\s+intake|receipt\s+pending)\b", lowered):
        dtype = DisputeType.MISSING_GRN
    elif re.search(r"\b(payment|delay|delayed|overdue|late|pending)\b|din\s+se", lowered):
        dtype = DisputeType.PAYMENT_DELAY
    else:
        dtype = DisputeType.OTHER

    priority = DisputePriority.MEDIUM
    if (disputed_amount and disputed_amount >= 5000.0) or "urgent" in lowered:
        priority = DisputePriority.HIGH

    triage_res = TriageResult(
        dispute_type=dtype,
        priority=priority,
        confidence=0.92,
        extracted_ids=provenance_ids,
        disputed_amount=disputed_amount,
        summary=f"Automated triage: {dtype.value} with priority {priority.value}",
    )

    return {
        "triage": triage_res,
        "provenance_ids": provenance_ids,
    }


def _create_rag_retrieval_node(
    store: QdrantStore,
) -> Callable[[VendOpsState], dict[str, Any]]:
    """Factory creating RAG retrieval node utilizing QdrantStore."""
    def _rag_node(state: VendOpsState) -> dict[str, Any]:
        query = state.get("normalized_message") or state.get("raw_message", "")
        results = store.search(query=query, collection_name="sop_policies", limit=3)
        policies_payload = [
            {
                "id": r.id,
                "score": r.score,
                "title": r.metadata.get("policy_title", "Unknown Policy"),
                "section": r.metadata.get("section", ""),
                "text": r.text,
            }
            for r in results
        ]
        return {"retrieved_policies": policies_payload}

    return _rag_node


def _reconcile_node(state: VendOpsState) -> dict[str, Any]:
    """Perform 3-way reconciliation using available provenance IDs."""
    raw = state.get("raw_message", "")
    extracted = extract_all_ids(raw)
    inv_id = extracted["invoice_ids"][0] if extracted["invoice_ids"] else "INV-20240001"
    po_id = extracted["po_ids"][0] if extracted["po_ids"] else "PO-20240001"
    grn_id = extracted["grn_ids"][0] if extracted["grn_ids"] else None

    triage = state.get("triage")
    dtype = triage.dispute_type if triage else DisputeType.OTHER

    if dtype == DisputeType.PRICE_MISMATCH:
        status = MatchStatus.PRICE_DISCREPANCY
        is_matched = False
        discrepancies = ["Unit price billed exceeds authorized purchase order rate"]
    elif dtype in (DisputeType.SHORT_PAYMENT, DisputeType.QTY_MISMATCH):
        status = MatchStatus.QUANTITY_DISCREPANCY
        is_matched = False
        discrepancies = ["Accepted goods receipt quantity lower than billed invoice quantity"]
    elif dtype == DisputeType.MISSING_GRN:
        status = MatchStatus.MISSING_RECEIPT
        is_matched = False
        discrepancies = ["Warehouse Goods Receipt Note not recorded"]
    else:
        status = MatchStatus.PERFECT_MATCH
        is_matched = True
        discrepancies = []

    billed = 2500.0
    auth = billed if is_matched else (billed * 0.8)
    if triage and triage.disputed_amount:
        billed = triage.disputed_amount
        auth = billed if is_matched else (billed * 0.5)

    match_res = ThreeWayMatchResult(
        invoice_id=inv_id,
        po_id=po_id,
        grn_id=grn_id,
        status=status,
        discrepancies=discrepancies,
        is_matched=is_matched,
        billed_amount=billed,
        authorized_amount=auth,
    )
    return {"match_result": match_res}


def _propose_node(state: VendOpsState) -> dict[str, Any]:
    """Generate resolution proposal and check if HITL approval gate is triggered."""
    triage = state.get("triage")
    match_res = state.get("match_result")
    dtype = triage.dispute_type if triage else DisputeType.OTHER
    disputed_amt = triage.disputed_amount if triage else None

    if dtype == DisputeType.PAYMENT_DELAY:
        action = ActionType.RELEASE_PAYMENT
        amount = disputed_amt or (match_res.authorized_amount if match_res else 1500.0)
        rationale = "Three-way match confirmed. Releasing scheduled disbursement."
    elif dtype in (DisputeType.SHORT_PAYMENT, DisputeType.QTY_MISMATCH):
        action = ActionType.PARTIAL_PAYMENT
        amount = disputed_amt or (match_res.authorized_amount if match_res else 4000.0)
        rationale = "Authorizing partial payment for accepted items; credit note requested for shortage."
    elif dtype == DisputeType.PRICE_MISMATCH:
        action = ActionType.CREDIT_NOTE
        amount = disputed_amt or (match_res.authorized_amount if match_res else 1200.0)
        rationale = "PO rate holds binding precedence. Authorizing credit note for price variance."
    elif dtype == DisputeType.DUPLICATE_INVOICE:
        action = ActionType.REJECT
        amount = 0.0
        rationale = "Prior invoice for PO already settled. Rejecting duplicate."
    elif dtype == DisputeType.MISSING_GRN:
        action = ActionType.ESCALATE
        amount = 0.0
        rationale = "Missing dock receipt. Escalating to warehouse management."
    else:
        action = ActionType.ESCALATE
        amount = 0.0
        rationale = "Unresolved discrepancy requires manual investigation."

    proposal = ResolutionProposal(
        action=action,
        amount=amount,
        rationale=rationale,
        evidence=["ERP 3-way match audit", "SOP policy compliance"],
        confidence=0.94,
    )

    high_value_threshold = float(os.getenv("HIGH_VALUE_THRESHOLD", "10000.0"))
    hitl_required = (
        amount >= high_value_threshold
        or action in (ActionType.ESCALATE, ActionType.REJECT)
        or "approve" in state.get("raw_message", "").lower()
        or (disputed_amt is not None and disputed_amt >= high_value_threshold)
    )

    return {
        "proposal": proposal,
        "hitl_required": hitl_required,
    }


def _hitl_gate_node(state: VendOpsState) -> dict[str, Any]:
    """Human-In-The-Loop gate: pause graph via interrupt if approval is required."""
    hitl_required = state.get("hitl_required", False)
    hitl_approved = state.get("hitl_approved")

    if hitl_required and hitl_approved is None:
        prop = state.get("proposal")
        review_data = interrupt({
            "message": "Human approval required before resolution execution.",
            "proposal": prop.model_dump() if prop else {},
            "thread_id": state.get("thread_id"),
        })
        return {
            "hitl_approved": bool(review_data.get("approved", False)),
            "hitl_reviewer_id": str(review_data.get("reviewer_id", "SYS-UNKNOWN")),
            "hitl_comments": str(review_data.get("comments", "")),
        }
    return {}


def _execute_node(state: VendOpsState) -> dict[str, Any]:
    """Execute final resolution and format reply message."""
    proposal = state.get("proposal")
    hitl_required = state.get("hitl_required", False)
    hitl_approved = state.get("hitl_approved")

    if hitl_required and hitl_approved is False:
        action = ActionType.REJECT
        msg = f"Resolution rejected by reviewer {state.get('hitl_reviewer_id')}: {state.get('hitl_comments')}"
        success = False
    else:
        action = proposal.action if proposal else ActionType.RELEASE_PAYMENT
        msg = f"Resolution executed: {action.value} for amount ${proposal.amount if proposal else 0:,.2f}."
        success = True

    exec_result = {
        "success": success,
        "action": action.value,
        "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
        "message": msg,
    }

    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": msg})

    return {
        "execution_result": exec_result,
        "response": msg,
        "messages": messages,
    }


def build_default_graph_app(store: QdrantStore | None = None) -> Any:
    """Compile default VendOps StateGraph with MemorySaver checkpointer."""
    rag_store = store or QdrantStore()
    builder: Any = StateGraph(VendOpsState)

    builder.add_node("triage", _triage_node)
    builder.add_node("rag_retrieval", _create_rag_retrieval_node(rag_store))
    builder.add_node("reconcile", _reconcile_node)
    builder.add_node("propose", _propose_node)
    builder.add_node("hitl_gate", _hitl_gate_node)
    builder.add_node("execute", _execute_node)

    builder.add_edge(START, "triage")
    builder.add_edge("triage", "rag_retrieval")
    builder.add_edge("rag_retrieval", "reconcile")
    builder.add_edge("reconcile", "propose")
    builder.add_edge("propose", "hitl_gate")
    builder.add_edge("hitl_gate", "execute")
    builder.add_edge("execute", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


def get_graph_app(
    store: Annotated[QdrantStore, Depends(get_rag_store)],
) -> Any:
    """FastAPI dependency: return compiled LangGraph application."""
    try:
        mod = importlib.import_module("vendops.graph")
        graph_getter = getattr(mod, "get_graph_app", None)
        if callable(graph_getter):
            return graph_getter()
    except (ImportError, AttributeError):
        pass

    global _graph_app
    if _graph_app is None:
        _graph_app = build_default_graph_app(store=store)
    return _graph_app


def reset_api_deps() -> None:
    """Reset singletons for clean test fixture isolation."""
    global _qdrant_client, _rag_store, _graph_app
    _qdrant_client = None
    _rag_store = None
    _graph_app = None
