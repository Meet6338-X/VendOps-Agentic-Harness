from typing import Any

from langgraph.types import interrupt

from vendops.contracts.enums import ActionType
from vendops.contracts.schemas import ResolutionProposal, ResolutionReview
from vendops.contracts.state import VendOpsState

HIGH_VALUE_THRESHOLD: float = 100_000.0
CONFIDENCE_THRESHOLD: float = 0.85
SENSITIVE_ACTIONS: set[ActionType] = {ActionType.ESCALATE, ActionType.REJECT}


def is_hitl_trigger(proposal: ResolutionProposal | None) -> tuple[bool, str]:
    """Check if a proposal triggers the Human-In-The-Loop gate."""
    if proposal is None:
        return True, "Missing resolution proposal"

    if proposal.amount >= HIGH_VALUE_THRESHOLD:
        return True, f"High value amount: ${proposal.amount:,.2f} >= ${HIGH_VALUE_THRESHOLD:,.2f}"

    if proposal.confidence < CONFIDENCE_THRESHOLD:
        return True, f"Low confidence: {proposal.confidence:.2f} < {CONFIDENCE_THRESHOLD:.2f}"

    if proposal.action in SENSITIVE_ACTIONS:
        return True, f"Sensitive action: {proposal.action.value}"

    return False, ""


def hitl_gate_node(state: VendOpsState) -> dict[str, Any]:
    """HITL Gate node: trigger LangGraph interrupt() when high value, low confidence, or sensitive action."""
    # If approval already decided in state, bypass
    if state.get("hitl_approved") is not None:
        return {
            "hitl_required": bool(state.get("hitl_required", False)),
            "hitl_approved": state.get("hitl_approved"),
            "hitl_reviewer_id": state.get("hitl_reviewer_id"),
            "hitl_comments": state.get("hitl_comments"),
        }

    proposal = state.get("proposal")
    requires_hitl, reason = is_hitl_trigger(proposal)

    if not requires_hitl:
        return {
            "hitl_required": False,
            "hitl_approved": True,
            "hitl_reviewer_id": None,
            "hitl_comments": "Automated approval: below risk thresholds",
        }

    # Trigger LangGraph interrupt and await human review
    match_result = state.get("match_result")
    interrupt_payload = {
        "reason": reason,
        "proposal": proposal.model_dump() if proposal else None,
        "thread_id": state.get("thread_id"),
        "match_result": match_result.model_dump() if match_result is not None else None,
    }

    # When execution resumes, review_data receives the payload from Command(resume=...)
    review_data = interrupt(interrupt_payload)

    # Parse review payload into ResolutionReview contract
    if isinstance(review_data, ResolutionReview):
        review = review_data
    elif isinstance(review_data, dict):
        review = ResolutionReview.model_validate(review_data)
    else:
        # Fallback if raw boolean or other primitive is sent
        approved = bool(review_data)
        review = ResolutionReview(
            approved=approved,
            reviewer_id="HUMAN-REVIEWER",
            comments="Manual review recorded",
        )

    # Apply reviewer decisions to proposal
    updated_proposal = proposal
    if updated_proposal is not None:
        # Override action if specified
        if review.override_action is not None:
            updated_proposal = updated_proposal.model_copy(
                update={"action": review.override_action}
            )
        elif not review.approved:
            updated_proposal = updated_proposal.model_copy(
                update={"action": ActionType.REJECT}
            )

        # Override amount if specified
        if review.override_amount is not None:
            updated_proposal = updated_proposal.model_copy(
                update={"amount": review.override_amount}
            )

        if review.comments:
            rationale_suffix = f" [Reviewer ({review.reviewer_id}): {review.comments}]"
            new_rationale = (updated_proposal.rationale + rationale_suffix)[:2000]
            updated_proposal = updated_proposal.model_copy(
                update={"rationale": new_rationale}
            )

    return {
        "hitl_required": True,
        "hitl_approved": review.approved,
        "hitl_reviewer_id": review.reviewer_id,
        "hitl_comments": review.comments,
        "proposal": updated_proposal,
    }
