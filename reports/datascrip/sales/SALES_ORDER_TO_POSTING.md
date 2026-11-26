# Sales Order to Posting — Datascrip Source Reconstruction

Branch: `datascrip`  
Repository: `ayabenz/nav2015-agent`  
Analysis basis: exported company object source and dependency edges in this branch.

## 1. Scope and evidence

Reviewed source files:

- `reports/datascrip/sales/Codeunit_80.txt` — Codeunit 80, Sales-Post
- `reports/datascrip/sales/Codeunit_12.txt` — Codeunit 12, Gen. Jnl.-Post Line
- `reports/datascrip/sales_next/Codeunit_22.txt` — Codeunit 22, Item Jnl.-Post Line
- `reports/datascrip/sales/Table_32.txt` — Table 32, Item Ledger Entry
- `reports/datascrip/sales_next/posting_edges.csv` — static dependency edges

The source files identify themselves as `NAVW18.00.00`:
- Codeunit 80: `NAVW18.00.00.41370`
- Codeunit 22: `NAVW18.00.00.40938`
- Codeunit 12: `NAVW18.00.00.41779`

**Version warning:** the project has been described as NAV 2015, but these exported object headers identify a NAVW18 code line. Confirm the actual application version and ensure the original baseline is from the same NAV release before treating a difference as a company customization. This document reports what the current branch source says; it does not silently reconcile that version discrepancy.

## 2. High-level posting flow

```text
Page 42 — Sales Order
  |
  | user selects Ship / Invoice / Post
  v
Codeunit 80 — Sales-Post (TableNo = 36)
  |
  | creates Item Journal Line from Sales Line
  | copies SalesLine.Owner to ItemJnlLine.Owner
  v
Codeunit 22 — Item Jnl.-Post Line (TableNo = 83)
  |
  +--> custom Ownership entry (Table 50035), when location ownership is enabled
  |
  +--> Item Ledger Entry (Table 32)
  |
  +--> Value Entry (Table 5802)
  |      +--> inventory-to-G/L path when applicable
  |
  v
Codeunit 80 — customer posting
  |
  | builds General Journal Line for Bill-to Customer
  v
Codeunit 12 — Gen. Jnl.-Post Line (TableNo = 81)
  |
  +--> Customer Ledger Entry (Table 21) and detailed customer entries
  |
  +--> G/L Entry (Table 17) and VAT Entry (Table 254), as applicable
```

This is a source-derived control-flow outline, not a runtime trace. Exact branches depend on document type, Ship/Invoice flags, quantities, setup, location, tracking, and posting configuration.

## 3. Codeunit 80 — Sales-Post

### 3.1 Entry and preconditions

- Object: Codeunit 80, `TableNo=36`.
- `OnRun` starts at source line 32.
- Line 83 reads General Ledger Setup.
- Line 85 calls the company-specific `CheckDeptMAS(Rec)`.
- Lines 101–105 require Document Type, Sell-to Customer No., Bill-to Customer No., Posting Date, and Document Date.
- Posting mode is derived from document type and the Ship/Invoice/Receive flags. For example, an Invoice document sets Ship and Invoice true; a Credit Memo sets Invoice and Receive true (lines 129–154).

### 3.2 Company-specific quantity validation

In the shipment path, Codeunit 80 checks sales lines and calls `ValidateQuantity(Item No., Location Code, Qty. to Ship)` (lines 238–246). If it returns false, posting stops with an insufficient-quantity error.

This is a company-specific validation path in the current source. Its exact stock basis and interaction with the Ownership ledger should be reviewed alongside `ValidateQuantity` and Table 50035 before assuming it is equivalent to standard NAV availability checks.

### 3.3 Sales Line to Item Journal Line

Procedure `PostItemJnlLine` starts at line 2672.

Important assignments:
- Line 2688: `ItemJnlLine.Owner := Owner` — transfers the Sales Line Owner value into the Item Journal Line.
- Lines 2717 onward: sets Entry Type to Sale and copies item, location, dimensions, tracking and document context.
- The posting routine calls `ItemJnlPostLine.RunWithCheck(ItemJnlLine)` at line 2853 (other paths call it at lines 3004, 3031, 3046 and 3244).

This establishes the source path from a Sales Line's Owner value into Codeunit 22.

## 4. Codeunit 22 — Item Jnl.-Post Line

### 4.1 Entry point and standard item posting path

