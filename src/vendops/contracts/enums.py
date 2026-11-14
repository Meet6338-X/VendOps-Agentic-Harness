from enum import Enum


class DisputeType(str, Enum):
    PAYMENT_DELAY = "PAYMENT_DELAY"
    SHORT_PAYMENT = "SHORT_PAYMENT"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    QTY_MISMATCH = "QTY_MISMATCH"
    MISSING_GRN = "MISSING_GRN"
    OTHER = "OTHER"


class DisputePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ActionType(str, Enum):
    """Actions permissible for automated ERP resolution."""

    CREDIT_NOTE = "CREDIT_NOTE"
    REPLACEMENT = "REPLACEMENT"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    RELEASE_PAYMENT = "RELEASE_PAYMENT"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class MatchStatus(str, Enum):
    """Outcome of 3-way reconciliation (PO vs GRN vs Invoice)."""

    PERFECT_MATCH = "PERFECT_MATCH"
    PRICE_DISCREPANCY = "PRICE_DISCREPANCY"
    QUANTITY_DISCREPANCY = "QUANTITY_DISCREPANCY"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    ALREADY_PAID = "ALREADY_PAID"
    NOT_FOUND = "NOT_FOUND"


class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ON_HOLD = "ON_HOLD"


class LanguageCode(str, Enum):
    ENGLISH = "en"
    HINGLISH = "hi-Latn"
    HINDI = "hi"
    MIXED = "mixed"
