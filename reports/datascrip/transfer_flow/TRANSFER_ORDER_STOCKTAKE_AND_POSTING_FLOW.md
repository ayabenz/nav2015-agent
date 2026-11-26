# Transfer Order — Stocktake, Ownership, and Posting Flow

**Scope:** Transfer Type = Transfer, from Page 5740 / Table 5740 / Table 5741 through direct and warehouse shipment/receipt posting. The exported source is a customized NAVW18.00 build. This report describes static source behavior; runtime behavior still requires validation against the deployed NAV database.

## 1. Executive summary

The regular Transfer Order flow has an active stocktake gate at the posting-engine entry points:

- **Shipment / OUT:** Codeunit 5704 calls `Codeunit 50107.BlockStocktakeTransferHeader(Rec,'OUT')` as the first operation in `OnRun`.
- **Receipt / IN:** Codeunit 5705 calls `Codeunit 50107.BlockStocktakeTransferHeader(Rec,'IN')` as the first operation in `OnRun`.

These checks run before status handling, release logic, document creation, inventory journal posting, and the later commits. The standard UI wrappers and warehouse posting routes delegate to Codeunit 5704 or 5705, so they inherit the posting-time check.

**Conclusion:** For the inspected Transfer Order routes, stocktake is checked at posting time, not only when a warehouse document is created. This is consistent with the company's accepted design: validation must happen before posting, but does not need to be centralized in one universal posting engine.

## 2. Entry points and call graph

### 2.1 Transfer Order page

Page 5740 exposes:

- **Post (F9)** → Codeunit 5706 `TransferOrder-Post (Yes/No)`.
- **Post and Print (Shift+F9)** → Codeunit 5707 `TransferOrder-Post + Print`.
- **Create Warehouse Shipment** → Page action calls its local `CheckBlockStockTake`, then `CheckOwnership`, then Codeunit 5752 `CreateFromOutbndTransferOrder`.
- **Create Warehouse Receipt** → Page action calls `CheckOwnership`, then Codeunit 5751 `CreateFromInbndTransferOrder`.

### 2.2 Direct posting wrappers

Codeunit 5706 displays a Shipment/Receipt selection:
- Shipment selection calls `TransferPostShipment.RUN(TransHeader)` → Codeunit 5704.
- Receipt selection calls `TransferPostReceipt.RUN(TransHeader)` → Codeunit 5705.

Codeunit 5707 has the same Shipment/Receipt selection, delegates to Codeunit 5704/5705, then prints the posted transfer document. Neither wrapper needs to duplicate the stocktake call because the called posting codeunits perform it.

### 2.3 Posting call graph

```text
Page 5740
  ├─ Post (F9) → Codeunit 5706
  │                ├─ Shipment → Codeunit 5704 → Stocktake OUT → post shipment
  │                └─ Receipt  → Codeunit 5705 → Stocktake IN  → post receipt
  │
  ├─ Post and Print → Codeunit 5707
  │                    ├─ Shipment → Codeunit 5704 → Stocktake OUT → post → print
  │                    └─ Receipt  → Codeunit 5705 → Stocktake IN  → post → print
  │
  ├─ Create Whse. Shipment → Codeunit 5752 → Stocktake OUT → create source lines
  └─ Create Whse. Receipt  → Codeunit 5751 → Stocktake IN  → create source lines

Warehouse posting:
  ├─ Codeunit 5763 (Whse.-Post Shipment)
  │    └─ Transfer Line → Codeunit 5704 → Stocktake OUT → post
  └─ Codeunit 5760 (Whse.-Post Receipt)
       └─ Transfer Line → Codeunit 5705 → Stocktake IN → post
```

## 3. Posting-time stocktake checks

### Codeunit 5704 — TransferOrder-Post Shipment

The first executable statement in `OnRun` is:

```pascal
CUBlockStocktake.BlockStocktakeTransferHeader(Rec, 'OUT');
```

It executes before the code checks Released status, posting date, shipment quantities, warehouse/bin handling, creates the posted Transfer Shipment Header/Lines, or calls Codeunit 22 through Item Journal Line posting.

When a transfer shipment creates an Item Journal Line:
- Owner is taken from the posted transfer shipment line when present.
- Otherwise, if the source location has Ownership enabled, Owner falls back to the posted header's `From Location Ownership`.
- Item Journal Document Type is Transfer Shipment.
- `ItemJnlPostLine.RunWithCheck(ItemJnlLine)` invokes the item posting engine.

### Codeunit 5705 — TransferOrder-Post Receipt

The first executable statement in `OnRun` is:

```pascal
CUBlockStocktake.BlockStocktakeTransferHeader(Rec, 'IN');
```

It executes before automatic release handling (which can modify and COMMIT), receipt quantity validation, posted receipt document creation, and item journal posting.

When a transfer receipt creates an Item Journal Line:
- Owner is taken from the posted transfer receipt line when present.
- Otherwise, if the destination location has Ownership enabled, Owner falls back to the posted header's `To Location Ownership`.
- Item Journal Document Type is Transfer Receipt.
- The journal line moves inventory from the In-Transit location to the destination location.
- `ItemJnlPostLine.RunWithCheck(ItemJnlLine)` invokes the item posting engine.

