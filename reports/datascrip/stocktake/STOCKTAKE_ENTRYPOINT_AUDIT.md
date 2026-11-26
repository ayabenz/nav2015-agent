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

The highest-value correction is to enforce stocktake at common posting boundaries while passing the actual posting intent (Ship, Receive, Invoice) and to add a posting-time warehouse shipment check. Simply calling the existing `BlockStocktakeSalesHeader(SalesHeader,FALSE)` at Codeunit 80 is **not sufficient**: for Sales Orders it filters only Qty. to Ship, and for Return Orders only Return Qty. to Receive. An invoice-only posting normally has those quantities at zero and would still escape the gate.

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


## 7. Return Order / Credit Memo entry points

The return-side pages confirm the same invoice-only gap found on Sales Orders:

| Entry point | Route observed | Stocktake gate | Assessment |
|---|---|---|---|
| Page 6630 — Sales Return Order, Post Ship/Receive choice | Codeunit 50081 → Codeunit 80 | Codeunit 50081 OnRun calls `BlockStocktakeSalesHeader(Rec,FALSE)` | Gate present for Return Qty. to Receive. |
| Page 6630 — Post Invoice/Credit Memo choice | Codeunit 50082 → Codeunit 80 | None | **Gap.** Codeunit 50082 sets Receive=FALSE / Invoice=TRUE for Return Order. |
| Page 6630 — Post and Print | Codeunit 82 → Codeunit 80 or Codeunit 88 | None | **Gap.** |
| Page 6630 — Post Batch | Report 6655 → Codeunit 80 | None | **Gap.** Report 6655 sets Receive/Invoice request flags and calls Sales-Post directly. |
| Page 44 — Sales Credit Memo, Post | Codeunit 81 → Codeunit 80 or Codeunit 88 | None | **Gap.** |
| Page 44 — Post and Print / Post and Email | Codeunit 82 → Codeunit 80 or Codeunit 88 | None | **Gap.** |
| Page 44 — Post Batch | Report 298 → Codeunit 80 | None | **Gap.** Report 298 calls Sales-Post directly for Credit Memo records. |
| Sales Return Order → Warehouse Receipt source creation | Codeunit 5751 `CreateFromSalesReturnOrder` | `BlockStocktakeSalesHeader(SalesHeader,FALSE)` | Gate present at source-document creation. |
| Warehouse Receipt → Return Order posting | Page 5768 → Page 7342/subform → Codeunit 5760 → Codeunit 80 | Page 5768 calls `BlockStocktakeWarehouseReceiptHeader(Rec)` before both inspected posting actions | Gate present in the inspected UI route; Codeunit 5760 itself has no Codeunit 50107 call. |

Evidence:
- Page 6630 action definitions around lines 394–443 show Ship/Receive uses Codeunit 50081 and Invoice uses Codeunit 50082. Post and Print around lines 453–480 calls the standard Codeunit 82 wrapper. Post Batch around lines 482–489 invokes Report 6655.
- Page 44 action definitions around lines 250–300 call Codeunit 81, Codeunit 82, Codeunit 82 PostAndEmail, and Report 298.
- Report 298 and Report 6655 each call Codeunit 80 directly from their Sales Header data item's OnAfterGetRecord trigger.
- Codeunit 5760 `PostSourceDocument` around lines 326–412 calls Purchase-Post, Sales-Post and TransferOrder-Post Receipt. It contains no Codeunit 50107 reference. Page 5768 is the inspected UI guard for warehouse receipts, while Codeunit 5705 independently protects transfer receipt posting.

## 8. Warehouse Shipment posting — additional bypass

Warehouse shipment creation and warehouse shipment posting are separate stages. Codeunit 5752 protects selected source-document creation methods, but the later posting stage does not repeat the Table 50063 check.

| Entry point | Route observed | Stocktake gate | Assessment |
|---|---|---|---|
| Page 7335 — Post Shipment | Page 7335 → Page 7336 subform `PostShipmentYesNo` → Codeunit 5764 → Codeunit 5763 | None in Page 7335, Page 7336, Codeunit 5764 or Codeunit 5763 | **Gap at posting time.** |
| Page 7335 — Post and Print | Page 7335 → Page 7336 `PostShipmentPrintYesNo` → Codeunit 5765 → Codeunit 5763 | None | **Gap at posting time.** The action is currently hidden/disabled in this page export, but the callable procedure exists. |
| Page 7335 — Post Batch | Report 50223 → Codeunit 5763 | None | **Gap.** Batch path bypasses the source-document creation wrapper. |
| Codeunit 5763 — Whse.-Post Shipment | Iterates warehouse shipment lines, then posts source Sales/Purchase/Transfer documents | No Codeunit 50107 reference in the full exported object | **No central warehouse shipment gate.** |
| Codeunit 5760 — Whse.-Post Receipt | Iterates warehouse receipt lines, then posts Purchase/Sales Return/Transfer source documents | No Codeunit 50107 reference in the full exported object | UI guard exists on Page 5768; direct invocation is not protected by this codeunit. |

Evidence:
- Page 7335 Post Shipment action around lines 168–178 delegates to the subform. Post Batch around lines 194–221 calls Report 50223 through `SetPostBatch(FALSE)`.
- Page 7336 `PostShipmentYesNo` around lines 248–258 runs Codeunit 5764; `PostShipmentPrintYesNo` around lines 260–270 runs Codeunit 5765.
- Codeunit 5764 and 5765 both configure and run Codeunit 5763; neither calls Codeunit 50107.
- Codeunit 5763 OnRun around lines 16–22 runs its posting Code and then CheckDeptMAS. Its `PostSourceDocument` procedure around lines 335–465 directly calls Codeunit 80 for Sales Order/Return Receipt source lines, Codeunit 90 for Purchase Return Order source lines, and Codeunit 5704 for Transfer Shipment source lines.
- Report 50223 around lines 38–87 collects finished, completely picked warehouse shipments and runs Codeunit 5763 for each. No stocktake call is present.
- Full exported Codeunit 5760 and Codeunit 5763 contain no `BlockStocktake` or `50107` reference.

**Operational consequence:** a warehouse shipment created before a stocktake window begins can remain available to post during the stocktake window. The source-creation gate in Codeunit 5752 does not re-evaluate an already-created warehouse shipment. Manually assembled or otherwise populated warehouse shipments may also avoid that source-creation gate.

**Recommended correction:** add a posting-time check at Codeunit 5763 before source-document posting, evaluating the actual Warehouse Shipment Line quantities and source document type/direction against Table 50063. Preserve the existing Codeunit 5752 checks because they prevent adding blocked source documents to new warehouse shipments. For receipts, consider a corresponding check inside Codeunit 5760 so non-Page-5768 callers cannot bypass the Page 5768 gate. Transfer shipment/receipt still has its own Codeunit 5704/5705 checks; avoid duplicate errors and validate the intended behavior.

## 9. Updated remediation order

1. **Sales posting:** enforce a posting-intent-aware check at Codeunit 80, including Qty. to Invoice.
2. **Warehouse shipment posting:** add a posting-time gate to Codeunit 5763, not only the source-document creation check in Codeunit 5752.
3. **Purchase posting:** enforce at the common Purch.-Post boundary with Ship/Receive/Invoice intent; current Codeunits 91/92 gate only Ship or Receive.
4. **Warehouse receipt posting:** retain Page 5768 checks and consider a central check in Codeunit 5760 for alternate callers.
5. **Transfer posting:** preserve Codeunit 5704/5705 gates.
6. Regression-test UI, batch, job queue, warehouse shipment created before a stocktake window, manually assembled warehouse shipments, and direct codeunit execution.
