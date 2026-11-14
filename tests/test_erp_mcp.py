"""Unit and integration tests for VendOps ERP database and MCP server."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from vendops.contracts.enums import ActionType, InvoiceStatus, PaymentStatus
from vendops.contracts.schemas import (
    PurchaseOrder,
    PurchaseOrderLine,
)
from vendops.erp.db import ERPDatabase, get_default_db, set_default_db
from vendops.erp.seed import seed_database
from vendops.mcp_server.server import create_mcp_server, streamable_http_app
from vendops.mcp_server.tools_read import (
    get_grn,
    get_invoice,
    get_payment_status,
    get_purchase_order,
    get_vendor,
)
from vendops.mcp_server.tools_write import execute_resolution


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path) -> None:
    """Initialize a fresh isolated SQLite database for each test."""
    db_file = tmp_path / "test_erp.db"
    test_db = ERPDatabase(db_file)
    test_db.init_schema()
    seed_database(test_db)
    set_default_db(test_db)


# =============================================================================
# 1. Database & Seed Scenarios Tests
# =============================================================================


def test_seed_generation_scenario_counts() -> None:
    """Verify that all 16 scenarios are loaded into the database."""
    db = get_default_db()

    # 16 vendors (VND-000001 through VND-000016)
    for i in range(1, 17):
        vid = f"VND-{i:06d}"
        vendor = db.get_vendor(vid)
        assert vendor is not None, f"Vendor {vid} missing"
        assert vendor.vendor_id == vid

    # Check clean match scenario (PO-20240001 == GRN-20240001 == INV-20240001)
    po1 = db.get_purchase_order("PO-20240001")
    grn1 = db.get_grn("GRN-20240001")
    inv1 = db.get_invoice("INV-20240001")
    assert po1 is not None and grn1 is not None and inv1 is not None
    assert po1.total_amount == 5000.0
    assert grn1.lines[0].accepted_qty == 100
    assert inv1.total_amount == 5000.0

    # Check short delivery scenario (INV-20240003 billed 100, GRN-20240003 accepted 60)
    inv3 = db.get_invoice("INV-20240003")
    grn3 = db.get_grn("GRN-20240003")
    assert inv3 is not None and grn3 is not None
    assert inv3.lines[0].billed_qty == 100
    assert grn3.lines[0].accepted_qty == 60

    # Check damaged goods rejection (GRN-20240004 rejected 50 with reason)
    grn4 = db.get_grn("GRN-20240004")
    assert grn4 is not None
    assert grn4.lines[0].rejected_qty == 50
    assert "Damaged" in (grn4.lines[0].rejection_reason or "")

    # Check price mismatch scenario (PO-20240005 unit price 120 vs INV-20240005 unit price 140)
    po5 = db.get_purchase_order("PO-20240005")
    inv5 = db.get_invoice("INV-20240005")
    assert po5 is not None and inv5 is not None
    assert po5.lines[0].unit_price == 120.0
    assert inv5.lines[0].unit_price == 140.0

    # Check missing GRN scenario (INV-20240007 billed for PO-20240007 with no GRN)
    inv7 = db.get_invoice("INV-20240007")
    assert inv7 is not None
    assert len(db.get_grns_for_po(inv7.po_id)) == 0

    # Check duplicate invoice scenario (PO-20240009 billed twice: INV-20240009 and INV-20240010)
    invoices_po9 = db.get_invoices_for_po("PO-20240009")
    assert len(invoices_po9) == 2
    assert {inv.invoice_id for inv in invoices_po9} == {"INV-20240009", "INV-20240010"}
    assert invoices_po9[0].status == InvoiceStatus.PAID or invoices_po9[1].status == InvoiceStatus.PAID

    # Check payment delay scenario (INV-20240013 has SCHEDULED payment overdue)
    pay11 = db.get_payment_for_invoice("INV-20240013")
    assert pay11 is not None
    assert pay11.status == PaymentStatus.SCHEDULED

    # Check payment ON_HOLD scenario (INV-20240014)
    pay12 = db.get_payment_for_invoice("INV-20240014")
    assert pay12 is not None
    assert pay12.status == PaymentStatus.ON_HOLD

    # Check high-value invoice scenario (INV-20240015 amount >= 100,000 for HITL testing)
    inv13 = db.get_invoice("INV-20240015")
    assert inv13 is not None
    assert inv13.total_amount >= 100000.0


def test_foreign_key_constraints_enforced() -> None:
    """Verify SQLite foreign key enforcement is active."""
    db = get_default_db()

    invalid_po = PurchaseOrder(
        po_id="PO-20249999",
        vendor_id="VND-999999",  # Vendor does not exist
        total_amount=100.0,
        currency="USD",
        created_date=date(2024, 1, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-FAKE",
                description="Fake line",
                ordered_qty=1,
                unit_price=100.0,
            )
        ],
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.insert_purchase_order(invalid_po)


# =============================================================================
# 2. Read Tools Tests
# =============================================================================


def test_get_invoice_valid() -> None:
    inv = get_invoice("INV-20240001")
    assert inv is not None
    assert inv.invoice_id == "INV-20240001"
    assert inv.vendor_id == "VND-000001"
    assert inv.total_amount == 5000.0
    assert len(inv.lines) == 1


def test_get_invoice_not_found() -> None:
    inv = get_invoice("INV-20249999")
    assert inv is None


def test_get_invoice_invalid_format() -> None:
    with pytest.raises(ValidationError):
        get_invoice("INVALID-INV-ID")


def test_get_purchase_order_valid() -> None:
    po = get_purchase_order("PO-20240001")
    assert po is not None
    assert po.po_id == "PO-20240001"
    assert po.vendor_id == "VND-000001"
    assert po.total_amount == 5000.0


def test_get_purchase_order_not_found() -> None:
    po = get_purchase_order("PO-20249999")
    assert po is None


def test_get_purchase_order_invalid_format() -> None:
    with pytest.raises(ValidationError):
        get_purchase_order("PO-123")


def test_get_grn_valid() -> None:
    grn = get_grn("GRN-20240001")
    assert grn is not None
    assert grn.grn_id == "GRN-20240001"
    assert grn.po_id == "PO-20240001"
    assert grn.lines[0].accepted_qty == 100


def test_get_grn_not_found() -> None:
    grn = get_grn("GRN-20249999")
    assert grn is None


def test_get_grn_invalid_format() -> None:
    with pytest.raises(ValidationError):
        get_grn("BAD_GRN")


def test_get_vendor_valid() -> None:
    vendor = get_vendor("VND-000001")
    assert vendor is not None
    assert vendor.vendor_id == "VND-000001"
    assert vendor.name == "Acme Industrial Supplies"
    assert vendor.status == "ACTIVE"


def test_get_vendor_not_found() -> None:
    vendor = get_vendor("VND-999999")
    assert vendor is None


def test_get_vendor_invalid_format() -> None:
    with pytest.raises(ValidationError):
        get_vendor("VENDOR-01")


def test_get_payment_status_valid() -> None:
    pay = get_payment_status("INV-20240002")
    assert pay is not None
    assert pay.invoice_id == "INV-20240002"
    assert pay.amount == 5500.0
    assert pay.status == PaymentStatus.SCHEDULED


def test_get_payment_status_unpaid_invoice() -> None:
    # INV-20240001 has no payment record yet
    pay = get_payment_status("INV-20240001")
    assert pay is None


def test_get_payment_status_invalid_format() -> None:
    with pytest.raises(ValidationError):
        get_payment_status("NOT_AN_INVOICE")


# =============================================================================
# 3. Write Tool & Resolution Execution Tests
# =============================================================================


def test_execute_resolution_release_payment() -> None:
    db = get_default_db()

    output = execute_resolution(
        action=ActionType.RELEASE_PAYMENT,
        invoice_id="INV-20240001",
        vendor_id="VND-000001",
        amount=5000.0,
        rationale="Three-way reconciliation succeeded without discrepancy.",
        idempotency_key="idemp-rel-pay-000000000001",
    )

    assert output.success is True
    assert output.action == ActionType.RELEASE_PAYMENT
    assert output.invoice_id == "INV-20240001"
    assert output.audit_id.startswith("AUD-")

    # Verify database side-effects
    inv = db.get_invoice("INV-20240001")
    assert inv is not None
    assert inv.status == InvoiceStatus.APPROVED

    pay = db.get_payment_for_invoice("INV-20240001")
    assert pay is not None
    assert pay.amount == 5000.0

    # Verify audit entry
    audit_entries = db.get_audit_log_for_invoice("INV-20240001")
    assert len(audit_entries) == 1
    assert audit_entries[0].action == ActionType.RELEASE_PAYMENT
    assert audit_entries[0].idempotency_key == "idemp-rel-pay-000000000001"


def test_execute_resolution_credit_note() -> None:
    db = get_default_db()

    output = execute_resolution(
        action=ActionType.CREDIT_NOTE,
        invoice_id="INV-20240005",
        vendor_id="VND-000005",
        amount=1000.0,
        rationale="Overbilled unit price escalated by vendor. Credit note issued.",
        idempotency_key="idemp-cred-note-000000000002",
        reviewer_id="HITL-USER-42",
    )

    assert output.success is True
    assert output.action == ActionType.CREDIT_NOTE

    audit = db.get_audit_entry_by_idempotency_key("idemp-cred-note-000000000002")
    assert audit is not None
    assert audit.reviewer_id == "HITL-USER-42"
    assert audit.amount == 1000.0


def test_execute_resolution_partial_payment() -> None:
    db = get_default_db()

    output = execute_resolution(
        action=ActionType.PARTIAL_PAYMENT,
        invoice_id="INV-20240003",
        vendor_id="VND-000003",
        amount=1200.0,
        rationale="Short delivery: 60/100 units accepted. Releasing payment for 60 units.",
        idempotency_key="idemp-partial-000000000003",
    )

    assert output.success is True
    assert output.action == ActionType.PARTIAL_PAYMENT

    pay = db.get_payment_for_invoice("INV-20240003")
    assert pay is not None
    assert pay.amount == 1200.0
    assert pay.status == PaymentStatus.SCHEDULED


def test_execute_resolution_reject() -> None:
    db = get_default_db()

    output = execute_resolution(
        action=ActionType.REJECT,
        invoice_id="INV-20240010",
        vendor_id="VND-000009",
        amount=7500.0,
        rationale="Duplicate invoice detected; original invoice INV-20240009 is already paid.",
        idempotency_key="idemp-reject-000000000004",
    )

    assert output.success is True
    inv = db.get_invoice("INV-20240010")
    assert inv is not None
    assert inv.status == InvoiceStatus.CANCELLED


def test_execute_resolution_escalate() -> None:
    db = get_default_db()

    output = execute_resolution(
        action=ActionType.ESCALATE,
        invoice_id="INV-20240016",
        vendor_id="VND-000014",
        amount=135000.0,
        rationale="High-value dispute with severe price disparity requires manual negotiation.",
        idempotency_key="idemp-escalate-0000000005",
    )

    assert output.success is True
    inv = db.get_invoice("INV-20240016")
    assert inv is not None
    assert inv.status == InvoiceStatus.DISPUTED


def test_execute_resolution_idempotency_deduplication() -> None:
    """Duplicate submission with same idempotency key must not duplicate execution."""
    db = get_default_db()
    idemp_key = "idemp-dedup-test-key-00000001"

    # First call
    out1 = execute_resolution(
        action=ActionType.RELEASE_PAYMENT,
        invoice_id="INV-20240001",
        vendor_id="VND-000001",
        amount=5000.0,
        rationale="Valid first attempt for resolution.",
        idempotency_key=idemp_key,
    )
    assert out1.success is True
    first_audit_id = out1.audit_id

    # Second duplicate call with exact same idempotency_key
    out2 = execute_resolution(
        action=ActionType.RELEASE_PAYMENT,
        invoice_id="INV-20240001",
        vendor_id="VND-000001",
        amount=5000.0,
        rationale="Duplicate second attempt for resolution.",
        idempotency_key=idemp_key,
    )
    assert out2.success is True
    # Audit ID must match the original execution
    assert out2.audit_id == first_audit_id
    assert "Duplicate execution prevented" in out2.message

    # Verify only 1 audit entry exists
    audit_entries = db.get_audit_log_for_invoice("INV-20240001")
    assert len(audit_entries) == 1


def test_execute_resolution_non_existent_invoice_raises() -> None:
    with pytest.raises(ValueError, match="does not exist in ERP"):
        execute_resolution(
            action=ActionType.RELEASE_PAYMENT,
            invoice_id="INV-20249999",
            vendor_id="VND-000001",
            amount=100.0,
            rationale="Attempting resolution on non-existent invoice.",
            idempotency_key="idemp-err-inv-000000000001",
        )


def test_execute_resolution_non_existent_vendor_raises() -> None:
    with pytest.raises(ValueError, match="does not exist in ERP"):
        execute_resolution(
            action=ActionType.RELEASE_PAYMENT,
            invoice_id="INV-20240001",
            vendor_id="VND-999999",
            amount=100.0,
            rationale="Attempting resolution with fake vendor.",
            idempotency_key="idemp-err-vnd-000000000001",
        )


def test_execute_resolution_invalid_idempotency_key_length() -> None:
    """Idempotency key must be at least 16 chars."""
    with pytest.raises(ValidationError):
        execute_resolution(
            action=ActionType.RELEASE_PAYMENT,
            invoice_id="INV-20240001",
            vendor_id="VND-000001",
            amount=100.0,
            rationale="Valid rationale here.",
            idempotency_key="too-short",  # < 16 chars
        )


# =============================================================================
# 4. MCP Server Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_mcp_server_tool_listing() -> None:
    mcp_server = create_mcp_server("test-vendops-erp")
    tools = await mcp_server.list_tools()

    tool_names = {t.name for t in tools}
    expected_tools = {
        "get_invoice",
        "get_purchase_order",
        "get_grn",
        "get_vendor",
        "get_payment_status",
        "execute_resolution",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_mcp_server_call_read_tool() -> None:
    mcp_server = create_mcp_server("test-vendops-erp")

    result = await mcp_server.call_tool(
        "get_invoice",
        {"invoice_id": "INV-20240001"},
    )
    assert not result.is_error
    assert result.structured_content is not None
    data = result.structured_content.get("result")
    assert isinstance(data, dict)
    assert data["invoice_id"] == "INV-20240001"
    assert data["total_amount"] == 5000.0


@pytest.mark.asyncio
async def test_mcp_server_call_write_tool_and_deduplication() -> None:
    mcp_server = create_mcp_server("test-vendops-erp")
    idemp_key = "mcp-test-idemp-key-00000001"

    res1 = await mcp_server.call_tool(
        "execute_resolution",
        {
            "action": "RELEASE_PAYMENT",
            "invoice_id": "INV-20240001",
            "vendor_id": "VND-000001",
            "amount": 5000.0,
            "rationale": "Automated MCP test resolution executed.",
            "idempotency_key": idemp_key,
        },
    )
    assert not res1.is_error
    content1 = res1.structured_content
    assert content1 is not None
    assert content1["success"] is True
    audit_id = content1["audit_id"]

    # Re-call with same idempotency key
    res2 = await mcp_server.call_tool(
        "execute_resolution",
        {
            "action": "RELEASE_PAYMENT",
            "invoice_id": "INV-20240001",
            "vendor_id": "VND-000001",
            "amount": 5000.0,
            "rationale": "Duplicate call via MCP.",
            "idempotency_key": idemp_key,
        },
    )
    assert not res2.is_error
    content2 = res2.structured_content
    assert content2 is not None
    assert content2["audit_id"] == audit_id
    assert "Duplicate execution prevented" in content2["message"]


def test_streamable_http_app_creation() -> None:
    """Verify streamable HTTP app instance can be generated."""
    app = streamable_http_app()
    assert app is not None
