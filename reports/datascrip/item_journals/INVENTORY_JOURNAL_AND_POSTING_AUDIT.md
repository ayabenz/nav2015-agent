# Item Journal and Inventory Posting — Stocktake Audit

**Scope:** Manual Item Journal, Physical Inventory Journal, Item Reclass Journal, Mini Adjust Inventory, Warehouse Journal registration, Assembly, Production, Job, Service, Warehouse Activity, and undo posting routes that reach Codeunit 22 Item Jnl.-Post Line.

## 1. Executive summary

Codeunit 22 `Item Jnl.-Post Line` is a shared physical inventory posting engine. It does not call Codeunit 50107 (Block Stocktake). Codeunit 23 `Item Jnl.-Post Batch` also has no stocktake call.

The caller audit identified multiple inventory posting families beyond Sales, Purchase and Transfer:
- Manual Item Journal and Mini Adjust Inventory.
- Item Reclass Journal.
- Assembly consumption/output.
- Production consumption/output.
- Job Journal item usage.
- Service consumption/shipment.
- Warehouse Activity production consumption/output.
- Undo/reversal of posted inventory documents.
- Warehouse Journal reclassification.

No stocktake check was found in the inspected posting codeunits for these families. This does not automatically mean every route is a defect: the company must define which physical movements stocktake freezes, and preserve the Physical Inventory Journal route used to post stocktake differences.

## 2. Common Item Journal posting path

The normal Item Journal route is:

```text
Page 40 Item Journal
  ├─ Post → Codeunit 241 Item Jnl.-Post
  ├─ Post & Print → Codeunit 242 Item Jnl.-Post+Print
  ├─ Batch Post → Codeunit 243 Item Jnl.-B.Post
  └─ Batch Post & Print → Codeunit 244 Item Jnl.-B.Post+Print
        └─ Codeunit 23 Item Jnl.-Post Batch
             └─ Codeunit 22 Item Jnl.-Post Line
                  └─ Item Ledger Entry / Value Entry posting
```

Findings:
- Page 40 and Codeunits 241–244 do not call Codeunit 50107.
- Codeunit 23 posts journal lines through Codeunit 22; no stocktake call was found.
- Codeunit 22 performs item quantity/value posting, inserts Item Ledger Entry and Value Entry, and creates Ownership Ledger entries where applicable. It has no direct stocktake check.

### Alternate direct route — Page 1327 Mini Adjust Inventory

Page 1327 calls Codeunit 23 directly for its mini adjustment flow. It does not pass through Codeunits 241/242 and has no inspected stocktake check. This route creates/posts item adjustment journal lines.

## 3. Physical Inventory Journal — Page 392

Page 392 Physical Inventory Journal uses the Item Journal posting path (Codeunits 241/242 → 23 → 22).

It has no stocktake check, which is expected: this journal is part of the stocktake process and is used to post the physical inventory count differences. A future policy must explicitly preserve this route while deciding whether other Item Journal entry types should be blocked during an active stocktake.

## 4. Item Reclass Journal — Page 393

Page 393 Item Reclass Journal uses the Item Journal posting path and ultimately Codeunit 22. No stocktake check was found.

Item Reclass can move inventory between locations and/or ownership dimensions. This is a physical inventory movement and may need a stocktake gate, depending on whether the stocktake freeze covers location reclassification. Do not treat it as equivalent to the Physical Inventory Journal.

## 5. Warehouse Journal registration

- Page 7324 Warehouse Item Journal and Page 7365 Warehouse Reclassification Journal use the Warehouse Journal registration route through Codeunit 7303 / Codeunit 7304.
- Codeunit 7304 `Whse. Jnl.-Register Batch` has no Codeunit 50107 call.
- Its reclassification path creates Item Journal Lines and calls Codeunit 22.
- Its physical inventory count handling updates physical-inventory tracking structures; that route is part of the stocktake process itself.
- Page 7365 bin/warehouse reclassification may change bin placement without changing total inventory at the location. Whether it should be frozen during stocktake is a separate operational policy.

## 6. Assembly posting

Assembly posting reaches Codeunit 22 through:

```text
Page 900 Assembly Order
  └─ Codeunit 901 Assembly-Post (Yes/No)
       └─ Codeunit 900 Assembly-Post
            └─ Codeunit 22 Item Jnl.-Post Line
```

Batch assembly posting also calls Codeunit 900.

