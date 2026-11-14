"""Seed database generator with rich dispute scenarios for VendOps ERP."""

from datetime import date

from vendops.contracts.enums import InvoiceStatus, PaymentStatus
from vendops.contracts.schemas import (
    GoodsReceiptNote,
    GoodsReceiptNoteLine,
    Invoice,
    InvoiceLine,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from vendops.erp.db import ERPDatabase, get_default_db


def seed_database(db: ERPDatabase | None = None) -> ERPDatabase:
    """Populate database with 16 rich dispute scenarios."""
    if db is None:
        db = get_default_db()

    db.reset_schema()

    # =========================================================================
    # Scenario 1: Clean perfect match (Single line: PO == GRN == Invoice)
    # =========================================================================
    v1 = Vendor(
        vendor_id="VND-000001",
        name="Acme Industrial Supplies",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v1)

    po1 = PurchaseOrder(
        po_id="PO-20240001",
        vendor_id="VND-000001",
        total_amount=5000.0,
        currency="USD",
        created_date=date(2024, 1, 10),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-STEEL-01",
                description="Cold Rolled Steel Sheet 2mm",
                ordered_qty=100,
                unit_price=50.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po1)

    grn1 = GoodsReceiptNote(
        grn_id="GRN-20240001",
        po_id="PO-20240001",
        vendor_id="VND-000001",
        received_date=date(2024, 1, 15),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-STEEL-01",
                received_qty=100,
                accepted_qty=100,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn1)

    inv1 = Invoice(
        invoice_id="INV-20240001",
        po_id="PO-20240001",
        vendor_id="VND-000001",
        total_amount=5000.0,
        currency="USD",
        invoice_date=date(2024, 1, 16),
        due_date=date(2024, 2, 15),
        status=InvoiceStatus.PENDING,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-STEEL-01",
                description="Cold Rolled Steel Sheet 2mm",
                billed_qty=100,
                unit_price=50.0,
                total_price=5000.0,
            )
        ],
    )
    db.insert_invoice(inv1)

    # =========================================================================
    # Scenario 2: Clean perfect match (Multi-line PO/GRN/Invoice)
    # =========================================================================
    v2 = Vendor(
        vendor_id="VND-000002",
        name="Bharat Electronics Ltd",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v2)

    po2 = PurchaseOrder(
        po_id="PO-20240002",
        vendor_id="VND-000002",
        total_amount=5500.0,
        currency="USD",
        created_date=date(2024, 2, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-CHIP-01",
                description="Microcontroller Unit Cortex-M4",
                ordered_qty=50,
                unit_price=100.0,
                currency="USD",
            ),
            PurchaseOrderLine(
                line_number=2,
                item_sku="SKU-CABLE-02",
                description="Shielded USB-C Industrial Cable",
                ordered_qty=20,
                unit_price=25.0,
                currency="USD",
            ),
        ],
    )
    db.insert_purchase_order(po2)

    grn2 = GoodsReceiptNote(
        grn_id="GRN-20240002",
        po_id="PO-20240002",
        vendor_id="VND-000002",
        received_date=date(2024, 2, 5),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-CHIP-01",
                received_qty=50,
                accepted_qty=50,
                rejected_qty=0,
            ),
            GoodsReceiptNoteLine(
                line_number=2,
                item_sku="SKU-CABLE-02",
                received_qty=20,
                accepted_qty=20,
                rejected_qty=0,
            ),
        ],
    )
    db.insert_grn(grn2)

    inv2 = Invoice(
        invoice_id="INV-20240002",
        po_id="PO-20240002",
        vendor_id="VND-000002",
        total_amount=5500.0,
        currency="USD",
        invoice_date=date(2024, 2, 6),
        due_date=date(2024, 3, 8),
        status=InvoiceStatus.APPROVED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-CHIP-01",
                description="Microcontroller Unit Cortex-M4",
                billed_qty=50,
                unit_price=100.0,
                total_price=5000.0,
            ),
            InvoiceLine(
                line_number=2,
                item_sku="SKU-CABLE-02",
                description="Shielded USB-C Industrial Cable",
                billed_qty=20,
                unit_price=25.0,
                total_price=500.0,
            ),
        ],
    )
    db.insert_invoice(inv2)

    pay2 = Payment(
        payment_id="PAY-20240002",
        invoice_id="INV-20240002",
        amount=5500.0,
        payment_date=date(2024, 3, 1),
        status=PaymentStatus.SCHEDULED,
        reference="ACH-BATCH-0203",
    )
    db.insert_payment(pay2)

    # =========================================================================
    # Scenario 3: Short payment / partial delivery (GRN accepted < billed qty)
    # =========================================================================
    v3 = Vendor(
        vendor_id="VND-000003",
        name="Apex Logistics Packaging",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v3)

    po3 = PurchaseOrder(
        po_id="PO-20240003",
        vendor_id="VND-000003",
        total_amount=2000.0,
        currency="USD",
        created_date=date(2024, 2, 10),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-BOX-10",
                description="Heavy Duty Corrugated Box 50x50cm",
                ordered_qty=100,
                unit_price=20.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po3)

    grn3 = GoodsReceiptNote(
        grn_id="GRN-20240003",
        po_id="PO-20240003",
        vendor_id="VND-000003",
        received_date=date(2024, 2, 15),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-BOX-10",
                received_qty=60,
                accepted_qty=60,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn3)

    inv3 = Invoice(
        invoice_id="INV-20240003",
        po_id="PO-20240003",
        vendor_id="VND-000003",
        total_amount=2000.0,
        currency="USD",
        invoice_date=date(2024, 2, 16),
        due_date=date(2024, 3, 18),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-BOX-10",
                description="Heavy Duty Corrugated Box 50x50cm",
                billed_qty=100,
                unit_price=20.0,
                total_price=2000.0,
            )
        ],
    )
    db.insert_invoice(inv3)

    # =========================================================================
    # Scenario 4: Short delivery with damaged goods rejected at GRN
    # =========================================================================
    v4 = Vendor(
        vendor_id="VND-000004",
        name="Delta Chemical Works",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v4)

    po4 = PurchaseOrder(
        po_id="PO-20240004",
        vendor_id="VND-000004",
        total_amount=9000.0,
        currency="USD",
        created_date=date(2024, 2, 15),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-CHEM-05",
                description="Industrial Solvent Grade A (200L Drum)",
                ordered_qty=200,
                unit_price=45.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po4)

    grn4 = GoodsReceiptNote(
        grn_id="GRN-20240004",
        po_id="PO-20240004",
        vendor_id="VND-000004",
        received_date=date(2024, 2, 20),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-CHEM-05",
                received_qty=200,
                accepted_qty=150,
                rejected_qty=50,
                rejection_reason="Damaged barrels in transit, seal broken",
            )
        ],
    )
    db.insert_grn(grn4)

    inv4 = Invoice(
        invoice_id="INV-20240004",
        po_id="PO-20240004",
        vendor_id="VND-000004",
        total_amount=9000.0,
        currency="USD",
        invoice_date=date(2024, 2, 21),
        due_date=date(2024, 3, 23),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-CHEM-05",
                description="Industrial Solvent Grade A (200L Drum)",
                billed_qty=200,
                unit_price=45.0,
                total_price=9000.0,
            )
        ],
    )
    db.insert_invoice(inv4)

    # =========================================================================
    # Scenario 5: Price mismatch (Invoice unit price > PO unit price)
    # =========================================================================
    v5 = Vendor(
        vendor_id="VND-000005",
        name="Global Metals Corp",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v5)

    po5 = PurchaseOrder(
        po_id="PO-20240005",
        vendor_id="VND-000005",
        total_amount=6000.0,
        currency="USD",
        created_date=date(2024, 3, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-ALUM-02",
                description="Structural Aluminum Rods 6061",
                ordered_qty=50,
                unit_price=120.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po5)

    grn5 = GoodsReceiptNote(
        grn_id="GRN-20240005",
        po_id="PO-20240005",
        vendor_id="VND-000005",
        received_date=date(2024, 3, 5),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-ALUM-02",
                received_qty=50,
                accepted_qty=50,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn5)

    inv5 = Invoice(
        invoice_id="INV-20240005",
        po_id="PO-20240005",
        vendor_id="VND-000005",
        total_amount=7000.0,
        currency="USD",
        invoice_date=date(2024, 3, 6),
        due_date=date(2024, 4, 5),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-ALUM-02",
                description="Structural Aluminum Rods 6061",
                billed_qty=50,
                unit_price=140.0,
                total_price=7000.0,
            )
        ],
    )
    db.insert_invoice(inv5)

    # =========================================================================
    # Scenario 6: Multi-line price escalation mismatch
    # =========================================================================
    v6 = Vendor(
        vendor_id="VND-000006",
        name="Precision Fasteners Inc",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v6)

    po6 = PurchaseOrder(
        po_id="PO-20240006",
        vendor_id="VND-000006",
        total_amount=1500.0,
        currency="USD",
        created_date=date(2024, 3, 10),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-BOLT-M8",
                description="Hex Flange Bolt M8x40 Grade 8.8",
                ordered_qty=500,
                unit_price=2.0,
                currency="USD",
            ),
            PurchaseOrderLine(
                line_number=2,
                item_sku="SKU-NUT-M8",
                description="Nylon Lock Nut M8 Galvanized",
                ordered_qty=500,
                unit_price=1.0,
                currency="USD",
            ),
        ],
    )
    db.insert_purchase_order(po6)

    grn6 = GoodsReceiptNote(
        grn_id="GRN-20240006",
        po_id="PO-20240006",
        vendor_id="VND-000006",
        received_date=date(2024, 3, 15),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-BOLT-M8",
                received_qty=500,
                accepted_qty=500,
                rejected_qty=0,
            ),
            GoodsReceiptNoteLine(
                line_number=2,
                item_sku="SKU-NUT-M8",
                received_qty=500,
                accepted_qty=500,
                rejected_qty=0,
            ),
        ],
    )
    db.insert_grn(grn6)

    inv6 = Invoice(
        invoice_id="INV-20240006",
        po_id="PO-20240006",
        vendor_id="VND-000006",
        total_amount=1850.0,
        currency="USD",
        invoice_date=date(2024, 3, 16),
        due_date=date(2024, 4, 15),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-BOLT-M8",
                description="Hex Flange Bolt M8x40 Grade 8.8",
                billed_qty=500,
                unit_price=2.5,
                total_price=1250.0,
            ),
            InvoiceLine(
                line_number=2,
                item_sku="SKU-NUT-M8",
                description="Nylon Lock Nut M8 Galvanized",
                billed_qty=500,
                unit_price=1.2,
                total_price=600.0,
            ),
        ],
    )
    db.insert_invoice(inv6)

    # =========================================================================
    # Scenario 7: Missing GRN (Invoice billed before goods delivery)
    # =========================================================================
    v7 = Vendor(
        vendor_id="VND-000007",
        name="Sterling Office Supplies",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v7)

    po7 = PurchaseOrder(
        po_id="PO-20240007",
        vendor_id="VND-000007",
        total_amount=12000.0,
        currency="USD",
        created_date=date(2024, 3, 20),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-CHAIR-ERG",
                description="Ergonomic Mesh Office Task Chair",
                ordered_qty=80,
                unit_price=150.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po7)

    # Note: No GRN inserted for PO-20240007
    inv7 = Invoice(
        invoice_id="INV-20240007",
        po_id="PO-20240007",
        vendor_id="VND-000007",
        total_amount=12000.0,
        currency="USD",
        invoice_date=date(2024, 3, 22),
        due_date=date(2024, 4, 21),
        status=InvoiceStatus.PENDING,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-CHAIR-ERG",
                description="Ergonomic Mesh Office Task Chair",
                billed_qty=80,
                unit_price=150.0,
                total_price=12000.0,
            )
        ],
    )
    db.insert_invoice(inv7)

    # =========================================================================
    # Scenario 8: Missing GRN with delayed shipment disputed
    # =========================================================================
    v8 = Vendor(
        vendor_id="VND-000008",
        name="Zenith Medical Devices",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v8)

    po8 = PurchaseOrder(
        po_id="PO-20240008",
        vendor_id="VND-000008",
        total_amount=24000.0,
        currency="USD",
        created_date=date(2024, 3, 25),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-MED-SCAN",
                description="Handheld Diagnostic Ultrasound Scanner",
                ordered_qty=30,
                unit_price=800.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po8)

    # No GRN exists for PO-20240008
    inv8 = Invoice(
        invoice_id="INV-20240008",
        po_id="PO-20240008",
        vendor_id="VND-000008",
        total_amount=24000.0,
        currency="USD",
        invoice_date=date(2024, 3, 28),
        due_date=date(2024, 4, 27),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-MED-SCAN",
                description="Handheld Diagnostic Ultrasound Scanner",
                billed_qty=30,
                unit_price=800.0,
                total_price=24000.0,
            )
        ],
    )
    db.insert_invoice(inv8)

    # =========================================================================
    # Scenario 9: Duplicate invoice (PO billed and paid, billed again)
    # =========================================================================
    v9 = Vendor(
        vendor_id="VND-000009",
        name="Omni Logistics Transport",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v9)

    po9 = PurchaseOrder(
        po_id="PO-20240009",
        vendor_id="VND-000009",
        total_amount=7500.0,
        currency="USD",
        created_date=date(2024, 4, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-FREIGHT-01",
                description="Cross-Country Container Freight Service",
                ordered_qty=100,
                unit_price=75.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po9)

    grn9 = GoodsReceiptNote(
        grn_id="GRN-20240009",
        po_id="PO-20240009",
        vendor_id="VND-000009",
        received_date=date(2024, 4, 5),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-FREIGHT-01",
                received_qty=100,
                accepted_qty=100,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn9)

    # First original invoice - already PAID
    inv9_orig = Invoice(
        invoice_id="INV-20240009",
        po_id="PO-20240009",
        vendor_id="VND-000009",
        total_amount=7500.0,
        currency="USD",
        invoice_date=date(2024, 4, 6),
        due_date=date(2024, 5, 6),
        status=InvoiceStatus.PAID,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-FREIGHT-01",
                description="Cross-Country Container Freight Service",
                billed_qty=100,
                unit_price=75.0,
                total_price=7500.0,
            )
        ],
    )
    db.insert_invoice(inv9_orig)

    pay9 = Payment(
        payment_id="PAY-20240009",
        invoice_id="INV-20240009",
        amount=7500.0,
        payment_date=date(2024, 5, 1),
        status=PaymentStatus.COMPLETED,
        reference="WIRE-REF-90901",
    )
    db.insert_payment(pay9)

    # Second duplicate invoice for the same PO
    inv9_dup = Invoice(
        invoice_id="INV-20240010",
        po_id="PO-20240009",
        vendor_id="VND-000009",
        total_amount=7500.0,
        currency="USD",
        invoice_date=date(2024, 4, 20),
        due_date=date(2024, 5, 20),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-FREIGHT-01",
                description="Cross-Country Container Freight Service",
                billed_qty=100,
                unit_price=75.0,
                total_price=7500.0,
            )
        ],
    )
    db.insert_invoice(inv9_dup)

    # =========================================================================
    # Scenario 10: Duplicate invoice submitted simultaneously
    # =========================================================================
    v10 = Vendor(
        vendor_id="VND-000010",
        name="Horizon Energy Solutions",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v10)

    po10 = PurchaseOrder(
        po_id="PO-20240010",
        vendor_id="VND-000010",
        total_amount=10000.0,
        currency="USD",
        created_date=date(2024, 4, 10),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-SOLAR-PANEL",
                description="Monocrystalline 450W Solar Panel",
                ordered_qty=40,
                unit_price=250.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po10)

    grn10 = GoodsReceiptNote(
        grn_id="GRN-20240010",
        po_id="PO-20240010",
        vendor_id="VND-000010",
        received_date=date(2024, 4, 15),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-SOLAR-PANEL",
                received_qty=40,
                accepted_qty=40,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn10)

    inv10_a = Invoice(
        invoice_id="INV-20240011",
        po_id="PO-20240010",
        vendor_id="VND-000010",
        total_amount=10000.0,
        currency="USD",
        invoice_date=date(2024, 4, 16),
        due_date=date(2024, 5, 16),
        status=InvoiceStatus.PENDING,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-SOLAR-PANEL",
                description="Monocrystalline 450W Solar Panel",
                billed_qty=40,
                unit_price=250.0,
                total_price=10000.0,
            )
        ],
    )
    db.insert_invoice(inv10_a)

    inv10_b = Invoice(
        invoice_id="INV-20240012",
        po_id="PO-20240010",
        vendor_id="VND-000010",
        total_amount=10000.0,
        currency="USD",
        invoice_date=date(2024, 4, 16),
        due_date=date(2024, 5, 16),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-SOLAR-PANEL",
                description="Monocrystalline 450W Solar Panel",
                billed_qty=40,
                unit_price=250.0,
                total_price=10000.0,
            )
        ],
    )
    db.insert_invoice(inv10_b)

    # =========================================================================
    # Scenario 11: Payment delay (Past due date, status SCHEDULED)
    # =========================================================================
    v11 = Vendor(
        vendor_id="VND-000011",
        name="Vortex Polymer Industries",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v11)

    po11 = PurchaseOrder(
        po_id="PO-20240011",
        vendor_id="VND-000011",
        total_amount=9000.0,
        currency="USD",
        created_date=date(2024, 1, 5),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-RESIN-HDPE",
                description="High Density Polyethylene Pellets (50kg)",
                ordered_qty=150,
                unit_price=60.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po11)

    grn11 = GoodsReceiptNote(
        grn_id="GRN-20240011",
        po_id="PO-20240011",
        vendor_id="VND-000011",
        received_date=date(2024, 1, 10),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-RESIN-HDPE",
                received_qty=150,
                accepted_qty=150,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn11)

    inv11 = Invoice(
        invoice_id="INV-20240013",
        po_id="PO-20240011",
        vendor_id="VND-000011",
        total_amount=9000.0,
        currency="USD",
        invoice_date=date(2024, 1, 11),
        due_date=date(2024, 2, 10),
        status=InvoiceStatus.APPROVED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-RESIN-HDPE",
                description="High Density Polyethylene Pellets (50kg)",
                billed_qty=150,
                unit_price=60.0,
                total_price=9000.0,
            )
        ],
    )
    db.insert_invoice(inv11)

    pay11 = Payment(
        payment_id="PAY-20240013",
        invoice_id="INV-20240013",
        amount=9000.0,
        payment_date=date(2024, 2, 15),  # Overdue relative to due_date
        status=PaymentStatus.SCHEDULED,
        reference="BATCH-DELAYED-01",
    )
    db.insert_payment(pay11)

    # =========================================================================
    # Scenario 12: Payment delay (Payment placed ON_HOLD due to audit)
    # =========================================================================
    v12 = Vendor(
        vendor_id="VND-000012",
        name="Aura Textiles & Garments",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v12)

    po12 = PurchaseOrder(
        po_id="PO-20240012",
        vendor_id="VND-000012",
        total_amount=9000.0,
        currency="USD",
        created_date=date(2024, 1, 15),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-FABRIC-COTTON",
                description="100% Organic Raw Cotton Fabric Roll",
                ordered_qty=300,
                unit_price=30.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po12)

    grn12 = GoodsReceiptNote(
        grn_id="GRN-20240012",
        po_id="PO-20240012",
        vendor_id="VND-000012",
        received_date=date(2024, 1, 20),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-FABRIC-COTTON",
                received_qty=300,
                accepted_qty=300,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn12)

    inv12 = Invoice(
        invoice_id="INV-20240014",
        po_id="PO-20240012",
        vendor_id="VND-000012",
        total_amount=9000.0,
        currency="USD",
        invoice_date=date(2024, 1, 21),
        due_date=date(2024, 2, 20),
        status=InvoiceStatus.APPROVED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-FABRIC-COTTON",
                description="100% Organic Raw Cotton Fabric Roll",
                billed_qty=300,
                unit_price=30.0,
                total_price=9000.0,
            )
        ],
    )
    db.insert_invoice(inv12)

    pay12 = Payment(
        payment_id="PAY-20240014",
        invoice_id="INV-20240014",
        amount=9000.0,
        payment_date=date(2024, 2, 22),
        status=PaymentStatus.ON_HOLD,
        reference="HOLD-COMPLIANCE-CHECK",
    )
    db.insert_payment(pay12)

    # =========================================================================
    # Scenario 13: High-value invoice clean match (total_amount >= 100,000 for HITL gate testing)
    # =========================================================================
    v13 = Vendor(
        vendor_id="VND-000013",
        name="Titan Heavy Machinery Ltd",
        payment_terms_days=45,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v13)

    po13 = PurchaseOrder(
        po_id="PO-20240013",
        vendor_id="VND-000013",
        total_amount=150000.0,
        currency="USD",
        created_date=date(2024, 4, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-EXCAVATOR-X1",
                description="Hydraulic Crawler Excavator 30 Ton",
                ordered_qty=2,
                unit_price=75000.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po13)

    grn13 = GoodsReceiptNote(
        grn_id="GRN-20240013",
        po_id="PO-20240013",
        vendor_id="VND-000013",
        received_date=date(2024, 4, 10),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-EXCAVATOR-X1",
                received_qty=2,
                accepted_qty=2,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn13)

    inv13 = Invoice(
        invoice_id="INV-20240015",
        po_id="PO-20240013",
        vendor_id="VND-000013",
        total_amount=150000.0,
        currency="USD",
        invoice_date=date(2024, 4, 11),
        due_date=date(2024, 5, 26),
        status=InvoiceStatus.PENDING,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-EXCAVATOR-X1",
                description="Hydraulic Crawler Excavator 30 Ton",
                billed_qty=2,
                unit_price=75000.0,
                total_price=150000.0,
            )
        ],
    )
    db.insert_invoice(inv13)

    # =========================================================================
    # Scenario 14: High-value invoice with price mismatch (HITL gate + Credit Note)
    # =========================================================================
    v14 = Vendor(
        vendor_id="VND-000014",
        name="Kavach Defense Systems",
        payment_terms_days=45,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v14)

    po14 = PurchaseOrder(
        po_id="PO-20240014",
        vendor_id="VND-000014",
        total_amount=120000.0,
        currency="USD",
        created_date=date(2024, 4, 5),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-DRONE-SURV",
                description="Autonomous Tactical Surveillance Drone",
                ordered_qty=10,
                unit_price=12000.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po14)

    grn14 = GoodsReceiptNote(
        grn_id="GRN-20240014",
        po_id="PO-20240014",
        vendor_id="VND-000014",
        received_date=date(2024, 4, 15),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-DRONE-SURV",
                received_qty=10,
                accepted_qty=10,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn14)

    inv14 = Invoice(
        invoice_id="INV-20240016",
        po_id="PO-20240014",
        vendor_id="VND-000014",
        total_amount=135000.0,
        currency="USD",
        invoice_date=date(2024, 4, 16),
        due_date=date(2024, 5, 31),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-DRONE-SURV",
                description="Autonomous Tactical Surveillance Drone",
                billed_qty=10,
                unit_price=13500.0,
                total_price=135000.0,
            )
        ],
    )
    db.insert_invoice(inv14)

    # =========================================================================
    # Scenario 15: High-value invoice with short delivery (HITL gate + Partial Payment)
    # =========================================================================
    v15 = Vendor(
        vendor_id="VND-000015",
        name="Shakti Power Turbines",
        payment_terms_days=60,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v15)

    po15 = PurchaseOrder(
        po_id="PO-20240015",
        vendor_id="VND-000015",
        total_amount=200000.0,
        currency="USD",
        created_date=date(2024, 4, 10),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-TURBINE-500K",
                description="Hydroelectric Generator Turbine 500kW",
                ordered_qty=4,
                unit_price=50000.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po15)

    grn15 = GoodsReceiptNote(
        grn_id="GRN-20240015",
        po_id="PO-20240015",
        vendor_id="VND-000015",
        received_date=date(2024, 4, 20),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-TURBINE-500K",
                received_qty=3,
                accepted_qty=3,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn15)

    inv15 = Invoice(
        invoice_id="INV-20240017",
        po_id="PO-20240015",
        vendor_id="VND-000015",
        total_amount=200000.0,
        currency="USD",
        invoice_date=date(2024, 4, 21),
        due_date=date(2024, 6, 20),
        status=InvoiceStatus.DISPUTED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-TURBINE-500K",
                description="Hydroelectric Generator Turbine 500kW",
                billed_qty=4,
                unit_price=50000.0,
                total_price=200000.0,
            )
        ],
    )
    db.insert_invoice(inv15)

    # =========================================================================
    # Scenario 16: Payment failed (Payment attempted but status FAILED)
    # =========================================================================
    v16 = Vendor(
        vendor_id="VND-000016",
        name="Nexus Cloud Hardware",
        payment_terms_days=30,
        status="ACTIVE",
        currency="USD",
    )
    db.insert_vendor(v16)

    po16 = PurchaseOrder(
        po_id="PO-20240016",
        vendor_id="VND-000016",
        total_amount=30000.0,
        currency="USD",
        created_date=date(2024, 2, 1),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-SERVER-BLADE",
                description="Enterprise High Density Server Blade",
                ordered_qty=25,
                unit_price=1200.0,
                currency="USD",
            )
        ],
    )
    db.insert_purchase_order(po16)

    grn16 = GoodsReceiptNote(
        grn_id="GRN-20240016",
        po_id="PO-20240016",
        vendor_id="VND-000016",
        received_date=date(2024, 2, 8),
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-SERVER-BLADE",
                received_qty=25,
                accepted_qty=25,
                rejected_qty=0,
            )
        ],
    )
    db.insert_grn(grn16)

    inv16 = Invoice(
        invoice_id="INV-20240018",
        po_id="PO-20240016",
        vendor_id="VND-000016",
        total_amount=30000.0,
        currency="USD",
        invoice_date=date(2024, 2, 9),
        due_date=date(2024, 3, 10),
        status=InvoiceStatus.APPROVED,
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-SERVER-BLADE",
                description="Enterprise High Density Server Blade",
                billed_qty=25,
                unit_price=1200.0,
                total_price=30000.0,
            )
        ],
    )
    db.insert_invoice(inv16)

    pay16 = Payment(
        payment_id="PAY-20240016",
        invoice_id="INV-20240018",
        amount=30000.0,
        payment_date=date(2024, 3, 9),
        status=PaymentStatus.FAILED,
        reference="ERR-INVALID-IFSC",
    )
    db.insert_payment(pay16)

    return db


if __name__ == "__main__":
    db = seed_database()
    print("VendOps ERP database seeded successfully at", db.db_path)
