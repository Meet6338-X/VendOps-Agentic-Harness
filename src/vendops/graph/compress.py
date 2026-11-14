import re
from typing import Any

from vendops.contracts.ids import extract_all_ids

AMOUNT_REGEX: re.Pattern[str] = re.compile(
    r"(?:(?:\$|₹|INR|USD|EUR|Rs\.?|Rupees)\s*)?\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b|"
    r"(?:(?:\$|₹|INR|USD|EUR|Rs\.?|Rupees)\s*)\b\d+(?:\.\d{1,2})?\b|"
    r"\b\d+\.\d{2}\b",
    re.IGNORECASE,
)

DATE_REGEX: re.Pattern[str] = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
    re.IGNORECASE,
)


def estimate_token_count(text: str) -> int:
    """Estimate token count accounting for non-Latin script fertility."""
    if not text.strip():
        return 0

    tokens = 0
    words = text.split()
    for word in words:
        has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in word)
        has_non_ascii = any(ord(ch) > 127 for ch in word)

        if has_devanagari:
            # Subword tokenizers produce 2-4 tokens per Devanagari character
            tokens += max(len(word) * 2, 2)
        elif has_non_ascii:
            tokens += max(len(word), 2)
        else:
            # Standard English: ~4 characters per token
            tokens += max(1, (len(word) + 3) // 4)

    return max(1, tokens)


def calculate_token_fertility(text: str) -> float:
    """Calculate token fertility (tokens per word) for a given text or message."""
    words = text.strip().split()
    if not words:
        return 1.0
    token_count = estimate_token_count(text)
    return round(token_count / len(words), 3)


def extract_preserved_entities(
    text: str, vendor_names: list[str] | None = None
) -> dict[str, list[str]]:
    """Extract all entity IDs, amounts, dates, and vendor names that must survive compression."""
    all_ids_dict = extract_all_ids(text)
    combined_ids: list[str] = []
    for id_list in all_ids_dict.values():
        combined_ids.extend(id_list)
    # Deduplicate while preserving order
    unique_ids: list[str] = list(dict.fromkeys(combined_ids))

    # Amounts
    raw_amounts = AMOUNT_REGEX.findall(text)
    # Filter out standalone numbers that are merely sub-components of IDs
    cleaned_amounts: list[str] = []
    for amt in raw_amounts:
        amt_str = amt.strip()
        if not any(amt_str in canonical_id for canonical_id in unique_ids):
            cleaned_amounts.append(amt_str)
    unique_amounts = list(dict.fromkeys(cleaned_amounts))

    # Dates
    raw_dates = DATE_REGEX.findall(text)
    unique_dates = list(dict.fromkeys([d.strip() for d in raw_dates]))

    # Vendor names
    found_vendors: list[str] = []
    if vendor_names:
        for v in vendor_names:
            if re.search(rf"\b{re.escape(v)}\b", text, re.IGNORECASE):
                found_vendors.append(v)
    unique_vendors = list(dict.fromkeys(found_vendors))

    return {
        "ids": unique_ids,
        "amounts": unique_amounts,
        "dates": unique_dates,
        "vendors": unique_vendors,
    }


def compress_text(
    text: str,
    token_budget: int = 200,
    vendor_names: list[str] | None = None,
) -> str:
    """Adaptively compress text when exceeding token budget while strictly preserving entities."""
    if estimate_token_count(text) <= token_budget:
        return text

    entities = extract_preserved_entities(text, vendor_names=vendor_names)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip()]

    # Categorize sentences
    critical_sentences: list[str] = []
    secondary_sentences: list[str] = []

    for s in sentences:
        has_id = any(item in s for item in entities["ids"])
        has_amount = any(item in s for item in entities["amounts"])
        has_date = any(item in s for item in entities["dates"])
        has_vendor = any(item in s for item in entities["vendors"])

        if has_id or has_amount or has_date or has_vendor:
            critical_sentences.append(s)
        else:
            # Check for domain keywords
            if any(
                kw in s.lower()
                for kw in (
                    "invoice",
                    "payment",
                    "grn",
                    "order",
                    "po",
                    "dispute",
                    "deliver",
                    "received",
                    "accepted",
                    "billed",
                    "delay",
                    "short",
                    "mismatch",
                )
            ):
                secondary_sentences.append(s)

    # Build compressed text prioritizing critical sentences
    selected = list(critical_sentences)
    current_tokens = estimate_token_count(" ".join(selected))

    for s in secondary_sentences:
        s_tokens = estimate_token_count(s)
        if current_tokens + s_tokens <= token_budget:
            selected.append(s)
            current_tokens += s_tokens

    # Verify all preserved entities are present in result
    result = " ".join(selected)
    missing_ids = [i for i in entities["ids"] if i not in result]
    missing_amounts = [a for a in entities["amounts"] if a not in result]
    missing_dates = [d for d in entities["dates"] if d not in result]
    missing_vendors = [v for v in entities["vendors"] if v not in result]

    # If any entity is missing or if still over budget, append guaranteed entity header
    if missing_ids or missing_amounts or missing_dates or missing_vendors:
        header_parts: list[str] = []
        if entities["ids"]:
            header_parts.append(f"IDs: {', '.join(entities['ids'])}")
        if entities["amounts"]:
            header_parts.append(f"Amounts: {', '.join(entities['amounts'])}")
        if entities["dates"]:
            header_parts.append(f"Dates: {', '.join(entities['dates'])}")
        if entities["vendors"]:
            header_parts.append(f"Vendors: {', '.join(entities['vendors'])}")
        entity_header = "[Preserved: " + " | ".join(header_parts) + "]"
        result = f"{entity_header}\n{result}"

    return result.strip()


def compress_messages(
    messages: list[dict[str, Any]],
    token_budget: int = 1000,
    vendor_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compress older thread messages while preserving latest message and critical entities."""
    total_tokens = sum(
        estimate_token_count(str(m.get("content", ""))) for m in messages
    )
    if total_tokens <= token_budget or not messages:
        return messages

    # Always preserve the most recent message verbatim
    latest_message = messages[-1]
    history_messages = messages[:-1]

    per_message_budget = max(50, (token_budget // max(1, len(messages))))
    compressed_history: list[dict[str, Any]] = []

    for msg in history_messages:
        content = str(msg.get("content", ""))
        compressed_content = compress_text(
            content, token_budget=per_message_budget, vendor_names=vendor_names
        )
        new_msg = dict(msg)
        new_msg["content"] = compressed_content
        compressed_history.append(new_msg)

    compressed_history.append(latest_message)
    return compressed_history
