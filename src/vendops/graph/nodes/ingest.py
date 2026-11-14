import re
import unicodedata
from typing import Any

from vendops.contracts.ids import extract_all_ids
from vendops.contracts.state import VendOpsState
from vendops.graph.compress import calculate_token_fertility

SIGNATURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)\b(?:thanks(?:\s+and|\s*&)?\s+regards|best\s+regards|warm\s+regards|regards|sincerely|dhanyawad|shukriya|cheers)\b.*$",
        re.DOTALL,
    ),
    re.compile(r"(?i)\b(?:sent\s+from\s+my\s+(?:iphone|android|ipad|outlook|galaxy))\b.*$", re.DOTALL),
    re.compile(r"(?i)---++\s*(?:original\s+message|forwarded\s+message)\s*---+.*$", re.DOTALL),
    re.compile(r"(?i)\b(?:disclaimer|confidentiality\s+notice)\b.*$", re.DOTALL),
]


def strip_signatures(text: str) -> str:
    """Strip common email signatures, mobile footers, and disclaimers."""
    cleaned = text
    for pattern in SIGNATURE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    # Strip trailing phone numbers and boilerplate lines
    lines = cleaned.splitlines()
    filtered_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Drop lines that are purely phone numbers, email addresses, or website links
        if re.match(r"^(\+?\d[\d\s\-\(\)]{7,}\d)$", stripped):
            continue
        if re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", stripped):
            continue
        if re.match(r"^https?://\S+$", stripped):
            continue
        filtered_lines.append(line)

    return "\n".join(filtered_lines).strip()


def ingest_node(state: VendOpsState) -> dict[str, Any]:
    """Ingestion node: normalize unicode, strip signatures, extract candidate tokens & initial provenance."""
    raw_text = state.get("raw_message", "")
    if not raw_text and state.get("messages"):
        # Fall back to content of first user message
        for m in state["messages"]:
            if m.get("role") in ("user", "human") or not m.get("role"):
                raw_text = str(m.get("content", ""))
                break

    # Normalize unicode to NFKC
    normalized_unicode = unicodedata.normalize("NFKC", raw_text)

    # Strip signatures and footers
    cleaned_message = strip_signatures(normalized_unicode)

    # Extract all candidate entity IDs from the message
    id_dict = extract_all_ids(cleaned_message)
    initial_ids: list[str] = []
    for id_list in id_dict.values():
        for i in id_list:
            if i not in initial_ids:
                initial_ids.append(i)

    # Calculate token fertility
    fertility = calculate_token_fertility(cleaned_message)

    return {
        "raw_message": raw_text,
        "normalized_message": cleaned_message,
        "provenance_ids": initial_ids,
        "token_fertility": fertility,
        "tool_call_errors": state.get("tool_call_errors", []),
        "repair_attempts": state.get("repair_attempts", 0),
        "erp_data": state.get("erp_data", {}),
    }
