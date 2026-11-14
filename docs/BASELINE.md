# Accounts Payable (AP) Dispute Handling Baseline Specification

## 1. Executive Summary & Purpose

This document establishes the empirical manual baselines, labor handling times, and financial cost models for vendor dispute resolution across enterprise Accounts Payable (AP) operations.

In automated agent evaluation within the **VendOps** multi-agent harness, performance improvements in dispute resolution velocity must be measured dynamically against these documented baselines rather than relying on arbitrary or hardcoded reduction targets.

---

## 2. Industry Benchmark & Manual Workflow Breakdown

In conventional enterprise finance operations (SAP S/4HANA, Oracle ERP Cloud, NetSuite), resolving an inbound vendor invoice dispute manually requires the following stages:

| Stage | Operation Description | Typical Time (Minutes) |
|---|---|---|
| **1. Triage & Ingestion** | Extracting vendor identity, validating invoice IDs against mailbox records, assigning ticket | 2.5 |
| **2. ERP Records Retrieval** | Querying Purchase Orders (PO), Goods Receipt Notes (GRN), and Invoice status across disparate ERP tables | 5.0 |
| **3. 3-Way Reconciliation** | Manual line-item audit: comparing PO ordered quantity/price against GRN accepted/inspected quantity and Invoice billed quantity/price | 8.0 |
| **4. Cross-Departmental Query** | Warehouse or procurement coordination for missing receipts, inspection failures, or freight discrepancies | 6.0 |
| **5. Resolution Formulation** | Formulating resolution action (Credit Note, Replacement PO, Partial Payment, Payment Release, Rejection) | 3.5 |
| **6. Execution & Communication** | ERP ledger entry, journal adjustment, and formal email response drafting to vendor | 3.0 |

---

## 3. Manual Handling Time Baseline by Dispute Category

The time required to investigate and resolve a dispute varies significantly based on dispute complexity and document availability:

| Dispute Type (`DisputeType`) | Description & Root Cause | Manual Handling Time (Minutes) | Manual Handling Time (Seconds) |
|---|---|---|---|
| `PAYMENT_DELAY` | Invoice approved or pending payment release past contract payment terms | 18.0 | 1,080 |
| `SHORT_PAYMENT` | Discrepancy between billed amount and remitted amount; partial settlement investigation | 28.0 | 1,680 |
| `DUPLICATE_INVOICE` | Duplicate submission identification, voucher lookup, and reversal posting | 16.0 | 960 |
| `PRICE_MISMATCH` | Invoiced unit price differs from PO contract rate; rate card verification | 32.0 | 1,920 |
| `QTY_MISMATCH` | Invoiced quantity differs from GRN accepted quantity (short-shipment or damage) | 26.0 | 1,560 |
| `MISSING_GRN` | Warehouse receipt note not logged or pending dock inspection | 24.0 | 1,440 |
| `OTHER` | Unclassified, miscellaneous terms, or ambiguous claim | 20.0 | 1,200 |

**Weighted AP Benchmark Average**: **23.4 minutes** (1,404 seconds) per ticket.

---

## 4. Automated Agent Operation Times

When handled by the VendOps autonomous agent pipeline:

| Execution Mode | Operational Description | Handling Time (Minutes) | Handling Time (Seconds) |
|---|---|---|---|
| **Straight-Through Processing (STP)** | Fully automated resolution: extraction, ERP queries, 3-way match, policy verification, ERP write-tool execution | 0.25 | 15 |
| **Human-in-the-Loop (HITL) Review** | High-value threshold or policy exception: Agent pre-assembles dossier, 3-way match diff, and resolution proposal; Human reviewer reviews & approves | 3.50 | 210 |
| **Escalated / Policy Failure** | Unresolvable anomaly or policy breach falling back to standard manual investigation | Full Manual Baseline | Full Manual Baseline |

---

## 5. Mathematical Handling-Time Reduction Proxy

The **Handling-Time Reduction (%)** proxy measures the labor savings achieved by the autonomous system across an evaluation dataset $D = \{c_1, c_2, \dots, c_M\}$:

$$T_{\text{manual}} = \sum_{i=1}^M \text{BaselineManualTime}(c_i.\text{dispute\_type})$$

$$T_{\text{automated}} = \sum_{i=1}^M \begin{cases}
T_{\text{STP}}, & \text{if resolved without HITL and no policy violation} \\
T_{\text{STP}} + T_{\text{HITL}}, & \text{if resolved with HITL review approved} \\
\text{BaselineManualTime}(c_i.\text{dispute\_type}), & \text{if policy violation, unhandled error, or rejected}
\end{cases}$$

$$\text{Handling-Time Reduction (\%)} = \left( \frac{T_{\text{manual}} - T_{\text{automated}}}{T_{\text{manual}}} \right) \times 100\%$$

---

## 6. Machine-Readable Configuration

```json
{
  "manual_baseline_minutes": {
    "PAYMENT_DELAY": 18.0,
    "SHORT_PAYMENT": 28.0,
    "DUPLICATE_INVOICE": 16.0,
    "PRICE_MISMATCH": 32.0,
    "QTY_MISMATCH": 26.0,
    "MISSING_GRN": 24.0,
    "OTHER": 20.0
  },
  "automated_baseline_minutes": {
    "stp_time": 0.25,
    "hitl_review_time": 3.50
  },
  "cost_assumptions": {
    "ap_clerk_hourly_rate_usd": 35.0,
    "target_minimum_reduction_pct": 75.0
  }
}
```