Codeunits 900/901 and the inspected batch report contain no Codeunit 50107 stocktake check. Assembly posting consumes component inventory and creates assembly output, so it changes physical inventory.

## 7. Production posting

Codeunit 5407 `Prod. Order Status Management` calls Codeunit 22 for production consumption/output posting. The inspected codeunit contains no Codeunit 50107 call.

The production-order status change page routes through Codeunit 5407. The posting path can consume components and create finished output. Whether stocktake blocks production consumption/output must be explicitly decided; the stocktake window may need to distinguish production consumption from production output.

## 8. Job Journal posting

The Job Journal route uses Codeunits 1021/1022 for Post / Post & Print and 1023/1024 for batch posting, then Codeunit 1013 / 1012 for job journal item posting, which reaches Codeunit 22.

No Codeunit 50107 call was found in the inspected job posting codeunits. Item usage from Job Journal changes physical inventory and may need to be included in the stocktake freeze.

## 9. Service posting

The Service Order route uses:
- Codeunit 5981 Service-Post (Yes/No).
- Codeunit 5982 Service-Post + Print.
- Codeunit 5980 Service-Post.
- Codeunit 5987 Serv.-Posting Journals Mgt. for item/service journal posting.

Batch service posting uses Reports 6001, 6004 and 6005. The inspected service posting codeunits and reports do not call Codeunit 50107.

Service consumption and shipment can reduce inventory. Whether stocktake blocks these service movements requires business confirmation.

## 10. Warehouse Activity posting

Codeunit 7324 `Whse.-Activity-Post` directly posts production consumption/output Item Journal Lines through Codeunit 22. No Codeunit 50107 call was found in the inspected codeunit.

Its source-document posting route is mixed:
- Transfer Line sources delegate to Codeunit 5704/5705 and inherit OUT/IN stocktake checks.
- Purchase/Sales Line sources call Codeunit 90/80 directly; see the Purchase and Sales warehouse posting reports.
- Production consumption/output paths call Codeunit 22 directly and do not inherit the transfer stocktake check.

The separate Page 5770 / Codeunit 7306 / Codeunit 7307 warehouse activity registration route registers warehouse activity and tracking/bin entries; it should not be mistaken for the final item-ledger posting path.

## 11. Undo / reversal posting

The following undo codeunits call Codeunit 22 and have no inspected Codeunit 50107 call:
- Codeunit 5814 Undo Return Shipment Line.
- Codeunit 5815 Undo Sales Shipment Line.
- Codeunit 5816 Undo Return Receipt Line.
- Codeunit 5817 Undo Posting Management.
- Codeunit 5818 Undo Service Shipment Line.
- Codeunit 5819 Undo Service Consumption Line.

These reverse previously posted inventory movements. Whether undo/correction operations should be blocked during stocktake is a business decision; some corrections may be necessary to restore ledger accuracy, but they can also change the stock being counted.

## 12. Cost-only inventory adjustment

Codeunit 5895 Inventory Adjustment appears in the Codeunit 22 caller manifest, but its relevant posting work is cost/value adjustment rather than a physical quantity movement. Do not automatically classify cost adjustment as a stocktake bypass; verify the specific Entry Type and whether it changes Quantity before adding a stocktake gate.

## 13. Findings matrix

| Posting family | Route | Stocktake call found? | Physical effect |
|---|---|---|---|
| Manual Item Journal | Page 40 → 241/242 → 23 → 22 | No | Depends on Entry Type; may change quantity |
| Mini Adjust Inventory | Page 1327 → 23 → 22 | No | Positive/Negative Adjustment |
| Physical Inventory Journal | Page 392 → 241/242 → 23 → 22 | No | Stocktake count adjustment; should remain allowed |
| Item Reclass Journal | Page 393 → 241/242 → 23 → 22 | No | Moves inventory / owner attribution |
| Warehouse Item Journal | Page 7324 → 7303/7304 | No | Warehouse entries; physical count handling |
| Warehouse Reclass Journal | Page 7365 → 7303/7304 | No | Bin reclassification; total location quantity may remain unchanged |
| Assembly | Page 900 → 901 → 900 → 22 | No | Component consumption / assembly output |
| Production | Status page → 5407 → 22 | No | Consumption / production output |
| Job Journal | 1021–1024 → 1013/1012 → 22 | No | Job item usage |
| Service | 5981/5982 → 5980/5987 → 22 | No | Service consumption / shipment |
| Warehouse Activity | 7324 → 22 | No | Production consumption/output; source documents vary |
| Undo / reversal | 5814–5819 → 22 | No | Reverses posted physical movements |
| Inventory cost adjustment | 5895 | No | Primarily value/cost adjustment |