- Object: Codeunit 22, `TableNo=83`.
- `OnRun` calls `GetGLSetup` and `RunWithCheck(Rec)`.
- `RunWithCheck` copies the Item Journal Line, prepares/splits it, calls `Code` for each line to be posted, then corrects valuation date and redoes applications (lines 131–146).
- `Code` calls `ItemJnlCheckLine.RunCheck` (line 158), checks item tracking where required, and dispatches to posting routines.
- `PostItem` (lines 557–624) performs item checks and routes quantity posting to `ItemQtyPosting` (line 606) and value posting to `ItemValuePosting` (line 620).
- `ItemQtyPosting` (lines 930–975) initializes Item Ledger Entry and Value Entry, handles applications/tracking, then calls `InsertItemLedgEntry` (line 967).
- `InsertItemLedgEntry` inserts Table 32 and then creates an Item Register reference (lines 1917–1985).
- `ItemValuePosting` calls `InsertValueEntry` (line 996); `InsertValueEntry` inserts Table 5802 and can invoke inventory-to-G/L posting when the Value Entry is inventoriable (see lines 2515 onward, including line 2605).

### 4.2 Confirmed company customization: Ownership ledger

The customization is in Codeunit 22:

1. Global variable `Ownership : Record 50035` is declared at line 127.
2. In `Code`, before normal item posting, `InsertOwnership` is called only when:
   - Value Entry Type is not Revaluation (lines 178–180); and
   - Source Code is not `RECLASSJNL` or `WHRCLSSJNL` (lines 187–193).
3. For Transfer Receipt it passes New Location Code; otherwise it passes Location Code.
4. `InsertOwnership` (lines 4846–4915):
   - calls `GetLocation(Lokasi)`;
   - exits unless `Location.Ownership` is enabled (line 4852);
   - skips source codes `INVTADJMT` and `INVTPCOST`;
   - skips zero base quantity;
   - locks Table 50035, finds the last entry number, and creates a new Ownership record;
   - stores posting date, entry type, document no., item no., owner, location, document type and user ID;
   - sets quantity positive or negative according to the posting direction;
   - assigns the related Item Ledger Entry No. as current ItemLedgEntryNo + 1, or +2 for Transfer Receipt (lines 4906–4909).
5. For Sale, Negative Adjmt. and Consumption, it calls `CheckRemainingQty` before creating a negative Ownership quantity. Transfer Shipment also checks remaining owner quantity.
6. `CheckRemainingQty` (lines 4917–4933) sums Quantity from Table 50035 filtered by Item No., Location Code and Owner. It does not set a Posting Date range even though Posting Date appears in the selected key.

The dependency export independently marks the Codeunit 22 → Table 50035 reference and the `CheckRemainingQty` call edges as `new_vs_original=1`. That is consistent with the source-level company-specific logic.

### 4.3 Additional Table 32 customization

Table 32 source contains field:
- Field 50099 — `Entry No Plus Satu`, description: `AFR : Keperluan Query untuk Report Loan`.

Codeunit 22 `InitItemLedgEntry` sets this field to `ItemLedgEntryNo + 1` (source line 1826).

The same procedure also contains a company-specific `T00.01` block (lines 1842–1848) that can replace `Applies-to Entry` with the original Item Journal Line's Applies-to Entry when the lot number matches the referenced Item Ledger Entry.

These should be assessed separately from the Ownership ledger; they are two additional modifications in the item posting path.

### 4.4 Important verification points

- Ownership's linked Item Ledger Entry No. is predicted before the standard Item Ledger Entry insert. The +1/+2 rule must be validated with transfer shipment/receipt scenarios and any code paths that create multiple item ledger entries.
- `CheckRemainingQty` sums all Ownership rows for the filtered item/location/owner; no date range or Entry Type filter is applied. Confirm that this is the intended definition of remaining owner quantity.
- Confirm how Owner is populated for every relevant sales line and what happens when Owner is blank.
- Test the exception source codes and location Ownership toggle explicitly.
- Static dependency edges show source references/calls, not proof that a branch executed in production.

## 5. Codeunit 80 to Codeunit 12 — customer and G/L posting

### 5.1 Customer journal line construction

Codeunit 80 procedure `PostCustomerEntry` begins at line 6192.

It constructs a General Journal Line with:
- Account Type = Customer (line 6205).
- Account No. = Bill-to Customer No. (line 6206).
- Document Type/No. and external document no. (lines 6207–6209).
- Amount = negative Amount Including VAT (line 6211).
- LCY amount = negative Amount Including VAT in LCY (line 6214).
- Payment, due date, dimensions, salesperson and source-code context.

It then calls `GenJnlPostLine.RunWithCheck(GenJnlLine2)` at line 6244.

### 5.2 Codeunit 12 dispatch

