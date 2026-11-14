import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime
from enum import Enum
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

logger = logging.getLogger(__name__)

router = APIRouter()


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

    return {
        "thread_id": thread_id,
        "status": "RESUMED",
        "review": resume_payload,
        "state": serialize_data(updated_state.values),
    }
