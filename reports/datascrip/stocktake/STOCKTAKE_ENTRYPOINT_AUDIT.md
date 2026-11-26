# Stocktake Gate — Posting Entry-Point Audit

**Branch:** `datascrip`  
**Scope:** Static source inspection of NAV posting and warehouse entry points that can reach Sales-Post, Purchase-Post, transfer posting, and warehouse receipt/shipment flows.  
**Source:** Company export `data/input/datascrip/datascrip.zip`, extracted by GitHub Actions. This is a static source audit, not runtime proof.

## Executive finding

The Table 50063 stocktake gate is **not consistently enforced across posting entry points**.

- Sales shipment/receipt paths have several gates, but invoice-only paths bypass them.
- Standard Sales posting wrappers and batch reports reach Codeunit 80 without calling Codeunit 50107.
- The Sales job-queue worker (Codeunit 88) also calls Codeunit 80 directly without a stocktake gate.
- Purchase wrappers gate Ship/Receive, but their invoice-only path skips the gate. The Purchase job-queue worker does not add a gate.
- Transfer shipment/receipt and the inspected warehouse source-document / warehouse-receipt actions do call the corresponding gate.

The highest-value correction is to enforce stocktake at a common posting boundary while passing the actual posting intent (Ship, Receive, Invoice). Simply calling the existing `BlockStocktakeSalesHeader(SalesHeader,FALSE)` at Codeunit 80 is **not sufficient**: for Sales Orders it filters only Qty. to Ship, and for Return Orders only Return Qty. to Receive. An invoice-only posting normally has those quantities at zero and would still escape the gate.

## 1. Sales posting routes

| Entry point | Route observed | Stocktake gate | Assessment |
|---|---|---|---|
| Page 42 — Post Ship action | Page 42 local `CheckBlockStockTake(FALSE)` → `ActionPostShipClick` → Codeunit 50081 → Codeunit 80 | Legacy local check plus `BlockStocktakeSalesHeader(Rec,FALSE)` in Codeunit 50081 | Gate present. The Page 42 local check is a separate older hard-coded location/category rule, not the Table 50063 rule. |
| Page 42 — F9 Post, Ship choice | `ActionPostShipClick` → Codeunit 50081 → Codeunit 80 | Codeunit 50081 OnRun | Gate present. F9 does not call the Page 42 local `CheckBlockStockTake`; it relies on Codeunit 50081. |
| Page 42 — F9 Post, Invoice choice | `ActionPostInvoiceClick` → Codeunit 50082 → Codeunit 80 | None in Codeunit 50082 | **Gap.** Codeunit 50082 sets Ship=FALSE / Invoice=TRUE for Orders and Receive=FALSE / Invoice=TRUE for Return Orders, then calls Sales-Post directly. |
| Page 42 — Post Invoice action | `ActionPostInvoiceClick` → Codeunit 50082 → Codeunit 80 | None | **Gap**, same route as above. |
| Page 42 — Post and Print | Codeunit 50084 → Codeunit 80 | None | **Gap.** Codeunit 50084's inspected Code procedure selects invoice-only posting for Orders and Return Orders. |
| Page 42 — Create Warehouse Shipment | Codeunit 5752 `CreateFromSalesOrder` | `BlockStocktakeSalesHeader(SalesHeader,TRUE)` | Gate present; uses Qty. to Whse. Shipment. |
| Page 43 — Post | Codeunit 81 → Codeunit 80, or Codeunit 88 when job queue is enabled | None in Codeunit 81 / 88 | **Gap.** Standard wrapper does not invoke Codeunit 50107. |
| Page 43 — Post and Print | Codeunit 82 → Codeunit 80, or Codeunit 88 for queued posting | None in Codeunit 82 / 88 | **Gap.** |
| Page 43 — Post and Email | Codeunit 82 `PostAndEmail` → Codeunit 80 | None | **Gap.** Email path explicitly posts synchronously through Codeunit 80. |
| Page 43 — Post Batch | Report 297 → Codeunit 80 | None | **Gap.** Report 297 runs Sales-Post for each Sales Header directly. |
| Report 296 — Batch Post Sales Orders | Report 296 → Codeunit 80 | None | **Gap.** Sets Ship/Invoice request flags and calls Sales-Post directly. |
| Report 297 — Batch Post Sales Invoices | Report 297 → Codeunit 80 | None | **Gap.** Calls Sales-Post directly for Sales Invoice records. |
| Sales job queue | Codeunit 88 `Sales Post via Job Queue` → Codeunit 80 | None in Codeunit 88 | **Gap.** Worker calls `CODEUNIT.RUN(CODEUNIT::"Sales-Post",SalesHeader)`; no Codeunit 50107 reference exists in this object. |