- Object: Codeunit 12, `TableNo=81`.
- `RunWithCheck` copies the General Journal Line and calls `Code(GenJnlLine, TRUE)` (lines 101–109).
- `Code` validates the line, initializes amounts and posting context, starts/continues posting, dispatches the account line and optional balancing account line, checks unrealized VAT and finishes posting (lines 121–177).
- `PostGenJnlLine` dispatches by Account Type: G/L Account → `PostGLAcc`; Customer → `PostCust`; Vendor, Bank, Fixed Asset and IC Partner use their respective procedures (lines 180–197).

### 5.3 Customer Ledger Entry

In `PostCust`:
- Customer and Customer Posting Group are validated.
- Customer Ledger Entry is initialized (line 805).
- Application and detailed-entry buffers are prepared.
- The Customer Ledger Entry is inserted into Table 21 (line 845).
- Detailed customer entries are posted (line 848).

### 5.4 G/L Entry and VAT

In `PostGLAcc`:
- G/L Account is loaded and validated.
- A G/L Entry is initialized (lines 745–750).
- Posting groups and VAT are initialized.
- `InsertGLEntry` is called (line 774), followed by job and VAT posting.

`InsertGLEntry` validates G/L Account No. and amount rounding, updates debit/credit and balance checks, inserts into the temporary G/L Entry buffer, and increments the next entry number (lines 1401–1425). The final posting process flushes the posting buffers to persistent ledger tables; this source excerpt confirms the buffer insertion path, while the persistent insert should be followed through the remainder of Codeunit 12 if a line-by-line physical write trace is required.

## 6. Confirmed customizations identified in this pass

| Object | Customization | Evidence |
|---|---|---|
| Codeunit 80 | Department validation before posting | `CheckDeptMAS(Rec)`, line 85 |
| Codeunit 80 | Sales quantity validation before shipment | `ValidateQuantity`, lines 238–246 |
| Codeunit 80 | Transfer Sales Line Owner into Item Journal Line | line 2688 |
| Codeunit 22 | Ownership ledger posting to Table 50035 | `InsertOwnership`, lines 178–195 and 4846–4915 |
| Codeunit 22 | Owner-specific remaining quantity validation | `CheckRemainingQty`, lines 4917–4933 |
| Codeunit 22 / Table 32 | Additional Item Ledger Entry reference field | `Entry No Plus Satu`, Table 32 field 50099; Codeunit 22 line 1826 |
| Codeunit 22 | Lot-aware Applies-to Entry override | `T00.01`, lines 1842–1848 |

This is not an exhaustive customization inventory for Codeunit 80 or Codeunit 12. Their other added/changed procedures need separate source comparison and business-owner confirmation.

## 7. Open questions / next investigation

1. Verify the actual NAV application version and ensure the original baseline is version-compatible with NAVW18 source metadata.
2. Inspect Table 50035 field definitions, keys, and any triggers; verify the business meaning of Owner and the Location.Ownership flag.
3. Trace the transfer shipment/receipt two-entry behavior that motivates the +2 Item Ledger Entry reference.
4. Inspect the complete `ValidateQuantity` implementation and reconcile it with Ownership remaining quantity.
5. Trace the final Codeunit 12 posting-buffer flush to persistent Table 17 and related VAT/customer ledger writes.
6. Compare Codeunit 22 and Table 32 against the correct same-version original baseline at procedure/field level.
7. Validate representative cases: normal shipment, partial shipment, invoice-only after shipment, return/credit memo, transfer shipment/receipt, reclassification, warehouse reclassification, inventory adjustment, and locations with Ownership on/off.

## 8. Evidence links

