import pytest
from pydantic import ValidationError

from vendops.contracts import (
    ActionType,
    DisputeType,
    ExecuteResolutionInput,
    GetInvoiceInput,
    ResolutionProposal,
    TriageResult,
    extract_all_ids,
    is_valid_grn_id,
    is_valid_invoice_id,
    is_valid_po_id,
    is_valid_vendor_id,
    normalize_id,
)


def test_id_normalization_and_validation() -> None:
    assert normalize_id(" inv-20240456 ") == "INV-20240456"
    assert is_valid_invoice_id("INV-20240456")
    assert not is_valid_invoice_id("INV-2024")
    assert not is_valid_invoice_id("INV-20240456X")

    assert is_valid_po_id("PO-20240123")
    assert not is_valid_po_id("PO-123")

    assert is_valid_grn_id("GRN-20240789")
    assert not is_valid_grn_id("GRN-999")

    assert is_valid_vendor_id("VND-000123")
    assert not is_valid_vendor_id("VND-123")


def test_extract_all_ids_from_mixed_text() -> None:
    text = (
        "Bhai INV-20240456 ka payment abhi tak nahi aaya, "
        "PO-20240123 ke against 50 units deliver kar diye the, "
        "GRN-20240789 bhi ho gaya vendor VND-000123."
    )
    extracted = extract_all_ids(text)
    assert extracted["invoice_ids"] == ["INV-20240456"]
    assert extracted["po_ids"] == ["PO-20240123"]
    assert extracted["grn_ids"] == ["GRN-20240789"]
    assert extracted["vendor_ids"] == ["VND-000123"]


def test_schema_extra_forbid() -> None:
    # Valid input
    inp = GetInvoiceInput(invoice_id="INV-20240456")
    assert inp.invoice_id == "INV-20240456"

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        GetInvoiceInput(invoice_id="INV-20240456", extra_field="forbidden")  # type: ignore[call-arg]


def test_execute_resolution_input_action_enum() -> None:
    res = ExecuteResolutionInput(
        action=ActionType.RELEASE_PAYMENT,
        invoice_id="INV-20240456",
        vendor_id="VND-000123",
        amount=50000.0,
        rationale="3-way match verified successfully against PO and GRN",
        idempotency_key="idemp_1234567890abcdef",
    )
    assert res.action == ActionType.RELEASE_PAYMENT

    # Free-text invalid action rejected
    with pytest.raises(ValidationError):
        ExecuteResolutionInput(
            action="FREE_TEXT_ACTION",  # type: ignore[arg-type]
            invoice_id="INV-20240456",
            vendor_id="VND-000123",
            amount=50000.0,
            rationale="Invalid action",
            idempotency_key="idemp_1234567890abcdef",
        )


def test_resolution_proposal_validation() -> None:
    prop = ResolutionProposal(
        action=ActionType.PARTIAL_PAYMENT,
        amount=12500.50,
        rationale="GRN shows 25 units accepted out of 50 units billed.",
        evidence=["GRN-20240789 accepted 25 units", "Unit price $500.02"],
        confidence=0.98,
    )
    assert prop.confidence == 0.98
    assert prop.amount == 12500.50

    # Negative amount forbidden
    with pytest.raises(ValidationError):
        ResolutionProposal(
            action=ActionType.PARTIAL_PAYMENT,
            amount=-100.0,
            rationale="Invalid negative amount",
            evidence=["None"],
            confidence=0.5,
        )


def test_triage_result_validation() -> None:
    triage = TriageResult(
        dispute_type=DisputeType.PAYMENT_DELAY,
        priority="HIGH",  # type: ignore[arg-type]
        confidence=0.95,
        extracted_ids=["INV-20240456"],
        vendor_name="Acme Supplies",
        disputed_amount=50000.0,
        summary="Vendor reports payment delayed for invoice INV-20240456.",
    )
    assert triage.dispute_type == DisputeType.PAYMENT_DELAY
