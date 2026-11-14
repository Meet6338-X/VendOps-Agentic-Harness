"""Read tools for VendOps ERP MCP server."""


from vendops.contracts.schemas import (
    GetGRNInput,
    GetInvoiceInput,
    GetPaymentStatusInput,
    GetPurchaseOrderInput,
    GetVendorInput,
    GoodsReceiptNote,
    Invoice,
    Payment,
    PurchaseOrder,
    Vendor,
)
from vendops.erp.db import get_default_db


def get_invoice(invoice_id: str) -> Invoice | None:
    """Fetch invoice details by canonical invoice ID (INV-XXXXXXXX).

    Validates inputs strictly with GetInvoiceInput.
    """
    if isinstance(invoice_id, GetInvoiceInput):
        validated = invoice_id
    else:
        validated = GetInvoiceInput(invoice_id=invoice_id)
    return get_default_db().get_invoice(validated.invoice_id)


def get_invoice_from_input(input_data: GetInvoiceInput) -> Invoice | None:
    """Fetch invoice using validated GetInvoiceInput."""
    return get_default_db().get_invoice(input_data.invoice_id)


def get_purchase_order(po_id: str) -> PurchaseOrder | None:
    """Fetch purchase order details by canonical PO ID (PO-XXXXXXXX).

    Validates inputs strictly with GetPurchaseOrderInput.
    """
    if isinstance(po_id, GetPurchaseOrderInput):
        validated = po_id
    else:
        validated = GetPurchaseOrderInput(po_id=po_id)
    return get_default_db().get_purchase_order(validated.po_id)


def get_purchase_order_from_input(input_data: GetPurchaseOrderInput) -> PurchaseOrder | None:
    """Fetch purchase order using validated GetPurchaseOrderInput."""
    return get_default_db().get_purchase_order(input_data.po_id)


def get_grn(grn_id: str) -> GoodsReceiptNote | None:
    """Fetch goods receipt note details by canonical GRN ID (GRN-XXXXXXXX).

    Validates inputs strictly with GetGRNInput.
    """
    if isinstance(grn_id, GetGRNInput):
        validated = grn_id
    else:
        validated = GetGRNInput(grn_id=grn_id)
    return get_default_db().get_grn(validated.grn_id)


def get_grn_from_input(input_data: GetGRNInput) -> GoodsReceiptNote | None:
    """Fetch GRN using validated GetGRNInput."""
    return get_default_db().get_grn(input_data.grn_id)


def get_vendor(vendor_id: str) -> Vendor | None:
    """Fetch vendor profile by canonical vendor ID (VND-XXXXXX).

    Validates inputs strictly with GetVendorInput.
    """
    if isinstance(vendor_id, GetVendorInput):
        validated = vendor_id
    else:
        validated = GetVendorInput(vendor_id=vendor_id)
    return get_default_db().get_vendor(validated.vendor_id)


def get_vendor_from_input(input_data: GetVendorInput) -> Vendor | None:
    """Fetch vendor using validated GetVendorInput."""
    return get_default_db().get_vendor(input_data.vendor_id)


def get_payment_status(invoice_id: str) -> Payment | None:
    """Fetch payment record associated with an invoice ID (INV-XXXXXXXX).

    Validates inputs strictly with GetPaymentStatusInput.
    """
    if isinstance(invoice_id, GetPaymentStatusInput):
        validated = invoice_id
    else:
        validated = GetPaymentStatusInput(invoice_id=invoice_id)
    return get_default_db().get_payment_for_invoice(validated.invoice_id)


def get_payment_status_from_input(input_data: GetPaymentStatusInput) -> Payment | None:
    """Fetch payment record using validated GetPaymentStatusInput."""
    return get_default_db().get_payment_for_invoice(input_data.invoice_id)
