# How VendOps Works: Deep-Dive Technical Guide

This document provides a comprehensive, end-to-end technical explanation of how **VendOps** automates vendor dispute resolution, enforces zero tool-call hallucinations, coordinates multilingual accounts payable (AP) workflows, and manages human approvals.

---

## Table of Contents
1. [End-to-End System Overview](#1-end-to-end-system-overview)
2. [Data Lifecycle & The LangGraph State Machine](#2-data-lifecycle--the-langgraph-state-machine)
3. [Multilingual Ingestion & Script Normalization](#3-multilingual-ingestion--script-normalization)
4. [Token Fertility & Adaptive Context Compression](#4-token-fertility--adaptive-context-compression)
5. [Triage & Classification Engine](#5-triage--classification-engine)
6. [ERP Verification & 3-Way Reconciliation](#6-erp-verification--3-way-reconciliation)
7. [Multilingual Vector RAG (Qdrant & FastEmbed)](#7-multilingual-vector-rag-qdrant--fastembed)
8. [Zero-Hallucination Provenance Guard](#8-zero-hallucination-provenance-guard)
9. [Human-in-the-Loop (HITL) Gate Architecture](#9-human-in-the-loop-hitl-gate-architecture)
10. [Model Context Protocol (MCP 2.x) & ERP Mutations](#10-model-context-protocol-mcp-2x--erp-mutations)
11. [FastAPI Real-Time Server-Sent Events (SSE) Streaming](#11-fastapi-real-time-server-sent-events-sse-streaming)
12. [Docker Container Architecture & Offline Runtime](#12-docker-container-architecture--offline-runtime)

---

## 1. End-to-End System Overview

Enterprise Accounts Payable teams receive hundreds of vendor queries daily across multiple channels and languages (e.g. English, Roman-script Hinglish, and mixed Devanagari). Resolving each dispute manually takes approximately **26.0 minutes** of clerk labor: reading the message, querying the ERP, finding dock intake slips, performing line-by-line math, checking SOP policies, and keying in ERP adjustments.

VendOps replaces this manual sequence with an **autonomous agentic pipeline** that executes in $< 3.5\text{ seconds}$ machine time while guaranteeing zero hallucinations:

```mermaid
flowchart TD
    VendorMsg["Vendor Dispute Message\n(English / Hinglish / Devanagari)"] --> Ingest["1. Ingest & Normalize\n(NFKC, Devanagari ०-९, Signatures)"]
    Ingest --> Compress["2. Token Fertility & Compress\n(Preserve IDs, Dates & Amounts)"]
    Compress --> Triage["3. Triage Node\n(Classify DisputeType & Priority)"]
    Triage --> Verify["4. Verify & 3-Way Match\n(PO vs GRN vs Invoice via MCP Read)"]
    Verify --> RAG["5. Multilingual Vector RAG\n(SOP Policies & Historical Cases via Qdrant)"]
    RAG --> Decide["6. Decide Node\n(Formulate ResolutionProposal)"]
    Decide --> Gate{"7. HITL Gate Check\n(Amount >= $100K or Sensitive?)"}
    
    Gate -- "Yes (Threshold Breached)" --> Interrupt["LangGraph interrupt()\nState Suspended"]
    Interrupt --> Reviewer["AP Human Reviewer\n(POST /resume with Reviewer ID)"]
    Reviewer --> Execute["8. Execute Write Node\n(Idempotent MCP Tool Mutation)"]
    
    Gate -- "No (Standard Approved)" --> Execute
    Execute --> Respond["9. Grounded Respond Node\n(Hinglish in -> Hinglish out)"]
    Respond --> FinalReply["Final Grounded Reply to Vendor"]
```

---

## 2. Data Lifecycle & The LangGraph State Machine

VendOps models its workflow as a stateful directed acyclic graph (`StateGraph`) using **LangGraph** with checkpointing (`SqliteSaver` in production, `MemorySaver` in demo/tests).

### Canonical State (`VendOpsState`)
All nodes read from and write to a shared, strongly-typed dictionary defined in `src/vendops/contracts/state.py`:

```python
class VendOpsState(TypedDict, total=False):
    thread_id: str                      # Unique conversation thread pointer
    raw_message: str                    # Original unmodified vendor email/text
    normalized_message: str             # Normalized text (digits, unicode)
    language_detected: str              # 'en', 'hi-Latn', 'hi', or 'mixed'
    token_fertility: float              # Tokens-per-word expansion ratio
    provenance_ids: list[str]           # Dynamic registry of verified IDs
    triage: TriageResult | None         # Dispute type, priority, and extracted data
    erp_data: dict[str, Any]            # Cached ERP lookup payloads
    match_result: ThreeWayMatchResult   # 3-way reconciliation audit
    retrieved_policies: list[dict]      # Relevant SOP sections and citations
    proposal: ResolutionProposal | None # Proposed action, amount, and rationale
    hitl_required: bool                 # Flag indicating if approval gate is armed
    hitl_approved: bool | None          # Review outcome: True, False, or None
    hitl_reviewer_id: str | None        # Staff ID of reviewer (e.g. REV-DIR-402)
    hitl_comments: str | None           # Audit comments from reviewer
    execution_result: dict[str, Any]    # Outcome of ERP write mutation
    response: str | None                # Grounded final reply to vendor
    tool_call_errors: list[str]         # Tracked repair attempts
    repair_attempts: int                # Circuit breaker counter (max 2)
```

---

## 3. Multilingual Ingestion & Script Normalization

**File:** `src/vendops/graph/nodes/ingest.py` & `src/vendops/graph/nodes/normalize.py`

### Challenges in South Asian Vendor Operations
Vendor emails from the Indian subcontinent frequently code-mix Hindi and English (Hinglish) using either Latin script or Devanagari, alongside localized colloquialisms:
> *"Bhai INV-20240456 ka payment abhi tak nahi aaya, PO-20240123 ke against 50 units deliver kar diye the, GRN bhi ho gaya."*

### How Normalization Operates:
1. **Unicode Canonical Decomposition (NFKC)**: Standardizes variable ligature encodings and cleans zero-width non-joiners (ZWNJ).
2. **Signature & Noise Stripping**: Removes mobile footers (*"Sent from my iPhone"*), email sign-offs (*"Thanks & Regards"*), and disclaimer blocks.
3. **Devanagari Numeral Transliteration**:
   Vendors often input numbers in Devanagari script (`०, १, २, ३, ४, ५, ६, ७, ८, ९`). The normalizer converts these to standard ASCII digits (`0-9`) before entity extraction runs:
   $$\text{INV-२०२४०४५६} \longrightarrow \text{INV-20240456}$$
4. **Phonetic Hinglish Standardisation**:
   Standardizes noisy phonetic spellings (`"nhi"`, `"nhn"` $\rightarrow$ `"nahi"`; `"paymnt"`, `"pymnt"` $\rightarrow$ `"payment"`; `"invc"` $\rightarrow$ `"invoice"`).
5. **Language Identification**: Computes Latin vs Devanagari character ratios to categorize the query into `en`, `hi-Latn`, `hi`, or `mixed`.

---

## 4. Token Fertility & Adaptive Context Compression

**File:** `src/vendops/graph/compress.py`

### The Subword Tokenization Problem
Modern LLM tokenizers (BPE / WordPiece) are heavily trained on English corpora. When tokenizing code-mixed Hinglish or Devanagari, subword fragmentation causes a massive spike in **Token Fertility** (the ratio of subword tokens to white-space words):
- **English Fertility**: $\approx 1.2\text{--}1.4\text{ tokens / word}$
- **Roman Hinglish Fertility**: $\approx 2.4\text{--}3.8\text{ tokens / word}$
- **Devanagari Fertility**: $\approx 4.0\text{--}6.5\text{ tokens / word}$

In deep multi-turn vendor dispute threads ($> 4\text{ turns}$), this rapid token bloat burns LLM rate limits and increases API latency.

### How Compression Works:
1. **Adaptive Threshold Trigger**: If estimated tokens exceed the context budget ($> 400\text{ tokens}$):
2. **Deterministic Entity Preservation**:
   Before summarizing or compressing text, regex matchers scan and protect all enterprise anchors:
   - Invoice IDs (`INV-\d{8}`)
   - Purchase Orders (`PO-\d{8}`)
   - Goods Receipt Notes (`GRN-\d{8}`)
   - Vendor IDs (`VND-\d{6}`)
   - Currency amounts (`\$\d+[\d,]*(\.\d{2})?`)
   - Dates (`\d{4}-\d{2}-\d{2}`)
3. **Structured Context Summarization**: The conversational narrative is compressed while entities are re-injected as immutable state anchors.
4. **Empirical Savings**: Benchmark ablation confirms **-45.9% total token reduction** and **25.1 ms latency speedup** with **zero loss in task completion accuracy (100% TCR retention)**.

---

## 5. Triage & Classification Engine

**File:** `src/vendops/graph/nodes/triage.py`

The triage node analyzes the normalized query and outputs a validated `TriageResult` model:

### Supported Dispute Taxonomies (`DisputeType`):
| Dispute Type | Description | Typical Root Cause |
|---|---|---|
| `PAYMENT_DELAY` | Vendor claims payment is overdue. | Terms matured (Net 30) but payment scheduled run was delayed. |
| `SHORT_PAYMENT` | Remittance received is less than invoiced amount. | Warehouse short shipment or line rejection. |
| `PRICE_MISMATCH` | Invoiced unit price differs from PO line price. | Vendor billed higher tariff than contracted. |
| `QTY_MISMATCH` | Billed quantity exceeds PO or received quantity. | Shipping over-allocation or damaged goods. |
| `MISSING_GRN` | Invoice submitted before dock intake receipt logged. | Delivery slip not yet scanned at warehouse. |
| `DUPLICATE_INVOICE` | Vendor resubmits identical invoice for settled PO. | Accidental double-billing. |
| `OTHER` | Unclassified dispute or general inquiry. | Contract ambiguity, missing master vendor agreement. |

### Dynamic Priority Calculation:
- **`URGENT`**: Keywords like *"urgent"*, *"legal notice"*, or amounts $\ge \$100,000$.
- **`HIGH`**: Amounts $\ge \$10,000$ or payment delay $> 15\text{ days}$.
- **`MEDIUM`**: Standard disputed invoices within normal settlement window.
- **`LOW`**: General inquiries or zero-dollar reconciliations.

---

## 6. ERP Verification & 3-Way Reconciliation

**File:** `src/vendops/graph/nodes/verify.py`

Reconciliation cross-checks three enterprise records:
1. **Purchase Order (PO)**: What was authorized (`ordered_qty`, `unit_price`, `terms`).
2. **Goods Receipt Note (GRN)**: What was physically accepted at the dock (`received_qty`, `accepted_qty`, `rejected_qty`).
3. **Invoice (INV)**: What the vendor billed (`billed_qty`, `unit_price`, `total_amount`).

### The 3-Way Reconciliation Algorithm:
```
           Purchase Order (PO)
          [ordered_qty, po_price]
               /          \
              /            \
             /              \
            ▼                ▼
   Goods Receipt (GRN)   Invoice (INV)
  [accepted_qty]        [billed_qty, inv_price]
```

1. **Step 1: Quantity Matching**:
   $$\Delta_{\text{qty}} = \text{billed\_qty} - \text{accepted\_qty}$$
   - If $\Delta_{\text{qty}} > 0$: Short shipment detected. Authorized quantity is capped at $\text{accepted\_qty}$. The delta is flagged for a `CREDIT_NOTE`.
2. **Step 2: Price Matching**:
   $$\Delta_{\text{price}} = \text{inv\_price} - \text{po\_price}$$
   - If $\Delta_{\text{price}} > 0.01$: Unauthorized price variance. By contract SOP, the PO unit price holds binding precedence.
3. **Step 3: Financial Authorization**:
   $$\text{Authorized Amount} = \min(\text{billed\_qty}, \text{accepted\_qty}) \times \text{po\_price}$$
4. **Outcome Assignment (`MatchStatus`)**:
   - `PERFECT_MATCH`: Quantities and prices match perfectly.
   - `QUANTITY_DISCREPANCY`: Billed quantity exceeds dock accepted quantity.
   - `PRICE_DISCREPANCY`: Invoiced unit price exceeds PO rate.
   - `MISSING_RECEIPT`: No GRN exists for the billed PO.
   - `ALREADY_PAID`: Prior disbursement record already settles this invoice.

---

## 7. Multilingual Vector RAG (Qdrant & FastEmbed)

**File:** `src/vendops/rag/qdrant_store.py` & `src/vendops/rag/ingest.py`

When resolving edge cases or policy conflicts, the agent retrieves standard operating procedures (SOPs) and historical dispute precedents from **Qdrant**.

### Vector Search Architecture:
- **Embedding Model**: FastEmbed's `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- **Dimensions**: 384-dimensional dense vectors.
- **Language Support**: 50+ languages natively embedded in the same metric space (enabling an English SOP to semantically match a Hinglish vendor query).
- **Embedded Cache**: Stored in `/app/.cache/fastembed`, operating 100% offline without PyTorch or external API calls.

### Collections:
1. **`sop_policies`**: Chunked sections from standard operating procedures:
   - `standard_payment_terms.md` (Net 30 baseline, 2/10 discount deductions).
   - `short_shipment_policy.md` (Partial payment authorization, credit note rules).
   - `pricing_discrepancy_policy.md` (PO precedence, $1.00 rounding band).
   - `damaged_goods_replacement.md` (Dock quarantine, return merchandise auth).
2. **`historical_disputes`**: 14+ resolved historical dispute cases indexed with outcomes and citations to provide few-shot grounding.

---

## 8. Zero-Hallucination Provenance Guard

**File:** `src/vendops/guard/provenance.py` & `src/vendops/guard/validate.py`

Large Language Models frequently hallucinate IDs when generating tool arguments (e.g. inventing an invoice ID `INV-99999999` or guessing a PO `PO-20249999`). In enterprise finance, querying or mutating non-existent IDs corrupts ledgers and creates compliance violations.

VendOps enforces **0 hallucinated tool calls reaching the ERP** via a 3-layer guardrail:

### Layer 1: Schema Constraint
Every tool input validates against a Pydantic model with `extra="forbid"`. Extra parameters injected by jailbreaks (e.g. `{"bypass_security": true}`) raise a `ToolCallValidationError`.

### Layer 2: Provenance Verification
State maintains a dynamic **Provenance Registry**:
$$\mathcal{P}_{\text{provenance}} = \mathcal{P}_{\text{user\_input}} \cup \mathcal{P}_{\text{verified\_erp\_returns}}$$
- When a tool call is generated, **every ID** argument (`invoice_id`, `po_id`, `grn_id`, `vendor_id`) is checked:
  $$\forall \text{ID} \in \text{Arguments}: \text{ID} \in \mathcal{P}_{\text{provenance}}$$
- If an ID is not in $\mathcal{P}_{\text{provenance}}$, the tool call is **blocked immediately**.

### Layer 3: Circuit Breaker Repair Loop
- When a provenance violation occurs, a structured error is fed back to the LLM:
  ```json
  {
    "rejected_id": "INV-20249999",
    "id_type": "INVOICE",
    "allowed_ids": ["INV-20240101", "PO-20240101"],
    "message": "ID 'INV-20249999' is unverified. Only IDs from input or ERP are permitted.",
    "repair_attempts": 1,
    "must_escalate": false
  }
  ```
- The LLM has a maximum of **2 repair attempts** to self-correct.
- If the model fails a 2nd time, the circuit breaker trips and automatically routes the transaction to `ESCALATE` (manual human ticket). It **never silently coerces**.

---

## 9. Human-in-the-Loop (HITL) Gate Architecture

**File:** `src/vendops/graph/nodes/hitl_gate.py`

### When is the Gate Armed?
The pipeline arms the HITL gate if **any** of the following criteria are met:
1. **High-Value Threshold**: $\text{Proposed Amount} \ge \text{HIGH\_VALUE\_THRESHOLD}$ (Default: **$100,000.00 USD**).
2. **Low Model Confidence**: $\text{Proposal Confidence} < 0.85$.
3. **Sensitive Operations**: Action is `ESCALATE` or `REJECT` on contested master vendors.

### The Suspend & Resume Cycle:
1. **Suspend (`interrupt`)**:
   The node calls LangGraph's native `interrupt()` function:
   ```python
   review_data = interrupt({
       "reason": "Amount exceeds HIGH_VALUE_THRESHOLD ($100,000.00)",
       "action": proposal.action.value,
       "amount": proposal.amount,
       "evidence": proposal.evidence,
       "thread_id": state["thread_id"],
   })
   ```
   LangGraph suspends execution and persists the graph state into the checkpointer.
2. **Surface to Reviewer**:
   The pending proposal appears in the AP Clerk Dashboard via the API.
3. **Resume via API**:
   The reviewer approves or rejects via `POST /api/v1/disputes/{thread_id}/resume`:
   ```bash
   curl -X POST http://localhost:8000/api/v1/disputes/thread-123/resume \
     -H "Content-Type: application/json" \
     -d '{
       "approved": true,
       "reviewer_id": "REV-DIR-402",
       "comments": "Verified warehouse intake slip. Approved for release."
     }'
   ```
4. **Execution Continuation**:
   The API passes `Command(resume=review_payload)` to the graph. The `interrupt()` function unblocks, receives `review_data`, and routes to the `execute` node.

---

## 10. Model Context Protocol (MCP 2.x) & ERP Mutations

**File:** `src/vendops/mcp_server/server.py`

VendOps decouples ERP access from the core reasoning graph using the **official Anthropic Model Context Protocol (MCP SDK v2.x)**:

### Server Initialization (`MCPServer`)
```python
from mcp.server.mcpserver import MCPServer

server = MCPServer("vendops-erp")
```

### Read Tools (Read-Only)
- `@server.tool() get_invoice(invoice_id: str)`
- `@server.tool() get_purchase_order(po_id: str)`
- `@server.tool() get_grn(grn_id: str)`
- `@server.tool() get_vendor(vendor_id: str)`
- `@server.tool() get_payment_status(invoice_id: str)`

### Write Tool (Guarded Mutations)
- `@server.tool() execute_resolution(...)`
  - Accepts **only** the `ActionType` enum:
    `CREDIT_NOTE`, `REPLACEMENT`, `PARTIAL_PAYMENT`, `RELEASE_PAYMENT`, `REJECT`, `ESCALATE`.
  - **No free-text mutation commands** can ever reach the ERP database.
  - Requires a unique `idempotency_key` (UUID format). If duplicate keys are sent, the server detects the prior execution and returns the existing audit record without double-debiting.
  - Automatically records a timestamped, signed record in the `audit_log` table.

---

## 11. FastAPI Real-Time Server-Sent Events (SSE) Streaming

**File:** `src/vendops/api/routes.py`

VendOps exposes real-time state streaming to frontend dashboards using **Server-Sent Events (SSE)** via `sse-starlette`:

### Client SSE Request:
```http
GET /api/v1/disputes/{thread_id}/stream HTTP/1.1
Accept: text/event-stream
```

### Event Stream Protocol:
1. **Node Transition Events (`event: node_transition`)**:
   Emitted as the state machine advances through nodes (`triage` $\rightarrow$ `rag_retrieval` $\rightarrow$ `reconcile` $\rightarrow$ `propose`):
   ```text
   event: node_transition
   data: {"node": "triage", "update": {"triage": {"dispute_type": "PAYMENT_DELAY", "priority": "MEDIUM"}}}
   ```
2. **Interrupt Event (`event: interrupt`)**:
   Emitted when execution halts at the HITL approval gate:
   ```text
   event: interrupt
   data: {"thread_id": "thread-01", "status": "WAITING_APPROVAL", "interrupt": {"amount": 120000.0}}
   ```
3. **Execution & End Event (`event: end`)**:
   Emitted when the resolution executes and the thread reaches completion:
   ```text
   event: end
   data: {"status": "COMPLETED", "final_state": {"response": "Payment of $2,500.00 released."}}
   ```

---

## 12. Docker Container Architecture & Offline Runtime

VendOps packages all dependencies into a **single, unified Docker container image** (`vendops:latest`):

```
┌────────────────────────────────────────────────────────┐
│                   Docker Compose Host                  │
│                                                        │
│  ┌─────────────────────────┐  ┌─────────────────────┐  │
│  │   qdrant/qdrant:latest  │  │   vendops:latest    │  │
│  │   (Port 6333 / 6334)    │  │   (Port 8000 / 8001)│  │
│  │                         │  │                     │  │
│  │  - Vector Collections   │  │  - FastAPI Service  │  │
│  │  - HNSW Indexing        │  │  - LangGraph Engine │  │
│  │  - Persistent Volume    │  │  - FastEmbed Model  │  │
│  │    (qdrant_storage)     │  │  - SQLite Mock ERP  │  │
│  └────────────▲────────────┘  └──────────┬──────────┘  │
│               │                          │             │
│               └──── Internal Bridge ─────┘             │
│                     (http://qdrant:6333)               │
└────────────────────────────────────────────────────────┘
```

### Offline & Startup Optimizations:
1. **Baked FastEmbed Model**:
   During `docker build`, the 220MB ONNX model is pre-downloaded to `/app/.cache/fastembed`. At runtime, the container starts **100% offline** with zero external network dependencies.
2. **Non-Blocking Lifespan**:
   The FastAPI application starts immediately in `< 0.2\text{s}`, allowing `/health` and `/healthz` probes to pass while vector collections warm up asynchronously in a background worker thread.
3. **Bash TCP Socket Health Check**:
   Qdrant uses native `/dev/tcp` socket verification (`bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/6333'`), eliminating the need for `curl` inside minimal container images.
