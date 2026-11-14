import re
from typing import Annotated

from pydantic import Field

INVOICE_ID_PATTERN = r"^INV-\d{8}$"
PO_ID_PATTERN = r"^PO-\d{8}$"
GRN_ID_PATTERN = r"^GRN-\d{8}$"
VENDOR_ID_PATTERN = r"^VND-\d{6}$"

INVOICE_ID_REGEX: re.Pattern[str] = re.compile(r"\bINV-\d{8}\b", re.IGNORECASE)
PO_ID_REGEX: re.Pattern[str] = re.compile(r"\bPO-\d{8}\b", re.IGNORECASE)
GRN_ID_REGEX: re.Pattern[str] = re.compile(r"\bGRN-\d{8}\b", re.IGNORECASE)
VENDOR_ID_REGEX: re.Pattern[str] = re.compile(r"\bVND-\d{6}\b", re.IGNORECASE)

InvoiceId = Annotated[
    str, Field(pattern=INVOICE_ID_PATTERN, description="Canonical Invoice ID (e.g. INV-20240456)")
]
POId = Annotated[
    str, Field(pattern=PO_ID_PATTERN, description="Canonical Purchase Order ID (e.g. PO-20240123)")
]
GRNId = Annotated[
    str, Field(pattern=GRN_ID_PATTERN, description="Canonical Goods Receipt Note ID (e.g. GRN-20240789)")
]
VendorId = Annotated[
    str, Field(pattern=VENDOR_ID_PATTERN, description="Canonical Vendor ID (e.g. VND-000123)")
]


def normalize_id(id_str: str) -> str:
    """Normalize ID string to uppercase with standard hyphen."""
    cleaned = id_str.strip().upper()
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    return cleaned


def is_valid_invoice_id(val: str) -> bool:
    return bool(re.match(INVOICE_ID_PATTERN, normalize_id(val)))


def is_valid_po_id(val: str) -> bool:
    return bool(re.match(PO_ID_PATTERN, normalize_id(val)))


def is_valid_grn_id(val: str) -> bool:
    return bool(re.match(GRN_ID_PATTERN, normalize_id(val)))


def is_valid_vendor_id(val: str) -> bool:
    return bool(re.match(VENDOR_ID_PATTERN, normalize_id(val)))


def extract_all_ids(text: str) -> dict[str, list[str]]:
    """Extract all canonical IDs found in arbitrary text."""
    return {
        "invoice_ids": [normalize_id(m) for m in INVOICE_ID_REGEX.findall(text)],
        "po_ids": [normalize_id(m) for m in PO_ID_REGEX.findall(text)],
        "grn_ids": [normalize_id(m) for m in GRN_ID_REGEX.findall(text)],
        "vendor_ids": [normalize_id(m) for m in VENDOR_ID_REGEX.findall(text)],
    }
