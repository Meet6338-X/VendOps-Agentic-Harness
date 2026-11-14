import re
from typing import Any

from vendops.contracts.enums import DisputePriority, DisputeType
from vendops.contracts.schemas import TriageResult
from vendops.contracts.state import VendOpsState
from vendops.graph.compress import extract_preserved_entities
from vendops.graph.llm import BaseLLMAdapter

SHORT_PAY_KEYWORDS = re.compile(
    r"\b(short\s*pay(?:ment)?|kam\s*paise|less\s*amount|deducted|partial|kam\s*mila)\b",
    re.IGNORECASE,
)
QTY_MISMATCH_KEYWORDS = re.compile(
    r"\b(qty\s*mismatch|quantity|units?\s*missing|short\s*delivery|kam\s*pieces?|kam\s*quantity|pieces?\s*kam)\b",
    re.IGNORECASE,
)
PRICE_MISMATCH_KEYWORDS = re.compile(
    r"\b(price\s*mismatch|rate\s*diff(?:erence)?|higher\s*rate|wrong\s*rate|unit\s*price)\b",
    re.IGNORECASE,
)
MISSING_GRN_KEYWORDS = re.compile(
    r"\b(grn\s*missing|grn\s*nahi|receipt\s*missing|no\s*grn|grn\s*pending)\b",
    re.IGNORECASE,
)
DUPLICATE_KEYWORDS = re.compile(
    r"\b(duplicate|already\s*submitted|double\s*bill(?:ing)?)\b",
    re.IGNORECASE,
)
PAYMENT_DELAY_KEYWORDS = re.compile(
    r"\b(delay(?:ed)?|nahi\s*aaya|not\s*received|pending\s*payment|overdue|kab\s*milega|kab\s*aayega|payment\s*due)\b",
    re.IGNORECASE,
)
URGENT_KEYWORDS = re.compile(
    r"\b(urgent|immediately|emergency|legal|stop\s*supply|stop\s*delivery|asap)\b",
    re.IGNORECASE,
)


def classify_dispute_heuristically(
    message: str,
    extracted_ids: list[str],
    disputed_amount: float | None = None,
    vendor_name: str | None = None,
) -> TriageResult:
    """Deterministic fallback triage classifier for offline testing and evals."""
    lower_msg = message.lower()

    # Determine dispute type
    if SHORT_PAY_KEYWORDS.search(lower_msg):
        dtype = DisputeType.SHORT_PAYMENT
    elif QTY_MISMATCH_KEYWORDS.search(lower_msg):
        dtype = DisputeType.QTY_MISMATCH
    elif PRICE_MISMATCH_KEYWORDS.search(lower_msg):
        dtype = DisputeType.PRICE_MISMATCH
    elif MISSING_GRN_KEYWORDS.search(lower_msg):
        dtype = DisputeType.MISSING_GRN
    elif DUPLICATE_KEYWORDS.search(lower_msg):
        dtype = DisputeType.DUPLICATE_INVOICE
    elif PAYMENT_DELAY_KEYWORDS.search(lower_msg) or any(
        i.startswith("INV-") for i in extracted_ids
    ):
        dtype = DisputeType.PAYMENT_DELAY
    else:
        dtype = DisputeType.OTHER

    # Determine priority
    amt = disputed_amount or 0.0
    if URGENT_KEYWORDS.search(lower_msg) or amt >= 100_000.0:
        priority = DisputePriority.URGENT
    elif amt >= 50_000.0:
        priority = DisputePriority.HIGH
    elif amt >= 10_000.0:
        priority = DisputePriority.MEDIUM
    else:
        priority = DisputePriority.LOW

    # Generate summary
    id_str = ", ".join(extracted_ids) if extracted_ids else "unspecified invoice"
    summary = f"Dispute classified as {dtype.value} with priority {priority.value} for {id_str}."

    return TriageResult(
        dispute_type=dtype,
        priority=priority,
        confidence=0.95,
        extracted_ids=extracted_ids,
        vendor_name=vendor_name,
        disputed_amount=disputed_amount,
        summary=summary,
    )


def triage_node(
    state: VendOpsState, llm: BaseLLMAdapter | None = None
) -> dict[str, Any]:
    """Triage node: classify DisputeType, priority, and extract entities into TriageResult."""
    message = state.get("normalized_message", "")
    extracted_ids = list(state.get("provenance_ids", []))

    # Extract amounts and entities
    entities = extract_preserved_entities(message)
    disputed_amount: float | None = None
    if entities["amounts"]:
        # Parse first numeric amount
        raw_amt = entities["amounts"][0]
        cleaned_num = re.sub(r"[^\d.]", "", raw_amt)
        try:
            disputed_amount = float(cleaned_num)
        except ValueError:
            disputed_amount = None

    vendor_name = entities["vendors"][0] if entities["vendors"] else None

    # Check for vendor name heuristics if none matched
    if not vendor_name:
        vnd_match = re.search(
            r"\bvendor\s+([A-Za-z0-9\s]+?)(?:\s+reported|\s+says|\s+regarding|\s+INV|\s+PO|\s*$)",
            message,
            re.IGNORECASE,
        )
        if vnd_match:
            cand = vnd_match.group(1).strip()
            if len(cand) <= 50 and not cand.startswith("VND-"):
                vendor_name = cand

    # Attempt structured generation via LLM if provided
    triage_result: TriageResult
    if llm is not None:
        try:
            prompt = (
                f"Classify this vendor dispute and extract entities:\n"
                f"Message: {message}\n"
                f"Extracted IDs: {extracted_ids}\n"
                f"Disputed Amount: {disputed_amount}\n"
                f"Vendor: {vendor_name}"
            )
            triage_result = llm.generate_structured(prompt, TriageResult)
        except (ValueError, RuntimeError, TypeError):
            # Fall back deterministically
            triage_result = classify_dispute_heuristically(
                message=message,
                extracted_ids=extracted_ids,
                disputed_amount=disputed_amount,
                vendor_name=vendor_name,
            )
    else:
        triage_result = classify_dispute_heuristically(
            message=message,
            extracted_ids=extracted_ids,
            disputed_amount=disputed_amount,
            vendor_name=vendor_name,
        )

    return {"triage": triage_result}
