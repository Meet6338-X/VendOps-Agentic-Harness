import pytest
from pydantic import ValidationError

from vendops.contracts.enums import ActionType
from vendops.contracts.schemas import (
    ExecuteResolutionInput,
    GetInvoiceInput,
    ResolutionProposal,
)
from vendops.guard.validate import ToolCallValidationError, ToolCallValidator


def test_extra_fields_rejected_by_tool_validator() -> None:
    """Extra unexpected parameters are strictly rejected (extra='forbid')."""
    # Valid payload with extra parameter injected
    payload_with_extra = {
        "invoice_id": "INV-20240101",
        "bypass_security": True,
        "debug_mode": "enable",
    }

    with pytest.raises(ToolCallValidationError):
        ToolCallValidator.validate_schema("get_invoice", payload_with_extra)


def test_free_text_mutation_action_rejected() -> None:
    """Only enum ActionType is allowed for write mutations."""
    with pytest.raises(ValidationError):
        ExecuteResolutionInput(
            action="UNAUTHORIZED_FREE_TEXT_ACTION",  # type: ignore[arg-type]
            invoice_id="INV-20240101",
            vendor_id="VND-000101",
            amount=500.0,
            rationale="Attempting free-text mutation",
            idempotency_key="idemp_random_12345678",
        )


def test_negative_or_overflow_amounts_rejected() -> None:
    """Negative amounts and amounts exceeding upper bounds are rejected."""
    with pytest.raises(ValidationError):
        ResolutionProposal(
            action=ActionType.RELEASE_PAYMENT,
            amount=-500.0,  # Negative
            rationale="Negative refund",
            evidence=["None"],
            confidence=0.9,
        )

    with pytest.raises(ValidationError):
        ResolutionProposal(
            action=ActionType.RELEASE_PAYMENT,
            amount=999_999_999_999.0,  # Exceeds bounded limit
            rationale="Trillion dollar error",
            evidence=["None"],
            confidence=0.9,
        )


def test_malformed_id_patterns_rejected() -> None:
    """Malformed ID patterns that do not match canonical regex are rejected."""
    invalid_ids = [
        "INV-123",          # Too short
        "INV-20240101X",     # Extra char
        "PO_20240101",       # Underscore instead of hyphen
        "GRN-ABCDEFGH",      # Non-numeric digits
        "VND-12345",         # 5 digits instead of 6
        "",                  # Empty
        "   ",               # Whitespace
        "INV-20240101;--",   # Injection attempt
    ]

    for bad_id in invalid_ids:
        with pytest.raises(ValidationError):
            GetInvoiceInput(invoice_id=bad_id)
