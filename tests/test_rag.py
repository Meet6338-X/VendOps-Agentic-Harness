import pytest
from qdrant_client import QdrantClient

from vendops.contracts.enums import ActionType, DisputeType
from vendops.rag.ingest import (
    SYNTHETIC_HISTORICAL_DISPUTES,
    ingest_all,
    ingest_historical_disputes,
    ingest_policies,
)
from vendops.rag.qdrant_store import Document, QdrantStore


@pytest.fixture
def in_memory_store() -> QdrantStore:
    """Provide a fresh in-memory QdrantStore for offline, deterministic tests."""
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client)
    store.ensure_collections()
    return store


def test_qdrant_store_lifecycle(in_memory_store: QdrantStore) -> None:
    """Verify in-memory store initialization, collection creation, and counts."""
    assert in_memory_store.client.collection_exists("sop_policies")
    assert in_memory_store.client.collection_exists("historical_disputes")
    assert in_memory_store.count("sop_policies") == 0
    assert in_memory_store.count("historical_disputes") == 0


def test_add_and_search_documents(in_memory_store: QdrantStore) -> None:
    """Verify document upsertion and cosine similarity search retrieval."""
    docs = [
        Document(
            id="test-doc-1",
            text="VendOps Standard Net 30 payment terms and 2/10 discount policy.",
            metadata={"category": "Finance", "code": "POL-PAY-001"},
        ),
        Document(
            id="test-doc-2",
            text="Damaged goods quarantine protocol and zero-cost replacement purchase orders.",
            metadata={"category": "Warehouse", "code": "POL-DMG-004"},
        ),
    ]

    doc_ids = in_memory_store.add_documents(docs, collection_name="sop_policies")
    assert len(doc_ids) == 2
    assert in_memory_store.count("sop_policies") == 2

    # Query for payment terms
    results = in_memory_store.search(
        query="When is vendor invoice payment due under Net 30?",
        collection_name="sop_policies",
        limit=2,
    )
    assert len(results) >= 1
    top_result = results[0]
    assert top_result.metadata.get("code") == "POL-PAY-001"
    assert top_result.score > 0.3
    assert "Net 30" in top_result.text


def test_policy_ingestion_from_disk(in_memory_store: QdrantStore) -> None:
    """Verify markdown policies are parsed and ingested into vector store."""
    count = ingest_policies(in_memory_store)
    assert count >= 15
    assert in_memory_store.count("sop_policies") == count

    # Search for short shipment policy
    results = in_memory_store.search(
        query="goods receipt discrepancy partial payment for accepted items credit note",
        collection_name="sop_policies",
        limit=3,
    )
    assert len(results) > 0
    matched_sections = [r.text for r in results]
    assert any("SOP-INV-002" in text or "Short Shipment" in text for text in matched_sections)


def test_synthetic_disputes_metadata_and_citations(in_memory_store: QdrantStore) -> None:
    """Verify all 12+ historical disputes have valid metadata, IDs, and citations."""
    count = ingest_historical_disputes(in_memory_store)
    assert count >= 12
    assert len(SYNTHETIC_HISTORICAL_DISPUTES) >= 12

    for case in SYNTHETIC_HISTORICAL_DISPUTES:
        assert case["id"].startswith("CASE-")
        assert case["invoice_id"].startswith("INV-")
        assert case["po_id"].startswith("PO-")
        assert case["vendor_id"].startswith("VND-")
        assert case["dispute_type"] in [e.value for e in DisputeType]
        assert case["outcome"] in [e.value for e in ActionType]
        assert len(case["citations"]) >= 1
        assert len(case["vendor_query"]) > 5
        assert len(case["resolution_summary"]) > 10


def test_multilingual_hinglish_retrieval(in_memory_store: QdrantStore) -> None:
    """Verify FastEmbed multilingual model correctly matches Hinglish queries to English SOPs."""
    ingest_all(in_memory_store)

    test_queries = [
        # Hinglish Query 1: Short shipment and partial payment
        (
            "Bhai GRN mein count short aaya tha, partial payment ho gaya kya baaki credit note kab milega?",
            "sop_policies",
            ["Short Shipment", "INV-002", "Quantity", "PARTIAL_PAYMENT"],
        ),
        # Hinglish Query 2: Price mismatch rate hike
        (
            "Invoice rate PO rate se 20 percent zyada bill ho gaya tha accounts team ne reject kiya",
            "sop_policies",
            ["Pricing Discrepancy", "PRC-003", "Precedence", "Tolerance"],
        ),
        # Hinglish Query 3: Payment delay
        (
            "INV-20240106 ka payment 40 din se pending hai bhai kab release hoga?",
            "historical_disputes",
            ["CASE-2024-006", "INV-20240106", "PAYMENT_DELAY", "RELEASE_PAYMENT"],
        ),
    ]

    for query, col, expected_keywords in test_queries:
        results = in_memory_store.search(query=query, collection_name=col, limit=3)
        assert len(results) > 0, f"No results for multilingual query: {query}"
        combined_text = " ".join([r.text for r in results])
        matched = any(kw.lower() in combined_text.lower() for kw in expected_keywords)
        assert matched, f"None of {expected_keywords} found in results for '{query}'"
