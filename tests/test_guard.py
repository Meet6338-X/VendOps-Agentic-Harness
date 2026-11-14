import pytest

from vendops.contracts.enums import ActionType
from vendops.contracts.schemas import ExecuteResolutionInput
from vendops.guard.provenance import ProvenanceValidator, ProvenanceViolation
from vendops.guard.validate import ToolCallValidationError, ToolCallValidator


def test_provenance_extract_from_text() -> None:
    text = (
        "Hello, checking status of INV-20240456 and PO-20240123. "
        "Also received GRN-20240789 for vendor VND-000123."
    )
    ids = ProvenanceValidator.extract_from_text(text)
    assert ids == {"INV-20240456", "PO-20240123", "GRN-20240789", "VND-000123"}


def test_provenance_extract_from_erp_data() -> None:
    erp_payload = {
        "invoice": {
            "invoice_id": "INV-20240456",
            "po_id": "PO-20240123",
            "vendor_id": "VND-000123",
            "status": "PENDING",
        },
        "grn": {
            "grn_id": "GRN-20240789",
            "po_id": "PO-20240123",
            "vendor_id": "VND-000123",
        },
    }
    ids = ProvenanceValidator.extract_from_erp_data(erp_payload)
    assert ids == {"INV-20240456", "PO-20240123", "VND-000123", "GRN-20240789"}


def test_provenance_valid_tool_call() -> None:
    allowed = {"INV-20240456", "PO-20240123"}
    valid, violation = ProvenanceValidator.validate_tool_call(
        tool_name="get_invoice",
        arguments={"invoice_id": "INV-20240456"},
        allowed_ids=allowed,
    )
    assert valid is True
    assert violation is None


def test_provenance_blocks_hallucinated_id_and_returns_structured_error() -> None:
    allowed = {"INV-20240456"}
    hallucinated_args = {"invoice_id": "INV-99999999"}

    valid, violation = ProvenanceValidator.validate_tool_call(
        tool_name="get_invoice",
        arguments=hallucinated_args,
        allowed_ids=allowed,
        current_repair_attempts=0,
    )

    assert valid is False
    assert isinstance(violation, ProvenanceViolation)
    assert violation.rejected_id == "INV-99999999"
    assert violation.id_type == "INVOICE"
    assert violation.allowed_ids == ["INV-20240456"]
    assert violation.repair_attempts == 1
    assert violation.must_escalate is False
    assert "Provenance violation in tool 'get_invoice'" in violation.message


def test_provenance_maximum_two_repair_attempts_escalates() -> None:
    allowed = {"INV-20240456"}
    hallucinated_args = {"invoice_id": "INV-88888888"}

    # Second failed attempt
    valid, violation = ProvenanceValidator.validate_tool_call(
        tool_name="get_invoice",
        arguments=hallucinated_args,
        allowed_ids=allowed,
        current_repair_attempts=1,
    )

    assert valid is False
    assert violation is not None
    assert violation.repair_attempts == 2
    assert violation.must_escalate is True
    assert "Repair attempt 2/2" in violation.message


def test_provenance_never_silently_coerces() -> None:
    allowed = {"INV-20240456"}
    hallucinated_args = {"invoice_id": "INV-00000000"}

    valid, violation = ProvenanceValidator.validate_tool_call(
        tool_name="get_invoice",
        arguments=hallucinated_args,
        allowed_ids=allowed,
    )

    assert valid is False
    assert violation is not None
    # Ensure the hallucinated ID is recorded as rejected, never coerced to an allowed ID
    assert violation.rejected_id == "INV-00000000"
    assert hallucinated_args["invoice_id"] == "INV-00000000"


def test_tool_validator_schema_extra_forbid() -> None:
    # Extra parameters are strictly forbidden
    with pytest.raises(ToolCallValidationError) as exc_info:
        ToolCallValidator.validate_schema(
            "get_invoice",
            {"invoice_id": "INV-20240456", "unexpected_field": "disallowed"},
        )
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_tool_validator_rejects_free_text_mutation_actions() -> None:
    # Mutation action must be strict ActionType enum
    with pytest.raises(ToolCallValidationError) as exc_info:
        ToolCallValidator.validate_schema(
            "execute_resolution",
            {
                "action": "CUSTOM_FREE_TEXT_ACTION",
                "invoice_id": "INV-20240456",
                "vendor_id": "VND-000123",
                "amount": 5000.0,
                "rationale": "Arbitrary mutation rationale",
                "idempotency_key": "idemp_1234567890abcdef",
            },
        )
    assert "Free-text mutations are strictly forbidden" in str(exc_info.value)


def test_tool_validator_accepts_valid_action_enum() -> None:
    model = ToolCallValidator.validate_schema(
        "execute_resolution",
        {
            "action": ActionType.RELEASE_PAYMENT,
            "invoice_id": "INV-20240456",
            "vendor_id": "VND-000123",
            "amount": 50000.0,
            "rationale": "Verified 3-way match",
            "idempotency_key": "idemp_1234567890abcdef",
        },
    )
    assert isinstance(model, ExecuteResolutionInput)
    assert model.action == ActionType.RELEASE_PAYMENT
