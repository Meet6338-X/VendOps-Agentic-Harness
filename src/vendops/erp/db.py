"""SQLite mock database engine for VendOps ERP."""

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from vendops.contracts.enums import ActionType, InvoiceStatus, PaymentStatus
from vendops.contracts.schemas import (
    AuditEntry,
    GoodsReceiptNote,
    GoodsReceiptNoteLine,
    Invoice,
    InvoiceLine,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)

DEFAULT_DB_PATH = Path("vendops_erp.db")


class ERPDatabase:
    """SQLite ERP Database with foreign keys enabled."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("VENDOPS_DB_PATH")
            self.db_path = Path(env_path) if env_path else DEFAULT_DB_PATH
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(db_path)

        self._in_memory_conn: sqlite3.Connection | None = None
        if str(self.db_path) == ":memory:":
            self._in_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._in_memory_conn.row_factory = sqlite3.Row
            self._in_memory_conn.execute("PRAGMA foreign_keys = ON;")

    def get_connection(self) -> sqlite3.Connection:
        if self._in_memory_conn is not None:
            return self._in_memory_conn
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_schema(self) -> None:
        """Create tables if they do not exist."""
        conn = self.get_connection()
        try:
            with conn:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = ON;

                    CREATE TABLE IF NOT EXISTS vendors (
                        vendor_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        payment_terms_days INTEGER NOT NULL DEFAULT 30,
                        status TEXT NOT NULL DEFAULT 'ACTIVE',
                        currency TEXT NOT NULL DEFAULT 'USD'
                    );

                    CREATE TABLE IF NOT EXISTS purchase_orders (
                        po_id TEXT PRIMARY KEY,
                        vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
                        total_amount REAL NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        created_date TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS purchase_order_lines (
                        po_id TEXT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
                        line_number INTEGER NOT NULL,
                        item_sku TEXT NOT NULL,
                        description TEXT NOT NULL,
                        ordered_qty INTEGER NOT NULL,
                        unit_price REAL NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        PRIMARY KEY (po_id, line_number)
                    );

                    CREATE TABLE IF NOT EXISTS goods_receipt_notes (
                        grn_id TEXT PRIMARY KEY,
                        po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
                        vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
                        received_date TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS goods_receipt_note_lines (
                        grn_id TEXT NOT NULL REFERENCES goods_receipt_notes(grn_id) ON DELETE CASCADE,
                        line_number INTEGER NOT NULL,
                        item_sku TEXT NOT NULL,
                        received_qty INTEGER NOT NULL,
                        accepted_qty INTEGER NOT NULL,
                        rejected_qty INTEGER NOT NULL DEFAULT 0,
                        rejection_reason TEXT,
                        PRIMARY KEY (grn_id, line_number)
                    );

                    CREATE TABLE IF NOT EXISTS invoices (
                        invoice_id TEXT PRIMARY KEY,
                        po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
                        vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
                        total_amount REAL NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        invoice_date TEXT NOT NULL,
                        due_date TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'PENDING'
                    );

                    CREATE TABLE IF NOT EXISTS invoice_lines (
                        invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
                        line_number INTEGER NOT NULL,
                        item_sku TEXT NOT NULL,
                        description TEXT NOT NULL,
                        billed_qty INTEGER NOT NULL,
                        unit_price REAL NOT NULL,
                        total_price REAL NOT NULL,
                        PRIMARY KEY (invoice_id, line_number)
                    );

                    CREATE TABLE IF NOT EXISTS payments (
                        payment_id TEXT PRIMARY KEY,
                        invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
                        amount REAL NOT NULL,
                        payment_date TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'SCHEDULED',
                        reference TEXT
                    );

                    CREATE TABLE IF NOT EXISTS audit_log (
                        audit_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        action TEXT NOT NULL,
                        invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
                        po_id TEXT REFERENCES purchase_orders(po_id),
                        vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
                        amount REAL NOT NULL,
                        rationale TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        reviewer_id TEXT
                    );
                    """
                )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def reset_schema(self) -> None:
        """Drop all tables and re-create schema."""
        conn = self.get_connection()
        try:
            with conn:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = OFF;
                    DROP TABLE IF EXISTS audit_log;
                    DROP TABLE IF EXISTS payments;
                    DROP TABLE IF EXISTS invoice_lines;
                    DROP TABLE IF EXISTS invoices;
                    DROP TABLE IF EXISTS goods_receipt_note_lines;
                    DROP TABLE IF EXISTS goods_receipt_notes;
                    DROP TABLE IF EXISTS purchase_order_lines;
                    DROP TABLE IF EXISTS purchase_orders;
                    DROP TABLE IF EXISTS vendors;
                    PRAGMA foreign_keys = ON;
                    """
                )
        finally:
            if self._in_memory_conn is None:
                conn.close()
        self.init_schema()

    # --- Vendor operations ---

    def insert_vendor(self, vendor: Vendor) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO vendors (vendor_id, name, payment_terms_days, status, currency)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        vendor.vendor_id,
                        vendor.name,
                        vendor.payment_terms_days,
                        vendor.status,
                        vendor.currency,
                    ),
                )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_vendor(self, vendor_id: str) -> Vendor | None:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM vendors WHERE vendor_id = ?",
                (vendor_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Vendor(
                vendor_id=row["vendor_id"],
                name=row["name"],
                payment_terms_days=row["payment_terms_days"],
                status=row["status"],
                currency=row["currency"],
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    # --- Purchase Order operations ---

    def insert_purchase_order(self, po: PurchaseOrder) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO purchase_orders (po_id, vendor_id, total_amount, currency, created_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        po.po_id,
                        po.vendor_id,
                        po.total_amount,
                        po.currency,
                        po.created_date.isoformat(),
                    ),
                )
                for line in po.lines:
                    conn.execute(
                        """
                        INSERT INTO purchase_order_lines (
                            po_id, line_number, item_sku, description, ordered_qty, unit_price, currency
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            po.po_id,
                            line.line_number,
                            line.item_sku,
                            line.description,
                            line.ordered_qty,
                            line.unit_price,
                            line.currency,
                        ),
                    )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_purchase_order(self, po_id: str) -> PurchaseOrder | None:
        conn = self.get_connection()
        try:
            po_cursor = conn.execute(
                "SELECT * FROM purchase_orders WHERE po_id = ?",
                (po_id,),
            )
            po_row = po_cursor.fetchone()
            if po_row is None:
                return None

            lines_cursor = conn.execute(
                "SELECT * FROM purchase_order_lines WHERE po_id = ? ORDER BY line_number ASC",
                (po_id,),
            )
            lines = [
                PurchaseOrderLine(
                    line_number=row["line_number"],
                    item_sku=row["item_sku"],
                    description=row["description"],
                    ordered_qty=row["ordered_qty"],
                    unit_price=row["unit_price"],
                    currency=row["currency"],
                )
                for row in lines_cursor.fetchall()
            ]

            return PurchaseOrder(
                po_id=po_row["po_id"],
                vendor_id=po_row["vendor_id"],
                lines=lines,
                total_amount=po_row["total_amount"],
                currency=po_row["currency"],
                created_date=date.fromisoformat(po_row["created_date"]),
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    # --- Goods Receipt Note operations ---

    def insert_grn(self, grn: GoodsReceiptNote) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO goods_receipt_notes (grn_id, po_id, vendor_id, received_date)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        grn.grn_id,
                        grn.po_id,
                        grn.vendor_id,
                        grn.received_date.isoformat(),
                    ),
                )
                for line in grn.lines:
                    conn.execute(
                        """
                        INSERT INTO goods_receipt_note_lines (
                            grn_id, line_number, item_sku, received_qty, accepted_qty, rejected_qty, rejection_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            grn.grn_id,
                            line.line_number,
                            line.item_sku,
                            line.received_qty,
                            line.accepted_qty,
                            line.rejected_qty,
                            line.rejection_reason,
                        ),
                    )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_grn(self, grn_id: str) -> GoodsReceiptNote | None:
        conn = self.get_connection()
        try:
            grn_cursor = conn.execute(
                "SELECT * FROM goods_receipt_notes WHERE grn_id = ?",
                (grn_id,),
            )
            grn_row = grn_cursor.fetchone()
            if grn_row is None:
                return None

            lines_cursor = conn.execute(
                "SELECT * FROM goods_receipt_note_lines WHERE grn_id = ? ORDER BY line_number ASC",
                (grn_id,),
            )
            lines = [
                GoodsReceiptNoteLine(
                    line_number=row["line_number"],
                    item_sku=row["item_sku"],
                    received_qty=row["received_qty"],
                    accepted_qty=row["accepted_qty"],
                    rejected_qty=row["rejected_qty"],
                    rejection_reason=row["rejection_reason"],
                )
                for row in lines_cursor.fetchall()
            ]

            return GoodsReceiptNote(
                grn_id=grn_row["grn_id"],
                po_id=grn_row["po_id"],
                vendor_id=grn_row["vendor_id"],
                lines=lines,
                received_date=date.fromisoformat(grn_row["received_date"]),
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_grns_for_po(self, po_id: str) -> list[GoodsReceiptNote]:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT grn_id FROM goods_receipt_notes WHERE po_id = ? ORDER BY grn_id ASC",
                (po_id,),
            )
            grn_ids = [row["grn_id"] for row in cursor.fetchall()]
        finally:
            if self._in_memory_conn is None:
                conn.close()

        notes: list[GoodsReceiptNote] = []
        for gid in grn_ids:
            note = self.get_grn(gid)
            if note is not None:
                notes.append(note)
        return notes

    # --- Invoice operations ---

    def insert_invoice(self, invoice: Invoice) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO invoices (
                        invoice_id, po_id, vendor_id, total_amount, currency, invoice_date, due_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice.invoice_id,
                        invoice.po_id,
                        invoice.vendor_id,
                        invoice.total_amount,
                        invoice.currency,
                        invoice.invoice_date.isoformat(),
                        invoice.due_date.isoformat(),
                        invoice.status.value,
                    ),
                )
                for line in invoice.lines:
                    conn.execute(
                        """
                        INSERT INTO invoice_lines (
                            invoice_id, line_number, item_sku, description, billed_qty, unit_price, total_price
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            invoice.invoice_id,
                            line.line_number,
                            line.item_sku,
                            line.description,
                            line.billed_qty,
                            line.unit_price,
                            line.total_price,
                        ),
                    )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        conn = self.get_connection()
        try:
            inv_cursor = conn.execute(
                "SELECT * FROM invoices WHERE invoice_id = ?",
                (invoice_id,),
            )
            inv_row = inv_cursor.fetchone()
            if inv_row is None:
                return None

            lines_cursor = conn.execute(
                "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number ASC",
                (invoice_id,),
            )
            lines = [
                InvoiceLine(
                    line_number=row["line_number"],
                    item_sku=row["item_sku"],
                    description=row["description"],
                    billed_qty=row["billed_qty"],
                    unit_price=row["unit_price"],
                    total_price=row["total_price"],
                )
                for row in lines_cursor.fetchall()
            ]

            return Invoice(
                invoice_id=inv_row["invoice_id"],
                po_id=inv_row["po_id"],
                vendor_id=inv_row["vendor_id"],
                lines=lines,
                total_amount=inv_row["total_amount"],
                currency=inv_row["currency"],
                invoice_date=date.fromisoformat(inv_row["invoice_date"]),
                due_date=date.fromisoformat(inv_row["due_date"]),
                status=InvoiceStatus(inv_row["status"]),
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_invoices_for_po(self, po_id: str) -> list[Invoice]:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT invoice_id FROM invoices WHERE po_id = ? ORDER BY invoice_id ASC",
                (po_id,),
            )
            inv_ids = [row["invoice_id"] for row in cursor.fetchall()]
        finally:
            if self._in_memory_conn is None:
                conn.close()

        invoices: list[Invoice] = []
        for iid in inv_ids:
            inv = self.get_invoice(iid)
            if inv is not None:
                invoices.append(inv)
        return invoices

    def update_invoice_status(self, invoice_id: str, status: InvoiceStatus) -> bool:
        conn = self.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE invoices SET status = ? WHERE invoice_id = ?",
                    (status.value, invoice_id),
                )
                return cursor.rowcount > 0
        finally:
            if self._in_memory_conn is None:
                conn.close()

    # --- Payment operations ---

    def insert_payment(self, payment: Payment) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO payments (payment_id, invoice_id, amount, payment_date, status, reference)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payment.payment_id,
                        payment.invoice_id,
                        payment.amount,
                        payment.payment_date.isoformat(),
                        payment.status.value,
                        payment.reference,
                    ),
                )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_payment(self, payment_id: str) -> Payment | None:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM payments WHERE payment_id = ?",
                (payment_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Payment(
                payment_id=row["payment_id"],
                invoice_id=row["invoice_id"],
                amount=row["amount"],
                payment_date=date.fromisoformat(row["payment_date"]),
                status=PaymentStatus(row["status"]),
                reference=row["reference"],
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_payment_for_invoice(self, invoice_id: str) -> Payment | None:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM payments WHERE invoice_id = ? ORDER BY payment_date DESC LIMIT 1",
                (invoice_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Payment(
                payment_id=row["payment_id"],
                invoice_id=row["invoice_id"],
                amount=row["amount"],
                payment_date=date.fromisoformat(row["payment_date"]),
                status=PaymentStatus(row["status"]),
                reference=row["reference"],
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    # --- Audit Log operations ---

    def insert_audit_entry(self, entry: AuditEntry) -> None:
        conn = self.get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO audit_log (
                        audit_id, timestamp, action, invoice_id, po_id, vendor_id, amount, rationale, idempotency_key, reviewer_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.audit_id,
                        entry.timestamp.isoformat(),
                        entry.action.value,
                        entry.invoice_id,
                        entry.po_id,
                        entry.vendor_id,
                        entry.amount,
                        entry.rationale,
                        entry.idempotency_key,
                        entry.reviewer_id,
                    ),
                )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_audit_entry_by_idempotency_key(self, idempotency_key: str) -> AuditEntry | None:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM audit_log WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return AuditEntry(
                audit_id=row["audit_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                action=ActionType(row["action"]),
                invoice_id=row["invoice_id"],
                po_id=row["po_id"],
                vendor_id=row["vendor_id"],
                amount=row["amount"],
                rationale=row["rationale"],
                idempotency_key=row["idempotency_key"],
                reviewer_id=row["reviewer_id"],
            )
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def get_audit_log_for_invoice(self, invoice_id: str) -> list[AuditEntry]:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM audit_log WHERE invoice_id = ? ORDER BY timestamp ASC",
                (invoice_id,),
            )
            entries: list[AuditEntry] = []
            for row in cursor.fetchall():
                entries.append(
                    AuditEntry(
                        audit_id=row["audit_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        action=ActionType(row["action"]),
                        invoice_id=row["invoice_id"],
                        po_id=row["po_id"],
                        vendor_id=row["vendor_id"],
                        amount=row["amount"],
                        rationale=row["rationale"],
                        idempotency_key=row["idempotency_key"],
                        reviewer_id=row["reviewer_id"],
                    )
                )
            return entries
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def list_invoices(self, limit: int = 50) -> list[Invoice]:
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT invoice_id FROM invoices LIMIT ?", (limit,))
            invoices: list[Invoice] = []
            for row in cursor.fetchall():
                inv = self.get_invoice(row["invoice_id"])
                if inv:
                    invoices.append(inv)
            return invoices
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def list_purchase_orders(self, limit: int = 50) -> list[PurchaseOrder]:
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT po_id FROM purchase_orders LIMIT ?", (limit,))
            pos: list[PurchaseOrder] = []
            for row in cursor.fetchall():
                po = self.get_purchase_order(row["po_id"])
                if po:
                    pos.append(po)
            return pos
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def list_grns(self, limit: int = 50) -> list[GoodsReceiptNote]:
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT grn_id FROM goods_receipt_notes LIMIT ?", (limit,))
            grns: list[GoodsReceiptNote] = []
            for row in cursor.fetchall():
                grn = self.get_grn(row["grn_id"])
                if grn:
                    grns.append(grn)
            return grns
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def list_vendors(self, limit: int = 50) -> list[Vendor]:
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT vendor_id FROM vendors LIMIT ?", (limit,))
            vendors: list[Vendor] = []
            for row in cursor.fetchall():
                v = self.get_vendor(row["vendor_id"])
                if v:
                    vendors.append(v)
            return vendors
        finally:
            if self._in_memory_conn is None:
                conn.close()

    def list_audit_entries(self, limit: int = 100) -> list[AuditEntry]:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            entries: list[AuditEntry] = []
            for row in cursor.fetchall():
                entries.append(
                    AuditEntry(
                        audit_id=row["audit_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        action=ActionType(row["action"]),
                        invoice_id=row["invoice_id"],
                        po_id=row["po_id"],
                        vendor_id=row["vendor_id"],
                        amount=row["amount"],
                        rationale=row["rationale"],
                        idempotency_key=row["idempotency_key"],
                        reviewer_id=row["reviewer_id"],
                    )
                )
            return entries
        finally:
            if self._in_memory_conn is None:
                conn.close()


# Default singleton instance
_default_db: ERPDatabase | None = None


def get_default_db() -> ERPDatabase:
    global _default_db
    if _default_db is None:
        _default_db = ERPDatabase()
        _default_db.init_schema()
    return _default_db


def set_default_db(db: ERPDatabase) -> None:
    global _default_db
    _default_db = db
