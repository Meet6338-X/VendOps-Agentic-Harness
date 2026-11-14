# SOP-DMG-004: Damaged Goods Rejection, Quarantine, and Replacement Protocol

**Document ID**: POL-DMG-004  
**Category**: Quality Assurance & Receiving Reconciliation  
**Effective Date**: 2024-01-01  
**Target Roles**: Inbound Quality Inspectors, AP Clerks, Supply Chain Operations  

---

## 1. Purpose and Scope
This policy specifies procedures for logging damaged or substandard goods upon warehouse intake, quarantine management, and executing financial remedies via replacement purchase orders or credit notes.

## 2. Inbound Goods Inspection and Rejection Logging
1. Inbound shipments undergo mandatory physical inspection at unloading docks.
2. If goods are damaged, compromised, or defective, the dock inspector logs the rejected count on the Goods Receipt Note (`GRN-XXXXXXXX`) under `rejected_qty`.
3. Standard rejection codes logged in `rejection_reason`:
   - `TRANSIT_DAMAGE`: Crushed cartons, broken packaging, exterior trauma.
   - `SEAL_TAMPERED`: Broken security seals or compromised packaging integrity.
   - `WATER_MOISTURE`: Liquid penetration, dampness, mold.
   - `NON_CONFORMING`: Deviations from technical specifications or expired product life.

## 3. Financial and Inventory Remedies
When goods are recorded as rejected on `GRN-XXXXXXXX`, two standardized settlement paths exist:

### Path A: Zero-Cost Replacement PO (`REPLACEMENT`)
- **Applicability**: When the buyer still requires the damaged inventory and the supplier can deliver compliant items within operational lead times.
- **Workflow**:
  1. The original invoice is authorized only for accepted items (`accepted_qty`).
  2. Procurement issues a linked replacement purchase order (`REPLACEMENT`) at zero additional cost to the buyer.
  3. The vendor dispatches replacement items referencing the replacement PO and new GRN.

### Path B: Vendor Credit Note (`CREDIT_NOTE`)
- **Applicability**: When replacement inventory is unavailable, lead times are unacceptable, or the buyer elects to cancel the damaged portion.
- **Workflow**:
  1. The vendor must issue a canonical `CREDIT_NOTE` for the full value of the rejected quantity: `Credit Amount = rejected_qty * PO_unit_price`.
  2. The credit note is credited against pending vendor payables or offset against future invoices.

## 4. Quarantine and Evidence Retention
1. Rejected goods are moved to the warehouse quarantine bay for **14 calendar days**.
2. For damaged claims exceeding **$1,000.00 USD**, high-resolution photographic evidence and carrier inspection reports must be archived with the GRN.
3. If the supplier fails to arrange return shipping or salvage within 14 days, the goods are scrapped at vendor expense.

## 5. Dispute Resolution Actions
- **`REPLACEMENT`**: Authorized when supplier agrees to expedited redelivery.
- **`CREDIT_NOTE`**: Issued to deduct damaged quantity value from total invoice balance.
- **`PARTIAL_PAYMENT`**: Immediately released for undamaged accepted items (`accepted_qty`).
- **`ESCALATE`**: Damage claims exceeding $5,000 USD require Supply Chain Director approval before final settlement.
