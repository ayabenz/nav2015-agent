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
