from vendops.contracts.enums import ActionType
from vendops.guard.provenance import ProvenanceValidator


def test_zero_hallucinated_ids_pass_provenance() -> None:
    """Verify that invented or hallucinated IDs are 100% blocked."""
    legitimate_message = "Payment delayed for invoice INV-20240101 under PO-20240101."
    allowed_ids = ProvenanceValidator.extract_from_text(legitimate_message)

    # Simulated hallucinated tool call with invented GRN and Vendor ID
    hallucinated_tool_call = {
        "invoice_id": "INV-20240101",
        "po_id": "PO-20240101",
        "grn_id": "GRN-20249999",  # Invented!
        "vendor_id": "VND-888888",  # Invented!
    }

    is_valid, violation = ProvenanceValidator.validate_tool_call(
        "get_grn", hallucinated_tool_call, allowed_ids=allowed_ids, current_repair_attempts=0
    )
    assert not is_valid
    assert violation is not None
    assert violation.rejected_id in {"GRN-20249999", "VND-888888"}


def test_max_two_repair_attempts_then_escalate() -> None:
    """Validator enforces max 2 repair attempts before mandatory human escalation."""
    allowed_ids = ProvenanceValidator.extract_from_text("Dispute on INV-20240101.")
    bad_call = {"invoice_id": "INV-20249999"}

    # Attempt 0 (first attempt) -> repair_attempts becomes 1, must_escalate is False
    _, v1 = ProvenanceValidator.validate_tool_call(
        "get_invoice", bad_call, allowed_ids=allowed_ids, current_repair_attempts=0
    )
    assert v1 is not None
    assert not v1.must_escalate
    assert v1.repair_attempts == 1

    # Attempt 1 -> repair_attempts becomes 2, must_escalate is True
    _, v2 = ProvenanceValidator.validate_tool_call(
        "get_invoice", bad_call, allowed_ids=allowed_ids, current_repair_attempts=1
    )
    assert v2 is not None
    assert v2.must_escalate
    assert v2.repair_attempts == 2


def test_provenance_registry_expansion_from_trusted_tool_results() -> None:
    """Valid ERP tool output legally expands provenance registry."""
    allowed_ids = ProvenanceValidator.extract_from_text("Checking invoice INV-20240101.")

    # Prior to lookup, PO-20240101 is not in provenance
    is_valid, _ = ProvenanceValidator.validate_tool_call(
        "get_purchase_order", {"po_id": "PO-20240101"}, allowed_ids=allowed_ids
    )
    assert not is_valid

    # Trusted ERP lookup returns the associated PO-20240101
    trusted_erp_output = {
        "invoice_id": "INV-20240101",
        "po_id": "PO-20240101",
        "vendor_id": "VND-000101",
    }
    extracted_from_erp = ProvenanceValidator.extract_from_erp_data(trusted_erp_output)
    allowed_ids.update(extracted_from_erp)

    # Now PO-20240101 and VND-000101 are verified and allowed
    is_valid_now, _ = ProvenanceValidator.validate_tool_call(
        "get_purchase_order", {"po_id": "PO-20240101"}, allowed_ids=allowed_ids
    )
    assert is_valid_now
    is_write_valid, _ = ProvenanceValidator.validate_tool_call(
        "execute_resolution",
        {
            "action": ActionType.RELEASE_PAYMENT,
            "invoice_id": "INV-20240101",
            "po_id": "PO-20240101",
            "vendor_id": "VND-000101",
            "amount": 1000.0,
            "rationale": "Audit verified",
            "idempotency_key": "idemp_valid_12345678",
        },
        allowed_ids=allowed_ids,
    )
    assert is_write_valid
