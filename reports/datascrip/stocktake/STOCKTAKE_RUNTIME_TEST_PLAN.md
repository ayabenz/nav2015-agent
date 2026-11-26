# Stocktake Runtime Validation Test Plan

**Purpose:** Convert the source-level stocktake audit into repeatable NAV test cases. This plan does not authorize code changes. Tests marked POLICY REQUIRED must not be judged as defects until the company confirms the expected behavior.

## 1. Test environment and evidence

Run in a non-production company using the same NAV application build and relevant setup as production.

For each test, capture:
- Company and NAV application build.
- User ID and posting date.
- Stocktake setting ID, Start Date, End Date, transaction direction (IN/OUT/ALL), location, and item scope.
- Source document number, document type, item, quantity, location, Owner, and warehouse source document if applicable.
- Entry point used (page action, batch report, job queue, warehouse activity, or direct codeunit).
- Error text and point at which it occurs.
- Before/after counts and quantities in Item Ledger Entry, Value Entry, Ownership Ledger Entry, posted document tables, and warehouse activity/shipment/receipt tables as relevant.

Use a test item and location that match exactly one active Table 50063 rule. Keep a second item outside the rule scope as a control.

## 2. Company-confirmed behavior

| ID | Scenario | Entry point | Expected result |
|---|---|---|---|
| ST-001 | Sales Return Order, active IN stocktake rule, receive quantity > 0 | Page 6630 → Codeunit 50081 → Codeunit 80 | Stocktake check blocks before Return Receipt / Item Ledger posting |
| ST-002 | Sales Return Order, already-received quantity available to invoice, active IN stocktake rule | Page 6630 → Codeunit 50082 → Codeunit 80 | Invoice-only route proceeds without a duplicate stocktake check, as explicitly approved by the company |
| ST-003 | Transfer Order shipment, active OUT rule | Page 5740 → Codeunit 5706/5707 → Codeunit 5704 | Block before Transfer Shipment / Item Ledger posting |
| ST-004 | Transfer Order receipt, active IN rule | Page 5740 → Codeunit 5706/5707 → Codeunit 5705 | Block before Transfer Receipt / Item Ledger posting |
| ST-005 | Loan shipment and Return Loan receipt | Page 50000/50004 or relevant loan page → shared transfer wrappers → Codeunit 5704/5705 | Apply the same OUT/IN rules as the shared transfer posting codeunits |
| ST-006 | Warehouse Shipment with Transfer Line source | Page 7335 or Report 50223 → Codeunit 5763 → Codeunit 5704 | Block at the transfer posting boundary even if the warehouse shipment existed before stocktake |
| ST-007 | Warehouse Receipt with Transfer Line source | Page 5768/7342 → Codeunit 5760 → Codeunit 5705 | Block at the transfer posting boundary |
| ST-008 | Warehouse Activity with Transfer Line source | Codeunit 7324 → Codeunit 5704/5705 | Block according to OUT/IN transfer direction; record any warehouse activity state committed before the downstream check |

For ST-001 through ST-008, verify that a blocked attempt does not create the corresponding posted shipment/receipt or new Item Ledger Entry. For ST-008, separately inspect warehouse activity state because Codeunit 7324 executes COMMIT before calling the transfer posting codeunit.

## 3. Purchase routes — policy required

| ID | Scenario | Entry point to exercise | Current source finding |
|---|---|---|---|
| ST-101 | Purchase Order Receive | Page 50 / Codeunit 91 or 92 → Codeunit 90 | Wrapper calls purchase stocktake check when Receive is TRUE |
| ST-102 | Purchase Invoice receiving | Page 51 or invoice route → Codeunit 90 | Codeunit 90 applies Receive=TRUE; wrapper's conditional gate may be skipped |
| ST-103 | Purchase Return Order Ship | Purchase Return Order page → Codeunit 91/92 → Codeunit 90 | Wrapper calls stocktake check when Ship is TRUE |
| ST-104 | Purchase Credit Memo shipment | Purchase Credit Memo route → Codeunit 90 | Codeunit 90 applies Ship=TRUE; wrapper's conditional gate may be skipped |
| ST-105 | Purchase batch posting | Reports 496/497/498/6665 → Codeunit 90 | Direct batch routes have no inspected stocktake check |
| ST-106 | Warehouse Receipt purchase source | Page 5768 → Codeunit 5760 → Codeunit 90 | UI gate exists; Codeunit 5760 has no internal check |
| ST-107 | Warehouse Shipment purchase-return source | Codeunit 5763 → Codeunit 90 | No inspected posting-time stocktake check |
| ST-108 | Warehouse Activity purchase source | Codeunit 7324 → Codeunit 90 | No inspected posting-time stocktake check |
| ST-109 | Purchase Job Queue | Codeunit 98 → Codeunit 90 | Queue worker does not recheck at execution time |

Do not mark these as failures until the business owner confirms which Purchase Receive/Ship/Invoice/Credit Memo operations must be blocked.

