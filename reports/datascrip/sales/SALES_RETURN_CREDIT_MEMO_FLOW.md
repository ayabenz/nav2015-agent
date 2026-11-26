# Sales Return Order → Return Receipt / Credit Memo

**Scope:** NAVW18 company export, objects Page 6630, Page 44, Table 36/37, Codeunits 80, 50081, 50082, 82, 5751, 5760 and Reports 298/6655. This is source-level reconstruction; runtime behavior and setup-dependent paths still require validation.

**Company-confirmed exception:** Codeunit 50081's Receive/Ship route performs the stocktake check; Codeunit 50082's invoice-only route intentionally does not repeat it. This behavior is accepted by the company and is not a defect.

## 1. Process overview

A Sales Return Order (Table 36, Document Type = Return Order) has two distinct posting intents:

1. **Receive goods** — records the physical return and creates a Posted Return Receipt (Table 6660). The key quantity is `Return Qty. to Receive`.
2. **Invoice / credit the customer** — creates a Posted Sales Credit Memo (Table 114). The key quantity is `Qty. to Invoice`, constrained by quantities already received when invoice-only posting is selected.

These operations can be performed separately or together, depending on the entry point. A standalone Sales Credit Memo (Document Type = Credit Memo) has a different default: Codeunit 80 sets Invoice=TRUE and Receive=TRUE. Whether it creates a Return Receipt is additionally controlled by Sales & Receivables Setup `Return Receipt on Credit Memo`.

## 2. Entry points and posting modes

| UI / batch entry | Wrapper | Return Order behavior | Credit Memo behavior |
|---|---|---|---|
| Page 6630 F9 Post | Custom Codeunit 50081 / 50082 | Choice 1 invokes Receive-only; choice 2 invokes Invoice-only | Page 6630 is filtered to Return Order |
| Page 6630 Post & Print | Standard Codeunit 82 | Offers Receive, Invoice, or Receive and Invoice | Not applicable to this page |
| Page 6630 Post Batch | Report 6655 → Codeunit 80 | Uses request-page Receive/Invoice flags | Not applicable |
| Page 44 Sales Credit Memo F9 | Standard Codeunit 81 → Codeunit 80 | Not applicable | Codeunit 80 defaults Invoice=TRUE and Receive=TRUE |
| Page 44 Post & Print / Post & Email | Standard Codeunit 82 → Codeunit 80 | Not applicable | Codeunit 80 defaults Invoice=TRUE and Receive=TRUE |
| Page 44 Post Batch | Report 298 → Codeunit 80 | Not applicable | Report runs Codeunit 80 directly |
| Page 6630 Create Whse. Receipt | Codeunit 5751 `CreateFromSalesReturnOrder` | Creates warehouse receipt source lines after stocktake check | Not applicable |
| Page 5768 Warehouse Receipt Post | Page 5768 → Page 7342 → Codeunit 5760 → Codeunit 80 | Receive-only from warehouse receipt source line | Not applicable for Sales Credit Memo source in this inspected branch |

### Wrapper behavior

- Codeunit 50081 OnRun calls `BlockStocktakeSalesHeader(Rec,FALSE)` before its Code procedure. For Return Order it sets Receive=TRUE and Invoice=FALSE, then runs Codeunit 80.
- Codeunit 50082 does not call Codeunit 50107. For Return Order it sets Receive=FALSE and Invoice=TRUE, then runs Codeunit 80.
- Codeunit 82 supports the combined Receive + Invoice choice for Return Order. Its posting path may be direct to Codeunit 80 or via Codeunit 88 job queue.
- Report 6655 sets Receive and Invoice from its request parameters, then runs Codeunit 80 directly.
- Report 298 runs Codeunit 80 directly for Credit Memo records.

## 3. Warehouse receipt route

1. Page 6630 action **Create Whse. Receipt** invokes Codeunit 5751 `CreateFromSalesReturnOrder(Rec)`.
2. Codeunit 5751 calls `BlockStocktakeSalesHeader(SalesHeader,FALSE)` before creating/locating the inbound warehouse receipt for the released Return Order.
3. Page 5768 Warehouse Receipt has two inspected posting actions (Post and Post & Print). Both call `BlockStocktakeWarehouseReceiptHeader(Rec)` before delegating to the receipt subform.
4. Page 7342 subform calls Codeunit 5760 `Whse.-Post Receipt`.
5. Codeunit 5760 `PostSourceDocument` identifies Sales Line source documents. For Sales Return Order it sets SalesHeader.Receive=TRUE and Invoice=FALSE, then calls Codeunit 80.
6. Codeunit 80 allocates Return Receipt No. when Receive is selected, inserts Return Receipt Header, and posts the return quantities. It also links the warehouse receipt reference to the posted return receipt when the warehouse path is used.

