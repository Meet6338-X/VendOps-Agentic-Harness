# SOP-INV-002: Short Shipment and Goods Receipt Discrepancy Resolution

**Document ID**: POL-INV-002  
**Category**: Inventory Reconciliation & Payment Disputes  
**Effective Date**: 2024-01-01  
**Target Roles**: Receiving Warehouse Supervisors, AP Auditors, Dispute Resolution Agents  

---

## 1. Purpose and Scope
This policy establishes operational guidelines for resolving disputes arising from short shipments, partial deliveries, and quantity discrepancies between billed invoices and warehouse Goods Receipt Notes (GRN).

## 2. Source of Truth for Physical Delivery
1. The physical count verified and recorded on the canonical Goods Receipt Note (`GRN-XXXXXXXX`) by the receiving warehouse dock supervisor is the definitive source of truth for goods received.
2. Carrier delivery slips or vendor packing lists do not override verified warehouse scan counts recorded on the GRN.
3. Relevant dispute classifications:
   - `QTY_MISMATCH`: Quantity billed on invoice differs from quantity accepted on GRN.
   - `SHORT_PAYMENT`: Vendor disputes deduction resulting from short shipment adjustment.
   - `MISSING_GRN`: Invoice received without corresponding warehouse intake record.

## 3. Automated Partial Payment Authorization
When an invoice reflects quantities higher than the accepted quantity confirmed on `GRN-XXXXXXXX`:
1. **Immediate Partial Payment (`PARTIAL_PAYMENT`)**:
   - VendOps will not withhold payment for the entirety of a disputed invoice.
   - The ERP system automatically calculates and authorizes `PARTIAL_PAYMENT` strictly for the verified accepted quantity (`accepted_qty`) multiplied by the authorized PO line unit price.
   - The authorized amount is scheduled for disbursement in accordance with vendor settlement terms.
2. **Shortage Balance Treatment**:
   - The delta quantity (`billed_qty - accepted_qty`) is flagged as unfulfilled.
   - No payment is released for unreceived goods under any circumstance.

## 4. Vendor Credit Note Requirement
1. **Mandatory Credit Note (`CREDIT_NOTE`)**:
   - To reconcile the accounting ledger, the vendor must furnish a canonical credit note matching the value of the unfulfilled balance within **10 business days** of notification.
   - Credit note calculation: `Shortage Value = (billed_qty - accepted_qty) * unit_price`.
2. **Back-order and Subsequent Deliveries**:
   - If the shortage represents a delayed back-order that will be fulfilled in a subsequent shipment:
     - The vendor must issue a revised invoice or supplementary invoice tied to a new Goods Receipt Note upon physical delivery.
     - Never bill unreceived goods on a prior short-shipped invoice.

## 5. Escalation Thresholds
- Quantity discrepancies where the shortage amount exceeds **$2,500.00 USD** or involves serial-controlled inventory require human reviewer sign-off (`ESCALATE`) before automated partial payment execution.