## 4. P2B and ownership routes — policy required

| ID | Scenario | Entry point | Current source finding |
|---|---|---|---|
| ST-201 | P2B, non-WMS location, Negative Adjustment | P2B Posting → Item Journal → Page 40 → 241 → 23 → 22 | No stocktake check in inspected posting path |
| ST-202 | P2B, WMS/Ownership location, Transfer Order output | P2B Posting → generated Transfer Order → 5704/5705 | Inherits OUT/IN checks at final posting |
| ST-203 | P2B, same WMS location, Ownership Transfer | P2B Posting → Page 50152 / Codeunit 50051 | No stocktake check found; same-location Owner reclassification |
| ST-204 | Manual Ownership Transfer journal | Page 50152 → Codeunit 50051 | No stocktake check found |

## 5. Other Item Journal / inventory routes — policy required

| ID | Scenario | Entry point | Current source finding |
|---|---|---|---|
| ST-301 | Manual Item Journal Positive/Negative Adjustment, Transfer, Consumption, Output | Page 40 → Codeunit 241/242/243/244 → 23 → 22 | No stocktake check found |
| ST-302 | Mini Adjust Inventory | Page 1327 → Codeunit 23 → 22 | No stocktake check found |
| ST-303 | Item Reclass Journal | Page 393 → Codeunit 23 → 22 | No stocktake check found |
| ST-304 | Physical Inventory Journal | Page 392 → Codeunit 241/242 → 23 → 22 | No stocktake check; preserve this route for posting count differences |
| ST-305 | Assembly consumption/output | Page 900 / Codeunit 901 → Codeunit 900 → 22 | No stocktake check found |
| ST-306 | Production consumption/output | Production Order status flow → Codeunit 5407 → 22 | No stocktake check found |
| ST-307 | Job Journal item usage | Job Journal posting → Codeunit 1012/1013 → 22 | No stocktake check found |
| ST-308 | Service item shipment/consumption | Service posting → Codeunit 5980/5987 → 22 | No stocktake check found |
| ST-309 | Warehouse Activity production consumption/output | Codeunit 7324 → Codeunit 22 | No stocktake check found |
| ST-310 | Warehouse Journal reclassification | Page 7365 / Codeunit 7304 → Codeunit 22 | No stocktake check found |
| ST-311 | Undo/reversal of shipment, receipt, service, or consumption | Codeunits 5814–5819 → Codeunit 22 | No stocktake check found; correction policy must be confirmed |

ST-304 is a required exception candidate: the Physical Inventory Journal is used to post stocktake count differences and should remain usable during stocktake unless the company specifies otherwise.

## 6. Negative and control tests

For each applicable route:
1. Repeat with no active Table 50063 rule; posting should follow normal NAV behavior.
2. Repeat with an active rule that does not match the item; posting should not be blocked by that rule.
3. Repeat with an active rule that matches the item but not the location; posting should not be blocked by that rule.
4. Repeat with direction IN, OUT, and ALL as applicable; confirm direction mapping.
5. Repeat with stocktake Start Date in the future and End Date in the past; confirm the inclusive DateTime window.
6. Test a multi-item document with one blocked item; confirm the expected whole-document rollback behavior and whether any pre-posting commits persist.
7. For Ownership-enabled locations, vary Owner and confirm the expected Owner-specific validation independently from stocktake validation.

## 7. Completion criteria

A route is considered validated only when:
- The expected business policy is confirmed.
- The test runs on the matching NAV build and relevant setup.
- The entry point and actual downstream posting path are recorded.
- A blocked operation produces no unintended Item Ledger, Value Entry, Ownership Ledger, posted shipment/receipt, or source-document quantity changes.
- Any pre-check COMMIT or partial state is documented.
- The same result is reproduced for UI, batch, job queue, and warehouse routes where those entry points exist.

## 8. Related source analysis

- [Stocktake entry-point audit](./STOCKTAKE_ENTRYPOINT_AUDIT.md)
- [Sales Return Order / Credit Memo flow](../sales/SALES_RETURN_CREDIT_MEMO_FLOW.md)
- [Purchase posting audit](../purchase_flow/PURCHASE_POSTING_STOCKTAKE_AUDIT.md)
- [Transfer Order flow](../transfer_flow/TRANSFER_ORDER_STOCKTAKE_AND_POSTING_FLOW.md)
- [Loan and Return Loan flow](../transfer_flow/LOAN_AND_RETURN_LOAN_POSTING_FLOW.md)
- [P2B posting audit](../p2b/P2B_POSTING_AND_STOCKTAKE_AUDIT.md)
- [Item Journal and inventory posting audit](../item_journals/INVENTORY_JOURNAL_AND_POSTING_AUDIT.md)
- [Ownership Transfer journal](../ownership_transfer/OWNERSHIP_TRANSFER_POSTING_AND_STOCKTAKE.md)
