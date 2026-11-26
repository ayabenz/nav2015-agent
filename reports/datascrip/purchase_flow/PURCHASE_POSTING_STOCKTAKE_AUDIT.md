# Purchase Posting — Stocktake Entry-Point Audit

**Scope:** Purchase Order, Purchase Invoice, Purchase Return Order, Purchase Credit Memo, warehouse receipt/shipment, warehouse activity posting, batch posting, job queue, and correction posting. Sources are from the customized NAVW18.00 export.

## 1. Executive summary

Codeunit 90 `Purch.-Post` is the shared purchase posting engine and contains no direct Codeunit 50107 / stocktake call in the inspected source. Stocktake protection currently depends on which entry point calls it.

- Codeunits 91 and 92 call `BlockStocktakePurchaseHeader` only when their `Ship` or `Receive` flags are already TRUE.
- Normal Purchase Order / Purchase Return Order UI choices set those flags before the check, so receipt/shipment selections are checked.
- Purchase Invoice / Purchase Credit Memo paths do not set those flags in Codeunits 91/92 before the check; Codeunit 90 later defaults Purchase Invoice to Receive=TRUE and Purchase Credit Memo to Ship=TRUE. Static inspection therefore indicates the check can be skipped for those physical movements.
- Batch reports, warehouse posting codeunits, warehouse activity posting, and purchase invoice correction call Codeunit 90 directly without a stocktake check.
- Warehouse source-document creation does check stocktake in Codeunits 5751/5752, but that check is not repeated by the purchase posting routes in Codeunits 5760/5763 or 7324.

**Conclusion:** Purchase posting has several routes that may physically receive or ship inventory without a stocktake check at the moment of posting. These are potential gaps pending company policy confirmation, not automatic defects. Preserve the existing Codeunit 91/92 behavior for normal Purchase Order / Return Order selections unless the company requests a change.

## 2. Shared posting engine — Codeunit 90

Codeunit 90 `Purch.-Post`:
- Requires Released status and validates vendor, posting date, document date, and other purchase constraints.
- Validates Owner on Item lines when the Location has Ownership enabled.
- Sets posting flags by Document Type:
  - Order: `Ship := FALSE`; Receive/Invoice are supplied by caller.
  - Invoice: `Receive := TRUE; Invoice := TRUE; Ship := FALSE`.
  - Return Order: `Receive := FALSE`; Ship/Invoice supplied by caller.
  - Credit Memo: `Receive := FALSE; Invoice := TRUE; Ship := TRUE`.
- Does not call Codeunit 50107 in the inspected 6,405-line source.

This means a caller must perform the stocktake check before calling Codeunit 90 if the selected operation moves inventory. Codeunit 90 itself will not enforce the stocktake window.

## 3. Single-document UI posting

### 3.1 Purchase Order — Page 50

- Post (F9) → Codeunit 91 `Purch.-Post (Yes/No)`.
- Post & Print → Codeunit 92 `Purch.-Post + Print`.
- Codeunit 91/92 show Invoice or Receive + Invoice choices.
- They set Receive/Invoice according to the selected option.
- They call `BlockStocktakePurchaseHeader(PurchHeader)` when `Ship OR Receive` is TRUE, before enqueuing or running Codeunit 90.

Result:
- Receive + Invoice is checked before posting.
- Invoice-only does not receive inventory and does not invoke the stocktake check.

### 3.2 Purchase Return Order — Page 6640

- Post (F9) → Codeunit 91.
- Post & Print → Codeunit 92.
- The wrapper shows Ship, Invoice, or Ship + Invoice.
- Ship is set before the stocktake condition.
- The wrapper calls `BlockStocktakePurchaseHeader` when Ship is TRUE.

Result:
- Ship and Ship + Invoice are checked.
- Invoice-only does not ship physical inventory and does not invoke the check.

### 3.3 Purchase Invoice — Page 51

Page 51 routes Post / Post & Print through Codeunit 91/92. For Document Type Invoice, neither wrapper's CASE branch explicitly sets Receive before the stocktake condition; the ELSE branch only confirms the action. Codeunit 90 later defaults Invoice to Receive=TRUE and Invoice=TRUE.

Therefore, the pre-posting stocktake condition in Codeunit 91/92 may be false before Codeunit 90 sets Receive=TRUE. **The actual Purchase Invoice receipt path appears unprotected by the wrapper check.** Confirm the Receive field's runtime value on the Purchase Header before treating this as a confirmed bypass.

### 3.4 Purchase Credit Memo — Page 52

Page 52 also routes Post / Post & Print through Codeunit 91/92. For Document Type Credit Memo, the wrapper's ELSE branch only confirms the action; it does not explicitly set Ship before the stocktake condition. Codeunit 90 later defaults Credit Memo to Ship=TRUE and Invoice=TRUE.

