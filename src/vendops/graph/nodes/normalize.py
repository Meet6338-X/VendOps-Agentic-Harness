import re
from typing import Any

from vendops.contracts.enums import LanguageCode
from vendops.contracts.ids import extract_all_ids, normalize_id
from vendops.contracts.state import VendOpsState

DEVANAGARI_DIGITS_MAP: dict[str, str] = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}

HINGLISH_KEYWORDS: set[str] = {
    "bhai",
    "bhaiya",
    "nahi",
    "nahin",
    "nhi",
    "aaya",
    "aya",
    "kripya",
    "kripaya",
    "kab",
    "karo",
    "karna",
    "kar",
    "diya",
    "diye",
    "hoga",
    "hogi",
    "hua",
    "shukriya",
    "dhanyawad",
    "paise",
    "pese",
    "rupaye",
    "maal",
    "bheja",
    "bheji",
    "mil",
    "gaya",
    "gayi",
    "kitna",
    "rakha",
    "baaki",
    "baki",
    "abhi",
    "tak",
    "tha",
    "the",
    "thi",
    "aur",
    "ka",
    "ki",
    "ke",
    "ko",
    "se",
    "par",
    "humne",
    "aapka",
    "aapke",
    "kijiye",
}

HINGLISH_SPELLING_NORMALIZATION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(nhi|nahin|naahi)\b", re.IGNORECASE), "nahi"),
    (re.compile(r"\b(aya|aayaa)\b", re.IGNORECASE), "aaya"),
    (re.compile(r"\b(bhaiya|bhaijaan)\b", re.IGNORECASE), "bhai"),
    (re.compile(r"\b(kripaya|plz|pls)\b", re.IGNORECASE), "kripya"),
    (re.compile(r"\b(pese|rupay)\b", re.IGNORECASE), "paise"),
    (re.compile(r"\b(baki)\b", re.IGNORECASE), "baaki"),
    (re.compile(r"\b(?:inv(?:oice)?|bill)\s*(?:no\.?|num(?:ber)?|#)\s*", re.IGNORECASE), "INV-"),
    (re.compile(r"\b(?:po|order)\s*(?:no\.?|num(?:ber)?|#)\s*", re.IGNORECASE), "PO-"),
    (re.compile(r"\b(?:grn|receipt)\s*(?:no\.?|num(?:ber)?|#)\s*", re.IGNORECASE), "GRN-"),
]

# Simple Devanagari to Latin transliteration mapping for fallback
DEVANAGARI_TO_LATIN: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "am", "अः": "ah",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "m", "ः": "h", "्": "",
    "।": ".", "॥": ".",
}


def normalize_devanagari_digits(text: str) -> str:
    """Map Devanagari numerals ०-९ to standard ASCII digits 0-9."""
    res: list[str] = []
    for ch in text:
        res.append(DEVANAGARI_DIGITS_MAP.get(ch, ch))
    return "".join(res)


def detect_language(text: str) -> str:
    """Detect whether input message is English, Hindi (Devanagari), Roman Hinglish, or Mixed."""
    has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in text)
    has_latin = any(("a" <= ch.lower() <= "z") for ch in text)

    if has_devanagari and has_latin:
        return LanguageCode.MIXED.value
    if has_devanagari:
        return LanguageCode.HINDI.value

    # Latin text - check for Hinglish markers
    words = [re.sub(r"[^\w]", "", w.lower()) for w in text.split()]
    hinglish_count = sum(1 for w in words if w in HINGLISH_KEYWORDS)
    if hinglish_count >= 1 or (len(words) > 0 and hinglish_count / len(words) >= 0.1):
        return LanguageCode.HINGLISH.value

    return LanguageCode.ENGLISH.value


def normalize_hinglish_text(text: str) -> str:
    """Standardize phonetic variations and common prefixes in Roman Hinglish text."""
    normalized = text
    for pattern, replacement in HINGLISH_SPELLING_NORMALIZATION:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def normalize_node(state: VendOpsState) -> dict[str, Any]:
    """Normalization node: transliteration-tolerant normalizer for Roman Hinglish & Devanagari."""
    msg = state.get("normalized_message", "")

    # 1. Normalize Devanagari digits to ASCII (e.g. INV-२०२४०४५६ -> INV-20240456)
    msg_with_ascii_digits = normalize_devanagari_digits(msg)

    # 2. Detect language / script style
    lang = detect_language(msg_with_ascii_digits)

    # 3. Normalize Hinglish spelling variants
    cleaned_msg = normalize_hinglish_text(msg_with_ascii_digits)

    # 4. Check if any new canonical IDs were revealed by digit normalization
    provenance_ids = list(state.get("provenance_ids", []))
    new_ids_dict = extract_all_ids(cleaned_msg)
    for id_list in new_ids_dict.values():
        for i in id_list:
            norm_i = normalize_id(i)
            if norm_i not in provenance_ids:
                provenance_ids.append(norm_i)

    return {
        "normalized_message": cleaned_msg,
        "language_detected": lang,
        "provenance_ids": provenance_ids,
    }
