# P2B — Workflow, Downstream Posting, and Stocktake Audit

**Scope:** P2B Transaction / Approval pages, P2B Header and Line, Codeunit 50100 P2B Management, downstream Transfer Order / Loan / Ownership Transfer / Item Journal generation, and the standard Item Journal posting path.

## 1. Executive summary

P2B is a workflow and document-generation process. The P2B page's **Posting** action does not always post inventory immediately. Codeunit 50100 `Posted` dispatches to one of several downstream paths, then closes the P2B document.

The stocktake conclusion depends on the selected Posting To and location type:

| P2B route | What Codeunit 50100 creates | Actual inventory posting | Stocktake result |
|---|---|---|---|
| Item Journal, non-WMS location | Negative Adjustment Item Journal lines | Later, from Item Journal page | No stocktake check found in Page 40 → 241 → 23 → 22 |
| Item Journal, WMS/Ownership location | Transfer Order with Transfer to Item Journal flag | Later, through transfer posting | OUT/IN check in Codeunit 5704/5705 |
| Transfer Order, different locations | Transfer Order and lines | Later, through transfer posting | OUT/IN check in Codeunit 5704/5705 |
| Transfer Order, same WMS location | Ownership Transfer journal lines | Later, through Ownership Transfer journal | No stocktake check found in Codeunit 50051 |
| Loan | Loan document and lines | Later, through transfer posting | OUT/IN check in Codeunit 5704/5705 |

**Important:** the non-WMS Item Journal route creates negative adjustment lines but does not post them during P2B `Posted`. The code that would post the Item Journal directly is commented out. The physical inventory change happens later when the journal is posted from Page 40.

## 2. Workflow and approval

- Page 50054 P2B Transaction is the document page; it exposes Request Approval.
- Request Approval validates required header/line fields, checks the P2B status is Open, then calls Codeunit 50100 `Released`.
- Page 50062 P2B Approval exposes Approve and Posting actions.
- Approve calls Codeunit 50100 `Approved`.
- Posting calls Codeunit 50100 `Posted` after checking for blank item numbers and blocked Items.
- Page 50057 is the P2B list; Page 50073 shows posted transactions.

Codeunit 50100 `Posted`:
1. Calls `CheckDeptMAS`.
2. Requires Status=Release and validates Document Type, Warehouse Code, Requester, Owner and Requester User ID.
3. Calls `CheckingHeader` and `CheckingLine`.
4. Verifies the current user is an eligible approver/poster.
5. Dispatches according to Posting To and location type.
6. Processes the workflow, sets status Close, updates P2B Line status, writes Posting Date, modifies and commits.

There is no direct Codeunit 50107 stocktake call in the inspected P2B posting router.

## 3. Posting To = Item Journal

### 3.1 Non-WMS location

When Posting To is Item Journal, Codeunit 50100 calls `CheckLocationType`:
- If the location is WMS/Ownership-enabled, it routes to `PostingTransferOrderWMS`.
- Otherwise, it calls `PostingItemJournal`.

`PostingItemJournal`:
- Deletes prior unposted Item Journal lines with the same P2B Document No. before rebuilding.
- Creates Item Journal Line records in the selected template/batch.
- Sets Entry Type = Negative Adjmt.
- Sets Item No., Unit of Measure, Location Code, Owner when present, Quantity, P2B Document No., posting context, dimensions and interdivision fields.
- Copies comments and records the generated journal Document No. in P2B Posted Doc No.
- The direct `CODEUNIT.RUN(CODEUNIT::"Item Jnl.-Post",LItemJnlLine)` is commented out.

Therefore, P2B's Posting action creates the journal lines and closes the P2B workflow; it does not itself create the Item Ledger Entries.

### 3.2 Actual Item Journal posting

Page 40 Item Journal exposes:
- Post (F9) → Codeunit 241 Item Jnl.-Post.
- Post and Print (Shift+F9) → Item Jnl.-Post+Print.

The inspected Post route is:

```text
Page 40 Item Journal
  └─ Codeunit 241 Item Jnl.-Post
       └─ Codeunit 23 Item Jnl.-Post Batch
            └─ Codeunit 22 Item Jnl.-Post Line
                 └─ Item Ledger Entry / Value Entry posting
```

Findings:
- Codeunit 241 validates Gen. Bus. Posting Group, then calls Codeunit 23.
- Codeunit 23 calls Codeunit 22 `ItemJnlPostLine.RunWithCheck`.
- No `BlockStocktake...` or Codeunit 50107 reference was found in Page 40, Codeunit 241, Codeunit 23, or the inspected Codeunit 22 source.

**Stocktake status:** no stocktake validation was identified at the actual non-WMS Item Journal posting path. If the company requires stocktake to block negative adjustments, the check must be placed before the Item Journal is actually posted (or at an appropriate common posting entry point), not only when P2B creates the journal lines.

## 4. Posting To = Item Journal, WMS/Ownership location

When the source location is WMS/Ownership-enabled, Codeunit 50100 uses `PostingTransferOrderWMS` instead of creating a direct Item Journal.

It:
- Creates a Table 5740 Transfer Order.
- Sets Transfer Type = Transfer.
- Sets Transfer-from Code to the selected WMS location.
- Sets Transfer-to Code to Inventory Setup's P2B Location Code.
- Sets In-Transit Code to TRANSIT.
- Sets Transfer to Item Journal = TRUE.
- Carries the P2B Document No., journal template/batch, Gen. Bus. Posting Group, dimensions, Owner and item lines.

The resulting Transfer Order is posted later through Codeunit 5704/5705, which run the stocktake OUT/IN checks before posting. This WMS route is therefore different from the direct non-WMS Item Journal route.

