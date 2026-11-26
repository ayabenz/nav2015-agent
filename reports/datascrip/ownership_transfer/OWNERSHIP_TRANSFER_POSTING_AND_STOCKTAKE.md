# Ownership Transfer Journal — Posting and Stocktake Relationship

**Scope:** Page 50152 Ownership Transfer, Page 50156 list, Table 50036 batch, Table 50037 journal lines, Codeunit 50051 Custom WMS Management, Table 50035 Ownership Ledger Entry, and related reports/pages.

## 1. Executive summary

Ownership Transfer is **not the same operation as a physical Transfer Order**.

- It transfers quantity between two Owner balances at the **same Location Code**.
- It does not create an Item Ledger Entry or move inventory between locations in the inspected posting procedure.
- Codeunit 50051 writes two Ownership Ledger Entry rows: a negative row for Transfer-from Owner and a positive row for Transfer-to Owner, both with Entry Type and Document Type = Transfer Ownership.
- Quantity validation checks that the source Owner has enough available quantity.
- Posting validates that the source and destination owner quantities balance.

No call to Codeunit 50107 (stocktake) was found in Page 50152, Table 50037, or Codeunit 50051. Because this process reclassifies ownership rather than physically moving inventory, **do not classify the missing stocktake call as a confirmed bypass or defect without the company's explicit rule for ownership reclassification during stocktake**.

## 2. User interface and posting route

- Page 50152 is the Ownership Transfer journal page.
- Page 50156 is the Ownership Transfer list.
- The journal batch comes from Table 50036.
- Page 50152 Post action:
  1. Checks `TotalBalance <> 0`; if true, raises “Transfer Owner belum balance..”.
  2. Calls Codeunit 50051 `PostingOwnershipTransfer(Rec)`.
- Codeunit 50051 calls `CekPostOwnTransfer` first. If validation succeeds, it asks for confirmation, locks Table 50035, allocates Ownership Ledger Entry numbers, inserts entries, and deletes the posted journal lines.

## 3. Journal data model

Table 50037 Ownership Transfer contains:
- Item No., Posting Date, Document No., Description, Location Code.
- Quantity, Unit of Measure Code, Quantity (Base).
- Journal Batch Name, Reason Code, Posting No. Series.
- Transfer-from Owner, Transfer-to Owner, and P2B Document No.

Location Code is related to Location where Ownership = Yes. The OnValidate trigger rejects Location DUNEX with a message directing the user to use PLG.

Transfer-from Owner and Transfer-to Owner validation:
- Validates that the selected location is Ownership-enabled.
- Clears Quantity and Quantity (Base) when the owner changes.
- Rejects the same owner on both sides.
- Sets the general Owner field from whichever side is selected and clears the opposite side.

The general Owner field's OnValidate currently raises “sudah tidak dipakai”; the intended entry fields are Transfer-from Owner and Transfer-to Owner.

## 4. Quantity and balance validation

### Entry-time availability

When Quantity is validated and P2B Document No. is blank and Transfer-to Owner is blank, Table 50037 calls:

```pascal
cuCWM.CekQuantity(
  6, Item No., Location Code, Transfer-from Owner,
  Quantity, Unit of Measure Code, xRec.Quantity,
  xRec.Unit of Measure Code, Available, FALSE)
```

Transaction type 6 is Ownership Transfer. Codeunit 50051 checks the selected source owner's availability using Item/Ownership Ledger quantities and outstanding sales, purchase-return, transfer, negative item journal, P2B, and ownership-transfer quantities. It raises an insufficient-quantity error if the source owner cannot cover the requested amount.

The destination-owner line skips this source availability check; the source-owner side is the side that reduces an existing owner balance.

### Posting-time balance

Codeunit 50051 `CekPostOwnTransfer` validates each journal line:
- Item No., Posting Date, Document No., Location Code, Quantity and Owner are required.
- Location must have Ownership enabled.
- Transfer-from Owner and Transfer-to Owner cannot both be populated on one line.
- If P2B Document No. is supplied, an existing Ownership Ledger Entry with the same P2B Doc No. prevents reposting.
- For each Item No. + Document No. + Posting Date + Journal Batch, total source-owner quantity must equal total destination-owner quantity.

