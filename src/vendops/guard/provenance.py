import re
from typing import Any

from vendops.contracts.ids import (
    GRN_ID_PATTERN,
    INVOICE_ID_PATTERN,
    PO_ID_PATTERN,
    VENDOR_ID_PATTERN,
    extract_all_ids,
    normalize_id,
)
from vendops.contracts.schemas import StrictBaseModel

ID_KEYS: set[str] = {"invoice_id", "po_id", "grn_id", "vendor_id"}
ANY_ID_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:INV-\d{8}|PO-\d{8}|GRN-\d{8}|VND-\d{6})\b", re.IGNORECASE
)


def _get_id_type(canonical_id: str) -> str:
    if re.match(INVOICE_ID_PATTERN, canonical_id):
        return "INVOICE"
    if re.match(PO_ID_PATTERN, canonical_id):
        return "PURCHASE_ORDER"
    if re.match(GRN_ID_PATTERN, canonical_id):
        return "GRN"
    if re.match(VENDOR_ID_PATTERN, canonical_id):
        return "VENDOR"
    return "UNKNOWN"


class ProvenanceViolation(StrictBaseModel):
    """Structured error payload emitted when a tool call contains hallucinated IDs."""

    rejected_id: str
    id_type: str
    allowed_ids: list[str]
    message: str
    repair_attempts: int
    must_escalate: bool


class ProvenanceValidator:
    """Enforces zero-hallucination provenance: all IDs must trace to user input or ERP."""

    @staticmethod
    def extract_from_text(text: str) -> set[str]:
        """Extract all valid normalized IDs from arbitrary text."""
        id_dict = extract_all_ids(text)
        found: set[str] = set()
        for ids in id_dict.values():
            found.update(ids)
        return found

    @staticmethod
    def extract_from_erp_data(data: dict[str, Any] | list[Any]) -> set[str]:
        """Recursively scan ERP payloads for verified entity IDs."""
        found: set[str] = set()

        def _scan(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ID_KEYS and isinstance(v, str):
                        norm = normalize_id(v)
                        if _get_id_type(norm) != "UNKNOWN":
                            found.add(norm)
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)
            elif isinstance(obj, str):
                matches = ANY_ID_PATTERN.findall(obj)
                for m in matches:
                    norm = normalize_id(m)
                    if _get_id_type(norm) != "UNKNOWN":
                        found.add(norm)

        _scan(data)
        return found

    @classmethod
    def validate_tool_call(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_ids: set[str] | list[str],
        current_repair_attempts: int = 0,
    ) -> tuple[bool, ProvenanceViolation | None]:
        """Verify that every entity ID in tool call arguments exists in allowed_ids.

        Never silently coerces hallucinated IDs. Maximum 2 repair attempts before ESCALATE.
        """
        allowed_set = {normalize_id(i) for i in allowed_ids}

        # Scan arguments for any ID
        candidate_ids: set[str] = set()
        for k, v in arguments.items():
            if k in ID_KEYS and isinstance(v, str):
                candidate_ids.add(normalize_id(v))
            elif isinstance(v, str):
                for match in ANY_ID_PATTERN.findall(v):
                    candidate_ids.add(normalize_id(match))

        for cid in candidate_ids:
            if cid not in allowed_set:
                new_attempts = current_repair_attempts + 1
                must_escalate = new_attempts >= 2
                violation = ProvenanceViolation(
                    rejected_id=cid,
                    id_type=_get_id_type(cid),
                    allowed_ids=sorted(allowed_set),
                    message=(
                        f"Provenance violation in tool '{tool_name}': ID '{cid}' does not exist "
                        f"in user input or verified ERP state. Allowed IDs: {sorted(allowed_set)}. "
                        f"Repair attempt {new_attempts}/2."
                    ),
                    repair_attempts=new_attempts,
                    must_escalate=must_escalate,
                )
                return False, violation

        return True, None