## 14. Business decisions required

Confirm whether stocktake should block:
1. Manual Item Journal Positive/Negative Adjustment, Purchase, Sale, Transfer, Consumption and Output entries, while keeping Page 392 Physical Inventory Journal available.
2. Mini Adjust Inventory (Page 1327).
3. Item Reclass Journal (Page 393).
4. Warehouse reclassification (Page 7365) and warehouse item journal registration (Page 7324).
5. Assembly consumption/output.
6. Production consumption/output.
7. Job Journal item usage.
8. Service consumption/shipment.
9. Warehouse Activity production consumption/output.
10. Undo / reversal of posted inventory documents.
11. Any other direct callers of Codeunit 22 that the company uses operationally.

Do not add a blanket check inside Codeunit 22 solely for convenience. That would also block approved processes such as Physical Inventory Journal and could affect Sales/Purchase/Transfer paths with their own company-specific validation. Put checks at the relevant business entry points after the company confirms the policy.

## 15. Caller inventories

The reusable caller exporter generated:
- [Codeunit 22 callers](../item_post_callers/callers_manifest.csv)
- [Codeunit 23 callers](../item_batch_post_callers/callers_manifest.csv)

These manifests identify candidate objects; a reference does not by itself prove that every procedure in the object posts inventory.

## 16. Source files

- `reports/datascrip/item_journals/Page_40.txt`
- `reports/datascrip/item_journals/Page_392.txt`
- `reports/datascrip/item_journals/Page_393.txt`
- `reports/datascrip/item_journals/Page_1327.txt`
- `reports/datascrip/item_journals/Page_7324.txt`
- `reports/datascrip/item_journals/Page_7365.txt`
- `reports/datascrip/item_journals/Codeunit_22.txt` (source is also retained in the Sales analysis export)
- `reports/datascrip/item_journals/Codeunit_23.txt`
- `reports/datascrip/item_journals/Codeunit_241.txt`
- `reports/datascrip/item_journals/Codeunit_242.txt`
- `reports/datascrip/item_journals/Codeunit_243.txt`
- `reports/datascrip/item_journals/Codeunit_244.txt`
- `reports/datascrip/item_journals/Codeunit_7304.txt`
- `reports/datascrip/item_journals/Codeunit_7306.txt`
- `reports/datascrip/item_journals/Codeunit_7307.txt`
- `reports/datascrip/item_post_callers/callers_manifest.csv`
- `reports/datascrip/item_batch_post_callers/callers_manifest.csv`

Related company decisions are tracked in [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3).


## 17. Complete Codeunit 5704/5705 and Codeunit 22 caller cross-check

The complete company export was scanned for direct references to Codeunit 5704 and Codeunit 5705. Four caller objects were found for each:

- Codeunit 5704 (OUT): Codeunits 5706, 5707, 5763 and 7324.
- Codeunit 5705 (IN): Codeunits 5706, 5707, 5760 and 7324.

Codeunits 5706/5707 are the UI wrappers; 5763/5760 are warehouse shipment/receipt posting; 7324 is warehouse activity posting. Its Transfer Line branch calls Codeunit 5705 for Invt. Put-away and Codeunit 5704 for other transfer activity types. No additional direct transfer posting caller was found in the exported archive.

**Warehouse Activity timing:** Codeunit 7324 performs COMMIT before invoking Codeunit 5704/5705 for Transfer Line. The transfer stocktake check still executes before the downstream transfer inventory posting, but the warehouse activity transaction preceding the call may already be committed. Runtime-test the persisted state when an active stocktake rule causes the transfer posting call to fail.

The same Codeunit 7324 has separate production activity paths: PostConsumptionLine and PostOutputLine construct Item Journal Lines (Consumption and Output) and call Codeunit 22 directly. Those production warehouse-activity paths do not inherit the transfer stocktake gate.

The Codeunit 22 caller manifest contains 21 caller objects. A direct-reference cross-check found explicit Codeunit 50107 / BlockStocktake references only in Codeunits 5704 and 5705. This does not rule out an indirect helper call, dynamic invocation, or external code outside the export.

Additional caller manifests:
- [Codeunit 5704 callers](../transfer_post_callers/5704/callers_manifest.csv)
- [Codeunit 5705 callers](../transfer_post_callers/5705/callers_manifest.csv)
