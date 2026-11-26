# Stocktake Runtime Environment Readiness

**Status:** BLOCKED — NAV test company/runtime endpoint has not been made available to this analysis workflow.

**Scope:** Prepare a safe, reproducible NAV 2015 environment for executing `STOCKTAKE_RUNTIME_TEST_PLAN.md`. This document does not authorize production posting or application-code changes.

## 1. Required environment

Before executing any runtime case, record and verify:

- NAV Server / service tier instance and exact NAV application build (including cumulative update/platform build).
- SQL Server instance and database name hosting the test company.
- A dedicated non-production company cloned or configured to match the relevant production setup.
- The matching Datascrip NAV objects and compiled application state in the test environment.
- A NAV user with permissions to run the required pages, reports, codeunits, and inspect resulting entries.
- A controlled test posting date and number-series setup.
- The relevant stocktake setup records in Table 50063, including Start Date, End Date, transaction direction, location, and item scope.
- At least one test item/location matching exactly one active rule and one control item outside the rule scope.
- Test document numbers and known opening quantities for the selected item/location/Owner combinations.

A source export alone is insufficient to prove runtime behavior. The NAV Server and company setup must match the intended application build and operational configuration.

## 2. Safety controls

Do not run these tests against a production company.

Before testing:
1. Confirm the company name and database are explicitly non-production.
2. Disable or redirect external integrations, EDI transmission, email dispatch, and any production-facing job queues.
3. Use dedicated test customers, vendors, items, locations, owners, and number series where practical.
4. Ensure test posting cannot trigger real warehouse, financial, or customer/vendor downstream processes.
5. Record a restore point/backup according to the environment owner's normal procedure.
6. Do not run destructive cleanup or reverse posted entries without an approved test-environment procedure.

## 3. Minimum configuration snapshot

Capture the following before the first test:

| Area | Required evidence |
|---|---|
| Application | NAV version, platform/build, object version and relevant custom object deployment |
| Company | Exact company name and explicit non-production designation |
| Stocktake | Table 50063 rule ID, Start/End Date, direction, location, item filters |
| Item | Item No., base unit, tracking setup, opening inventory |
| Location | Location Code, WMS/warehouse configuration, Ownership setting |
| Owner | Owner values and opening Ownership Ledger balance when applicable |
| Posting | Posting date, user ID, number-series values, relevant posting setup |
| Integrations | Job queue and external integrations disabled or safely redirected |

## 4. Execution order

Execute only the company-confirmed scenarios first:

1. ST-001 — Sales Return Order receive via Codeunit 50081; expect the stocktake gate to block before posting.
2. ST-002 — Sales Return Order invoice-only via Codeunit 50082; expect the company-approved exception to proceed without a duplicate stocktake check.
3. ST-003 and ST-004 — Transfer shipment OUT and receipt IN.
4. ST-005 — Loan and Return Loan through the shared transfer posting codeunits.
5. ST-006 through ST-008 — Warehouse shipment, receipt, and activity paths involving Transfer Line sources.

For each scenario, capture the before/after evidence specified in the runtime test plan. Do not execute POLICY REQUIRED scenarios until the business owner has recorded the expected behavior.

## 5. Posting evidence

For every attempted posting, capture:

- Source document type/number and line identifiers.
- Item, quantity, location, Owner, posting date, and stocktake rule ID.
- Exact entry point and any intermediate warehouse document/activity.
- Full NAV error text and whether it occurred before or after any COMMIT.
- Before/after Item Ledger Entry and Value Entry counts and quantities.
- Before/after Ownership Ledger Entry counts and quantities when Ownership applies.
- Posted shipment/receipt document numbers and source-document quantity changes.
- Warehouse activity/shipment/receipt state, especially for ST-008 where Codeunit 7324 may COMMIT before the downstream transfer posting call.

A blocked test passes only when the expected error occurs and no unintended posting artifacts or quantity changes remain. Any pre-check committed warehouse state must be recorded separately.

## 6. Current blocker and next action

The repository contains static source analysis and a test plan, but no NAV Server connection, test-company credentials, or runtime execution evidence is available to this workflow. Therefore no NAV transaction has been executed and no runtime pass/fail result can honestly be reported.

**Required environment-owner action:** provide access to a dedicated non-production NAV 2015 test company with the matching Datascrip build and stocktake setup, or have an authorized operator execute the cases and return the evidence package. Do not provide production credentials or production database access.

Once the test environment is available, execute the company-confirmed cases in order, record results in the runtime test matrix, and keep policy-required cases pending until the company confirms their expected behavior.

## Related documents

- [Stocktake Runtime Validation Test Plan](./STOCKTAKE_RUNTIME_TEST_PLAN.md)
- [Stocktake Entry-Point Audit](./STOCKTAKE_ENTRYPOINT_AUDIT.md)
- [Issue #3 — Company-approved behavior and open policy decisions](https://github.com/ayabenz/nav2015-agent/issues/3)
