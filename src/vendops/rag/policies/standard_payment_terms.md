# SOP-PAY-001: Standard Vendor Payment Terms and Invoice Validation

**Document ID**: POL-PAY-001  
**Category**: Accounts Payable & Vendor Operations  
**Effective Date**: 2024-01-01  
**Target Roles**: Accounts Payable Specialists, Procurement Managers, Vendor Support Agents  

---

## 1. Purpose and Scope
This Standard Operating Procedure (SOP) defines the mandatory payment terms, invoice verification protocols, early settlement discount schedules, and three-way matching criteria applied to all vendor disbursements across VendOps.

## 2. Standard Terms of Settlement
1. **Net 30 Baseline**:
   - Unless explicitly contracted otherwise in an approved master vendor agreement, standard settlement terms are **Net 30 calendar days** from the invoice receipt date logged in the ERP system.
   - Scheduled disbursements execute on the nearest weekly payment run following maturity.
2. **Early Payment Discounts**:
   - VendOps adheres to a standard **2/10 Net 30** discount term for eligible suppliers.
   - Vendors offering prompt settlement discounts will receive disbursement within **10 calendar days** of invoice approval, with a **2.0% deduction** applied against gross invoiced amount.
   - If processing delays on the VendOps side prevent payment within 10 days, the full Net 30 amount is paid without deduction.

## 3. Mandatory Canonical Invoice Criteria
Invoices submitted to VendOps must satisfy strict validation rules prior to processing:
- **Invoice ID**: Must follow the canonical uppercase format `INV-XXXXXXXX` (8 numeric digits, e.g., `INV-20240101`).
- **Purchase Order Reference**: Must reference a valid and approved Purchase Order ID in format `PO-XXXXXXXX`.
- **Vendor Identification**: Must state the registered Vendor ID (`VND-XXXXXX`) and legal entity name.
- **Line Item Specifics**: Each line must itemize line number, item SKU, unit price, quantity, and total extension in authorized currency (default: USD).
- Invoices failing canonical validation will be marked `DISPUTED` or `CANCELLED` and returned to the vendor.

## 4. Three-Way Reconciliation Protocol
Payment release requires automated 3-way matching between:
1. The authorized Purchase Order (`PO-XXXXXXXX`).
2. The warehouse Goods Receipt Note (`GRN-XXXXXXXX`).
3. The vendor Invoice (`INV-XXXXXXXX`).

- **Perfect Match (`PERFECT_MATCH`)**: Quantities and unit prices match within defined zero-variance limits. System automatically schedules `RELEASE_PAYMENT`.
- **Discrepant Invoices**: Invoices with discrepancies are placed on `ON_HOLD` status and routed to dispute resolution.

## 5. Dispute Resolution Actions
- **`RELEASE_PAYMENT`**: Executed when documentation confirms compliant delivery and billing.
- **`REJECT`**: Applied to duplicate invoices (`DUPLICATE_INVOICE`) or uncontracted charges.
- **`ESCALATE`**: Invoices with unresolved discrepancies exceeding $5,000 USD require human-in-the-loop managerial sign-off.
