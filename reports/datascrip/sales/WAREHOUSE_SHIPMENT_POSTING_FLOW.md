# Warehouse Shipment — Create, Pick and Post

**Scope:** NAVW18 company export; Page 7335/7336, Table 7320/7321, Codeunits 5752, 5763/5764/5765/5704/90/80, Report 50223. Source-level reconstruction only.

## 1. End-to-end overview

`Sales Order / Purchase Return Order / Transfer Order`
→ `Create Warehouse Shipment`
→ `Warehouse Shipment Header/Lines (7320/7321)`
→ `Release / Create Pick`
→ `Post Shipment`
→ `Codeunit 5763 Whse.-Post Shipment`
→ source-specific posting:
- Sales Line → Codeunit 80 Sales-Post
- Purchase Line → Codeunit 90 Purch.-Post
- Transfer Line → Codeunit 5704 TransferOrder-Post Shipment
- Service Line → Codeunit 5980 Service-Post

The shipment posting engine groups lines by source document, synchronizes source document quantities and posting dates, then posts each source document according to the Warehouse Setup Shipment Posting Policy.

## 2. Create warehouse shipment

Page 7335 exposes two source-document actions:
- **Use Filters to Get Src. Docs.** → Codeunit 5752 `GetOutboundDocs`
- **Get Source Documents** → Codeunit 5752 `GetSingleOutboundDoc`

Codeunit 5752 has explicit source creation methods:
- `CreateFromSalesOrder(SalesHeader)`: calls `BlockStocktakeSalesHeader(SalesHeader,TRUE)`, requires Released status, checks shipping advice/conflict, then finds outbound warehouse requests for Sales Lines and opens the warehouse shipment.
- `CreateFromPurchaseReturnOrder(PurchHeader)`: calls `BlockStocktakePurchaseHeader(PurchHeader)`, requires Released status, then finds outbound warehouse requests for Purchase Lines.
- `CreateFromOutbndTransferOrder(TransHeader)`: calls `BlockStocktakeTransferHeader(TransHeader,'OUT')`, requires Released status, performs transfer checks, then finds outbound warehouse requests for Transfer Lines.

The stocktake checks are at source-document creation time. They do not replace a posting-time check on the Warehouse Shipment itself.

## 3. Page 7335 workflow

Page 7335 provides:
1. Release / Reopen through Codeunit 7310.
2. Autofill Qty. to Ship and Delete Qty. to Ship.
3. Create Pick through the shipment subform.
4. Post Shipment (F9) through Page 7336 `PostShipmentYesNo`.
5. Post Batch through custom Report 50223.
6. Print and posted shipment navigation.

The Post Batch action checks for unfinished registered picks in the page action, then invokes `SetPostBatch(FALSE)`. The report selects Warehouse Shipment Headers with Document Status = Completely Picked and Finished = Yes, applies the default location filter, and processes each selected shipment.

## 4. Posting engine — Codeunit 5763

### 4.1 Wrappers

- Page 7336 `PostShipmentYesNo` runs Codeunit 5764.
- Page 7336 `PostShipmentPrintYesNo` runs Codeunit 5765.
- Codeunits 5764 and 5765 configure Invoice and Print options, then run Codeunit 5763.
- Report 50223 runs Codeunit 5763 directly for each selected Warehouse Shipment.

Neither Codeunit 5764 nor 5765 calls Codeunit 50107.

### 4.2 Pre-post validations

Codeunit 5763 `Code`:
- Filters the current Warehouse Shipment No. and Qty. to Ship > 0.
- Requires Unit of Measure Code.
- For Shipping Advice = Complete, requires total Qty. (Base) to equal Qty. to Ship (Base) + Qty. Shipped (Base).
- Requires an outbound Warehouse Request for the location/source.
- Loads Location; if Require Pick and Complete, calls `CheckItemTrkgPicked`.
- Requires Bin Code when Bin Mandatory.
- Requires Owner when Location.Ownership is enabled.
- Rejects incomplete Assemble-to-Order posting when `FullATOPosted` is false.
- Allocates Shipping No., sets Create Posted Header and commits.
- Groups Warehouse Shipment Lines by Source Type, Source Subtype and Source No.
- For each source document: loads source, applies batch posting date, checks posting date, calls EnsureAuthorization, synchronizes source lines/header, commits, then calls `PostSourceDocument`.

### 4.3 Source line synchronization

For Sales Line source documents, `HandleSalesLine` aligns source quantities with Warehouse Shipment quantities:
- Sales Order: adjusts Sales Line Qty. to Ship to the sum of relevant warehouse shipment lines.
- Non-Sales-Order Sales Line source: adjusts Return Qty. to Receive using the negative Warehouse Shipment Qty. to Ship.
- If Invoice option is enabled, recalculates Qty. to Invoice from shipped/received and already invoiced quantities.
- If a Sales Line has no corresponding Warehouse Shipment Line, it can clear Qty. to Ship / Return Qty. to Receive and Qty. to Invoice.

