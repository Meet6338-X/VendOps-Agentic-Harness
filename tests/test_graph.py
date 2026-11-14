import sqlite3
from datetime import date
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from vendops.contracts.enums import ActionType, DisputeType, InvoiceStatus, MatchStatus
from vendops.contracts.schemas import (
    GoodsReceiptNote,
    GoodsReceiptNoteLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ResolutionReview,
)
from vendops.contracts.state import VendOpsState
from vendops.graph.build import build_vendops_graph
from vendops.graph.compress import (
    calculate_token_fertility,
    compress_messages,
    compress_text,
    extract_preserved_entities,
)
from vendops.graph.llm import FakeLLM


def test_token_fertility_and_context_compression() -> None:
    # 1. Fertility comparison: Devanagari has higher fertility than English
    english_text = "Payment delayed for invoice INV-20240456."
    hindi_text = "कृप्या इनवॉइस INV-20240456 का भुगतान करें।"

    eng_fertility = calculate_token_fertility(english_text)
    hi_fertility = calculate_token_fertility(hindi_text)

    assert eng_fertility >= 1.0
    assert hi_fertility > eng_fertility

    # 2. Adaptive compression preserving entity IDs, amounts, dates, vendor names
    verbose_text = (
        "Dear Customer Operations Team,\n"
        "Hope you are doing well and having a great day ahead.\n"
        "We are writing from Acme Supplies regarding invoice INV-20240456 and purchase order PO-20240123.\n"
        "The goods receipt note GRN-20240789 was completed by your warehouse on 2024-01-18.\n"
        "The total invoice amount is $50,000.00 and vendor account is VND-000123.\n"
        "We request you to kindly check why this payment has not been released yet.\n"
        "Please let us know if you need any additional delivery challans or documents.\n"
        "Thanks and best regards,\n"
        "Acme Supplies Accounts Team"
    )

    entities = extract_preserved_entities(verbose_text, vendor_names=["Acme Supplies"])
    assert "INV-20240456" in entities["ids"]
    assert "PO-20240123" in entities["ids"]
    assert "GRN-20240789" in entities["ids"]
    assert "VND-000123" in entities["ids"]
    assert "$50,000.00" in entities["amounts"]
    assert "2024-01-18" in entities["dates"]
    assert "Acme Supplies" in entities["vendors"]

    # Compress with a strict token budget
    compressed = compress_text(verbose_text, token_budget=40, vendor_names=["Acme Supplies"])
    assert len(compressed) < len(verbose_text)

    # Every single preserved entity MUST survive compression
    assert "INV-20240456" in compressed
    assert "PO-20240123" in compressed
    assert "GRN-20240789" in compressed
    assert "VND-000123" in compressed
    assert "$50,000.00" in compressed
    assert "2024-01-18" in compressed
    assert "Acme Supplies" in compressed


def test_compress_messages() -> None:
    msgs = [
        {
            "role": "user",
            "content": (
                "Hello Sir, Hope you are well. We are following up on INV-20240456 with amount $12,500.50 "
                "against PO-20240123 for vendor VND-000123 on date 2024-02-10. Thank you."
            ),
        },
        {
            "role": "assistant",
            "content": "Checking with accounts team.",
        },
        {
            "role": "user",
            "content": "Any update on this?",
        },
    ]
    compressed_msgs = compress_messages(msgs, token_budget=30)
    assert len(compressed_msgs) == 3
    # Check that older message retained entities
    old_content = str(compressed_msgs[0]["content"])
    assert "INV-20240456" in old_content
    assert "$12,500.50" in old_content


def test_full_graph_execution_happy_path_hinglish() -> None:
    # Build checkpointer in memory
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Use deterministic pipeline without LLM override for exact grounded templates
    graph = build_vendops_graph(checkpointer=checkpointer, llm_adapter=None)

    thread_id = "thread-hinglish-001"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": (
            "Bhai INV-20240456 ka payment abhi tak nahi aaya, "
            "PO-20240123 ke against sab deliver ho gaya tha VND-000123. "
            "Kripya jaldi clear karo."
        ),
    }

    result: dict[str, Any] = graph.invoke(initial_state, config)

    # 1. Pipeline metadata
    assert result["language_detected"] == "hi-Latn"
    assert "INV-20240456" in result["provenance_ids"]
    assert "PO-20240123" in result["provenance_ids"]
    assert "VND-000123" in result["provenance_ids"]

    # 2. Triage & Match results
    assert result["triage"].dispute_type == DisputeType.PAYMENT_DELAY
    assert result["match_result"].status == MatchStatus.PERFECT_MATCH
    assert result["match_result"].is_matched is True
    assert result["match_result"].authorized_amount == 50000.0

    # 3. Decision & HITL
    assert result["proposal"].action == ActionType.RELEASE_PAYMENT
    assert result["hitl_required"] is False
    assert result["hitl_approved"] is True

    # 4. Execution & Response
    assert result["execution_result"]["success"] is True
    assert result["execution_result"]["action"] == ActionType.RELEASE_PAYMENT
    assert "Namaste!" in result["response"]
    assert "INV-20240456" in result["response"]
    assert "$50,000.00" in result["response"]


def test_full_graph_execution_english() -> None:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    graph = build_vendops_graph(checkpointer=checkpointer, llm_adapter=None)

    thread_id = "thread-english-002"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": (
            "Dear Finance, Our invoice INV-20240456 for purchase order PO-20240123 is overdue. "
            "Please release payment immediately for vendor VND-000123."
        ),
    }

    result: dict[str, Any] = graph.invoke(initial_state, config)

    assert result["language_detected"] == "en"
    assert "Dear Vendor" in result["response"]
    assert "payment of $50,000.00 has been released" in str(result["response"])
    assert "INV-20240456" in result["response"]


