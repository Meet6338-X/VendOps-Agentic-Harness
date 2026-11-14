import logging
import re
from pathlib import Path
from typing import Any

from vendops.contracts.enums import ActionType, DisputeType
from vendops.rag.qdrant_store import Document, QdrantStore

logger = logging.getLogger(__name__)

SYNTHETIC_HISTORICAL_DISPUTES: list[dict[str, Any]] = [
    {
        "id": "CASE-2024-001",
        "invoice_id": "INV-20240101",
        "po_id": "PO-20240101",
        "grn_id": "GRN-20240101",
        "vendor_id": "VND-000101",
        "dispute_type": DisputeType.SHORT_PAYMENT.value,
        "outcome": ActionType.PARTIAL_PAYMENT.value,
        "citations": ["POL-INV-002: Short Shipment Policy §3", "POL-PAY-001 §4"],
        "vendor_query": "Payment received for INV-20240101 is $4,000 short against our billed amount of $10,000 for PO-20240101.",
        "resolution_summary": "Warehouse intake GRN-20240101 confirmed accepted receipt of 60 units. Automatic partial payment of $6,000 authorized. Credit note required from vendor for $4,000 unfulfilled balance.",
    },
    {
        "id": "CASE-2024-002",
        "invoice_id": "INV-20240102",
        "po_id": "PO-20240102",
        "grn_id": "GRN-20240102",
        "vendor_id": "VND-000102",
        "dispute_type": DisputeType.QTY_MISMATCH.value,
        "outcome": ActionType.CREDIT_NOTE.value,
        "citations": ["POL-INV-002: Short Shipment Policy §4"],
        "vendor_query": "Bhai GRN-20240102 mein 80 boxes show ho rahe hain but humne invoice INV-20240102 mein 100 boxes bill kiye the PO-20240102 ke under. Remaining balance kab settle hoga?",
        "resolution_summary": "GRN-20240102 confirmed only 80 boxes delivered. Vendor notified that partial payment was released for 80 boxes and credit note was requested and processed for the remaining 20 boxes.",
    },
    {
        "id": "CASE-2024-003",
        "invoice_id": "INV-20240103",
        "po_id": "PO-20240103",
        "grn_id": "GRN-20240103",
        "vendor_id": "VND-000103",
        "dispute_type": DisputeType.PRICE_MISMATCH.value,
        "outcome": ActionType.PARTIAL_PAYMENT.value,
        "citations": ["POL-PRC-003: Pricing Discrepancy Policy §2 & §4"],
        "vendor_query": "Invoice INV-20240103 unit rate is $150 due to inflation, but payment was settled at $120 matching PO-20240103.",
        "resolution_summary": "Purchase order rate of $120 holds binding legal precedence over unilateral invoice price increases. Partial payment released at PO rate; vendor requested to issue credit note for $30/unit variance.",
    },
    {
        "id": "CASE-2024-004",
        "invoice_id": "INV-20240104",
        "po_id": "PO-20240104",
        "grn_id": "GRN-20240104",
        "vendor_id": "VND-000104",
        "dispute_type": DisputeType.PRICE_MISMATCH.value,
        "outcome": ActionType.REJECT.value,
        "citations": ["POL-PRC-003: Pricing Discrepancy Policy §4"],
        "vendor_query": "Sir invoice INV-20240104 ka rate 25% increase karke bheja tha PO-20240104 ke comparison mein, par accounts team ne reject kar diya.",
        "resolution_summary": "Unauthorized 25% price escalation exceeded variance threshold. Invoice completely rejected with instruction to resubmit with contracted PO rate.",
    },
    {
        "id": "CASE-2024-005",
        "invoice_id": "INV-20240105",
        "po_id": "PO-20240105",
        "grn_id": "GRN-20240105",
        "vendor_id": "VND-000105",
        "dispute_type": DisputeType.PAYMENT_DELAY.value,
        "outcome": ActionType.RELEASE_PAYMENT.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §2"],
        "vendor_query": "Payment for INV-20240105 is overdue by 12 days past Net 30 terms against PO-20240105.",
        "resolution_summary": "Three-way match confirmed perfect match on GRN-20240105. Verification completed and release payment executed immediately.",
    },
    {
        "id": "CASE-2024-006",
        "invoice_id": "INV-20240106",
        "po_id": "PO-20240106",
        "grn_id": "GRN-20240106",
        "vendor_id": "VND-000106",
        "dispute_type": DisputeType.PAYMENT_DELAY.value,
        "outcome": ActionType.RELEASE_PAYMENT.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §2 & §4"],
        "vendor_query": "Namaste, invoice INV-20240106 ka payment 40 din se pending hai PO-20240106 ke liye. GRN-20240106 already complete ho chuka hai.",
        "resolution_summary": "Automated 3-way match verified. Batch release payment processed for $15,400 after clearing hold flag.",
    },
    {
        "id": "CASE-2024-007",
        "invoice_id": "INV-20240107",
        "po_id": "PO-20240107",
        "grn_id": "GRN-20240107",
        "vendor_id": "VND-000107",
        "dispute_type": DisputeType.MISSING_GRN.value,
        "outcome": ActionType.ESCALATE.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §4", "POL-INV-002 §2"],
        "vendor_query": "Invoice INV-20240107 was delivered three weeks ago for PO-20240107, but AP portal says pending receipt.",
        "resolution_summary": "Warehouse intake dock had not logged GRN. Ticket escalated to warehouse receiving lead to inspect dock backlog and record GRN-20240107.",
    },
    {
        "id": "CASE-2024-008",
        "invoice_id": "INV-20240108",
        "po_id": "PO-20240108",
        "grn_id": "GRN-20240108",
        "vendor_id": "VND-000108",
        "dispute_type": DisputeType.DUPLICATE_INVOICE.value,
        "outcome": ActionType.REJECT.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §5"],
        "vendor_query": "We submitted INV-20240108 for PO-20240108 again because we thought the first copy was lost.",
        "resolution_summary": "Automated audit check confirmed that prior invoice for PO-20240108 had already been paid in full. Duplicate submission rejected.",
    },
    {
        "id": "CASE-2024-009",
        "invoice_id": "INV-20240109",
        "po_id": "PO-20240109",
        "grn_id": "GRN-20240109",
        "vendor_id": "VND-000109",
        "dispute_type": DisputeType.QTY_MISMATCH.value,
        "outcome": ActionType.REPLACEMENT.value,
        "citations": ["POL-DMG-004: Damaged Goods Replacement §3"],
        "vendor_query": "GRN-20240109 shows 30 units rejected due to transit packaging damage on INV-20240109. Can we replace them?",
        "resolution_summary": "Vendor agreed to expedited redelivery. Partial payment released for accepted units; zero-cost replacement purchase order generated for 30 damaged units.",
    },
    {
        "id": "CASE-2024-010",
        "invoice_id": "INV-20240110",
        "po_id": "PO-20240110",
        "grn_id": "GRN-20240110",
        "vendor_id": "VND-000110",
        "dispute_type": DisputeType.QTY_MISMATCH.value,
        "outcome": ActionType.CREDIT_NOTE.value,
        "citations": ["POL-DMG-004: Damaged Goods Replacement §3 & §5"],
        "vendor_query": "Sir GRN-20240110 pe 15 cartons moisture damage ki wajah se reject ho gaye the. Hum replacement nahi bhej sakte, credit note deduct kar lijiye.",
        "resolution_summary": "Replacement was unavailable from supplier. Partial payment released for undamaged units; credit note processed for 15 damaged units.",
    },
    {
        "id": "CASE-2024-011",
        "invoice_id": "INV-20240111",
        "po_id": "PO-20240111",
        "grn_id": "GRN-20240111",
        "vendor_id": "VND-000111",
        "dispute_type": DisputeType.PRICE_MISMATCH.value,
        "outcome": ActionType.ESCALATE.value,
        "citations": ["POL-PRC-003: Pricing Discrepancy Policy §5"],
        "vendor_query": "Dispute regarding raw material surcharge of $12,500 added to invoice INV-20240111 for PO-20240111.",
        "resolution_summary": "Disputed price variance exceeded $5,000 threshold. Escalated to Category Director for contractual assessment and HITL authorization.",
    },
    {
        "id": "CASE-2024-012",
        "invoice_id": "INV-20240112",
        "po_id": "PO-20240112",
        "grn_id": "GRN-20240112",
        "vendor_id": "VND-000112",
        "dispute_type": DisputeType.PAYMENT_DELAY.value,
        "outcome": ActionType.RELEASE_PAYMENT.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §2"],
        "vendor_query": "2/10 early settlement discount was deducted on INV-20240112, but payment was disbursed on day 25.",
        "resolution_summary": "Disbursement exceeded 10-day discount threshold due to internal queue delay. Reimbursed $500 early discount deduction and released full balance.",
    },
    {
        "id": "CASE-2024-013",
        "invoice_id": "INV-20240113",
        "po_id": "PO-20240113",
        "grn_id": "GRN-20240113",
        "vendor_id": "VND-000113",
        "dispute_type": DisputeType.SHORT_PAYMENT.value,
        "outcome": ActionType.PARTIAL_PAYMENT.value,
        "citations": ["POL-INV-002: Short Shipment Policy §3"],
        "vendor_query": "Hamara invoice INV-20240113 tha 500 items ka, par payment sirf 450 items ki aayi hai PO-20240113 ke tehat.",
        "resolution_summary": "Warehouse confirmed 450 items received on GRN-20240113. Partial payment confirmed correct for 450 items; vendor requested credit note for 50 short items.",
    },
    {
        "id": "CASE-2024-014",
        "invoice_id": "INV-20240114",
        "po_id": "PO-20240114",
        "grn_id": "GRN-20240114",
        "vendor_id": "VND-000114",
        "dispute_type": DisputeType.OTHER.value,
        "outcome": ActionType.REJECT.value,
        "citations": ["POL-PAY-001: Standard Payment Terms §3"],
        "vendor_query": "Invoice INV-20240114 includes a separate handling and freight surcharge not listed in PO-20240114.",
        "resolution_summary": "Uncontracted freight surcharge rejected per mandatory PO rate agreement. Base PO balance authorized without unauthorized fees.",
    },
]


