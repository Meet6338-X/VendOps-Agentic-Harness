import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sse_starlette import EventSourceResponse, ServerSentEvent

from vendops.api.deps import get_graph_app, get_qdrant_client
from vendops.contracts.schemas import ResolutionReview, VendorMessageInput
from vendops.contracts.state import VendOpsState
from vendops.erp.db import get_default_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Global thread registry for dispute history and approvals tracking
DISPUTE_HISTORY: dict[str, dict[str, Any]] = {}
GUARD_EVENTS: list[dict[str, Any]] = []


def serialize_data(val: Any) -> Any:
    """Recursively convert state and LangGraph values into JSON-serializable primitives."""
    if hasattr(val, "value") and not isinstance(val, Enum):
        return serialize_data(val.value)
    if isinstance(val, BaseModel):
        return val.model_dump(mode="json")
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, dict):
        return {str(k): serialize_data(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [serialize_data(x) for x in val]
    return val


@router.get("/", tags=["System"])
@router.get("/health", tags=["System"])
@router.get("/healthz", tags=["System"])
async def health_check(
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> JSONResponse:
    """Liveness & readiness health check for API and Qdrant vector store."""
    try:
        qdrant.get_collections()
        qdrant_status = "healthy"
        is_healthy = True
    except Exception as exc:
        logger.exception("Health check failed for Qdrant")
        qdrant_status = f"unhealthy: {exc}"
        is_healthy = False

    payload = {
        "status": "healthy" if is_healthy else "degraded",
        "service": "VendOps Dispute Resolution & RAG Service",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api": "healthy",
            "qdrant": qdrant_status,
        },
    }
    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload)


@router.post("/api/v1/disputes", status_code=status.HTTP_200_OK, tags=["Disputes"])
async def create_dispute(
    payload: VendorMessageInput,
    graph_app: Annotated[Any, Depends(get_graph_app)],
) -> dict[str, Any]:
    """Initialize a new dispute thread and return initial workflow state."""
    thread_id = payload.thread_id or f"thread_{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": payload.message,
        "normalized_message": payload.message.strip(),
        "language_detected": "en",
        "token_fertility": 1.0,
        "provenance_ids": [],
        "triage": None,
        "erp_data": {},
        "match_result": None,
        "retrieved_policies": [],
        "proposal": None,
        "hitl_required": False,
        "hitl_approved": None,
        "hitl_reviewer_id": None,
        "hitl_comments": None,
        "execution_result": None,
        "response": None,
        "tool_call_errors": [],
        "repair_attempts": 0,
        "messages": [{"role": "user", "content": payload.message}],
    }

    graph_app.update_state(config, initial_state)
    logger.info("Initialized dispute thread %s", thread_id)

    DISPUTE_HISTORY[thread_id] = {
        "thread_id": thread_id,
        "message": payload.message,
        "sender": payload.sender,
        "created_at": datetime.now().isoformat(),
        "status": "INITIALIZED",
    }

    return {
        "thread_id": thread_id,
        "status": "INITIALIZED",
        "state": serialize_data(initial_state),
    }


@router.get("/api/v1/disputes/{thread_id}/stream", tags=["Disputes"])
async def stream_dispute(
    thread_id: str,
    graph_app: Annotated[Any, Depends(get_graph_app)],
) -> EventSourceResponse:
    """Stream real-time LangGraph node transitions and token events via SSE."""
    config = {"configurable": {"thread_id": thread_id}}
    current_state = graph_app.get_state(config)

    if not current_state or not current_state.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute thread '{thread_id}' not found.",
        )

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        try:
            async for mode, payload in graph_app.astream(
                None, config=config, stream_mode=["updates", "messages"]
            ):
                if mode == "updates":
                    # Node state transitions
                    for node_name, node_update in payload.items():
                        if node_name == "__interrupt__":
                            interrupt_val = (
                                node_update[0].value
                                if hasattr(node_update[0], "value")
                                else node_update[0]
                            )
                            yield ServerSentEvent(
                                event="interrupt",
                                data=json.dumps(
                                    serialize_data({
                                        "thread_id": thread_id,
                                        "interrupt": interrupt_val,
                                    })
                                ),
                            )
                        else:
                            yield ServerSentEvent(
                                event="node_transition",
                                data=json.dumps(
                                    serialize_data({
                                        "thread_id": thread_id,
                                        "node": node_name,
                                        "update": node_update,
                                    })
                                ),
                            )
                elif mode == "messages":
                    chunk, _meta = payload
                    token_text = (
                        chunk.content
                        if hasattr(chunk, "content")
                        else str(chunk)
                    )
                    yield ServerSentEvent(
                        event="token",
                        data=json.dumps({
                            "thread_id": thread_id,
                            "token": token_text,
                        }),
                    )

            final_state = graph_app.get_state(config)
            is_interrupted = any(t.interrupts for t in final_state.tasks)

            if is_interrupted:
                pending_interrupt: Any = next(
                    (t.interrupts[0].value for t in final_state.tasks if t.interrupts),
                    {},
                )
                yield ServerSentEvent(
                    event="interrupt",
                    data=json.dumps(
                        serialize_data({
                            "thread_id": thread_id,
                            "status": "WAITING_APPROVAL",
                            "interrupt": pending_interrupt,
                        })
                    ),
                )
            else:
                yield ServerSentEvent(
                    event="end",
                    data=json.dumps(
                        serialize_data({
                            "thread_id": thread_id,
                            "status": "COMPLETED",
                            "final_state": final_state.values,
                        })
                    ),
                )

        except Exception as exc:
            logger.exception("Error during dispute SSE streaming for %s", thread_id)
            yield ServerSentEvent(
                event="error",
                data=json.dumps({"thread_id": thread_id, "error": str(exc)}),
            )

    return EventSourceResponse(event_generator())


