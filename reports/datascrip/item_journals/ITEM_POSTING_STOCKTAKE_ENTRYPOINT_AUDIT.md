# Item Posting — Stocktake Entry-Point Audit

**Scope:** Direct callers of Codeunit 22 (Item Jnl.-Post Line) discovered from the complete company export, with emphasis on inventory quantity posting routes outside Sales, Purchase, and Transfer. Static C/AL inspection only; no runtime test was performed.

## 1. Executive summary

The full caller scan found 21 objects referencing Codeunit 22. After excluding helper/view objects and cost-only adjustment behavior, several additional physical inventory posting flows are visible:

- Assembly consumption/output through Codeunit 900.
- Job Journal item usage through Codeunit 1012.
- Production Order output/consumption through Codeunit 5407.
- Service item posting through Codeunit 5987.
- Warehouse reclassification through Codeunit 7304.
- Warehouse Activity production consumption/output through Codeunit 7324.
- Undo/reversal posting through Codeunits 5814–5819.

The inspected posting code in these routes does not directly call Codeunit 50107. Transfer remains different: Codeunits 5704/5705 do call the stocktake checker before their inventory posting work.

**Important classification:** these are not automatically confirmed defects. The company must decide which operations stocktake is intended to block. In particular, correction/undo transactions and same-location/bin reclassifications may have different business treatment from ordinary physical receipts, shipments, consumption, or output.

## 2. Standard Item Journal route

The standard Item Journal path is:

```text
Page 40 — Item Journal
  ├─ Post → Codeunit 241 — Item Jnl.-Post
  │           └─ Codeunit 23 — Item Jnl.-Post Batch
  │                 └─ Codeunit 22 — Item Jnl.-Post Line
  └─ Post & Print → Codeunit 242 → Codeunit 23 → Codeunit 22
```

The inspected Page 40 / Codeunit 241 / Codeunit 23 / Codeunit 22 path contains no direct Codeunit 50107 or BlockStocktake call. Codeunit 23 posts the selected Item Journal lines through Codeunit 22.

This route can represent multiple Entry Types, including Purchase, Sale, Positive/Negative Adjustment, Transfer, Consumption, Output, Assembly Consumption, and Assembly Output. The journal's actual Entry Type and quantity determine whether physical inventory changes.

## 3. Additional Codeunit 22 posting routes

| Caller | Observed posting operation | Stocktake reference in caller | Classification |
|---|---|---|---|
| Codeunit 900 — Assembly-Post | Posts Assembly Consumption and Assembly Output Item Journal Lines through Codeunit 22 | None found | Physical component consumption and assembled-item output |
| Codeunit 1012 — Job Jnl.-Post Line | Converts Job Usage into an Item Journal Line and posts it through Codeunit 22 | None found | Job-related item consumption |
| Codeunit 5407 — Prod. Order Status Management | Flushes Production Order Output and Consumption through Codeunit 22 | None found | Production inventory movement |
| Codeunit 5987 — Serv-Posting Journals Mgt. | Posts Service Item Journal Lines through Codeunit 22 | None found | Service shipment/consumption or return-related item movement |
| Codeunit 7304 — Whse. Jnl.-Register Batch | When the journal template is a reclassification template and CreateItemJnlLine succeeds, posts the generated Item Journal Line through Codeunit 22 | None found | Warehouse reclassification; inspect whether the operation changes bins, location, or both |
| Codeunit 7324 — Whse.-Activity-Post | Production Consumption and Output activity lines post directly through Codeunit 22 | None found | Warehouse-driven production inventory movement |
| Codeunits 5814–5819 | Undo Return Shipment, Sales Shipment, Return Receipt, Service Shipment, Service Consumption, and shared undo management | None found | Correction/reversal posting; policy may differ from ordinary movements |

### Important Codeunit 7324 distinction

Codeunit 7324 has multiple source branches:

- Transfer Line: delegates to Codeunit 5705 for Invt. Put-away, otherwise Codeunit 5704. These paths inherit the IN/OUT stocktake checks.
- Purchase Line: calls Codeunit 90 directly.
- Sales Line: calls Codeunit 80 directly.
- Production Order Consumption: builds an Item Journal Line with Entry Type Consumption and calls Codeunit 22.
- Production Order Output: builds an Item Journal Line with Entry Type Output and calls Codeunit 22.

Therefore, the existence of a stocktake gate for Transfer Line does not mean every Warehouse Activity posting type is protected.

## 4. Caller objects that should not be treated as physical posting routes without further evidence

- Codeunit 5895 Inventory Adjustment: the inspected code uses Codeunit 22 adjustment-related methods to support costing/adjustment processing; no ordinary Item Journal quantity-posting call was identified in the inspected source. Treat this as cost adjustment until runtime/source evidence shows a physical quantity movement.
- Codeunit 5817 Undo Posting Management: shared undo validation and correction helper; assess together with its entry-point callers (5814–5816, 5818, 5819), not as an independent user posting action.
- Pages 521/522 and Table 83 appear as references in the caller scan but are not established as independent inventory posting entry points by this scan.

## 5. Direct stocktake-reference cross-check

The 21 Codeunit 22 caller objects were checked for direct references to Codeunit 50107, BlockStocktake procedures, and the legacy CheckBlockStockTake name.

- Codeunit 5704 contains the OUT stocktake check.
- Codeunit 5705 contains the IN stocktake check.
- No direct stocktake reference was found in the other caller objects listed by the manifest.

This is a direct-reference scan, not proof that no caller invokes an intermediate helper that performs a stocktake check. It also cannot include external integrations or source omitted from the export.

## 6. Business decisions required

Before classifying any route as a defect or proposing a code change, confirm whether stocktake should block:

1. Standard Item Journal physical adjustments, transfers, consumption, and output.
2. Assembly component consumption and assembly output.
3. Job Journal item usage.
4. Production Order output and consumption, including warehouse-driven flushing.
5. Service shipment, consumption, and return-related item posting.
6. Warehouse Journal reclassification.
7. Undo/reversal of previously posted shipment, receipt, service, or consumption documents.

Keep the already company-approved exceptions and posting routes documented in [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3). Do not add a universal Codeunit 22 check solely because it is a shared low-level posting engine; that could unintentionally block approved correction, service, assembly, or production workflows.

## 7. Source manifests and caller exports

- [Codeunit 22 caller manifest](../item_post_callers/callers_manifest.csv)
- [Codeunit 23 caller manifest](../item_batch_post_callers/callers_manifest.csv)
- [P2B non-WMS Item Journal flow](../p2b/P2B_POSTING_AND_STOCKTAKE_AUDIT.md)
- [Stocktake entry-point audit](../stocktake/STOCKTAKE_ENTRYPOINT_AUDIT.md)
- [Transfer Order flow](../transfer_flow/TRANSFER_ORDER_STOCKTAKE_AND_POSTING_FLOW.md)
- [Purchase posting audit](../purchase_flow/PURCHASE_POSTING_STOCKTAKE_AUDIT.md)