def test_full_graph_execution_with_fake_llm() -> None:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    fake_llm = FakeLLM(default_text="Custom LLM generated response for vendor.")

    graph = build_vendops_graph(checkpointer=checkpointer, llm_adapter=fake_llm)

    thread_id = "thread-fake-llm-005"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": "INV-20240456 payment inquiry for VND-000123.",
    }

    result: dict[str, Any] = graph.invoke(initial_state, config)
    assert result["response"] == "Custom LLM generated response for vendor."
    assert fake_llm.call_count > 0
    assert len(fake_llm.prompt_history) > 0


def test_hitl_gate_interrupt_and_resume_high_value() -> None:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    fake_llm = FakeLLM()

    graph = build_vendops_graph(checkpointer=checkpointer, llm_adapter=fake_llm)

    thread_id = "thread-hitl-003"
    config = {"configurable": {"thread_id": thread_id}}

    # Provide high-value invoice ($150,000 >= HIGH_VALUE_THRESHOLD 100,000)
    high_value_invoice = Invoice(
        invoice_id="INV-20240456",
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="TURBINE-01",
                description="Power generator turbine",
                billed_qty=1,
                unit_price=150000.0,
                total_price=150000.0,
            )
        ],
        total_amount=150000.0,
        currency="USD",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        status=InvoiceStatus.PENDING,
    )
    high_value_po = PurchaseOrder(
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="TURBINE-01",
                description="Power generator turbine",
                ordered_qty=1,
                unit_price=150000.0,
                currency="USD",
            )
        ],
        total_amount=150000.0,
        currency="USD",
        created_date=date(2024, 1, 10),
    )
    high_value_grn = GoodsReceiptNote(
        grn_id="GRN-20240789",
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="TURBINE-01",
                received_qty=1,
                accepted_qty=1,
                rejected_qty=0,
            )
        ],
        received_date=date(2024, 1, 18),
    )

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": "Urgent: Payment pending for INV-20240456 amount 150000 VND-000123.",
        "erp_data": {
            "invoice": high_value_invoice.model_dump(),
            "purchase_order": high_value_po.model_dump(),
            "grn": high_value_grn.model_dump(),
        },
    }

    # First invocation should pause at HITL interrupt
    interrupted_result: dict[str, Any] = graph.invoke(initial_state, config)

    # Check that LangGraph paused at the HITL gate
    assert "__interrupt__" in interrupted_result
    interrupt_info = interrupted_result["__interrupt__"][0]
    assert "High value amount" in interrupt_info.value["reason"]

    # Resume the workflow with human approval
    human_review = ResolutionReview(
        approved=True,
        reviewer_id="VP-FINANCE-001",
        comments="High-value payment approved following procurement verification.",
    )

    resumed_result: dict[str, Any] = graph.invoke(
        Command(resume=human_review.model_dump()), config
    )

    # Pipeline completed after resume
    assert resumed_result["hitl_required"] is True
    assert resumed_result["hitl_approved"] is True
    assert resumed_result["hitl_reviewer_id"] == "VP-FINANCE-001"
    assert resumed_result["execution_result"]["success"] is True
    assert resumed_result["response"] is not None


def test_three_way_match_quantity_discrepancy() -> None:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    fake_llm = FakeLLM()

    graph = build_vendops_graph(checkpointer=checkpointer, llm_adapter=fake_llm)

    thread_id = "thread-qty-disc-004"
    config = {"configurable": {"thread_id": thread_id}}

    # Invoice billed 50 units ($50,000), but GRN accepted only 25 units ($25,000)
    qty_invoice = Invoice(
        invoice_id="INV-20240456",
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            InvoiceLine(
                line_number=1,
                item_sku="SKU-VALVE",
                description="Industrial valve",
                billed_qty=50,
                unit_price=1000.0,
                total_price=50000.0,
            )
        ],
        total_amount=50000.0,
        currency="USD",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 15),
        status=InvoiceStatus.PENDING,
    )
    qty_po = PurchaseOrder(
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            PurchaseOrderLine(
                line_number=1,
                item_sku="SKU-VALVE",
                description="Industrial valve",
                ordered_qty=50,
                unit_price=1000.0,
                currency="USD",
            )
        ],
        total_amount=50000.0,
        currency="USD",
        created_date=date(2024, 1, 10),
    )
    qty_grn = GoodsReceiptNote(
        grn_id="GRN-20240789",
        po_id="PO-20240123",
        vendor_id="VND-000123",
        lines=[
            GoodsReceiptNoteLine(
                line_number=1,
                item_sku="SKU-VALVE",
                received_qty=50,
                accepted_qty=25,
                rejected_qty=25,
                rejection_reason="Damaged casing in transit",
            )
        ],
        received_date=date(2024, 1, 18),
    )

    initial_state: VendOpsState = {
        "thread_id": thread_id,
        "raw_message": "Payment inquiry for INV-20240456 VND-000123.",
        "erp_data": {
            "invoice": qty_invoice.model_dump(),
            "purchase_order": qty_po.model_dump(),
            "grn": qty_grn.model_dump(),
        },
    }

    result: dict[str, Any] = graph.invoke(initial_state, config)

    # Reconciled as quantity discrepancy, authorized partial payment of $25,000
    assert result["match_result"].status == MatchStatus.QUANTITY_DISCREPANCY
    assert result["match_result"].authorized_amount == 25000.0
    assert result["proposal"].action == ActionType.PARTIAL_PAYMENT
    assert result["proposal"].amount == 25000.0
    assert result["execution_result"]["action"] == ActionType.PARTIAL_PAYMENT