Therefore, the wrapper check may be skipped before Codeunit 90 applies the physical shipment flag. **The actual Purchase Credit Memo shipment path appears unprotected by the wrapper check.** Confirm the Ship field's runtime value before treating this as a confirmed bypass.

## 4. Batch posting routes

The batch reports call Codeunit 90 directly; they do not pass through Codeunit 91/92 and do not call Codeunit 50107.

| Entry point | Downstream call | Inventory movement | Stocktake check |
|---|---|---|---|
| Page 50 Post Batch → Report 496 Batch Post Purchase Orders | C90 directly | Receive when requested | No check in Report 496 |
| Page 51 Post Batch → Report 497 Batch Post Purchase Invoices | C90 directly | C90 defaults Receive=TRUE | No check in Report 497 |
| Page 52 Post Batch → Report 498 Batch Post Purch. Credit Memos | C90 directly | C90 defaults Ship=TRUE | No check in Report 498 |
| Page 6640 Post Batch → Report 6665 Batch Post Purch. Ret. Orders | C90 directly | Ship according to ShipReq | No check in Report 6665 |

Report 496 sets Receive and Invoice from request-page options. Report 6665 sets Ship and Invoice from request-page options. Reports 497 and 498 call Codeunit 90 with their document types; Codeunit 90 supplies the physical Receive/Ship defaults.

## 5. Job Queue posting

Codeunits 91/92 perform the stocktake check before calling Codeunit 98 when Post with Job Queue is enabled.

Codeunit 98 `Purchase Post via Job Queue`:
- OnRun retrieves the Purchase Header from the Job Queue Entry.
- Marks it Posting.
- Calls Codeunit 90 directly.
- Does not call Codeunit 50107.

This creates a time-of-check/time-of-use concern: if the wrapper check passes when the job is enqueued, but a stocktake window becomes active before the job actually executes, the job queue can post without rechecking stocktake at execution time.

## 6. Warehouse receipt and shipment

### 6.1 Source-document creation

- Codeunit 5751 `CreateFromPurchOrder` calls `BlockStocktakePurchaseHeader(PurchHeader)` before creating inbound warehouse source lines.
- Codeunit 5752 `CreateFromPurchaseReturnOrder` calls `BlockStocktakePurchaseHeader(PurchHeader)` before creating outbound warehouse source lines.

These are source-creation checks, not posting-time checks.

### 6.2 Actual warehouse receipt — Codeunit 5760

For Source Type Purchase Line:
- Purchase Order sets `Receive := TRUE`.
- Purchase Return Order sets `Ship := TRUE`.
- It sets `Invoice := TRUE`.
- It calls Codeunit 90 directly according to the Warehouse Receipt Posting Policy.

No Codeunit 50107 call is present in Codeunit 5760. Therefore a previously created warehouse receipt can be posted during an active stocktake window without re-evaluating the purchase stocktake rule.

Transfer Line is different: Codeunit 5760 delegates to Codeunit 5705, which performs the IN stocktake check.

### 6.3 Actual warehouse shipment — Codeunit 5763

For Source Type Purchase Line:
- Purchase Order sets `Receive := TRUE`.
- Purchase Return Order sets `Ship := TRUE`.
- It sets Invoice from the warehouse shipment option.
- It calls Codeunit 90 directly according to the Warehouse Shipment Posting Policy.

No Codeunit 50107 call is present in Codeunit 5763. Therefore a previously created Purchase Return Order warehouse shipment can be posted during an active stocktake window without re-evaluating the purchase stocktake rule.

Transfer Line is different: Codeunit 5763 delegates to Codeunit 5704, which performs the OUT stocktake check.

## 7. Warehouse Activity posting — Codeunit 7324

Codeunit 7324 `Whse.-Activity-Post` procedure `PostSourceDocument` handles Purchase Line:
- Executes COMMIT.
- Sets Receive=TRUE for Purchase Order, otherwise Ship=TRUE.
- Sets Invoice from InvoiceSourceDoc.
- Calls Codeunit 90 directly.
- Does not call Codeunit 50107.

Transfer Line sources are delegated to Codeunit 5704/5705, which perform stocktake checks. Purchase Line sources are not.

This is an additional posting route beyond the standard Purchase Order / Return Order pages and the warehouse receipt/shipment pages.

## 8. Purchase invoice correction — Codeunit 1313

Codeunit 1313 `Correct Posted Purch. Invoice` creates a Purchase Credit Memo from a posted invoice, copies document lines, then calls Codeunit 90 directly. It does not call Codeunit 50107.

Codeunit 90 defaults Credit Memo to Ship=TRUE and Invoice=TRUE. The correction route can therefore reverse physical inventory without an inspected stocktake check. Confirm whether the company expects invoice correction to be blocked during stocktake.

