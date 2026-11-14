# SOP-PRC-003: Purchase Order Pricing Precedence and Variance Tolerance

**Document ID**: POL-PRC-003  
**Category**: Procurement Integrity & Price Discrepancy Governance  
**Effective Date**: 2024-01-01  
**Target Roles**: Category Managers, Accounts Payable Analysts, Automated Resolution Engine  

---

## 1. Purpose and Scope
This policy governs the resolution of price mismatches between supplier invoices (`INV-XXXXXXXX`) and authorized purchase orders (`PO-XXXXXXXX`), setting forth legal precedence rules, tolerance bands, and settlement workflows.

## 2. Binding Legal Precedence of Purchase Orders
1. **PO Precedence Principle**:
   - The agreed unit price specified in an authorized VendOps Purchase Order (`PO-XXXXXXXX`) is legally binding and supersedes price claims on vendor invoices.
   - Price increases communicated after PO dispatch are void unless formal procurement change orders were approved prior to shipment.
2. **Dispute Classification**:
   - `PRICE_MISMATCH`: Unit price on invoice exceeds or deviates from the authorized PO line unit price.

## 3. Variance Tolerance Bands
VendOps applies rigid automated tolerances during 3-way reconciliation:
1. **Zero-Tolerance for Unit Price Hikes**:
   - Tolerance for unit price inflation is **0.0%**. Any unauthorized price increase will be blocked.
2. **De Minimis Currency & Rounding Tolerance**:
   - Cumulative total invoice variance attributable to mathematical rounding or fractional cent conversions is allowed up to a maximum threshold of **$1.00 USD**.
   - Rounding variances within $1.00 are absorbed automatically without withholding disbursement.

## 4. Standard Settlement Actions for Price Variances
When an invoice unit price exceeds the purchase order rate:
1. **Approved PO Settlement (`PARTIAL_PAYMENT` / Authorized Amount)**:
   - Automated settlement authorizes disbursement calculated strictly at the authorized PO unit price: `Authorized Amount = billed_qty * PO_unit_price`.
2. **Vendor Variance Rectification (`CREDIT_NOTE`)**:
   - The vendor must issue a `CREDIT_NOTE` covering the difference: `Variance = billed_qty * (invoice_unit_price - PO_unit_price)`.
3. **Outright Invoice Rejection (`REJECT`)**:
   - In cases where the unit price deviation exceeds 15% or where the vendor refuses the contracted rate, the entire invoice is rejected with status `REJECT`.

## 5. Escalation Rules
- When the total disputed price variance on a single purchase order exceeds **$5,000.00 USD**, the dispute cannot be auto-resolved and must trigger Human-In-The-Loop review (`ESCALATE`) requiring category manager authorization.