@router.post("/api/v1/disputes/{thread_id}/resume", tags=["Disputes"])
async def resume_dispute(
    thread_id: str,
    review: ResolutionReview,
    graph_app: Annotated[Any, Depends(get_graph_app)],
) -> dict[str, Any]:
    """Resume an interrupted dispute workflow after human-in-the-loop review."""
    config = {"configurable": {"thread_id": thread_id}}
    current_state = graph_app.get_state(config)

    if not current_state or not current_state.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute thread '{thread_id}' not found.",
        )

    has_interrupt = any(t.interrupts for t in current_state.tasks)
    if not has_interrupt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Thread '{thread_id}' is not in an interrupted state awaiting review.",
        )

    resume_payload = review.model_dump(mode="json")
    command: Any = Command(resume=resume_payload)
    await graph_app.ainvoke(command, config=config)

    updated_state = graph_app.get_state(config)
    logger.info("Resumed thread %s with approval=%s", thread_id, review.approved)

    if thread_id in DISPUTE_HISTORY:
        DISPUTE_HISTORY[thread_id]["status"] = "APPROVED" if review.approved else "REJECTED"

    return {
        "thread_id": thread_id,
        "status": "RESUMED",
        "review": resume_payload,
        "state": serialize_data(updated_state.values),
    }


# =========================================================================
# Additive UI Endpoints (Overview, History, Approvals, Audit, ERP, Evals)
# =========================================================================


@router.get("/api/v1/disputes", tags=["Disputes"])
async def list_disputes(
    limit: int = 50,
    graph_app: Annotated[Any, Depends(get_graph_app)] = None,
) -> list[dict[str, Any]]:
    """List recent dispute sessions with status and summary metrics."""
    results: list[dict[str, Any]] = []
    for tid, meta in list(DISPUTE_HISTORY.items())[-limit:]:
        item = dict(meta)
        if graph_app:
            try:
                state = graph_app.get_state({"configurable": {"thread_id": tid}})
                if state and state.values:
                    vals = state.values
                    triage = vals.get("triage")
                    proposal = vals.get("proposal")
                    item["dispute_type"] = triage.dispute_type.value if hasattr(triage, "dispute_type") else None
                    item["priority"] = triage.priority.value if hasattr(triage, "priority") else None
                    item["amount"] = proposal.amount if hasattr(proposal, "amount") else None
                    item["action"] = proposal.action.value if hasattr(proposal, "action") else None
                    item["language"] = vals.get("language_detected")
                    if any(t.interrupts for t in state.tasks):
                        item["status"] = "WAITING_APPROVAL"
                    elif vals.get("execution_result"):
                        item["status"] = "RESOLVED"
            except (KeyError, ValueError, AttributeError) as exc:
                logger.debug("Could not inspect state for thread %s: %s", tid, exc)
        results.append(item)
    return results


@router.get("/api/v1/disputes/{thread_id}", tags=["Disputes"])
async def get_dispute(
    thread_id: str,
    graph_app: Annotated[Any, Depends(get_graph_app)],
) -> dict[str, Any]:
    """Retrieve current state and tasks for a specific dispute thread."""
    config = {"configurable": {"thread_id": thread_id}}
    state = graph_app.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute thread '{thread_id}' not found.",
        )

    is_interrupted = any(t.interrupts for t in state.tasks)
    pending_interrupt = next((t.interrupts[0].value for t in state.tasks if t.interrupts), None)

    return {
        "thread_id": thread_id,
        "status": "WAITING_APPROVAL" if is_interrupted else "COMPLETED" if state.values.get("response") else "PROCESSING",
        "is_interrupted": is_interrupted,
        "pending_interrupt": serialize_data(pending_interrupt),
        "state": serialize_data(state.values),
    }


