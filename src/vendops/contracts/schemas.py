from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from vendops.contracts.enums import (
    ActionType,
    DisputePriority,
    DisputeType,
    InvoiceStatus,
    MatchStatus,
    PaymentStatus,
)
from vendops.contracts.ids import (
    GRN_ID_PATTERN,
    INVOICE_ID_PATTERN,
    PO_ID_PATTERN,
    VENDOR_ID_PATTERN,
)


class StrictBaseModel(BaseModel):
    """Base model prohibiting undeclared fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --- ERP Entities ---


class Vendor(StrictBaseModel):
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    payment_terms_days: Annotated[int, Field(ge=0, le=365)] = 30
    status: Annotated[str, Field(pattern=r"^(ACTIVE|INACTIVE|SUSPENDED)$")] = "ACTIVE"
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "USD"


class PurchaseOrderLine(StrictBaseModel):
    line_number: Annotated[int, Field(ge=1, le=1000)]
    item_sku: Annotated[str, Field(min_length=1, max_length=50)]
    description: Annotated[str, Field(min_length=1, max_length=255)]
    ordered_qty: Annotated[int, Field(ge=1, le=1_000_000)]
    unit_price: Annotated[float, Field(ge=0.0, le=10_000_000.0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "USD"


class PurchaseOrder(StrictBaseModel):
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN)]
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN)]
    lines: list[PurchaseOrderLine] = Field(min_length=1)
    total_amount: Annotated[float, Field(ge=0.0, le=100_000_000.0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "USD"
    created_date: date


class GoodsReceiptNoteLine(StrictBaseModel):
    line_number: Annotated[int, Field(ge=1, le=1000)]
    item_sku: Annotated[str, Field(min_length=1, max_length=50)]
    received_qty: Annotated[int, Field(ge=0, le=1_000_000)]
    accepted_qty: Annotated[int, Field(ge=0, le=1_000_000)]
    rejected_qty: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    rejection_reason: str | None = None


class GoodsReceiptNote(StrictBaseModel):
    grn_id: Annotated[str, Field(pattern=GRN_ID_PATTERN)]
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN)]
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN)]
    lines: list[GoodsReceiptNoteLine] = Field(min_length=1)
    received_date: date


class InvoiceLine(StrictBaseModel):
    line_number: Annotated[int, Field(ge=1, le=1000)]
    item_sku: Annotated[str, Field(min_length=1, max_length=50)]
    description: Annotated[str, Field(min_length=1, max_length=255)]
    billed_qty: Annotated[int, Field(ge=1, le=1_000_000)]
    unit_price: Annotated[float, Field(ge=0.0, le=10_000_000.0)]
    total_price: Annotated[float, Field(ge=0.0, le=100_000_000.0)]


class Invoice(StrictBaseModel):
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN)]
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN)]
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN)]
    lines: list[InvoiceLine] = Field(min_length=1)
    total_amount: Annotated[float, Field(ge=0.0, le=100_000_000.0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)] = "USD"
    invoice_date: date
    due_date: date
    status: InvoiceStatus = InvoiceStatus.PENDING


class Payment(StrictBaseModel):
    payment_id: Annotated[str, Field(min_length=1, max_length=50)]
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN)]
    amount: Annotated[float, Field(ge=0.0, le=100_000_000.0)]
    payment_date: date
    status: PaymentStatus = PaymentStatus.SCHEDULED
    reference: str | None = None


class AuditEntry(StrictBaseModel):
    audit_id: str
    timestamp: datetime
    action: ActionType
    invoice_id: str
    po_id: str | None = None
    vendor_id: str
    amount: float
    rationale: str
    idempotency_key: str
    reviewer_id: str | None = None


class ThreeWayMatchResult(StrictBaseModel):
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN)]
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN)]
    grn_id: Annotated[str, Field(pattern=GRN_ID_PATTERN)] | None = None
    status: MatchStatus
    discrepancies: list[str] = Field(default_factory=list)
    is_matched: bool
    billed_amount: Annotated[float, Field(ge=0.0)]
    authorized_amount: Annotated[float, Field(ge=0.0)]


# --- MCP Tool Input / Output Schemas ---


class GetInvoiceInput(StrictBaseModel):
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN, description="Target invoice ID")]


class GetPurchaseOrderInput(StrictBaseModel):
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN, description="Target purchase order ID")]


class GetGRNInput(StrictBaseModel):
    grn_id: Annotated[str, Field(pattern=GRN_ID_PATTERN, description="Target goods receipt note ID")]


class GetVendorInput(StrictBaseModel):
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN, description="Target vendor ID")]


class GetPaymentStatusInput(StrictBaseModel):
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN, description="Invoice ID to check payment status")]


class ExecuteResolutionInput(StrictBaseModel):
    action: ActionType = Field(description="Strict resolution action enum")
    invoice_id: Annotated[str, Field(pattern=INVOICE_ID_PATTERN, description="Target invoice ID")]
    po_id: Annotated[str, Field(pattern=PO_ID_PATTERN)] | None = Field(default=None, description="Optional associated PO ID")
    vendor_id: Annotated[str, Field(pattern=VENDOR_ID_PATTERN, description="Associated vendor ID")]
    amount: Annotated[float, Field(ge=0.0, le=100_000_000.0, description="Amount authorized or credited")]
    rationale: Annotated[str, Field(min_length=5, max_length=2000, description="Audit rationale for action")]
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128, description="Unique client-generated idempotency key")]
    reviewer_id: str | None = Field(default=None, description="Reviewer ID if approved via HITL gate")


class ExecuteResolutionOutput(StrictBaseModel):
    success: bool
    action: ActionType
    invoice_id: str
    audit_id: str
    timestamp: datetime
    message: str


# --- Agent Graph Pipeline Models ---


class TriageResult(StrictBaseModel):
    dispute_type: DisputeType
    priority: DisputePriority
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    extracted_ids: list[str] = Field(default_factory=list)
    vendor_name: str | None = None
    disputed_amount: float | None = None
    summary: Annotated[str, Field(min_length=1, max_length=1000)]


class ResolutionProposal(StrictBaseModel):
    action: ActionType
    amount: Annotated[float, Field(ge=0.0, le=100_000_000.0)]
    rationale: Annotated[str, Field(min_length=5, max_length=2000)]
    evidence: list[str] = Field(min_length=1)
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class ResolutionReview(StrictBaseModel):
    approved: bool
    reviewer_id: Annotated[str, Field(min_length=1, max_length=100)]
    comments: Annotated[str, Field(max_length=1000)] = ""
    override_amount: float | None = None
    override_action: ActionType | None = None


class VendorMessageInput(StrictBaseModel):
    message: Annotated[str, Field(min_length=1, max_length=10_000)]
    thread_id: str | None = None
    sender: str | None = None


class DisputeResponse(StrictBaseModel):
    thread_id: str
    dispute_type: DisputeType
    action: ActionType
    status: Annotated[str, Field(pattern=r"^(RESOLVED|PENDING_APPROVAL|REJECTED|ESCALATED)$")]
    reply_message: str
    proposal: ResolutionProposal
    is_hitl_gated: bool
    review_status: str | None = None
