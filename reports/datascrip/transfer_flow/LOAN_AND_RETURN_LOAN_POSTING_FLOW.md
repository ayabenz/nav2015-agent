# Loan and Return Loan — Stocktake and Posting Flow

**Scope:** Custom Pages 50000 (Loan), 50004 (Return Loan), 50115 (Loan List), 50116 (Return Loan List), shared Transfer Header/Line tables, Codeunits 5704–5708, 5751/5752, and warehouse posting Codeunits 5760/5763.

The source is a customized NAVW18.00 export. Findings below are based on static C/AL inspection; validate runtime behavior in the target NAV database before changing business logic.

## 1. Executive summary

Loan and Return Loan are separate document types stored in Table 5740, not separate posting engines.

- Page 50000 filters `Transfer Type = Loan`.
- Page 50004 filters `Transfer Type = Return Loan`.
- Both pages use Codeunit 5706 for Post and Codeunit 5707 for Post & Print.
- Both wrappers delegate shipment to Codeunit 5704 and receipt to Codeunit 5705.
- Codeunit 5704 performs the active stocktake OUT check before shipment posting.
- Codeunit 5705 performs the active stocktake IN check before receipt posting.
- Warehouse source-document creation uses Codeunit 5752 (OUT) and 5751 (IN); actual warehouse posting delegates back to Codeunit 5704/5705, so the posting-time check runs again.

**Conclusion:** The inspected Loan and Return Loan UI and warehouse routes inherit the same pre-posting stocktake protection as regular Transfer Orders. No missing posting-time stocktake check was identified in these routes.

## 2. Pages and entry points

| Object | Purpose | Main posting entry |
|---|---|---|
| Page 50000 | Loan document | Codeunit 5706 / 5707 |
| Page 50115 | Loan list; CardPageID Loan | Page 50000 |
| Page 50004 | Return Loan document | Codeunit 5706 / 5707 |
| Page 50116 | Return Loan list; CardPageID Return Loan | Page 50004 |

Both document pages expose:
- Post (F9) → Codeunit 5706.
- Post and Print (Shift+F9) → Codeunit 5707.
- Create Warehouse Shipment → Codeunit 5752.
- Create Warehouse Receipt → Codeunit 5751.

Codeunit 5706 offers Shipment or Receipt. Codeunit 5707 follows the same selection, calls the same posting codeunits, then prints the posted shipment or receipt.

## 3. Stocktake enforcement

### Shipment / OUT

Codeunit 5704 starts with:

```pascal
CUBlockStocktake.BlockStocktakeTransferHeader(Rec, 'OUT');
```

This is before release/status validation, quantity checks, posted shipment document creation, and Item Journal posting.

### Receipt / IN

Codeunit 5705 starts with:

```pascal
CUBlockStocktake.BlockStocktakeTransferHeader(Rec, 'IN');
```

This is before automatic release handling (including its possible COMMIT), receipt quantity checks, posted receipt creation, and Item Journal posting.

### Warehouse source creation and posting

- Codeunit 5752 `CreateFromOutbndTransferOrder` checks `BlockStocktakeTransferHeader(TransHeader,'OUT')`.
- Codeunit 5751 `CreateFromInbndTransferOrder` checks `BlockStocktakeTransferHeader(TransHeader,'IN')`.
- Codeunit 5763 routes Transfer Line warehouse shipment posting through Codeunit 5704.
- Codeunit 5760 routes Transfer Line warehouse receipt posting through Codeunit 5705.

Therefore, a warehouse document created before a stocktake window becomes active is checked again when it is actually posted.

### Page 50000 legacy cutoff check

The Loan page has an additional local `CheckBlockStockTake` call before creating a warehouse shipment. It contains fixed location/item-category restrictions (for example PLGx, STRx and PTCx), separate from the configurable Table 50063 rule.

**Source concern:** this local procedure declares `tSL1 : Record 39` (Purchase Line) and filters it by the Loan document number, while the page is a Table 5740 Transfer Header page. It then reads Purchase Line `Location Code` and `No.`. This appears inconsistent with the transfer document and may be stale or copied logic. Do not rely on this page-local check as the Loan stocktake control; the correct transfer-specific checks in Codeunits 5752 and 5704 remain active. Confirm whether the legacy check is still required before removing or changing it.

Page 50004 Return Loan does not have this same local page-level cutoff procedure; it calls Codeunit 5752 directly, which applies the general OUT check.

## 4. Loan-specific behavior

### Required fields and validations

- Page 50000 sets `Transfer Type := Loan` on new records.
- The page exposes Salesperson Code, Purchaser Code, Loan-to Customer No., Loan Due Date, and Ex Loan No.
- Codeunit 5704 explicitly requires both Salesperson Code and Purchaser Code when Transfer Type is Loan.
- Codeunit 5706 also requires Salesperson Code before either Shipment or Receipt selection for Loan.
- Codeunit 5704 copies Loan-to Customer No., Loan Due Date, Loan Type, Salesperson Code, Purchaser Code, and Transfer Type into the posted Transfer Shipment Header.
- Codeunit 5705 copies the corresponding Loan metadata into the posted Transfer Receipt Header.

### Ownership

Codeunit 5706's ownership validation treats Loan as a source-side ownership flow:
- If Transfer-from Location has Ownership enabled, either header From Location Ownership must be supplied or each positive transfer line must have Owner.
- The destination-side validation branch includes Transfer and Return Loan, not Loan.

