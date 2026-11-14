from typing import Any

from vendops.contracts.enums import ActionType, MatchStatus
from vendops.contracts.schemas import ResolutionProposal
from vendops.contracts.state import VendOpsState
from vendops.graph.llm import BaseLLMAdapter


def formulate_rule_proposal(state: VendOpsState) -> ResolutionProposal:
    """Formulate deterministic resolution proposal based on match results and provenance status."""
    # Check if repair attempts exhausted
    repair_attempts = state.get("repair_attempts", 0)
    tool_errors = state.get("tool_call_errors", [])
    if repair_attempts >= 2 and tool_errors:
        return ResolutionProposal(
            action=ActionType.ESCALATE,
            amount=0.0,
            rationale=(
                f"Maximum repair attempts (2) exceeded due to provenance violations or tool call errors: "
                f"{'; '.join(tool_errors[-2:])}. Routing to human review."
            ),
            evidence=["Provenance validation failure threshold exceeded"],
            confidence=0.50,
        )

    match_res = state.get("match_result")
    if not match_res:
        return ResolutionProposal(
            action=ActionType.ESCALATE,
            amount=0.0,
            rationale="Dispute could not be matched against ERP records. Escalating for manual investigation.",
            evidence=tool_errors or ["No match result available"],
            confidence=0.50,
        )

    match match_res.status:
        case MatchStatus.PERFECT_MATCH:
            return ResolutionProposal(
                action=ActionType.RELEASE_PAYMENT,
                amount=match_res.authorized_amount,
                rationale=(
                    f"3-way match verified successfully. Purchase Order {match_res.po_id}, "
                    f"GRN {match_res.grn_id}, and Invoice {match_res.invoice_id} are in complete agreement."
                ),
                evidence=[
                    f"Invoice {match_res.invoice_id} billed ${match_res.billed_amount:.2f}",
                    f"GRN {match_res.grn_id} accepted all ordered units",
                    f"Contracted PO {match_res.po_id} price verified",
                ],
                confidence=0.98,
            )

        case MatchStatus.QUANTITY_DISCREPANCY:
            if match_res.authorized_amount > 0:
                diff = match_res.billed_amount - match_res.authorized_amount
                return ResolutionProposal(
                    action=ActionType.PARTIAL_PAYMENT,
                    amount=match_res.authorized_amount,
                    rationale=(
                        f"Quantity discrepancy identified. Authorizing partial payment of "
                        f"${match_res.authorized_amount:.2f} for verified received units. "
                        f"Difference of ${diff:.2f} requires vendor credit note or reconciliation."
                    ),
                    evidence=list(match_res.discrepancies)
                    + [f"Authorized partial payment: ${match_res.authorized_amount:.2f}"],
                    confidence=0.92,
                )
            return ResolutionProposal(
                action=ActionType.REPLACEMENT,
                amount=0.0,
                rationale="Zero delivered units were accepted by receiving warehouse. Awaiting replacement delivery.",
                evidence=list(match_res.discrepancies),
                confidence=0.90,
            )

        case MatchStatus.PRICE_DISCREPANCY:
            return ResolutionProposal(
                action=ActionType.PARTIAL_PAYMENT,
                amount=match_res.authorized_amount,
                rationale=(
                    f"Unit price on invoice exceeds agreed Purchase Order rate. "
                    f"Authorizing payment of ${match_res.authorized_amount:.2f} at contracted PO rate."
                ),
                evidence=list(match_res.discrepancies),
                confidence=0.88,
            )

        case MatchStatus.MISSING_RECEIPT:
            return ResolutionProposal(
                action=ActionType.ESCALATE,
                amount=0.0,
                rationale=(
                    f"Goods Receipt Note (GRN) not found for PO {match_res.po_id}. "
                    f"Escalating to warehouse operations to verify physical receipt."
                ),
                evidence=list(match_res.discrepancies) or ["Missing GRN in ERP"],
                confidence=0.80,
            )

        case MatchStatus.ALREADY_PAID:
            return ResolutionProposal(
                action=ActionType.REJECT,
                amount=0.0,
                rationale=f"Invoice {match_res.invoice_id} has already been settled in a prior payment batch.",
                evidence=list(match_res.discrepancies),
                confidence=0.99,
            )

        case MatchStatus.NOT_FOUND:
            return ResolutionProposal(
                action=ActionType.ESCALATE,
                amount=0.0,
                rationale="Target records could not be located in ERP. Escalating to vendor master data team.",
                evidence=list(match_res.discrepancies),
                confidence=0.70,
            )

        case _:
            return ResolutionProposal(
                action=ActionType.ESCALATE,
                amount=0.0,
                rationale="Unrecognized reconciliation state. Escalated for specialist review.",
                evidence=list(match_res.discrepancies),
                confidence=0.60,
            )


def decide_node(
    state: VendOpsState, llm: BaseLLMAdapter | None = None
) -> dict[str, Any]:
    """Decision node: formulate ResolutionProposal {action, amount, rationale, evidence, confidence}."""
    if llm is not None:
        try:
            match_res = state.get("match_result")
            prompt = (
                f"Formulate a resolution proposal based on this reconciliation result:\n"
                f"{match_res.model_dump_json() if match_res else 'No match result'}"
            )
            proposal = llm.generate_structured(prompt, ResolutionProposal)
            return {"proposal": proposal}
        except (ValueError, RuntimeError, TypeError):
            proposal = formulate_rule_proposal(state)
            return {"proposal": proposal}

    proposal = formulate_rule_proposal(state)
    return {"proposal": proposal}
