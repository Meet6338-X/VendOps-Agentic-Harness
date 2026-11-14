from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from qdrant_client import QdrantClient

from vendops.api.deps import (
    build_default_graph_app,
    get_graph_app,
    get_qdrant_client,
    get_rag_store,
    reset_api_deps,
)
from vendops.api.main import create_app
from vendops.rag.qdrant_store import QdrantStore


@pytest.fixture
def test_app() -> FastAPI:
    """Create test FastAPI application with isolated in-memory dependencies."""
    reset_api_deps()
    application = create_app()

    client = QdrantClient(":memory:")
    store = QdrantStore(client=client)
    store.ensure_collections()
    graph_app = build_default_graph_app(store=store)

    application.dependency_overrides[get_qdrant_client] = lambda: client
    application.dependency_overrides[get_rag_store] = lambda: store
    application.dependency_overrides[get_graph_app] = lambda: graph_app

    return application


@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide httpx.AsyncClient configured with ASGI transport."""
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_healthz(async_client: httpx.AsyncClient) -> None:
    """Verify healthz endpoint checks API and Qdrant connectivity."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["api"] == "healthy"
    assert data["services"]["qdrant"] == "healthy"


@pytest.mark.asyncio
async def test_create_dispute(async_client: httpx.AsyncClient) -> None:
    """Verify dispute initialization endpoint accepts VendorMessageInput and sets initial state."""
    payload = {
        "message": "Payment for INV-20240101 against PO-20240101 is overdue by 15 days.",
        "sender": "vendor_support@acme.com",
    }
    response = await async_client.post("/api/v1/disputes", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data
    assert data["status"] == "INITIALIZED"
    assert "state" in data
    assert data["state"]["raw_message"] == payload["message"]
    assert data["state"]["thread_id"] == data["thread_id"]


@pytest.mark.asyncio
async def test_dispute_stream_execution(async_client: httpx.AsyncClient) -> None:
    """Verify Server-Sent Events stream yields node transitions and final state."""
    # 1. Initialize dispute
    init_res = await async_client.post(
        "/api/v1/disputes",
        json={"message": "Inquiry regarding scheduled payment for INV-20240105 under PO-20240105."},
    )
    assert init_res.status_code == 200
    thread_id = init_res.json()["thread_id"]

    # 2. Stream execution
    stream_res = await async_client.get(f"/api/v1/disputes/{thread_id}/stream")
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]

    body = stream_res.text
    assert "event: node_transition" in body
    assert "triage" in body
    assert "rag_retrieval" in body
    assert "reconcile" in body
    assert "propose" in body
    assert "execute" in body
    assert "event: end" in body


@pytest.mark.asyncio
async def test_hitl_interrupt_and_resume_flow(async_client: httpx.AsyncClient) -> None:
    """Verify high-value dispute triggers HITL interrupt and can be resumed with approval."""
    # 1. Create dispute with amount over threshold ($8,500)
    init_res = await async_client.post(
        "/api/v1/disputes",
        json={
            "message": "Claiming short payment of $8,500 on INV-20240103 against PO-20240103. Please approve.",
        },
    )
    assert init_res.status_code == 200
    thread_id = init_res.json()["thread_id"]

    # 2. Stream until graph pauses at HITL gate
    stream_res = await async_client.get(f"/api/v1/disputes/{thread_id}/stream")
    assert stream_res.status_code == 200
    body = stream_res.text
    assert "event: interrupt" in body
    assert "WAITING_APPROVAL" in body or "Human approval required" in body

    # 3. Resume with approval
    review_payload = {
        "approved": True,
        "reviewer_id": "REV-001-MANAGER",
        "comments": "Approved partial payment after reviewing GRN intake documentation.",
    }
    resume_res = await async_client.post(
        f"/api/v1/disputes/{thread_id}/resume", json=review_payload
    )
    assert resume_res.status_code == 200
    resume_data = resume_res.json()
    assert resume_data["status"] == "RESUMED"
    assert resume_data["state"]["hitl_approved"] is True
    assert resume_data["state"]["hitl_reviewer_id"] == "REV-001-MANAGER"
    assert "Resolution executed" in resume_data["state"]["response"]