### Sales source evidence

- Page 42 actions: `Page 42 Sales Order`, action definitions around lines 794–847 and 848–900. The dedicated Post Ship action calls local `CheckBlockStockTake(FALSE)`; F9 dispatches to `ActionPostShipClick` or `ActionPostInvoiceClick`. `ActionPostInvoiceClick` calls Codeunit 50082 around line 2034. Post and Print calls Codeunit 50084 around line 895.
- Page 42 `ActionPostInvoiceClick`: lines 1932–2052; invoice quantity validations are present, but no Codeunit 50107 call is made before Codeunit 50082.
- Page 42 local `CheckBlockStockTake`: lines 2339–2480. It contains hard-coded location/category checks (for example PLGx, PTCx, STRx, CKGx), not the configurable Table 50063 rules. Its invocation on the dedicated Post Ship action does not make it a common posting gate.
- Codeunit 50081: OnRun around lines 13–18 calls `BlockStocktakeSalesHeader(Rec,FALSE)`, then its Code procedure sets Ship or Receive and invokes Codeunit 80. This protects the shipment/receipt wrapper route.
- Codeunit 50082: Code procedure around lines 32–60 sets invoice-only flags and invokes Codeunit 80 at line 58; no stocktake call.
- Codeunit 50084: Code procedure around lines 37–84 sets invoice-only flags and invokes Codeunit 80 at line 84; no stocktake call.
- Page 43: Post action around lines 226–236 uses Codeunit 81; Post and Print around lines 246–255 uses Codeunit 82; Post and Email around lines 257–265 calls Codeunit 82; Post Batch around lines 266–273 invokes Report 297.
- Codeunit 81: Code procedure around lines 31–72 chooses Ship/Receive/Invoice and either queues through Codeunit 88 or runs Codeunit 80. No Codeunit 50107 call.
- Codeunit 82: Code procedure around lines 44–83 chooses posting flags and either queues through Codeunit 88 or runs Codeunit 80. No Codeunit 50107 call.
- Codeunit 88: OnRun around lines 12–31 runs Codeunit 80 directly; EnqueueSalesDoc around lines 52–97 schedules this worker. No stocktake call.
- Report 296: Sales Header data item OnAfterGetRecord around lines 36–53 sets Ship/Invoice and calls Sales-Post.
- Report 297: Sales Header data item OnAfterGetRecord around lines 36–50 calls Sales-Post directly.
- Codeunit 80: OnRun begins around line 32, calls `CheckDeptMAS(Rec)`, copies the Sales Header and enters the posting flow. The full exported Codeunit 80 contains no `BlockStocktake` or `50107` reference.

## 2. Sales gate semantics make invoice-only bypass more significant

Codeunit 50107 `BlockStocktakeSalesHeader` currently behaves as follows:

- `CreateWhseShipment=TRUE`: filters Item lines by Qty. to Whse. Shipment > 0.
- Otherwise, Sales Order filters Qty. to Ship <> 0.
- Otherwise, Return Order filters Return Qty. to Receive <> 0.
- Other document types do not receive those quantity filters.
- The active rule direction is OUT|ALL for Order/Invoice and IN|ALL for Credit Memo/Return Order.

Consequences:

1. The existing call from Codeunit 50081 is suitable for its shipment/receipt intent.
2. The same method cannot safely be used unchanged as a universal invoice-posting gate. An Order invoice-only operation has Qty. to Ship = 0; a Return Order credit-only operation has Return Qty. to Receive = 0. The procedure can exit before checking Table 50063.
3. A standalone Sales Invoice/Credit Memo document type has no quantity filter in the current procedure, but the inspected Page 43 routes still do not call it.

**Recommended design:** introduce a posting-aware gate, for example `BlockStocktakeSalesPosting(SalesHeader,Ship,Receive,Invoice)`. It should select relevant Sales Line quantities according to the actual operation:
- Ship: Qty. to Ship;
- Receive: Return Qty. to Receive;
- Invoice: Qty. to Invoice;
- combined posting: include every selected operation's relevant quantity, with document type determining IN/OUT direction.

Call this gate from Codeunit 80 after it has a reliable Sales Header and posting flags, before any irreversible posting work. Keep warehouse-shipment creation's existing separate check because Qty. to Whse. Shipment is a distinct operational quantity. Avoid relying only on page actions or wrappers, because batch and job-queue routes bypass them.