- [Codeunit 80 — Sales-Post](https://github.com/ayabenz/nav2015-agent/blob/datascrip/reports/datascrip/sales/Codeunit_80.txt)
- [Codeunit 12 — Gen. Jnl.-Post Line](https://github.com/ayabenz/nav2015-agent/blob/datascrip/reports/datascrip/sales/Codeunit_12.txt)
- [Codeunit 22 — Item Jnl.-Post Line](https://github.com/ayabenz/nav2015-agent/blob/datascrip/reports/datascrip/sales_next/Codeunit_22.txt)
- [Table 32 — Item Ledger Entry](https://github.com/ayabenz/nav2015-agent/blob/datascrip/reports/datascrip/sales/Table_32.txt)
- [Posting dependency edges](https://github.com/ayabenz/nav2015-agent/blob/datascrip/reports/datascrip/sales_next/posting_edges.csv)


## 9. Deeper validation findings

### 9.1 Codeunit 80 ValidateQuantity is an Item Ledger availability sum

Procedure `ValidateQuantity` is at Codeunit 80 lines 6998–7023.

It:
- filters Table 32 by Item No. (supports an `&` filter expression) and Location Code;
- iterates matching Item Ledger Entries and sums `Remaining Quantity` (lines 7006–7018);
- compares the total with requested quantity (line 7019).

The former filters on Open=TRUE and Quantity>0 are commented out (lines 7013–7014). The active implementation therefore sums Remaining Quantity for all matching Item Ledger Entry rows and does not filter by Owner.

**Important distinction:** this is a location/item availability check, not an owner-specific availability check. The later Codeunit 22 Ownership check is a separate control over Table 50035. The two checks should not be treated as equivalent.

### 9.2 Owner-specific and total inventory controls are separate

For a Sales shipment, current source indicates two validation layers:

1. Codeunit 80 `ValidateQuantity`: sum Item Ledger Entry Remaining Quantity for Item + Location.
2. Codeunit 22 `InsertOwnership` → `CheckRemainingQty`: sum Ownership Quantity for Item + Location + Owner, when location Ownership is enabled and the source/entry type is in the guarded cases.

This means a document may pass the total inventory check but fail the owner-specific check. That appears intentional if inventory is partitioned by owner, but the business rule must be confirmed with the inventory process owner.

### 9.3 Confirmed persistent G/L Entry write

Codeunit 12 `FinishPosting` (lines 1234–1267) iterates `TempGLEntryBuf`, copies each row to `GlobalGLEntry`, sets prior-year status, and calls `GlobalGLEntry.INSERT` at line 1248. This confirms the persistent Table 17 insert. It then updates/inserts the G/L Register range and checks posting balance consistency.



## 10. Sales posting wrappers: Codeunit 50081, 50082 and 50084

The additional wrapper objects are present in `sales_next` and have now been inspected.

### 10.1 Codeunit 50081 — Sales-Post (Y/N) Ship

- TableNo = 36.
- `OnRun` first calls `Codeunit 50107.BlockStocktakeSalesHeader(Rec, FALSE)`, then copies the Sales Header and executes its local `Code`.
- The local `Code` requires Status = Released.
- For Order: calls `AddLotNo`, sets Ship = TRUE and Invoice = FALSE.
- For Return Order: sets Receive = TRUE and Invoice = FALSE.
- It then calls Codeunit 80.
- `AddLotNo` scans item Sales Lines. For a location that is not Directed Put-away and Pick, with Qty. to Ship > 0, and an Item Tracking Code, it invokes `SalesReserve.CallItemTracking-HSL(SalesLine)`.

**Business implication:** the Ship action wrapper does more than set posting flags. It blocks a stocktake condition through Codeunit 50107 and opens item tracking for qualifying sales lines before posting. The exact stocktake rule is not established here because Codeunit 50107 source is not in this export.

### 10.2 Codeunit 50082 — Sales-Post (Y/N) Invoice

- TableNo = 36.
- Requires Status = Released.
- For Order: sets Ship = FALSE and Invoice = TRUE.
- For Return Order: sets Receive = FALSE and Invoice = TRUE.
- Calls Codeunit 80.

This wrapper explicitly selects invoice-only behavior for an Order; it does not request shipment in the same call. For a Return Order it selects invoice processing without receipt in this wrapper.

### 10.3 Codeunit 50084 — Sales-Post + Print Invoice

- Requires Status = Released.
- For Order, its active selection menu is invoice-only: Ship = FALSE and Invoice = TRUE.
- For Return Order, its active selection is invoice-only: Receive = FALSE and Invoice = TRUE.
- Calls Codeunit 80 and then prints the resulting posted document using Report Selection (Table 77).
- It selects posted shipment, invoice, return receipt or credit memo records based on document type and posting flags.

### 10.4 Wrapper-to-posting flow

```text
Page 42 action
  +-- Ship --> Codeunit 50081
  |              +-- Codeunit 50107 stocktake block
  |              +-- AddLotNo / item tracking
  |              +-- Ship=TRUE, Invoice=FALSE
  |              +-- Codeunit 80
  |
  +-- Invoice --> Codeunit 50082
  |                 +-- Ship=FALSE, Invoice=TRUE
  |                 +-- Codeunit 80
  |
  +-- Post + Print --> Codeunit 50084
                     +-- invoice-only selection in active code
                     +-- Codeunit 80
                     +-- Report Selection / print
```

The general Post action on Page 42 may have a different route and should be kept distinct from these named wrappers.

## 11. Ownership Table 50035 — schema and lifecycle

The object has now been extracted to `reports/datascrip/ownership/Table_50035.txt`. Its schema and keys are therefore source-verified. The remaining lifecycle gap is identifying every other writer/reader across the complete object set.

- exact field IDs, types, captions and validation triggers;
- primary key and secondary keys;
- table-level OnInsert/OnModify/OnDelete/OnRename triggers;
- whether Quantity is FlowField or stored Decimal;
- whether there are additional filters, FlowFilters, or relations;
- whether other codeunits/pages/reports mutate the Ownership table.

Table 50035 has 16 fields and these important definitions: `Quantity` is a stored Decimal; `Owner` (Code20) relates to Dimension Value where Dimension Code is `OWNERSHIP`; `Location Code` relates to Location; `Item Ledger Entry No.` relates to Table 32 and is non-editable; `Total` is a FlowField summing Quantity by Item No. + Location Code, without Owner. Its keys are Entry No. (clustered), Item No. + Location Code (SumIndex Quantity), Item No. + Location Code + Owner + Posting Date (SumIndex Quantity), and P2B Doc No.\n\nThe Codeunit 22 source does prove the fields it attempts to read/write: `Entry No.`, `Description`, `Posting Date`, `Entry Type`, `Document No.`, `Item No.`, `Owner`, `Location Code`, `Document Type`, `Item Ledger Entry No.`, `User ID`, and `Quantity`. It also proves the key selected by `CheckRemainingQty`: Item No., Location Code, Owner, Posting Date. This does not replace the missing table definition.

The code's object change history comments in Codeunit 22 record:
- T30.01 — 18 Sep 2015: add `InsertOwnership`.
- T30.02 — 30 Sep 2015: add `CheckRemainingQty` to prevent negative ownership.
- T30.03 — 20 Oct 2015: add User ID to Ownership Ledger Entry.

These comments are evidence of the developers' stated intent, not proof of all current table constraints or runtime behavior.

**Remaining source task:** search the complete object set for every writer/reader of Table 50035 (`Record 50035`, table ID references, and dynamic RecordRef use). Compare against a matching NAVW18 baseline before declaring the ownership feature fully custom.

## 12. Version and provenance warning

The three wrappers have `Version List=DTS:D34` and dates in 2015/2020/2026, while Codeunit 22 and Codeunit 80 source headers identify NAVW18.00.00. This reinforces the need to identify the exact NAV application build and compare against a matching original baseline before marking individual procedures as company-modified standard versus later-version standard.


### 14.1 Extraction command

The repository now includes `scripts/export_nav_objects.py`, which extracts selected objects from the existing TXT/ZIP source archive without requiring another NAV export. After pulling the latest `datascrip` branch, run this from the repository root:

```powershell
python scripts/export_nav_objects.py --input data/input/datascrip/datascrip.zip --output reports/datascrip/ownership --objects Table:50035 Table:14 Codeunit:50107 Codeunit:50035
```

To extract the standard comparison objects from the original archive (only where they exist):

```powershell
python scripts/export_nav_objects.py --input data/input/original/original.zip --output reports/original/ownership --objects Table:14 Codeunit:22
```

The original export may be from a different NAV build; use it as a comparison candidate, not as a trusted same-version baseline until the version headers are reconciled.


## 15. Ownership and stocktake source inspection — 26 Nov 2026

The previously missing company objects have now been extracted and inspected:

- `reports/datascrip/ownership/Table_50035.txt`
- `reports/datascrip/ownership/Table_14.txt`
- `reports/datascrip/ownership/Codeunit_50107.txt`
- `reports/datascrip/ownership/Codeunit_50035.txt`

### 15.1 Table 50035 — Ownership Ledger Entry schema

The table contains 16 fields. Relevant fields and definitions:

| Field | Definition |
|---|---|
| 1 | Entry No. — Integer |
| 2 | Document No. — Code20 |
| 3 | Item No. — Code20, relation to Item |
| 4 | Quantity — stored Decimal, 0:5 decimal places |
| 5 | Owner — Code20, relation to Dimension Value where Dimension Code = OWNERSHIP |
| 6 | Location Code — Code10, relation to Location |
| 7 | Total — FlowField summing Quantity by Item No. + Location Code; it does not filter Owner |
| 8 | Entry Type — Purchase, Sale, Positive Adjmt., Negative Adjmt., Transfer, Consumption, Output, Transfer Ownership, P2B |
| 9 | Description — Text50 |
| 10 | Posting Date — Date |
| 11 | Item Ledger Entry No. — Integer, relation to Item Ledger Entry, non-editable |
| 12 | Document Type — includes Sales Shipment/Invoice, Sales Return Receipt/Credit Memo, Purchase Receipt/Invoice, Transfer Shipment/Receipt, and other types |
| 13 | User ID — Code50, non-editable |
| 50000 | Original Doc No. — Code20 |
| 50001 | P2B Doc No. — Code20 |
| 50002 | Qty2 — Decimal |

Keys:
- Entry No. (clustered)
- Item No. + Location Code, SumIndexFields=Quantity
- Item No. + Location Code + Owner + Posting Date, SumIndexFields=Quantity
- P2B Doc No.

There are no table-level CODE triggers in this object export. The table's `Total` FlowField is **not an owner balance**: it aggregates every owner at the location for the item. The owner-specific balance is calculated by Codeunit 22 `CheckRemainingQty`.

### 15.2 Location.Ownership gate

Table 14 field 50035 is Boolean `Ownership`. Its OnValidate trigger checks whether any Table 32 Item Ledger Entry exists for the Location with `Open=TRUE`. If any exists, changing the flag raises `Text50000` and is blocked.

This is a location-level switch, not a per-item or per-owner switch. The validation checks open ILE rows, not the Ownership Ledger table.

### 15.3 Ownership posting rules in Codeunit 22

The posting call is in Codeunit 22 `Code` before normal item quantity posting (lines 178–195). It runs when Value Entry Type is not Revaluation and Source Code is not `RECLASSJNL` or `WHRCLSSJNL`. For Transfer Receipt, the location argument is `New Location Code`; otherwise it is `Location Code`.

`InsertOwnership` then:
- exits if `Location.Ownership=FALSE`;
- excludes source codes `INVTADJMT` and `INVTPCOST`;
- excludes zero base quantity;
- allocates the next Ownership Entry No. under table lock;
- records item, owner, location, document, posting date, entry type, user and linked ILE number;
- posts negative Ownership Quantity for Sale, Negative Adjmt., Consumption and Transfer Shipment after checking owner balance;
- posts positive Quantity for other applicable entry types, including Transfer Receipt.

The owner-balance check filters Item No., Location Code and Owner, then sums Quantity. Although the selected key includes Posting Date, there is no Posting Date range, nor Entry Type range. Thus it sums all historical rows for that item/location/owner.

**Important data-quality implication:** Owner is a Code20 dimension value. The source does not show a fallback owner assignment in `InsertOwnership`; blank Owner can therefore form its own balance bucket unless upstream validation prevents it. Confirm whether Sales Line / Item Journal Line always supplies a valid Owner when Location.Ownership is enabled.

### 15.4 Transfer Receipt +2 Item Ledger Entry reference — refined conclusion

The Ownership record is inserted before the standard posting branch increments the Item Ledger Entry sequence. The code assigns:
- normal case: `ItemLedgEntryNo + 1`;
- Transfer Receipt: `ItemLedgEntryNo + 2`.

The standard posting code explains why a second ILE can be created during a Transfer:
- `ItemQtyPosting` initializes the main ILE through `InitItemLedgEntry` (line 937);
- during application of a Transfer entry, `ApplyItemLedgEntry` can call `InsertTransferEntry` when the applied quantity is negative and the application was not itself caused by a transfer (lines 1719–1729);
- `InsertTransferEntry` calls `InitItemLedgEntry` again and inserts a second ILE (lines 1757–1811);
- `InitItemLedgEntry` increments the shared ItemLedgEntryNo each time (line 1821).

This makes the +2 offset plausible for the transfer-receipt flow where that transfer counterpart is generated. However, it is **not yet proven for every Transfer Receipt scenario**: the additional `InsertTransferEntry` call depends on the application path and quantities, and AverageTransfer has its own call path at lines 960–961. A definitive result requires tracing actual Transfer Receipt posting with and without matching in-transit applications and with Average costing. Do not treat +2 as universally correct or as a confirmed defect based only on static source.

### 15.5 Codeunit 50107 — Block Stocktake

`BlockStocktakeSalesHeader(SalesHeader, CreateWhseShipment)` applies these gates:

1. Select Sales Lines for the document and Item type.
2. If creating a warehouse shipment, require Qty. To Whse. Shipment > 0. Otherwise:
   - Sales Order: Qty. to Ship <> 0;
   - Return Order: Return Qty. to Receive <> 0.
3. If there are no matching item lines, exit without blocking.
4. Find stocktake records in Table 50063 where Start Date <= CURRENTDATETIME and End Date >= CURRENTDATETIME.
5. For Sales Order/Invoice, filter transaction type `OUT|ALL`; for Credit Memo/Return Order, filter `IN|ALL`.
6. For each active stocktake record, filter Sales Line by Location and then by the configured Block Type: Item Category, Product Group, or Item.
7. If a matching line exists, raise an error naming the blocked Item.

The same Codeunit contains analogous gates for Purchase, Transfer, Warehouse Receipt and other flows. This is a time-window + transaction-direction + location + item-scope block, not a global sales lock.

**Evidence limitation:** the Table 50063 definition was not part of the four extracted objects in this pass. The code proves which fields are read, but field types, defaults, table validation and maintenance UI still need inspection.

### 15.6 Codeunit 50035 — Item Tracking Lines

This is a **Codeunit**, not Table 50035. It must not be conflated with the Ownership Ledger Entry table despite sharing object ID 50035.

Its `CollectPostedTransferEntries` procedure:
- exits unless Tracking Specification Source Type is Transfer Line;
- filters Item Entry Relation by Transfer Order No. and Order Line No.;
- uses Source Type Transfer Shipment Line for outbound subtype 0 and Transfer Receipt Line for inbound subtype 1;
- retrieves the linked Item Ledger Entry and copies entry no., item, serial no., lot no., quantity, handled/invoiced quantities and UOM into the temporary Tracking Specification.

This procedure reconstructs posted transfer tracking from the actual Item Entry Relation and ILE rows; it does not write to the Ownership ledger.

### 15.7 Remaining investigation

1. Extract and inspect Table 50063 (Stocktake) and its maintenance page(s).
2. Search all company objects for writes to Table 50035, including direct `Record 50035` references and dynamic RecordRef access.
3. Trace Transfer Receipt runtime-equivalent paths with different costing methods and application states to validate the +2 link.
4. Confirm Owner mandatory rules and dimension validation upstream.
5. Reconcile the NAVW18 object headers against the actual installed NAV build and a matching original baseline.


## 16. Same-version baseline comparison — Ownership customization confirmed

A direct source comparison was made against:
- `reports/original/ownership/Codeunit_22.txt` — Version List `NAVW18.00.00.40938`
- `reports/original/ownership/Table_14.txt` — Version List `NAVW18.00`

The company Codeunit 22 has the same standard version header as the original Codeunit 22, but adds all of the following code/fields that are absent from the original object:
- global Record 50035 Ownership Ledger Entry;
- call to `InsertOwnership` from the posting `Code` procedure;
- `InsertOwnership` procedure;
- `CheckRemainingQty` procedure;
- assignment to Table 32 field `Entry No Plus Satu`.

The original Table 14 does not contain field 50035 `Ownership`; the company Table 14 adds it with an OnValidate check for open Item Ledger Entries at the location.

This is stronger evidence than comparing against a potentially unrelated standard release: **the Ownership Ledger and Location.Ownership gate are company customizations relative to the supplied NAVW18 baseline**. The same-version comparison confirms the feature is not part of the original Table 14 / Codeunit 22 source supplied in `original.zip`.

The Table 32 field 50099 `Entry No Plus Satu` should also be checked against the original Table 32 object before making a complete field-level customization statement. The company Codeunit 22 writes it, and the original Codeunit 22 does not contain that assignment.

## 17. Stocktake object extraction required

The inventory index identifies:
- Table 50063 — `Setting Blocked Stocktake`, modified, 13 fields, 1 trigger;
- Page 50169 — `Block Stocktake`, modified, 12 controls and 9 procedures.

These are not yet included in the extracted source folder. They are the next direct source inputs required to establish the configuration schema, date/time field types, default values, validation, and maintenance behavior. Extract them from the existing company archive:

```powershell
python scripts/export_nav_objects.py --input data/input/datascrip/datascrip.zip --output reports/datascrip/stocktake --objects Table:50063 Page:50169
```

Then commit/push `reports/datascrip/stocktake` to branch `datascrip`. No new NAV export is required.



## 18. Table 50063 and Page 50169 — Stocktake block configuration

The two objects were extracted from the existing `data/input/datascrip/datascrip.zip` archive using the new GitHub Actions extraction runner. Source files:
- `reports/datascrip/stocktake/Table_50063.txt`
- `reports/datascrip/stocktake/Page_50169.txt`

### 18.1 Table 50063 schema

Table 50063 `Setting Blocked Stocktake` has these fields:

| Field ID | Name | Type | Meaning / usage |
|---:|---|---|---|
| 1 | Item Category Code | Text250 | Item Category filter |
| 2 | Product Group Code | Text250 | Product Group filter |
| 3 | Item No. | Text250 | Item filter |
| 4 | Location Code | Text250 | Location filter |
| 5 | Start Date | DateTime | Inclusive block start |
| 6 | End Date | DateTime | Inclusive block end |
| 7 | Jenis Transaksi | Option: IN, OUT, ALL | Transaction direction |
| 8 | Dept. Code | Code100 | Present in schema; not read by Codeunit 50107 |
| 10 | ID | Integer, AutoIncrement | Primary key |
| 11 | Block Type | Option: Item, Product Group, Item Category | Chooses which item-scope field is applied |
| 12 | CreateUserID | Code30 | Audit field, non-editable |
| 13 | CreateDateTime | DateTime | Audit field, non-editable |
| 14 | Note | Text250 | Free-form note |

The only key is clustered ID. The table has an OnInsert trigger that stamps USERID and CURRENTDATETIME into CreateUserID and CreateDateTime. There are no table-level OnModify, OnDelete, or field validation triggers in this export.

**Important observations:**
- The active time window is based on DateTime, not Date. Codeunit 50107 uses inclusive comparisons: Start Date <= CURRENTDATETIME and End Date >= CURRENTDATETIME.
- The three item selectors and Location Code are Text250, not strongly typed Code fields with table relations. The maintenance page supplies lookups, but the table itself does not enforce referential integrity through field relations.
- Dept. Code exists in the schema but the inspected BlockStocktake procedures do not filter by it. It currently has no demonstrated effect on blocking.
- There is no source-level validation that Start Date <= End Date, that a selector is populated, or that overlapping rules are prohibited.
- A record with no populated Item Category Code, Product Group Code or Item No. will not block in the inspected Codeunit 50107 logic, because each gate checks that at least one selector is non-empty before applying the Block Type filter.

### 18.2 Page 50169 maintenance behavior

Page 50169 `Block Stocktake` is a List page over Table 50063 with DelayedInsert=Yes.

- Location Code lookup opens Location List and supports multi-value filter input by appending values with `|`.
- Item No. lookup opens Item List and supports the same multi-value syntax.
- Product Group Code and Item Category Code lookups likewise support pipe-separated selections.
- Block Type controls which selector is enabled in the UI.
- OnInsertRecord and OnModifyRecord clear the two selector fields that do not correspond to the selected Block Type:
  - Item: clear Product Group and Item Category;
  - Product Group: clear Item No. and Item Category;
  - Item Category: clear Product Group and Item No.
- The same clearing logic is performed on both insert and modify.
- The page exposes Start Date, End Date, Block Type, item-scope selector, Jenis Transaksi and Note.
- Dept. Code is explicitly Visible=FALSE.
- Page code contains no additional business actions or procedures beyond these page triggers and lookup handlers.

The page-level clearing reduces the chance of conflicting selectors when users maintain records through this page. It is not a database-level constraint: inserts/updates made outside Page 50169 can still populate multiple selectors or omit the intended selector.

### 18.3 Cross-check against Codeunit 50107

Combining Table 50063, Page 50169 and Codeunit 50107 establishes the full configuration model:

1. A stocktake rule is active only during its inclusive Start Date–End Date DateTime window.
2. It is scoped to one or more Location Code values using NAV filter syntax.
3. Direction is IN, OUT or ALL.
4. Block Type chooses one item selector: Item, Product Group or Item Category.
5. The posting gate checks the transaction's location and item attributes against the active rule, then raises an error naming the blocked item.
6. Dept. Code is stored but is not used by the inspected Codeunit 50107 procedures.

**Potential configuration risks to validate operationally:**
- Missing Start Date / End Date or reversed date ranges can create ineffective or unexpectedly active rules; no validation was found in these objects.
- Blank item-scope values silently make the rule ineffective in the inspected posting gates.
- Text250 filter fields accept NAV filter syntax. This enables multi-selection but also means manually entered filter expressions may have broader matching semantics than a literal code.
- Overlapping active rules are allowed by the table/page source; the first matching rule causes an error, so the displayed item is the first encountered match, not necessarily the only applicable rule.
- Dept. Code may mislead users because it is stored but hidden and not applied in the inspected blocking logic.

### 18.4 Sales flow nuance

In `BlockStocktakeSalesHeader`, the Qty. to Ship / Return Qty. to Receive filter is applied only for Sales Order and Return Order. Sales Invoice and Credit Memo use their document-type direction filter but do not apply those quantity filters in this procedure. Therefore all Item lines on those document types can be considered by the stocktake gate, subject to location and item-scope matching. This is a source observation; validate whether that behavior is intentional for the company's invoice/credit-memo workflow.

### 18.5 Evidence and remaining checks

- Table schema and OnInsert audit stamping: Table 50063, source object.
- Selector enablement, multi-value lookups and field clearing: Page 50169, page triggers and controls.
- Runtime block window, direction, location and item-scope filtering: Codeunit 50107 procedures `BlockStocktakeSalesHeader`, `BlockStocktakePurchaseHeader`, `BlockStocktakeTransferHeader` and `BlockStocktakeWarehouseReceiptHeader`.

The earlier Section 17 extraction instruction is superseded: both source files are now present in the repository. Remaining work is to inspect all callers of Codeunit 50107 and determine whether every relevant posting/warehouse entry point invokes the appropriate gate.