def parse_policy_markdown(file_path: Path) -> list[Document]:
    """Parse an SOP policy markdown file into structured documents for indexing."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    title = file_path.stem.replace("_", " ").title()
    doc_id = "UNKNOWN"
    category = "General"

    for line in lines[:10]:
        if line.startswith("# "):
            title = line[2:].strip()
        doc_id_match = re.search(r"\*\*Document ID\*\*:\s*([^\n\r]+)", line)
        if doc_id_match:
            doc_id = doc_id_match.group(1).strip()
        cat_match = re.search(r"\*\*Category\*\*:\s*([^\n\r]+)", line)
        if cat_match:
            category = cat_match.group(1).strip()

    sections: list[tuple[str, str]] = []
    current_sec_title = "Overview"
    current_sec_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_sec_lines:
                sec_text = "\n".join(current_sec_lines).strip()
                if sec_text:
                    sections.append((current_sec_title, sec_text))
            current_sec_title = line[3:].strip()
            current_sec_lines = []
        else:
            current_sec_lines.append(line)

    if current_sec_lines:
        sec_text = "\n".join(current_sec_lines).strip()
        if sec_text:
            sections.append((current_sec_title, sec_text))

    docs: list[Document] = []
    for idx, (sec_title, sec_body) in enumerate(sections, start=1):
        full_text = f"{title}\n{sec_title}\n{sec_body}"
        meta = {
            "source": file_path.name,
            "policy_id": doc_id,
            "policy_title": title,
            "category": category,
            "section": sec_title,
            "section_number": idx,
        }
        docs.append(Document(id=f"{file_path.stem}_{idx}", text=full_text, metadata=meta))

    return docs


def get_synthetic_disputes() -> list[Document]:
    """Return synthetic historical resolved dispute cases as Documents."""
    docs: list[Document] = []
    for item in SYNTHETIC_HISTORICAL_DISPUTES:
        searchable_text = (
            f"Case: {item['id']}\n"
            f"Dispute Type: {item['dispute_type']}\n"
            f"Outcome: {item['outcome']}\n"
            f"Vendor Query: {item['vendor_query']}\n"
            f"Resolution: {item['resolution_summary']}\n"
            f"Citations: {', '.join(item['citations'])}\n"
            f"IDs: {item['invoice_id']}, {item['po_id']}"
        )
        meta = {
            "case_id": item["id"],
            "invoice_id": item["invoice_id"],
            "po_id": item["po_id"],
            "grn_id": item.get("grn_id"),
            "vendor_id": item["vendor_id"],
            "dispute_type": item["dispute_type"],
            "outcome": item["outcome"],
            "citations": item["citations"],
            "vendor_query": item["vendor_query"],
            "resolution_summary": item["resolution_summary"],
        }
        docs.append(Document(id=item["id"], text=searchable_text, metadata=meta))
    return docs


def ingest_policies(
    store: QdrantStore, policies_dir: Path | None = None
) -> int:
    """Ingest markdown SOP policy files into Qdrant."""
    dir_path = policies_dir or Path(__file__).parent / "policies"
    if not dir_path.exists():
        logger.warning("Policies directory not found: %s", dir_path)
        return 0

    all_docs: list[Document] = []
    for md_file in sorted(dir_path.glob("*.md")):
        docs = parse_policy_markdown(md_file)
        all_docs.extend(docs)

    store.add_documents(all_docs, collection_name="sop_policies")
    logger.info("Ingested %d policy sections into sop_policies", len(all_docs))
    return len(all_docs)


def ingest_historical_disputes(
    store: QdrantStore, disputes: list[Document | dict[str, Any]] | None = None
) -> int:
    """Ingest synthetic historical resolved dispute cases into Qdrant."""
    if disputes is None:
        docs = get_synthetic_disputes()
    else:
        docs = [
            d if isinstance(d, Document) else Document(text=str(d.get("text", "")), metadata=d)
            for d in disputes
        ]

    store.add_documents(docs, collection_name="historical_disputes")
    logger.info("Ingested %d historical dispute cases into historical_disputes", len(docs))
    return len(docs)


def ingest_all(
    store: QdrantStore, policies_dir: Path | None = None
) -> dict[str, int]:
    """Ensure collections and ingest all SOP policies and historical disputes."""
    store.ensure_collections(["sop_policies", "historical_disputes"])
    policy_count = ingest_policies(store, policies_dir=policies_dir)
    dispute_count = ingest_historical_disputes(store)
    return {"policies": policy_count, "disputes": dispute_count}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store = QdrantStore()
    counts = ingest_all(store)
    print(f"Ingestion complete: {counts}")
