from typing import Any, TypedDict

from vendops.contracts.schemas import (
    ResolutionProposal,
    ThreeWayMatchResult,
    TriageResult,
)


class VendOpsState(TypedDict, total=False):
    """Canonical typed state for the VendOps LangGraph workflow."""

    # Thread & Message metadata
    thread_id: str
    raw_message: str
    normalized_message: str
    language_detected: str
    token_fertility: float

    # Verified Provenance Tracking
    provenance_ids: list[str]

    # Pipeline artifacts
    triage: TriageResult | None
    erp_data: dict[str, Any]
    match_result: ThreeWayMatchResult | None
    retrieved_policies: list[dict[str, Any]]
    proposal: ResolutionProposal | None

    # HITL Gate Controls
    hitl_required: bool
    hitl_approved: bool | None
    hitl_reviewer_id: str | None
    hitl_comments: str | None

    # Execution & Response
    execution_result: dict[str, Any] | None
    response: str | None

    # Resilience & Validation Loop
    tool_call_errors: list[str]
    repair_attempts: int
    messages: list[dict[str, Any]]
