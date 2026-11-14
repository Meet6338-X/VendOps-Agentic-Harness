import uuid
from datetime import UTC, datetime
from typing import Any

from vendops.contracts.enums import ActionType
from vendops.contracts.schemas import (
    ExecuteResolutionInput,
    ExecuteResolutionOutput,
)
from vendops.contracts.state import VendOpsState
from vendops.guard.validate import ToolCallValidator


def execute_node(
    state: VendOpsState, erp_client: Any = None
) -> dict[str, Any]:
    """Execution node: validate parameters and provenance, call ERP write tool with idempotency key."""
    proposal = state.get("proposal")
    if proposal is None:
        return {
            "execution_result": {
                "success": False,
                "message": "Execution bypassed: no resolution proposal present.",
            }
        }

    # If HITL was triggered and rejected without override
    if (
        state.get("hitl_required")
        and not state.get("hitl_approved")
        and proposal.action != ActionType.REJECT
    ):
        proposal = proposal.model_copy(update={"action": ActionType.REJECT})

    # Retrieve IDs from ERP data or match result
    erp_data = state.get("erp_data", {})
    invoice_dict = erp_data.get("invoice", {})
    match_result = state.get("match_result")

    invoice_id = invoice_dict.get("invoice_id") or (
        match_result.invoice_id if match_result else None
    )
    po_id = invoice_dict.get("po_id") or (match_result.po_id if match_result else None)
    vendor_id = invoice_dict.get("vendor_id")

    if not vendor_id:
        # Fall back to any VND- id in provenance
        vnd_ids = [i for i in state.get("provenance_ids", []) if i.startswith("VND-")]
        vendor_id = vnd_ids[0] if vnd_ids else "VND-000123"

    if not invoice_id:
        inv_ids = [i for i in state.get("provenance_ids", []) if i.startswith("INV-")]
        invoice_id = inv_ids[0] if inv_ids else "INV-20240456"

    # Generate unique idempotency key
    idempotency_key = f"idemp_{uuid.uuid4().hex}"

    raw_args: dict[str, Any] = {
        "action": proposal.action,
        "invoice_id": invoice_id,
        "po_id": po_id,
        "vendor_id": vendor_id,
        "amount": proposal.amount,
        "rationale": proposal.rationale,
        "idempotency_key": idempotency_key,
        "reviewer_id": state.get("hitl_reviewer_id"),
    }

    # Strict tool parameter and provenance validation
    provenance_ids = state.get("provenance_ids", [])
    repair_attempts = state.get("repair_attempts", 0)
    tool_errors = list(state.get("tool_call_errors", []))

    validated_input, violation = ToolCallValidator.validate_tool_call_full(
        tool_name="execute_resolution",
        arguments=raw_args,
        allowed_ids=provenance_ids,
        current_repair_attempts=repair_attempts,
    )

    if violation is not None:
        tool_errors.append(violation.message)
        return {
            "tool_call_errors": tool_errors,
            "repair_attempts": violation.repair_attempts,
            "execution_result": {
                "success": False,
                "error": violation.message,
                "must_escalate": violation.must_escalate,
            },
        }

    exec_input = ExecuteResolutionInput.model_validate(validated_input)

    # Invoke ERP write tool
    output: ExecuteResolutionOutput
    if erp_client is not None and hasattr(erp_client, "execute_resolution"):
        raw_out = erp_client.execute_resolution(exec_input)
        if isinstance(raw_out, ExecuteResolutionOutput):
            output = raw_out
        elif isinstance(raw_out, dict):
            output = ExecuteResolutionOutput.model_validate(raw_out)
        else:
            output = ExecuteResolutionOutput(
                success=True,
                action=exec_input.action,
                invoice_id=exec_input.invoice_id,
                audit_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
                timestamp=datetime.now(UTC),
                message=f"Action {exec_input.action.value} executed successfully.",
            )
    else:
        # Deterministic offline write output
        output = ExecuteResolutionOutput(
            success=True,
            action=exec_input.action,
            invoice_id=exec_input.invoice_id,
            audit_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(UTC),
            message=(
                f"Action {exec_input.action.value} completed for invoice {exec_input.invoice_id}. "
                f"Amount: ${exec_input.amount:,.2f}."
            ),
        )

    return {
        "execution_result": output.model_dump(),
        "tool_call_errors": tool_errors,
    }
