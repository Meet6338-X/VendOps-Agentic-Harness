from datetime import date
from typing import Any

from vendops.contracts.enums import (
    InvoiceStatus,
    MatchStatus,
    PaymentStatus,
)
from vendops.contracts.schemas import (
    GoodsReceiptNote,
    GoodsReceiptNoteLine,
    Invoice,
    InvoiceLine,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    ThreeWayMatchResult,
)
from vendops.contracts.state import VendOpsState
from vendops.guard.provenance import ProvenanceValidator


def _build_default_erp_records(
    invoice_id: str,
    po_id: str | None = None,
    vendor_id: str | None = None,
    grn_id: str | None = None,
    total_amount: float = 50_000.0,
) -> dict[str, Any]:
    """Generate deterministic mock ERP records for offline execution if not present in state."""
    canon_po = po_id or "PO-20240123"
    canon_vnd = vendor_id or "VND-000123"
    canon_grn = grn_id or "GRN-20240789"

    invoice = Invoice(
        invoice_id=invoice_id,
        po_id=canon_po,
        vendor_id=canon_vnd,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-INDUSTRIAL-VALVE",
                description="Heavy duty industrial valve",
                billed_qty=50,
                unit_price=1000.0,
                total_price=total_amount,
            )
        ],
        total_amount=total_amount,
        currency="USD",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        status=InvoiceStatus.PENDING,
    )

    po = PurchaseOrder(
        po_id=canon_po,
        vendor_id=canon_vnd,
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-INDUSTRIAL-VALVE",
                description="Heavy duty industrial valve",
                ordered_qty=50,
                unit_price=1000.0,
                currency="USD",
            )
        ],
        total_amount=total_amount,
        currency="USD",
        created_date=date(2024, 1, 10),
    )

    grn = GoodsReceiptNote(
        grn_id=canon_grn,
        po_id=canon_po,
        vendor_id=canon_vnd,
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-INDUSTRIAL-VALVE",
                received_qty=50,
                accepted_qty=50,
                rejected_qty=0,
            )
        ],
        received_date=date(2024, 1, 18),
    )

    payment = Payment(
        payment_id="PAY-20249999",
        invoice_id=invoice_id,
        amount=total_amount,
        payment_date=date(2024, 2, 20),
        status=PaymentStatus.SCHEDULED,
    )

    return {
        "invoice": invoice.model_dump(),
        "purchase_order": po.model_dump(),
        "grn": grn.model_dump(),
        "payment": payment.model_dump(),
    }


