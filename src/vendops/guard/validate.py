from typing import Any

from pydantic import ValidationError

from vendops.contracts.enums import ActionType
from vendops.contracts.schemas import (
    ExecuteResolutionInput,
    GetGRNInput,
    GetInvoiceInput,
    GetPaymentStatusInput,
    GetPurchaseOrderInput,
    GetVendorInput,
    StrictBaseModel,
)
from vendops.guard.provenance import ProvenanceValidator, ProvenanceViolation

TOOL_SCHEMA_REGISTRY: dict[str, type[StrictBaseModel]] = {
    "get_invoice": GetInvoiceInput,
    "get_purchase_order": GetPurchaseOrderInput,
    "get_grn": GetGRNInput,
    "get_vendor": GetVendorInput,
    "get_payment_status": GetPaymentStatusInput,
    "execute_resolution": ExecuteResolutionInput,
}


class ToolCallValidationError(ValueError):
    """Raised when a tool call violates schema validation or extra-fields prohibition."""


class ToolCallValidator:
    """Strict schema validator for all tool parameters enforcing extra='forbid' and enum safety."""

    @classmethod
    def validate_schema(
        cls, tool_name: str, arguments: dict[str, Any]
    ) -> StrictBaseModel:
        """Validate tool arguments against the target contract model with extra='forbid'."""
        schema_cls = TOOL_SCHEMA_REGISTRY.get(tool_name)
        if schema_cls is None:
            raise ToolCallValidationError(f"Unknown or uncontracted tool: '{tool_name}'")

        # For execute_resolution, enforce ActionType enum strictly
        if tool_name == "execute_resolution":
            action_val = arguments.get("action")
            if isinstance(action_val, str):
                try:
                    arguments["action"] = ActionType(action_val)
                except ValueError:
                    valid_actions = [a.value for a in ActionType]
                    raise ToolCallValidationError(
                        f"Invalid action '{action_val}'. Mutation actions must be one of {valid_actions}. "
                        "Free-text mutations are strictly forbidden."
                    )

        try:
            return schema_cls.model_validate(arguments)
        except ValidationError as e:
            raise ToolCallValidationError(
                f"Schema validation failed for tool '{tool_name}': {e}"
            ) from e

    @classmethod
    def validate_tool_call_full(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_ids: set[str] | list[str],
        current_repair_attempts: int = 0,
    ) -> tuple[StrictBaseModel, ProvenanceViolation | None]:
        """Validate both schema conformance (extra='forbid') and ID provenance."""
        validated_model = cls.validate_schema(tool_name, arguments)
        valid_prov, violation = ProvenanceValidator.validate_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            allowed_ids=allowed_ids,
            current_repair_attempts=current_repair_attempts,
        )
        if not valid_prov:
            return validated_model, violation
        return validated_model, None