## 5. Posting To = Transfer Order

Codeunit 50100 chooses between two paths:

### 5.1 Different locations or non-WMS combination

`PostingTransferOrder` creates a regular Transfer Order:
- Copies From Location, To Location, In-Transit, ownership fields, dimensions, salesperson and shipping details.
- Creates Transfer Lines from P2B Lines.
- Stores the P2B Document No. on the Transfer Header.

The actual shipment/receipt is posted later through Codeunit 5704/5705, so the transfer stocktake checks run at final posting.

### 5.2 Same WMS/Ownership location

If both From Location and To Location are Ownership-enabled and they are the same location, Codeunit 50100 calls `PostingOwnerTransfer` instead.

This creates paired Table 50037 Ownership Transfer journal lines:
- One line with Transfer-from Owner.
- One line with Transfer-to Owner.
- Same item, location, quantity and P2B reference.

The code explicitly leaves the actual ownership journal posting manual:

```pascal
// sementara posting manual dulu
//CLEAR(cWMS_Mgt);
//cWMS_Mgt.PostingOwnershipTransfer(LOwnTransfer);
```

The generated lines are later posted through Page 50152 / Codeunit 50051, not Codeunit 5704/5705. The Ownership Transfer posting procedure inserts paired Ownership Ledger entries and does not call Codeunit 50107.

This is an ownership reclassification at the same location, not a physical transfer. Its stocktake applicability is the same business-policy question documented in the Ownership Transfer report.

## 6. Posting To = Loan

Codeunit 50100 `PostingLoan` creates a Table 5740 Loan document and Table 5741 Transfer Lines, carrying:
- From/To Location and From/To Location Ownership.
- In-Transit Location.
- Loan Type, Loan-to Customer No., Loan Due Date.
- Salesperson Code and Purchaser Code.
- Ship-to and freight fields.
- Ex Loan No., dimensions and P2B Document No.

The P2B workflow does not directly post the Loan. The Loan page later posts through Codeunit 5706/5707 → Codeunit 5704/5705, which run the stocktake OUT/IN checks before posting.

## 7. P2B line and ownership validation

Table 50014 P2B Line:
- Requires a Workflow ID on insert.
- Copies header status, Posting To, From Location and From Location Ownership.
- Calls `CheckingHeader` for Transfer Order and Loan Posting To values.
- Validates Item No. against P2B responsibility-center / department restrictions.
- Validates location, Owner, item category/product group, and quantity through its field triggers and related management routines.

Codeunit 50100 `CheckingLine` supports:
- Quantity must be greater than zero.
- Location Code must be populated.
- Owner must be populated when the line's Location has Ownership enabled.

These are quantity, authorization, location and ownership controls; they are not stocktake-window checks.

## 8. Stocktake assessment and business decision required

The company-approved design from [Issue #3](https://github.com/ayabenz/nav2015-agent/issues/3) remains: stocktake validation is required where the business flow calls for it, but it need not be centralized in one universal posting engine. Company-approved exceptions must not be treated as defects.

For P2B, the source establishes the following facts:
- Transfer Order and Loan outputs reach Codeunit 5704/5705 at final posting and receive OUT/IN checks.
- WMS Item Journal output is converted to a Transfer Order and receives the same checks.
- Non-WMS Item Journal output becomes Negative Adjustment journal lines; actual posting via Page 40 → 241 → 23 → 22 has no inspected stocktake check.
- Same-location WMS Ownership Transfer output becomes Ownership Transfer journal lines; actual posting via Codeunit 50051 has no inspected stocktake check and does not move physical inventory.

**Decision still required:** confirm whether stocktake is intended to block:
1. Non-WMS Item Journal Negative Adjustments generated from P2B.
2. Same-location Ownership Transfer journal posting.

Do not implement a code change until those two policies are confirmed. The P2B Transfer Order / Loan routes already inherit the existing transfer posting checks.

## 9. Follow-up validation

1. Runtime-test a P2B non-WMS Item Journal from creation through Page 40 posting while a Table 50063 stocktake rule is active.
2. Runtime-test P2B Item Journal for a WMS/Ownership location and confirm it creates a Transfer Order and is blocked by the appropriate OUT rule at final shipment.
3. Runtime-test P2B Transfer Order and Loan to confirm the generated documents preserve Owner and P2B Document No.
4. Runtime-test same-location WMS P2B Ownership Transfer, including balanced and unbalanced owner quantities.
5. Confirm with the business owner whether the two no-stocktake routes are intentional.

## 10. Source files

- `reports/datascrip/p2b/Page_50054.txt`
- `reports/datascrip/p2b/Page_50057.txt`
- `reports/datascrip/p2b/Page_50062.txt`
- `reports/datascrip/p2b/Page_50073.txt`
- `reports/datascrip/p2b/Table_50013.txt`
- `reports/datascrip/p2b/Table_50014.txt`
- `reports/datascrip/p2b/Codeunit_50100.txt`
- `reports/datascrip/p2b/Codeunit_50101.txt`
- `reports/datascrip/p2b/Codeunit_50102.txt`
- `reports/datascrip/p2b/Page_40.txt`
- `reports/datascrip/p2b/Codeunit_241.txt`
- `reports/datascrip/p2b/Codeunit_23.txt`
- `reports/datascrip/sales_next/Codeunit_22.txt`
- `reports/datascrip/ownership_transfer/OWNERSHIP_TRANSFER_POSTING_AND_STOCKTAKE.md`
- `reports/datascrip/transfer_flow/TRANSFER_ORDER_STOCKTAKE_AND_POSTING_FLOW.md`
- `reports/datascrip/transfer_flow/LOAN_AND_RETURN_LOAN_POSTING_FLOW.md`