This is a key mutation boundary: warehouse shipment quantities can update Sales Line posting quantities before Codeunit 80 runs.

### 4.4 Source document posting

Codeunit 5763 `PostSourceDocument` dispatches by Warehouse Shipment Line Source Type:

| Source Type | Posting flags / action | Target |
|---|---|---|
| Sales Line, Sales Order | SalesHeader.Ship=TRUE; SalesHeader.Invoice=Invoice | Codeunit 80 |
| Sales Line, non-Sales-Order source | SalesHeader.Receive=TRUE; SalesHeader.Invoice=Invoice | Codeunit 80 |
| Purchase Line, Purchase Order | PurchHeader.Receive=TRUE; PurchHeader.Invoice=Invoice | Codeunit 90 |
| Purchase Line, non-Purchase-Order source (Purchase Return Order) | PurchHeader.Ship=TRUE; PurchHeader.Invoice=Invoice | Codeunit 90 |
| Transfer Line | Sets warehouse shipment context and posts transfer shipment | Codeunit 5704 |
| Service Line | Sets service posting options | Codeunit 5980 |

Warehouse Setup `Shipment Posting Policy` controls whether posting errors are collected/continued or the first error stops processing.

## 5. Stocktake coverage and bypass

**Source creation:** Codeunit 5752 checks Sales Order, Purchase Return Order and outbound Transfer Order before creating outbound warehouse source documents.

**Posting:** no Codeunit 50107 reference was found in:
- Page 7335
- Page 7336
- Codeunit 5763
- Codeunit 5764
- Codeunit 5765
- Report 50223

Codeunit 5763 calls Codeunit 80 for Sales Line sources and Codeunit 90 for Purchase Line sources. Neither posting boundary currently adds the Table 50063 check in the inspected export. Transfer Line sources call Codeunit 5704, which independently calls `BlockStocktakeTransferHeader(Rec,'OUT')`.

**Consequence:** a Sales Order or Purchase Return Order may be blocked when adding it to a new warehouse shipment during stocktake, but an already-created shipment can still reach the warehouse posting engine while a stocktake window is active. A manually created or alternate-populated shipment can also avoid the Codeunit 5752 source-creation method. Transfer shipment remains protected by Codeunit 5704 in the inspected route.

**Recommended design:** add a warehouse-shipment-level posting check in Codeunit 5763 before the first irreversible action (number allocation / Create Posted Header / COMMIT). Evaluate active Table 50063 rules against each positive Qty. to Ship Warehouse Shipment Line using location, source type/direction and item scope. Avoid simply calling `BlockStocktakeSalesHeader` on a source Sales Header: the warehouse shipment can include a partial selection, and the authoritative quantities are the Warehouse Shipment Lines. Retain Codeunit 5752 checks to prevent blocked source documents from being added in the first place.

For Warehouse Receipt, Page 5768 currently checks before its two posting actions, but Codeunit 5760 has no internal Codeunit 50107 call. Consider a corresponding central check in Codeunit 5760 if direct or alternate invocation is possible.

## 6. Other custom logic observed

- `EnsureAuthorization(SalesHeader)` is called during per-source processing.
- Codeunit 5763 OnRun calls `CheckDeptMAS(Rec)` after `Code`. The check validates Warehouse Shipment Header Source Department Code and historical department-code ranges.
- The posting engine carries Ownership requirements: when Location.Ownership is enabled, Warehouse Shipment Line Owner is required; the transfer posting engine then applies its separate Ownership Ledger check.
- Page 7335 Post Batch has additional unfinished-pick checks before calling Report 50223.

## 7. Evidence and limitations

- Page 7335 actions around lines 83–221 and local `SetPostBatch` around lines 513 onward.
- Page 7336 procedures `PostShipmentYesNo` and `PostShipmentPrintYesNo` around lines 248–270.
- Codeunit 5763 `Code` around lines 69–145; source loading around lines 147–160; source header synchronization around lines 172–315; line synchronization around lines 317–333 and 891–984; `PostSourceDocument` around lines 335–496; `CheckDeptMAS` around lines 1195–1228.
- Report 50223 data items around lines 16–87.
- Codeunit 5752 source creation methods and Codeunit 5704 transfer gate are separate evidence in the stocktake caller extracts.

Static source inspection does not prove every external integration, custom direct Codeunit.RUN, or manually scripted warehouse operation. Confirm actual production usage and test posting during an active stocktake window.