At shipment posting, Codeunit 5704 assigns the source Owner from the transfer line, falling back to header From Location Ownership when the source location has Ownership enabled.

## 5. Return Loan-specific behavior

### Document setup

- Page 50004 sets `Transfer Type := Return Loan` on new records.
- The page exposes To Location Ownership, Applies-to Doc. No. (read-only), and Forced Return.
- Page 50004 uses the same Codeunit 5706/5707 posting wrappers and Codeunit 5751/5752 warehouse source creation routes.

### Original item / lot application before shipment

Before calling Codeunit 5704 for a Return Loan Shipment, Codeunit 5706 calls `AddLotNo`.

For Return Loan lines with an Item Tracking Code, AddLotNo:
1. Looks up positive Transfer Item Ledger Entries for the item at the Transfer-from location, matching the original Source No. and Source Line No.
2. Reads each matching entry's Remaining Quantity and Lot No.
3. Creates paired Reservation Entry records for the outbound transfer line (negative at Transfer-from) and inbound side (positive at Transfer-to), carrying the lot number and original Item Ledger Entry application.
4. Stops when the transfer line quantity has been allocated.

After that, Codeunit 5706 checks each nonzero Return Loan line with Qty. to Ship > 0. If there is no matching reservation entry and `Appl.-to Item Entry` is zero, it raises **“Appl.-to Item Entry must be filled”**.

The source condition around Item Tracking Code is:

```pascal
(ItemRec."Item Tracking Code" = '') OR
(ItemRec."Item Tracking Code" <> '')
```

This expression is always true when the Item record exists. Consequently, the subsequent application check is effectively applied to every existing item, not only tracked items. This may be intentional because Return Loan needs an original-item reference even for non-tracked inventory; confirm the business rule before treating it as a defect.

### Ownership

Codeunit 5706 validates the destination-side ownership for Return Loan:
- If Transfer-to Location has Ownership enabled, either To Location Ownership must be supplied or each positive transfer line must have Owner.

At receipt posting, Codeunit 5705 assigns the destination Owner from the transfer receipt line, falling back to header To Location Ownership when the destination location has Ownership enabled.

## 6. Shared posting behavior and ownership ledger

Both Loan and Return Loan ultimately use the same posting codeunits:
- Codeunit 5704 creates the transfer shipment and posts an Item Journal Line with Document Type Transfer Shipment.
- Codeunit 5705 creates the transfer receipt and posts an Item Journal Line with Document Type Transfer Receipt.
- Both call Codeunit 22 through `ItemJnlPostLine.RunWithCheck(ItemJnlLine)`.
- Codeunit 22 creates Ownership Ledger entries when the relevant location has Ownership enabled, using the Owner carried on the Item Journal Line.

The two directions are distinct: shipment is checked as OUT; receipt is checked as IN. The Owner used at shipment is source-side, while receipt Owner is destination-side.

## 7. Findings matrix

| Route | Loan | Return Loan |
|---|---|---|
| Page Post / Post & Print | 5706/5707 → 5704/5705 | 5706/5707 → 5704/5705 |
| Direct shipment posting | 5704 checks OUT | 5704 checks OUT |
| Direct receipt posting | 5705 checks IN | 5705 checks IN |
| Create warehouse shipment | 5752 checks OUT; Loan page also has legacy local cutoff | 5752 checks OUT |
| Create warehouse receipt | 5751 checks IN | 5751 checks IN |
| Warehouse shipment posting | 5763 → 5704 → OUT check | 5763 → 5704 → OUT check |
| Warehouse receipt posting | 5760 → 5705 → IN check | 5760 → 5705 → IN check |
| Special application logic | Loan metadata + Salesperson/Purchaser requirements | AddLotNo + Applies-to Item Entry / reservation validation |

## 8. Follow-up validation

1. Confirm the legacy Page 50000 `CheckBlockStockTake` (Record 39) is still required and whether it was intended to inspect Purchase Lines. The active transfer-specific checks do not depend on it.
2. Confirm that Return Loan's applies-to requirement is intentionally enforced for both tracked and non-tracked items.
3. Runtime-test partial Loan and Return Loan shipments/receipts, including split lots, existing reservation entries, and a Return Loan with no Applies-to Item Entry.
4. Confirm whether any report, job queue, integration, or custom page posts Loan/Return Loan directly without Codeunit 5704/5705.
5. Validate the loan-to customer, salesperson/purchaser, due-date, and owner values in posted shipment/receipt records and the resulting Item Ledger / Ownership Ledger entries.

## 9. Source files

- `reports/datascrip/transfer_variants/Page_50000.txt`
- `reports/datascrip/transfer_variants/Page_50004.txt`
- `reports/datascrip/transfer_variants/Page_50115.txt`
- `reports/datascrip/transfer_variants/Page_50116.txt`
- `reports/datascrip/transfer_variants/Page_5742.txt`
- `reports/datascrip/transfer_variants/Codeunit_5708.txt`
- `reports/datascrip/transfer_wrappers/Codeunit_5706.txt`
- `reports/datascrip/transfer_wrappers/Codeunit_5707.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5704.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5705.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5751.txt`
- `reports/datascrip/stocktake_callers/Codeunit_5752.txt`
- `reports/datascrip/sales_return_warehouse/Codeunit_5760.txt`
- `reports/datascrip/sales_return_warehouse/Codeunit_5763.txt`

Related decision: [Issue #3 — Stocktake validation is an intentional pre-posting business rule](https://github.com/ayabenz/nav2015-agent/issues/3).