## 9. Mini Purchase Credit Memo pages

- Page 1367 Mini Purchase Credit Memos.
- Page 1369 Mini Purchase Credit Memo.

Post (F9) uses Codeunit 91 through Table 38 `SendToPosting`; Codeunit 91's stocktake condition depends on Ship/Receive flags before Codeunit 90 applies the Credit Memo defaults.

Post & Print passes Codeunit 90 directly through `SendToPosting`, bypassing Codeunit 91/92's stocktake condition entirely.

These are additional Credit Memo routes that should be included in runtime validation.

## 10. Codeunit 90 caller inventory

The caller exporter now supports a target Codeunit ID and produced:
[Purchase Post caller manifest](../purchase_post_callers/callers_manifest.csv).

The manifest contains 31 objects referencing Codeunit 90 or the `Purch.-Post` symbol. Not all are posting callers:
- Calculation/reporting helpers: Codeunits 57 and 439, reports 404/405/410/6641, and Table 50046.
- Approval / page helpers: Codeunit 80 and Pages 161/233/403.
- Actual posting routes identified: Codeunits 91/92/98/1313/5760/5763/7324, Pages 1367/1369, and Reports 496/497/498/6665.
- Page/report helpers that only calculate or preview purchase lines should not be classified as physical posting routes.

## 11. Findings matrix

| Route | Check before actual posting? | Assessment |
|---|---|---|
| Page 50 Purchase Order Receive | Yes, Codeunit 91/92 | Protected |
| Page 50 Purchase Order Invoice-only | No check, no physical receipt | Expected no movement |
| Page 6640 Purchase Return Order Ship | Yes, Codeunit 91/92 | Protected |
| Page 6640 Return Order Invoice-only | No check, no physical shipment | Expected no movement |
| Page 51 Purchase Invoice | Wrapper check may be skipped before C90 defaults Receive=TRUE | Needs runtime/policy confirmation |
| Page 52 Purchase Credit Memo | Wrapper check may be skipped before C90 defaults Ship=TRUE | Needs runtime/policy confirmation |
| Batch Reports 496/497/498/6665 | Direct C90 | No check found |
| Job Queue C98 | Check at enqueue only; none at execution | Timing gap |
| Warehouse Receipt C5760 Purchase Line | Direct C90 | No posting-time check |
| Warehouse Shipment C5763 Purchase Line | Direct C90 | No posting-time check |
| Warehouse Activity C7324 Purchase Line | Direct C90 | No posting-time check |
| Correct Posted Purchase Invoice C1313 | Direct C90 | No check found |
| Mini Purchase Credit Memo Post & Print | Direct C90 | No check found |
| Warehouse Transfer Line routes | C5704/C5705 | Protected by OUT/IN checks |

## 12. Open business decisions

Before recommending code changes, confirm whether stocktake should block:
1. Purchase Invoice receipt posting.
2. Purchase Credit Memo shipment posting.
3. Batch Purchase Order receipt and Purchase Return Order shipment.
4. Batch Purchase Invoice / Credit Memo, where Codeunit 90 applies Receive/Ship defaults.
5. Warehouse receipt/shipment and warehouse activity purchase posting.
6. Job Queue execution when a stocktake window starts after enqueue.
7. Correct Posted Purchase Invoice / Mini Purchase Credit Memo routes.

The requirement should be applied to the actual physical operation (Receive/Ship), not merely the document label. Preserve invoice-only selections that do not move inventory unless the business explicitly wants them blocked.

## 13. Source files

- `reports/datascrip/purchase_flow/Codeunit_90.txt`
- `reports/datascrip/purchase_flow/Codeunit_91.txt`
- `reports/datascrip/purchase_flow/Codeunit_92.txt`
- `reports/datascrip/purchase_flow/Codeunit_98.txt`
- `reports/datascrip/purchase_flow/Codeunit_5751.txt`
- `reports/datascrip/purchase_flow/Codeunit_5752.txt`
- `reports/datascrip/purchase_flow/Codeunit_5760.txt`
- `reports/datascrip/purchase_flow/Codeunit_5763.txt`
- `reports/datascrip/purchase_post_callers/Codeunit_1313.txt`
- `reports/datascrip/purchase_post_callers/Codeunit_7324.txt`
- `reports/datascrip/purchase_post_callers/Page_1367.txt`
- `reports/datascrip/purchase_post_callers/Page_1369.txt`
- `reports/datascrip/purchase_post_callers/Report_496.txt`
- `reports/datascrip/purchase_post_callers/Report_497.txt`
- `reports/datascrip/purchase_post_callers/Report_498.txt`
- `reports/datascrip/purchase_post_callers/Report_6665.txt`
- `reports/datascrip/purchase_post_callers/callers_manifest.csv`

Related company decision: [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3).