The OUT and IN directions are therefore checked separately against the transfer header using the corresponding Codeunit 50107 routine.

## 4. Warehouse routes

### Outbound transfer

- Page 5740 calls local `CheckBlockStockTake` before creating the warehouse shipment. This is an additional legacy hard-coded check for specific location/item-category combinations (including PLGx, PTCx, STRx and CKGx); it is not the general Table 50063 rule.
- Codeunit 5752 `CreateFromOutbndTransferOrder` independently calls `BlockStocktakeTransferHeader(TransHeader,'OUT')` before creating outbound warehouse source lines.
- During actual warehouse shipment posting, Codeunit 5763 handles Source Type Transfer Line by calling Codeunit 5704. Therefore the OUT check runs again at posting time, even if the warehouse shipment was created earlier.

### Inbound transfer

- Codeunit 5751 `CreateFromInbndTransferOrder` calls `BlockStocktakeTransferHeader(TransHeader,'IN')` before creating inbound warehouse source lines.
- During warehouse receipt posting, Codeunit 5760 handles Source Type Transfer Line by calling Codeunit 5705. Therefore the IN check runs at posting time.

**Important distinction:** warehouse source-document creation checks are not the only protection. The transfer posting codeunits re-check stocktake at the moment the transfer shipment/receipt is posted.

## 5. Ownership behavior

The transfer flow carries ownership at both header and line level.

- Page 5740 `CheckOwnership` validates the source and destination locations. If a location has Ownership enabled, the corresponding header ownership must be supplied, or each nonzero transfer line must contain Owner.
- Codeunit 5706 repeats ownership validation for the relevant Transfer / Loan / Return Loan cases before presenting the shipment/receipt selection.
- Table 5741 Quantity validation checks source-location availability through Codeunit 50051 `CekQuantity`, using Item, Transfer-from Code, From Location Ownership, requested quantity, and unit-of-measure context.
- Table 5741 Owner validation calls `ValidateOwnerTransferField`; changing Owner clears/revalidates Quantity and synchronizes the header's From/To Location Ownership values when those locations are Ownership-enabled.
- Codeunit 5704 assigns source Owner to the shipment Item Journal Line; Codeunit 5705 assigns destination Owner to the receipt Item Journal Line, using the header fallback when line Owner is blank.
- Codeunit 22 then creates Ownership Ledger entries when the relevant location has Ownership enabled, subject to its source-code, quantity, and owner-balance rules documented in the Ownership analysis.

This is a two-stage transfer: shipment reduces the source location and posts into In-Transit; receipt reduces In-Transit and posts into the destination location. The ownership value must remain consistent across both stages.

## 6. Findings and classification

| Route | Stocktake check | Timing | Assessment |
|---|---|---|---|
| Page 5740 Post → 5706 → 5704 | OUT in 5704 | Before posting | Protected |
| Page 5740 Post → 5706 → 5705 | IN in 5705 | Before posting | Protected |
| Page 5740 Post & Print → 5707 → 5704/5705 | OUT / IN in posting codeunit | Before posting | Protected |
| Create outbound warehouse shipment → 5752 | OUT | Before source creation | Protected at creation |
| Post outbound warehouse shipment → 5763 → 5704 | OUT | Before posting | Protected at posting |
| Create inbound warehouse receipt → 5751 | IN | Before source creation | Protected at creation |
| Post inbound warehouse receipt → 5760 → 5705 | IN | Before posting | Protected at posting |

No missing stocktake gate was identified in the inspected regular Transfer Order routes. The local Page 5740 hard-coded `CheckBlockStockTake` is an additional legacy restriction and should not be confused with the configurable Table 50063 stocktake rule.

## 7. Scope limitations / next validation

1. The Page 5740 source view is filtered to Transfer Type = Transfer. Codeunits 5704/5705 and 5706 also contain logic for Loan and Return Loan. Those variants should be audited separately, especially their owner fallback and item-application/tracking behavior.
2. Confirm whether any custom report, job queue, integration, or external extension posts transfer journals through an alternate code path that bypasses Codeunit 5704/5705.
3. Runtime-test an active Table 50063 rule for both OUT and IN, including a warehouse shipment/receipt created before the stocktake window becomes active.
4. Validate ownership continuity for partial shipments/receipts, blank line Owner with header fallback, and transfer lines with item tracking.

## 8. Source files

- `reports/datascrip/transfer_flow/Page_5740.txt`
- `reports/datascrip/transfer_flow/Page_5741.txt`
- `reports/datascrip/transfer_wrappers/Codeunit_5706.txt`
- `reports/datascrip/transfer_wrappers/Codeunit_5707.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5704.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5705.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5751.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5752.txt`
- `reports/datascrip/sales_return_warehouse/Codeunit_5760.txt`
- `reports/datascrip/sales_return_warehouse/Codeunit_5763.txt`
- `reports/datascrip/transfer_tables/Table_5740.txt`
- `reports/datascrip/transfer_tables/Table_5741.txt`

Related decision: [Issue #3 — Stocktake validation is an intentional pre-posting business rule](https://github.com/ayabenz/nav2015-agent/issues/3).
