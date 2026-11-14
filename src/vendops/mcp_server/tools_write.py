"""Write tools for VendOps ERP MCP server."""

import uuid
from datetime import UTC, datetime

from vendops.contracts.enums import ActionType, InvoiceStatus, PaymentStatus
from vendops.contracts.schemas import (
    AuditEntry,
    ExecuteResolutionInput,
    ExecuteResolutionOutput,
    Payment,
)
from vendops.erp.db import get_default_db


def execute_resolution(
    action: ActionType,
    invoice_id: str,
    vendor_id: str,
    amount: float,
    rationale: str,
    idempotency_key: str,
    po_id: str | None = None,
    reviewer_id: str | None = None,
) -> ExecuteResolutionOutput:
    """Execute automated ERP dispute resolution.

    Validates inputs strictly with ExecuteResolutionInput.
    Guarantees idempotency by checking idempotency_key against audit_log.
    """
    if isinstance(action, ExecuteResolutionInput):
        validated = action
    else:
        validated = ExecuteResolutionInput(
            action=action,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
            amount=amount,
            rationale=rationale,
            idempotency_key=idempotency_key,
            po_id=po_id,
            reviewer_id=reviewer_id,
        )

    return execute_resolution_from_input(validated)


def execute_resolution_from_input(
    input_data: ExecuteResolutionInput,
) -> ExecuteResolutionOutput:
    """Execute resolution from pre-validated ExecuteResolutionInput model."""
    db = get_default_db()

    # 1. Idempotency Check: Prevent duplicate execution
    existing_entry = db.get_audit_entry_by_idempotency_key(input_data.idempotency_key)
    if existing_entry is not None:
        return ExecuteResolutionOutput(
            success=True,
            action=existing_entry.action,
            invoice_id=existing_entry.invoice_id,
            audit_id=existing_entry.audit_id,
            timestamp=existing_entry.timestamp,
            message=(
                f"Duplicate execution prevented. Prior resolution recorded under "
                f"audit_id={existing_entry.audit_id}."
            ),
        )

    # 2. Existence & Provenance Check: Validate target entities exist in ERP
    invoice = db.get_invoice(input_data.invoice_id)
    if invoice is None:
        raise ValueError(
            f"Target invoice '{input_data.invoice_id}' does not exist in ERP database."
        )

    vendor = db.get_vendor(input_data.vendor_id)
    if vendor is None:
        raise ValueError(
            f"Associated vendor '{input_data.vendor_id}' does not exist in ERP database."
        )

    if input_data.po_id is not None:
        po = db.get_purchase_order(input_data.po_id)
        if po is None:
            raise ValueError(
                f"Associated purchase order '{input_data.po_id}' does not exist in ERP database."
            )

    # 3. Apply state mutation according to ActionType
    match input_data.action:
        case ActionType.RELEASE_PAYMENT:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.APPROVED)
            existing_payment = db.get_payment_for_invoice(input_data.invoice_id)
            if existing_payment is None:
                payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
                db.insert_payment(
                    Payment(
                        payment_id=payment_id,
                        invoice_id=input_data.invoice_id,
                        amount=input_data.amount,
                        payment_date=datetime.now(UTC).date(),
                        status=PaymentStatus.PROCESSING,
                        reference=f"AUTO-RELEASE-{input_data.idempotency_key[:12]}",
                    )
                )

        case ActionType.PARTIAL_PAYMENT:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.APPROVED)
            payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
            db.insert_payment(
                Payment(
                    payment_id=payment_id,
                    invoice_id=input_data.invoice_id,
                    amount=input_data.amount,
                    payment_date=datetime.now(UTC).date(),
                    status=PaymentStatus.SCHEDULED,
                    reference=f"PARTIAL-{input_data.idempotency_key[:12]}",
                )
            )

        case ActionType.CREDIT_NOTE:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.APPROVED)

        case ActionType.REPLACEMENT:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.PENDING)

        case ActionType.REJECT:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.CANCELLED)

        case ActionType.ESCALATE:
            db.update_invoice_status(input_data.invoice_id, InvoiceStatus.DISPUTED)

    # 4. Record entry in audit log
    audit_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
    timestamp = datetime.now(UTC)
    audit_entry = AuditEntry(
        audit_id=audit_id,
        timestamp=timestamp,
        action=input_data.action,
        invoice_id=input_data.invoice_id,
        po_id=input_data.po_id,
        vendor_id=input_data.vendor_id,
        amount=input_data.amount,
        rationale=input_data.rationale,
        idempotency_key=input_data.idempotency_key,
        reviewer_id=input_data.reviewer_id,
    )
    db.insert_audit_entry(audit_entry)

    # 5. Return structured output
    return ExecuteResolutionOutput(
        success=True,
        action=input_data.action,
        invoice_id=input_data.invoice_id,
        audit_id=audit_id,
        timestamp=timestamp,
        message=(
            f"Resolution action '{input_data.action.value}' executed successfully "
            f"for invoice '{input_data.invoice_id}'."
        ),
    )
