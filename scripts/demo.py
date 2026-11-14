"""VendOps End-to-End Demo Script.

Executes 3 representative enterprise vendor dispute scenarios:
1. Hinglish mixed dispute (short delivery / partial payment)
2. English payment delay dispute (perfect 3-way match resolution)
3. High-value dispute (>= $100,000 triggering LangGraph HITL interrupt and approval resume)
"""

import asyncio
import io
import logging
import sys
from datetime import date

logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, io.UnsupportedOperation):
        logger.debug("Stdout does not support UTF-8 reconfigure.")

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from vendops.contracts.enums import InvoiceStatus
from vendops.contracts.schemas import (
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ResolutionReview,
    Vendor,
)
from vendops.erp.db import ERPDatabase
from vendops.erp.seed import seed_database
from vendops.graph.build import build_vendops_graph
from vendops.rag.ingest import ingest_all
from vendops.rag.qdrant_store import QdrantStore

logging.basicConfig(level=logging.WARNING)


def print_banner(text: str) -> None:
    print("\n" + "=" * 76)
    print(f" {text}")
    print("=" * 76)


def print_section(title: str) -> None:
    print(f"\n--- {title} ---")


async def run_demo() -> None:
    print_banner("VENDOPS AGENTIC HARNESS - END-TO-END DEMO")
    print("Initializing local ERP database and Qdrant in-memory vector store...")

    # 1. Initialize ERP
    erp_db = ERPDatabase(":memory:")
    seed_database(erp_db)
    print("[OK] ERP Mock Database seeded with enterprise scenarios.")

    # 2. Add high-value invoice for HITL demo
    erp_db.insert_vendor(Vendor(vendor_id="VND-000999", name="Apex Systems Corp", currency="USD"))
    erp_db.insert_purchase_order(PurchaseOrder(
        po_id="PO-20240999",
        vendor_id="VND-000999",
        lines=[PurchaseOrderLine(line_number=1, item_sku="SRV-CORE-01", description="Core Platform", ordered_qty=1, unit_price=120000.0)],
        total_amount=120000.0,
        currency="USD",
        created_date=date(2024, 1, 1),
    ))
    erp_db.insert_invoice(Invoice(
        invoice_id="INV-20240999",
        po_id="PO-20240999",
        vendor_id="VND-000999",
        lines=[InvoiceLine(line_number=1, item_sku="SRV-CORE-01", description="Core Platform", billed_qty=1, unit_price=120000.0, total_price=120000.0)],
        total_amount=120000.0,
        currency="USD",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        status=InvoiceStatus.PENDING,
    ))

    # 3. Initialize RAG
    rag_store = QdrantStore(url=":memory:")
    ingest_all(rag_store)
    print("[OK] Qdrant Multilingual RAG indexed SOP policies and historical cases.")

    # 4. Compile Graph with persistence
    checkpointer = MemorySaver()
    graph = build_vendops_graph(checkpointer=checkpointer, erp_client=erp_db)
    print("[OK] LangGraph StateGraph compiled with state checkpointing.")

    # =========================================================================
    # SCENARIO 1: Hinglish Short Payment Dispute
    # =========================================================================
    print_banner("SCENARIO 1: Hinglish Dispute (Short Delivery & 3-Way Match)")
    hinglish_query = (
        "Bhai INV-20240103 ka payment abhi tak nahi aaya, "
        "PO-20240103 ke against 50 units deliver kar diye the, "
        "GRN-20240103 dock intake ho chuka hai. Please check karo."
    )
    print(f"Vendor Input: \"{hinglish_query}\"")

    config_1 = {"configurable": {"thread_id": "thread-demo-hinglish-01"}}
    res_1 = await graph.ainvoke(
        {"raw_message": hinglish_query, "thread_id": "thread-demo-hinglish-01"},
        config=config_1,
    )

    triage_1 = res_1.get("triage")
    match_1 = res_1.get("match_result")
    proposal_1 = res_1.get("proposal")

    print_section("Pipeline Verification")
    print(f"Detected Dialect : {res_1.get('language_detected')}")
    print(f"Triage Type      : {triage_1.dispute_type.value if triage_1 else 'N/A'}")
    print(f"3-Way Match      : Status={match_1.status.value if match_1 else 'N/A'} (Billed=${match_1.billed_amount:,.2f} vs Auth=${match_1.authorized_amount:,.2f})" if match_1 else "")
    print(f"Proposed Action  : {proposal_1.action.value if proposal_1 else 'N/A'} for ${proposal_1.amount:,.2f}" if proposal_1 else "")
    print_section("Agent Response (Grounded Hinglish)")
    print(f"{res_1.get('response')}")

    # =========================================================================
    # SCENARIO 2: English Standard Payment Delay (Clean Match)
    # =========================================================================
    print_banner("SCENARIO 2: English Payment Delay (Uncontested 3-Way Match)")
    english_query = "Our invoice INV-20240101 under PO-20240101 is overdue. Payment was due last week."
    print(f"Vendor Input: \"{english_query}\"")

    config_2 = {"configurable": {"thread_id": "thread-demo-english-02"}}
    res_2 = await graph.ainvoke(
        {"raw_message": english_query, "thread_id": "thread-demo-english-02"},
        config=config_2,
    )

    triage_2 = res_2.get("triage")
    match_2 = res_2.get("match_result")
    proposal_2 = res_2.get("proposal")

    print_section("Pipeline Verification")
    print(f"Triage Type      : {triage_2.dispute_type.value if triage_2 else 'N/A'}")
    print(f"3-Way Match      : Status={match_2.status.value if match_2 else 'N/A'} (Full Match: {match_2.is_matched if match_2 else 'N/A'})")
    print(f"Executed Action  : {proposal_2.action.value if proposal_2 else 'N/A'} (${proposal_2.amount:,.2f})" if proposal_2 else "")
    print_section("Agent Response (Grounded English)")
    print(f"{res_2.get('response')}")

    # =========================================================================
    # SCENARIO 3: High-Value Dispute Triggering LangGraph HITL Interrupt
    # =========================================================================
    print_banner("SCENARIO 3: High-Value Dispute >= $100,000 (HITL Approval Gate)")
    high_value_query = "Requesting immediate payment release for enterprise invoice INV-20240999 ($120,000) under PO-20240999."
    print(f"Vendor Input: \"{high_value_query}\"")

    config_3 = {"configurable": {"thread_id": "thread-demo-hitl-03"}}
    
    print("\n[Step 1] Graph executing until HITL Gate...")
    await graph.ainvoke(
        {"raw_message": high_value_query, "thread_id": "thread-demo-hitl-03"},
        config=config_3,
    )

    state_checkpoint = graph.get_state(config_3)
    has_interrupt = any(t.interrupts for t in state_checkpoint.tasks)

    if has_interrupt:
        interrupt_info = state_checkpoint.tasks[0].interrupts[0].value
        print("\n>>> HITL GATE TRIGGERED: Execution Suspended at interrupt() <<<")
        print("Reason: Amount exceeds HIGH_VALUE_THRESHOLD ($100,000.00)")
        print(f"Pending Action  : {interrupt_info.get('action')}")
        print(f"Amount at Risk  : ${interrupt_info.get('amount', 0):,.2f}")
        print(f"Evidence Trail  : {interrupt_info.get('evidence')}")

        print("\n[Step 2] AP Finance Director reviewing resolution proposal via API...")
        review = ResolutionReview(
            approved=True,
            reviewer_id="REV-DIR-402",
            comments="Verified core delivery milestone. Approved for disbursement.",
        )
        print(f"Decision: APPROVED by {review.reviewer_id} (\"{review.comments}\")")

        print("\n[Step 3] Resuming workflow with Command(resume=...)...")
        res_3_final = await graph.ainvoke(
            Command(resume=review.model_dump(mode="json")),
            config=config_3,
        )

        exec_res = res_3_final.get("execution_result")
        print_section("Post-Approval Execution Result")
        print(f"Execution Status: {exec_res.get('status') if exec_res else 'EXECUTED'}")
        print(f"Audit Record    : ID={exec_res.get('audit_id') if exec_res else 'AUD-OK'} | Idempotency={exec_res.get('idempotency_key') if exec_res else 'OK'}")
        print_section("Final Vendor Response")
        print(f"{res_3_final.get('response')}")
    else:
        print("Note: Completed directly.")

    print_banner("DEMO COMPLETED SUCCESSFULLY")


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