@pytest.mark.asyncio
async def test_hitl_interrupt_and_reject_flow(async_client: httpx.AsyncClient) -> None:
    """Verify high-value dispute can be rejected via HITL gate."""
    init_res = await async_client.post(
        "/api/v1/disputes",
        json={
            "message": "Claiming price variance of $12,000 on INV-20240111 against PO-20240111.",
        },
    )
    thread_id = init_res.json()["thread_id"]

    # Stream to pause at interrupt
    await async_client.get(f"/api/v1/disputes/{thread_id}/stream")

    # Resume with rejection
    review_payload = {
        "approved": False,
        "reviewer_id": "REV-002-DIRECTOR",
        "comments": "Rejected unauthorized surcharge.",
    }
    resume_res = await async_client.post(
        f"/api/v1/disputes/{thread_id}/resume", json=review_payload
    )
    assert resume_res.status_code == 200
    resume_data = resume_res.json()
    assert resume_data["status"] == "RESUMED"
    assert resume_data["state"]["hitl_approved"] is False
    assert "rejected by reviewer" in resume_data["state"]["response"].lower()


@pytest.mark.asyncio
async def test_error_handling(async_client: httpx.AsyncClient) -> None:
    """Verify appropriate error responses for non-existent threads and bad requests."""
    # 404 for unknown stream thread
    res_stream_404 = await async_client.get("/api/v1/disputes/non_existent_thread/stream")
    assert res_stream_404.status_code == 404

    # 404 for unknown resume thread
    res_resume_404 = await async_client.post(
        "/api/v1/disputes/non_existent_thread/resume",
        json={"approved": True, "reviewer_id": "REV-001", "comments": "ok"},
    )
    assert res_resume_404.status_code == 404

    # 400 when resuming thread that is not in interrupted state
    init_res = await async_client.post(
        "/api/v1/disputes",
        json={"message": "INV-20240105 status check."},
    )
    thread_id = init_res.json()["thread_id"]
    # Attempting to resume right away before hitting an interrupt
    res_resume_400 = await async_client.post(
        f"/api/v1/disputes/{thread_id}/resume",
        json={"approved": True, "reviewer_id": "REV-001", "comments": "premature"},
    )
    assert res_resume_400.status_code == 400

    # 422 for invalid dispute input
    res_invalid = await async_client.post("/api/v1/disputes", json={"message": ""})
    assert res_invalid.status_code == 422


@pytest.mark.asyncio
async def test_ui_additive_endpoints(async_client: httpx.AsyncClient) -> None:
    """Verify newly added UI endpoints: list disputes, single dispute, evals, ERP browse, audit."""
    # 1. Create a dispute
    init_res = await async_client.post(
        "/api/v1/disputes",
        json={"message": "Inquiry on INV-20240101 under PO-20240101."},
    )
    assert init_res.status_code == 200
    thread_id = init_res.json()["thread_id"]

    # 2. GET /api/v1/disputes
    list_res = await async_client.get("/api/v1/disputes")
    assert list_res.status_code == 200
    disputes = list_res.json()
    assert any(d["thread_id"] == thread_id for d in disputes)

    # 3. GET /api/v1/disputes/{thread_id}
    get_res = await async_client.get(f"/api/v1/disputes/{thread_id}")
    assert get_res.status_code == 200
    assert get_res.json()["thread_id"] == thread_id

    # 4. GET /api/v1/evals/latest
    eval_res = await async_client.get("/api/v1/evals/latest")
    assert eval_res.status_code == 200

    # 5. GET /api/v1/erp/*
    inv_res = await async_client.get("/api/v1/erp/invoices")
    assert inv_res.status_code == 200
    assert isinstance(inv_res.json(), list)

    audit_res = await async_client.get("/api/v1/audit")
    assert audit_res.status_code == 200
    assert isinstance(audit_res.json(), list)

    guard_res = await async_client.get("/api/v1/guard/events")
    assert guard_res.status_code == 200
    assert isinstance(guard_res.json(), list)

    # 6. POST /api/v1/ocr/extract
    sample_text = b"Invoice INV-20240105 for PO-20240105 total amount $4,500.00"
    ocr_res = await async_client.post(
        "/api/v1/ocr/extract",
        files={"file": ("invoice_sample.txt", sample_text, "text/plain")},
    )
    assert ocr_res.status_code == 200
    ocr_data = ocr_res.json()
    assert "INV-20240105" in ocr_data["canonical_ids"]
    assert ocr_data["detected_amount"] == 4500.0