Before implementation, verify the exact NAV 2015/NAVW18 build and confirm how the posting flags are represented in this customized Codeunit 80; then regression-test Order ship-only, Order invoice-only, Order ship+invoice, Return Order receive-only, Return Order invoice-only, standalone Invoice, standalone Credit Memo, batch, and job-queue routes.

## 3. Purchase posting routes

| Entry point | Route observed | Stocktake gate | Assessment |
|---|---|---|---|
| Codeunit 91 — Purch.-Post (Yes/No) | User choice → Codeunit 98 queue or Purch.-Post | Calls `BlockStocktakePurchaseHeader` only when Ship OR Receive | **Invoice-only gap.** |
| Codeunit 92 — Purch.-Post + Print | User choice → Codeunit 98 queue or Purch.-Post | Calls `BlockStocktakePurchaseHeader` only when Ship OR Receive | **Invoice-only gap.** |
| Codeunit 98 — Purchase Post via Job Queue | Queue worker → Purch.-Post | No gate in worker | Relies on wrapper having gated the selected operation; invoice-only was not gated upstream. |
| Warehouse inbound Purchase Order | Codeunit 5751 `CreateFromPurchOrder` | `BlockStocktakePurchaseHeader` | Gate present for warehouse receipt creation. |
| Warehouse outbound Purchase Return Order | Codeunit 5752 `CreateFromPurchaseReturnOrder` | `BlockStocktakePurchaseHeader` | Gate present for warehouse shipment creation. |

Codeunit 91 and 92 use the same condition: `IF Ship OR Receive THEN BlockStocktakePurchaseHeader(PurchHeader)`. The gate procedure itself maps Purchase Order/Invoice to IN|ALL and Purchase Return Order/Credit Memo to OUT|ALL. Therefore invoice-only posting is not checked even though the procedure can evaluate those document types.

## 4. Transfer and warehouse routes

| Entry point | Gate | Assessment |
|---|---|---|
| Transfer Order — Post Shipment, Codeunit 5704 | `BlockStocktakeTransferHeader(Rec,'OUT')` at OnRun | Present |
| Transfer Order — Post Receipt, Codeunit 5705 | `BlockStocktakeTransferHeader(Rec,'IN')` at OnRun | Present |
| Create inbound warehouse source documents, Codeunit 5751 | Purchase Order, Sales Return Order, inbound Transfer Order each call their relevant gate | Present for inspected source-document creation methods |
| Create outbound warehouse source documents, Codeunit 5752 | Sales Order, Purchase Return Order, outbound Transfer Order each call their relevant gate | Present for inspected source-document creation methods |
| Warehouse Receipt page, Page 5768 — Post | `BlockStocktakeWarehouseReceiptHeader(Rec)` before posting action | Present |
| Warehouse Receipt page, Page 5768 — Post and Print | Same gate before posting action | Present |

Page 5768 has the gate call on both inspected posting actions. The legacy local `CheckBlockStockTake` procedure in Page 5768 is not the basis for this conclusion; the active calls are to Codeunit 50107.

## 5. Recommended remediation order

1. **Sales central posting gate:** add a posting-intent-aware check to Codeunit 80. Include Qty. to Invoice; do not reuse the existing Ship/Receive-only filter unchanged.
2. **Purchase central posting gate:** add or move the check to the common Purch.-Post boundary, with invoice/receive/ship intent. At minimum, fix the `IF Ship OR Receive` condition in Codeunits 91/92, but central enforcement is safer for job queue and alternate entry points.
3. **Keep warehouse gates:** preserve the separate Create Warehouse Shipment and Warehouse Receipt checks, because their quantities and source-document timing differ from posting.
4. **Avoid duplicate user-facing errors:** if the central posting gate is authoritative, remove or demote duplicate wrapper checks only after regression tests prove no warehouse or pre-post route loses protection.
5. **Add automated source-level tests:** assert every known posting route reaches the central gate and test the operation/quantity matrix listed above.

## 6. Audit limitations

- This is static source inspection of the company export and selected entry points. It does not prove that every external integration, custom API, direct Codeunit.RUN, job queue record, or customer-specific extension has been enumerated.
- The extracted object headers include NAVW17/NAVW18 build markers while the target is described as NAV 2015. Confirm the installed application build before deploying code changes.
- Runtime tests are required to validate actual quantities, document-type behavior, job queue execution, and transaction rollback behavior.