Page 50152 also checks a page-level TotalBalance before posting. Its `CheckBalance` procedure is commented out and is not called by the Post action. The active per-document balance check is in Codeunit 50051.

## 5. What gets posted

For each nonzero journal line, Codeunit 50051 inserts one Table 50035 Ownership Ledger Entry:

| Journal line | Ownership Ledger Entry |
|---|---|
| Transfer-from Owner populated | Quantity = negative Quantity (Base); Owner = Transfer-from Owner |
| Transfer-to Owner populated | Quantity = positive Quantity (Base); Owner = Transfer-to Owner |

Both entries use:
- Same Item No., Location Code, Posting Date, Document No., Description.
- Entry Type = Transfer Ownership.
- Document Type = Transfer Ownership.
- User ID = USERID.
- Original Doc No. and P2B Doc No. carried from the journal.

The posting procedure does not call Codeunit 22 and does not create a physical Item Ledger Entry in the inspected code. The net physical quantity at the location is unchanged; the ownership balance is redistributed between owners.

## 6. Stocktake relationship

Static inspection found no `BlockStocktake...` call in the ownership journal page, Table 50037, or Codeunit 50051.

This is different from Transfer Order, where stock physically moves between source, in-transit, and destination locations and Codeunits 5704/5705 explicitly call the stocktake checker with OUT/IN.

For Ownership Transfer:
- The operation changes Owner attribution at one Ownership-enabled location.
- It does not change the Item Ledger quantity or location.
- It does change owner-specific availability in the Ownership Ledger.

**Classification:** stocktake applicability is a business-policy question, not a confirmed code defect. If the company requires stocktake to freeze ownership reclassification as well, a pre-posting check must be added to the Ownership Transfer posting route. If stocktake only freezes physical inventory movements, the current separate journal behavior may be intentional.

## 7. Source-level risks to validate

1. **Balance grouping does not include Location Code.** In `CekPostOwnTransfer`, the source/destination balance aggregation filters by Journal Batch Name, Item No., Document No., and Posting Date, but not Location Code. If one document number can contain the same item at multiple locations in one batch/date, quantities could balance across locations. Confirm whether document-number uniqueness or page filtering guarantees one location per document.
2. **Page TotalBalance is broad.** Page 50152 sums Quantity across the current page filter before posting. The Codeunit performs the more specific item/document/date balance validation; retain the Codeunit validation as the authoritative control.
3. **Owner field is legacy.** Table 50037's general Owner OnValidate errors “sudah tidak dipakai”; the UI uses Transfer-from Owner and Transfer-to Owner. Avoid integrations writing Owner directly.
4. **No physical ILE link is created.** The Ownership Ledger Entry Item Ledger Entry No. is not assigned by this posting procedure. This is consistent with an owner reclassification rather than a physical item movement, but reports must not assume every ownership transfer row links to an ILE.

## 8. Follow-up validation

- Confirm the company's stocktake policy for Ownership Transfer specifically.
- Confirm whether a journal document can contain multiple locations for the same item.
- Runtime-test a balanced two-sided owner transfer, insufficient source owner balance, unequal source/destination totals, same-owner transfer, and duplicate P2B document number.
- Reconcile Table 50035 balances by Item + Location + Owner before and after a posted ownership transfer; the sum across owners at the same location should remain unchanged.

## 9. Source files

- `reports/datascrip/ownership_transfer/Page_50152.txt`
- `reports/datascrip/ownership_transfer/Page_50153.txt`
- `reports/datascrip/ownership_transfer/Page_50156.txt`
- `reports/datascrip/ownership_transfer/Page_50161.txt`
- `reports/datascrip/ownership_transfer/Table_50036.txt`
- `reports/datascrip/ownership_transfer/Table_50037.txt`
- `reports/datascrip/ownership_transfer/Codeunit_50051.txt`
- `reports/datascrip/ownership_transfer/Codeunit_50200.txt`
- `reports/datascrip/ownership_transfer/Report_50168.txt`
- `reports/datascrip/ownership_transfer/Report_50190.txt`
- `reports/datascrip/ownership_transfer/Report_50220.txt`

Related stocktake decision: [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3).