Important distinction: the source-document creation check in Codeunit 5751 and posting action check on Page 5768 are separate gates. Codeunit 5760 itself contains no Codeunit 50107 reference, so direct or alternate invocation needs separate validation.

## 4. Codeunit 80 behavior and database impact

### 4.1 Posting flags and quantity eligibility

In Codeunit 80 OnRun:

- Return Order defaults Ship=FALSE; the wrapper or calling process supplies Receive/Invoice.
- Credit Memo defaults Ship=FALSE, Invoice=TRUE, Receive=TRUE.
- When Invoice is selected for a Return Order without Receive, Codeunit 80 verifies invoice eligibility against `Return Qty. Received - Quantity Invoiced`.
- When Receive is selected, it filters Sales Line by nonzero Quantity and nonzero Return Qty. to Receive, excludes lines with an existing Return Receipt No., and performs tracking / warehouse checks.

### 4.2 Posted Return Receipt

When Receive is true and the document is a Return Order, Codeunit 80:
- Allocates `Return Receipt No.` from the configured number series if missing.
- Inserts Return Receipt Header (Table 6660) using TRANSFERFIELDS from Sales Header.
- Stores the originating Return Order No. and series.
- Copies comments/record links when the corresponding setup option is enabled.
- If the warehouse path is active, creates the posted warehouse receipt header using the Return Receipt No.

Evidence: Codeunit 80 around lines 296–302 (number allocation), 729–776 (Return Receipt Header creation and warehouse links).

### 4.3 Posted Sales Credit Memo

When Invoice is true, Codeunit 80 creates a Sales Invoice Header for Order/Invoice document types, otherwise a Sales Credit Memo Header. For Return Order, it stores Return Order No. and the associated series on the posted Credit Memo.

Evidence: Codeunit 80 around lines 778–870.

### 4.4 Item Ledger and inventory movement context

Codeunit 80 `PostItemJnlLine`:
- Copies Sales Line Owner into Item Journal Line Owner.
- Sets Item Journal Entry Type to Sale.
- For Return Order/Credit Memo lines with nonzero shipped/received quantity, assigns Item Journal Document Type = Sales Return Receipt and references ReturnRcptHeader.
- For invoice-only quantity, it uses Sales Credit Memo as the Item Journal Document Type.
- Passes the Item Journal Line to Codeunit 22 through `ItemJnlPostLine.RunWithCheck`.

Evidence: Codeunit 80 around lines 2672–2720 and 2738–2854; Codeunit 22 then applies the standard item quantity/value posting and company Ownership Ledger extension documented in the main Sales Order → Posting report.

Do not infer final sign or inventory effect solely from Entry Type=Sale. The NAV return line quantity convention and the actual posting quantities determine the signed Item Journal quantity; validate with a real posted Return Order and linked Item Ledger Entry.

## 5. Stocktake enforcement findings

- Receive-only Return Order through Codeunit 50081 is gated using `BlockStocktakeSalesHeader`, which filters Return Qty. to Receive.
- Invoice-only Return Order through Codeunit 50082 is not gated; the company explicitly confirms this is intentional and it must not be treated as a defect.
- Combined Receive + Invoice through Codeunit 82 is not gated by the wrapper.
- Batch Return Order through Report 6655 is not gated.
- Credit Memo through Page 44 / Codeunits 81–82 and Report 298 is not gated in those entry points.
- Warehouse receipt Page 5768 gates both inspected UI posting actions. Codeunit 5760 itself has no central stocktake call.

This aligns with the broader [Stocktake Entry-Point Audit](../stocktake/STOCKTAKE_ENTRYPOINT_AUDIT.md). **Do not add a duplicate stocktake check to Codeunit 50082 or centralize a new gate in Codeunit 80 solely to cover this invoice-only route**; that would contradict the company-approved exception. Other routes such as Page 44, batch posting, and warehouse posting remain separate policy questions and must not be conflated with the accepted 50082 behavior.

## 6. Open validation items

1. Confirm Sales & Receivables Setup `Return Receipt on Credit Memo` in the production company and test standalone Credit Memo posting.
2. Confirm whether Page 6630's custom F9 two-choice menu intentionally omits combined Receive + Invoice; Post & Print via Codeunit 82 exposes a combined choice.
3. Trace one real Return Order through warehouse receipt to posted Return Receipt Header/Line and Item Ledger Entry, including Owner and warehouse references.
4. Validate whether the invoice-only path after a previous partial receipt correctly limits Qty. to Invoice to received-not-invoiced quantity.
5. Confirm direct Codeunit 5760 callers and job queue integrations; the page-level gate alone does not protect arbitrary direct invocation.