@router.get("/api/v1/approvals", tags=["Approvals"])
async def list_pending_approvals(
    graph_app: Annotated[Any, Depends(get_graph_app)],
) -> list[dict[str, Any]]:
    """List all dispute cases currently paused at the HITL gate awaiting review."""
    pending: list[dict[str, Any]] = []
    for tid, meta in DISPUTE_HISTORY.items():
        try:
            config = {"configurable": {"thread_id": tid}}
            state = graph_app.get_state(config)
            if state and any(t.interrupts for t in state.tasks):
                interrupt_val = state.tasks[0].interrupts[0].value
                prop = state.values.get("proposal")
                pending.append({
                    "thread_id": tid,
                    "created_at": meta.get("created_at"),
                    "raw_message": state.values.get("raw_message"),
                    "interrupt": serialize_data(interrupt_val),
                    "proposal": serialize_data(prop.model_dump() if hasattr(prop, "model_dump") else prop),
                    "match_result": serialize_data(state.values.get("match_result")),
                })
        except (KeyError, ValueError, AttributeError) as exc:
            logger.debug("Could not inspect pending approval for thread %s: %s", tid, exc)
    return pending


@router.get("/api/v1/audit", tags=["Audit"])
async def list_audit_log(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve immutable audit ledger records from the ERP database."""
    try:
        db = get_default_db()
        entries = db.list_audit_entries(limit=limit)
        return [serialize_data(e.model_dump()) for e in entries]
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to query audit log")
        return []


@router.get("/api/v1/erp/invoices", tags=["ERP"])
async def list_erp_invoices(limit: int = 50) -> list[dict[str, Any]]:
    """List invoices from ERP mock database."""
    try:
        db = get_default_db()
        invoices = db.list_invoices(limit=limit)
        return [serialize_data(i.model_dump()) for i in invoices]
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to query ERP invoices")
        return []


@router.get("/api/v1/erp/purchase-orders", tags=["ERP"])
async def list_erp_pos(limit: int = 50) -> list[dict[str, Any]]:
    """List purchase orders from ERP mock database."""
    try:
        db = get_default_db()
        pos = db.list_purchase_orders(limit=limit)
        return [serialize_data(p.model_dump()) for p in pos]
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to query ERP purchase orders")
        return []


@router.get("/api/v1/erp/grns", tags=["ERP"])
async def list_erp_grns(limit: int = 50) -> list[dict[str, Any]]:
    """List goods receipt notes from ERP mock database."""
    try:
        db = get_default_db()
        grns = db.list_grns(limit=limit)
        return [serialize_data(g.model_dump()) for g in grns]
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to query ERP GRNs")
        return []


@router.get("/api/v1/erp/vendors", tags=["ERP"])
async def list_erp_vendors(limit: int = 50) -> list[dict[str, Any]]:
    """List vendor profiles from ERP mock database."""
    try:
        db = get_default_db()
        vendors = db.list_vendors(limit=limit)
        return [serialize_data(v.model_dump()) for v in vendors]
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to query ERP vendors")
        return []


@router.get("/api/v1/evals/latest", tags=["Quality"])
async def get_latest_evals() -> dict[str, Any]:
    """Retrieve latest automated benchmark results, tail slices, and gate status."""
    report_path = Path("evals/results/latest_report.json")
    summary_path = Path("evals/results/release_gate_summary.json")
    md_path = Path("evals/results/latest_report.md")

    data: dict[str, Any] = {}
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("Could not parse summary json")
    elif report_path.exists():
        try:
            data = {"report": json.loads(report_path.read_text(encoding="utf-8")), "gate_passed": True}
        except (OSError, json.JSONDecodeError):
            logger.debug("Could not parse report json")

    if md_path.exists():
        try:
            data["markdown_report"] = md_path.read_text(encoding="utf-8")
        except OSError:
            logger.debug("Could not read markdown report")

    return data


@router.get("/api/v1/guard/events", tags=["Guard"])
async def list_guard_events(limit: int = 50) -> list[dict[str, Any]]:
    """List timeline of tool call intercept events, schema validation failures, and repairs."""
    return GUARD_EVENTS[-limit:]