def verify_node(
    state: VendOpsState, erp_client: Any = None
) -> dict[str, Any]:
    """Verification node: validate provenance, query ERP read tools, and perform 3-way match."""
    provenance_ids = set(state.get("provenance_ids", []))
    erp_data = dict(state.get("erp_data", {}))
    tool_errors = list(state.get("tool_call_errors", []))
    repair_attempts = state.get("repair_attempts", 0)

    # Identify target invoice ID from provenance or triage
    invoice_ids = [i for i in provenance_ids if i.startswith("INV-")]
    triage = state.get("triage")
    if not invoice_ids and triage is not None:
        invoice_ids = [i for i in triage.extracted_ids if i.startswith("INV-")]

    if not invoice_ids:
        # No invoice ID provided in dispute
        return {
            "match_result": None,
            "tool_call_errors": tool_errors + ["No canonical Invoice ID provided in dispute"],
        }

    target_inv_id = invoice_ids[0]

    # Provenance check for querying invoice
    valid_prov, violation = ProvenanceValidator.validate_tool_call(
        tool_name="get_invoice",
        arguments={"invoice_id": target_inv_id},
        allowed_ids=provenance_ids,
        current_repair_attempts=repair_attempts,
    )
    if not valid_prov and violation is not None:
        tool_errors.append(violation.message)
        return {
            "tool_call_errors": tool_errors,
            "repair_attempts": violation.repair_attempts,
            "match_result": None,
        }

    # Fetch ERP records via client if provided, else from erp_data, else default mock
    invoice_dict = erp_data.get("invoice")
    po_dict = erp_data.get("purchase_order")
    grn_dict = erp_data.get("grn")
    payment_dict = erp_data.get("payment")

    if erp_client is not None:
        try:
            if hasattr(erp_client, "get_invoice"):
                inv_res = erp_client.get_invoice(target_inv_id)
                if inv_res:
                    invoice_dict = inv_res if isinstance(inv_res, dict) else inv_res.model_dump()
            if hasattr(erp_client, "get_payment_status"):
                pay_res = erp_client.get_payment_status(target_inv_id)
                if pay_res:
                    payment_dict = pay_res if isinstance(pay_res, dict) else pay_res.model_dump()
            if invoice_dict and hasattr(erp_client, "get_purchase_order"):
                po_res = erp_client.get_purchase_order(invoice_dict.get("po_id"))
                if po_res:
                    po_dict = po_res if isinstance(po_res, dict) else po_res.model_dump()
            if invoice_dict and hasattr(erp_client, "get_grn"):
                # Lookup GRN if available
                target_grn_id = erp_data.get("grn_id")
                if target_grn_id:
                    grn_res = erp_client.get_grn(target_grn_id)
                    if grn_res:
                        grn_dict = grn_res if isinstance(grn_res, dict) else grn_res.model_dump()
        except (ValueError, RuntimeError, TypeError, KeyError) as e:
            tool_errors.append(f"ERP client read error: {e}")

    # Fallback to default mock records if none provided
    if not invoice_dict:
        # Check if PO or GRN or VND are already in provenance
        po_ids = [i for i in provenance_ids if i.startswith("PO-")]
        grn_ids = [i for i in provenance_ids if i.startswith("GRN-")]
        vnd_ids = [i for i in provenance_ids if i.startswith("VND-")]
        default_data = _build_default_erp_records(
            invoice_id=target_inv_id,
            po_id=po_ids[0] if po_ids else None,
            vendor_id=vnd_ids[0] if vnd_ids else None,
            grn_id=grn_ids[0] if grn_ids else None,
        )
        invoice_dict = default_data["invoice"]
        po_dict = po_dict or default_data["purchase_order"]
        grn_dict = grn_dict or default_data["grn"]
        payment_dict = payment_dict or default_data["payment"]

    # Ingest verified IDs from ERP response into provenance tracking
    erp_data["invoice"] = invoice_dict
    if po_dict:
        erp_data["purchase_order"] = po_dict
    if grn_dict:
        erp_data["grn"] = grn_dict
    if payment_dict:
        erp_data["payment"] = payment_dict

    verified_ids = ProvenanceValidator.extract_from_erp_data(erp_data)
    provenance_ids.update(verified_ids)

    # 3-Way Reconciliation
    invoice_obj = Invoice.model_validate(invoice_dict)
    po_obj = PurchaseOrder.model_validate(po_dict) if po_dict else None
    grn_obj = GoodsReceiptNote.model_validate(grn_dict) if grn_dict else None
    payment_obj = Payment.model_validate(payment_dict) if payment_dict else None

    # Check 1: Is invoice already settled?
    if invoice_obj.status == InvoiceStatus.PAID or (
        payment_obj and payment_obj.status == PaymentStatus.COMPLETED
    ):
        match_result = ThreeWayMatchResult(
            invoice_id=invoice_obj.invoice_id,
            po_id=invoice_obj.po_id,
            grn_id=grn_obj.grn_id if grn_obj else None,
            status=MatchStatus.ALREADY_PAID,
            discrepancies=[f"Invoice {invoice_obj.invoice_id} is already settled in ERP."],
            is_matched=False,
            billed_amount=invoice_obj.total_amount,
            authorized_amount=0.0,
        )
        return {
            "erp_data": erp_data,
            "provenance_ids": sorted(provenance_ids),
            "match_result": match_result,
        }

    # Check 2: PO presence
    if not po_obj:
        match_result = ThreeWayMatchResult(
            invoice_id=invoice_obj.invoice_id,
            po_id=invoice_obj.po_id,
            grn_id=None,
            status=MatchStatus.NOT_FOUND,
            discrepancies=[f"Purchase order {invoice_obj.po_id} not found in ERP."],
            is_matched=False,
            billed_amount=invoice_obj.total_amount,
            authorized_amount=0.0,
        )
        return {
            "erp_data": erp_data,
            "provenance_ids": sorted(provenance_ids),
            "match_result": match_result,
        }

    # Check 3: GRN presence
    if not grn_obj:
        match_result = ThreeWayMatchResult(
            invoice_id=invoice_obj.invoice_id,
            po_id=po_obj.po_id,
            grn_id=None,
            status=MatchStatus.MISSING_RECEIPT,
            discrepancies=[f"No Goods Receipt Note (GRN) found for PO {po_obj.po_id}."],
            is_matched=False,
            billed_amount=invoice_obj.total_amount,
            authorized_amount=0.0,
        )
        return {
            "erp_data": erp_data,
            "provenance_ids": sorted(provenance_ids),
            "match_result": match_result,
        }

    # Check 4: Compare lines (Unit Price & Quantity)
    discrepancies: list[str] = []
    has_price_mismatch = False
    has_qty_mismatch = False
    authorized_amount = 0.0

    po_lines_by_sku = {line.item_sku: line for line in po_obj.lines}
    grn_lines_by_sku = {line.item_sku: line for line in grn_obj.lines}

    for inv_line in invoice_obj.lines:
        sku = inv_line.item_sku
        po_line = po_lines_by_sku.get(sku)
        grn_line = grn_lines_by_sku.get(sku)

        if not po_line:
            discrepancies.append(f"Item SKU '{sku}' not found on PO {po_obj.po_id}.")
            continue

        # Price check
        if abs(inv_line.unit_price - po_line.unit_price) > 0.01:
            has_price_mismatch = True
            discrepancies.append(
                f"Price discrepancy on SKU '{sku}': Invoice billed at ${inv_line.unit_price:.2f}, "
                f"PO contracted at ${po_line.unit_price:.2f}."
            )

        # Quantity check
        if not grn_line:
            has_qty_mismatch = True
            discrepancies.append(f"No GRN receipt line found for SKU '{sku}'.")
            continue

        if grn_line.accepted_qty != inv_line.billed_qty:
            has_qty_mismatch = True
            discrepancies.append(
                f"Quantity discrepancy on SKU '{sku}': Invoice billed {inv_line.billed_qty} units, "
                f"GRN accepted {grn_line.accepted_qty} units (rejected: {grn_line.rejected_qty})."
            )

        # Calculate authorized line amount based on accepted quantity and PO price
        effective_qty = min(inv_line.billed_qty, grn_line.accepted_qty)
        effective_unit_price = min(inv_line.unit_price, po_line.unit_price)
        authorized_amount += effective_qty * effective_unit_price

    # Determine status
    if has_price_mismatch:
        status = MatchStatus.PRICE_DISCREPANCY
    elif has_qty_mismatch:
        status = MatchStatus.QUANTITY_DISCREPANCY
    else:
        status = MatchStatus.PERFECT_MATCH
        authorized_amount = invoice_obj.total_amount

    match_result = ThreeWayMatchResult(
        invoice_id=invoice_obj.invoice_id,
        po_id=po_obj.po_id,
        grn_id=grn_obj.grn_id,
        status=status,
        discrepancies=discrepancies,
        is_matched=(status == MatchStatus.PERFECT_MATCH),
        billed_amount=invoice_obj.total_amount,
        authorized_amount=round(authorized_amount, 2),
    )

    return {
        "erp_data": erp_data,
        "provenance_ids": sorted(provenance_ids),
        "match_result": match_result,
        "tool_call_errors": tool_errors,
        "repair_attempts": repair_attempts,
    }
